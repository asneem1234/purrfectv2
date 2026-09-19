from flask import Blueprint, render_template, redirect, url_for, request, jsonify, flash, current_app, session
from flask_login import login_required, current_user
from models import db, StudyPlan, StudyClass, ClassMaterial, get_student_profile
from db import get_db_context, db_operation
import json
# Fix import to include timedelta
from datetime import datetime, timedelta
import re
import os
import uuid
import logging
import time
from werkzeug.utils import secure_filename
# Import new study tools
from blueprints.study_tools import (
    schedule_tool, topic_ranker_tool, calendar_checker, topic_time_estimator
)
import PyPDF2
import requests
from markupsafe import escape
import google.generativeai as genai
import numpy as np
import hashlib

# NOTE: We're using the Gemini API key configuration from app1.py
# The genai module is already configured in the main application
# No need to configure it again here

print("Using Gemini API configuration from main application")

# RAG dependencies
from utils.model_loader import get_embedding_model
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
from qdrant_client.http.models import PointStruct
import os

# Create blueprint with explicit template folder to ensure proper resource access
study_plan = Blueprint('study_plan', __name__, template_folder='templates')

# Access to the application context ensures we share resources like the configured genai API
# The main app already initializes the genai module with the API key from .env

# RAG functionality with Qdrant for Study Plans
# ===========================================================

# Initialize logging
logger = logging.getLogger(__name__)

# We'll use lazy loading for the embedding model
logger.info("Using lazy-loading for sentence transformer model")
embedding_model = None  # Will be loaded on first use

# Initialize Qdrant client (will be None if env vars not available)
try:
    QDRANT_URL = os.getenv('QDRANT_URL')
    QDRANT_API_KEY = os.getenv('QDRANT_API_KEY')
    
    if QDRANT_URL and QDRANT_API_KEY:
        qdrant_client = QdrantClient(
            url=QDRANT_URL,
            api_key=QDRANT_API_KEY
        )
        logger.info("Qdrant client initialized successfully")
    else:
        logger.warning("QDRANT_URL or QDRANT_API_KEY not provided. RAG functionality will be disabled.")
        qdrant_client = None
except Exception as e:
    logger.error(f"Error initializing Qdrant client: {e}")
    qdrant_client = None

def get_collection_name(user_id):
    """Generate collection name for a specific user's study plans"""
    return f"studyplan_{user_id}"

def create_embedding(text):
    """Create embedding for text using sentence-transformers"""
    try:
        # Get the embedding model with lazy loading
        embedding_model = get_embedding_model()
        embedding = embedding_model.encode(text)
        return embedding.tolist()
    except Exception as e:
        logger.error(f"Error creating embedding: {e}")
        return None

def create_collection(collection_name, vector_size=384):
    """Create or recreate a Qdrant collection for study plans"""
    if qdrant_client is None:
        logger.warning("Qdrant client not available. Cannot create collection.")
        return False
    
    try:
        # Check if collection exists and delete it
        collections = qdrant_client.get_collections().collections
        if any(collection.name == collection_name for collection in collections):
            qdrant_client.delete_collection(collection_name)
            logger.info(f"Deleted existing collection: {collection_name}")
        
        # Create collection with vector config and payload indexes
        qdrant_client.create_collection(
            collection_name=collection_name,
            vectors_config=qdrant_models.VectorParams(
                size=vector_size,
                distance=qdrant_models.Distance.COSINE
            ),
            optimizers_config=qdrant_models.OptimizersConfigDiff(
                indexing_threshold=0  # Index immediately
            )
        )
        
        # Add payload indexes for efficient filtering
        for field in ["plan_id", "topic", "subtopic", "day", "importance", "type"]:
            qdrant_client.create_payload_index(
                collection_name=collection_name,
                field_name=field,
                field_schema=qdrant_models.PayloadSchemaType.KEYWORD
            )
        
        # Add numeric index for importance
        qdrant_client.create_payload_index(
            collection_name=collection_name,
            field_name="importance",
            field_schema=qdrant_models.PayloadSchemaType.INTEGER
        )
        
        logger.info(f"Created collection: {collection_name} with payload indexes")
        return True
    except Exception as e:
        logger.error(f"Error creating collection: {e}")
        return False

def insert_document(plan_id, content, metadata, collection_name):
    """Insert document into Qdrant collection with metadata"""
    if qdrant_client is None or embedding_model is None:
        print("⚠️ Qdrant client or embedding model not available. Cannot insert document.")
        return False
    
    try:
        # Determine document type for better logging
        doc_type = metadata.get("type", "note")
        topic = metadata.get("topic", "")
        
        if doc_type == "roadmap_step":
            doc_desc = f"topic '{topic}'"
        elif doc_type == "flashcard":
            subtopic = metadata.get("subtopic", "")
            doc_desc = f"flashcard '{subtopic}' for topic '{topic}'"
        elif doc_type == "schedule_activity":
            day = metadata.get("day", "")
            activity_title = content.split('\n')[0] if '\n' in content else content
            doc_desc = f"activity '{activity_title}' on {day}"
        else:
            doc_desc = f"{doc_type} document"
            
        # Create embedding for content
        print(f"    📑 Creating embedding for {doc_desc}")
        embedding_start = time.time()
        embedding = create_embedding(content)
        embedding_time = time.time() - embedding_start
        
        if embedding is None:
            print(f"    ❌ Failed to create embedding for {doc_desc}")
            return False
        
        # Create a content hash for duplicate detection
        import hashlib
        content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
        
        # Prepare metadata with required fields
        payload = {
            "plan_id": str(plan_id),
            "content": content,
            "topic": metadata.get("topic", ""),
            "subtopic": metadata.get("subtopic", ""),
            "day": metadata.get("day", ""),
            "importance": metadata.get("importance", 5),
            "type": metadata.get("type", "note"),
            "content_hash": content_hash  # Add content hash for duplicate detection
        }
        
        # Generate a deterministic ID based on content hash and plan_id for deduplication
        # This ensures the same content in the same plan always gets the same ID
        unique_key = f"{plan_id}:{metadata.get('type', '')}:{content_hash}"
        point_id = str(uuid.uuid5(uuid.NAMESPACE_OID, unique_key))
        
        # Check if this exact document (by point_id) already exists
        try:
            existing_point = qdrant_client.retrieve(
                collection_name=collection_name,
                ids=[point_id],
                with_payload=True
            )
            
            if existing_point and len(existing_point) > 0:
                print(f"    ⏩ Skipping duplicate: This exact {doc_desc} already exists in Qdrant")
                return True  # Return success since the document effectively exists
        except Exception as e:
            print(f"    ⚠️ Error checking for existing document: {e}")
        
        # Insert the point into the collection
        storage_start = time.time()
        qdrant_client.upsert(
            collection_name=collection_name,
            points=[
                PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload=payload
                )
            ]
        )
        storage_time = time.time() - storage_start
        total_time = embedding_time + storage_time
        
        # Print detailed info based on document type
        print(f"    ✅ Embedded {doc_desc} (time: {total_time:.2f}s)")
        
        # More detailed logging for debugging
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Inserted {doc_desc} into {collection_name}: {point_id[:8]}...")
            logger.debug(f"  - Embedding time: {embedding_time:.2f}s")
            logger.debug(f"  - Storage time: {storage_time:.2f}s")
            logger.debug(f"  - Vector dimensions: {len(embedding)}")
        
        return True
    except Exception as e:
        print(f"❌ Error inserting document: {e}")
        return False

def semantic_search(query, collection_name, filters=None, top_k=5):
    """Perform semantic search in Qdrant collection with optional filters"""
    if qdrant_client is None or embedding_model is None:
        logger.warning("Qdrant client or embedding model not available. Cannot perform semantic search.")
        return []
    
    try:
        # Create embedding for query
        query_embedding = create_embedding(query)
        if query_embedding is None:
            return []
        
        # Convert filters to Qdrant filter format
        qdrant_filters = None
        if filters:
            filter_conditions = []
            for key, value in filters.items():
                if isinstance(value, list):
                    filter_conditions.append(
                        qdrant_models.FieldCondition(
                            key=key,
                            match=qdrant_models.MatchAny(any=value)
                        )
                    )
                else:
                    filter_conditions.append(
                        qdrant_models.FieldCondition(
                            key=key,
                            match=qdrant_models.MatchValue(value=value)
                        )
                    )
            
            qdrant_filters = qdrant_models.Filter(
                must=filter_conditions
            )
        
        # Perform search
        search_results = qdrant_client.search(
            collection_name=collection_name,
            query_vector=query_embedding,
            limit=top_k,
            query_filter=qdrant_filters
        )
        
        # Format results
        results = []
        for result in search_results:
            results.append({
                "score": result.score,
                "content": result.payload.get("content", ""),
                "metadata": {
                    "plan_id": result.payload.get("plan_id", ""),
                    "topic": result.payload.get("topic", ""),
                    "subtopic": result.payload.get("subtopic", ""),
                    "day": result.payload.get("day", ""),
                    "importance": result.payload.get("importance", 5),
                    "type": result.payload.get("type", "")
                }
            })
        
        logger.info(f"Semantic search for '{query}' returned {len(results)} results")
        return results
    except Exception as e:
        logger.error(f"Error in semantic search: {e}")
        return []

def hybrid_search(query, collection_name, filters=None, top_k=5):
    """Perform hybrid search (vector + keyword) in Qdrant collection"""
    if qdrant_client is None or embedding_model is None:
        print("❌ Qdrant client or embedding model not available. Cannot perform hybrid search.")
        return []
    
    try:
        # Create embedding for query
        print(f"🧠 Creating vector embedding for query: \"{query}\"")
        embed_start = time.time()
        query_embedding = create_embedding(query)
        embed_time = time.time() - embed_start
        
        if query_embedding is None:
            print("❌ Failed to create query embedding")
            return []
        else:
            print(f"✅ Created {len(query_embedding)}d embedding in {embed_time:.2f}s")
        
        # Convert filters to Qdrant filter format
        qdrant_filters = None
        if filters:
            filter_conditions = []
            for key, value in filters.items():
                if isinstance(value, list):
                    filter_conditions.append(
                        qdrant_models.FieldCondition(
                            key=key,
                            match=qdrant_models.MatchAny(any=value)
                        )
                    )
                else:
                    filter_conditions.append(
                        qdrant_models.FieldCondition(
                            key=key,
                            match=qdrant_models.MatchValue(value=value)
                        )
                    )
            
            qdrant_filters = qdrant_models.Filter(
                must=filter_conditions
            )
            print(f"🔍 Applied {len(filter_conditions)} search filters")
        
        # Perform hybrid search
        print(f"🔎 Executing vector search on {collection_name}")
        search_start = time.time()
        search_results = qdrant_client.search(
            collection_name=collection_name,
            query_vector=query_embedding,
            query_filter=qdrant_filters,
            limit=top_k,
            with_payload=True,
            search_params=qdrant_models.SearchParams(
                hnsw_ef=128,
                exact=False
            ),
            # Use text to enhance vector search
            score_threshold=0.0,
            append_payload=True
        )
        search_time = time.time() - search_start
        
        # Format results
        results = []
        result_types = {}
        
        for result in search_results:
            doc_type = result.payload.get("type", "unknown")
            if doc_type in result_types:
                result_types[doc_type] += 1
            else:
                result_types[doc_type] = 1
                
            results.append({
                "score": result.score,
                "content": result.payload.get("content", ""),
                "metadata": {
                    "plan_id": result.payload.get("plan_id", ""),
                    "topic": result.payload.get("topic", ""),
                    "subtopic": result.payload.get("subtopic", ""),
                    "day": result.payload.get("day", ""),
                    "importance": result.payload.get("importance", 5),
                    "type": result.payload.get("type", "")
                }
            })
        
        # Print search summary
        print(f"✅ Search completed in {search_time:.2f}s, found {len(results)} results")
        if result_types:
            type_summary = ", ".join([f"{count} {doc_type}s" for doc_type, count in result_types.items()])
            print(f"📊 Result breakdown: {type_summary}")
        
        return results
    except Exception as e:
        print(f"❌ Error in hybrid search: {e}")
        return []

def store_study_plan_in_qdrant(user_id, plan_id, topics, detailed_schedule):
    """Store a complete study plan in Qdrant for RAG retrieval"""
    from datetime import datetime
    
    if qdrant_client is None or embedding_model is None:
        print("⚠️ Qdrant client or embedding model not available. Cannot store study plan.")
        return False
    
    collection_name = get_collection_name(user_id)
    success = False
    topic_count = 0
    flashcard_count = 0
    activity_count = 0
    
    print(f"🚀 Starting to store study plan {plan_id} for user {user_id} in Qdrant at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   - Topics: {len(topics) if topics else 0}")
    print(f"   - Schedule days: {len(detailed_schedule) if detailed_schedule else 0}")
    
    try:
        print(f"🔄 Preparing to store study plan in Qdrant collection: {collection_name}")
        
        # Ensure collection exists
        collections = qdrant_client.get_collections().collections
        if not any(collection.name == collection_name for collection in collections):
            print(f"📁 Creating new collection: {collection_name}")
            create_collection(collection_name)
        else:
            print(f"📁 Using existing collection: {collection_name}")
            
        # Check if plan already exists in collection to prevent duplicates
        try:
            # Create search filter for this plan's ID
            search_filter = qdrant_models.Filter(
                must=[
                    qdrant_models.FieldCondition(
                        key="plan_id",
                        match=qdrant_models.MatchValue(value=str(plan_id))
                    )
                ]
            )
            
            # Count points with this plan_id
            count_result = qdrant_client.count(
                collection_name=collection_name,
                count_filter=search_filter
            )
            
            # Check if this is a duplicate submission
            if count_result.count > 0:
                print(f"⚠️ Found {count_result.count} existing embeddings for plan {plan_id}.")
                # Get a small sample to check if this is exactly the same content
                sample_results = qdrant_client.scroll(
                    collection_name=collection_name,
                    filter=search_filter,
                    limit=5,
                    with_payload=True
                )[0]
                
                if sample_results:
                    print("Checking if content is identical to prevent duplicate storage...")
                    # If we have some results and this seems to be a duplicate submission
                    # (i.e., user accidentally clicked save button twice)
                    is_likely_duplicate = True
                    
                    # We'll keep the existing embeddings in this case
                    print(f"✅ Study plan {plan_id} appears to be already indexed. Skipping re-indexing to prevent duplicates.")
                    return True
                else:
                    # If we have embeddings but no actual results (odd state), clean up and re-index
                    print(f"⚠️ Found embeddings but couldn't retrieve sample data. Removing and re-indexing.")
                    qdrant_client.delete(
                        collection_name=collection_name,
                        points_selector=qdrant_models.FilterSelector(
                            filter=search_filter
                        )
                    )
                    print(f"✅ Successfully removed {count_result.count} potentially corrupt embeddings.")
        except Exception as e:
            print(f"⚠️ Error checking for duplicates: {e}. Will proceed with insertion anyway.")
        
        # Track content hashes to avoid duplicates within the same indexing operation
        processed_content_hashes = set()
        
        # Store topics
        print(f"📊 Processing {len(topics)} topics...")
        for topic in topics:
            topic_name = topic.get("name", "Unnamed Topic")
            topic_content = (
                f"Topic: {topic_name}\n"
                f"Importance: {topic.get('importance', 5)}/10\n"
                f"Explanation: {topic.get('explanation', '')}\n"
                f"Key points: {', '.join(topic.get('key_points', []))}"
            )
            
            # Create a hash for this content to avoid duplicates
            import hashlib
            content_hash = hashlib.md5(topic_content.encode('utf-8')).hexdigest()
            
            # Skip if we've already processed identical content in this batch
            if content_hash in processed_content_hashes:
                print(f"    ⏩ Skipping duplicate topic: '{topic_name}'")
                continue
            
            processed_content_hashes.add(content_hash)
            
            metadata = {
                "topic": topic_name,
                "subtopic": "",
                "day": "",
                "importance": topic.get("importance", 5),
                "type": "roadmap_step"
            }
            
            if insert_document(plan_id, topic_content, metadata, collection_name):
                topic_count += 1
            
            # Store key points as flashcards
            for key_point in topic.get("key_points", []):
                flashcard_content = f"Flashcard: {key_point} (Topic: {topic_name})"
                
                # Create a hash for this content to avoid duplicates
                content_hash = hashlib.md5(flashcard_content.encode('utf-8')).hexdigest()
                
                # Skip if we've already processed identical content in this batch
                if content_hash in processed_content_hashes:
                    print(f"    ⏩ Skipping duplicate flashcard: '{key_point}'")
                    continue
                    
                processed_content_hashes.add(content_hash)
                
                metadata = {
                    "topic": topic_name,
                    "subtopic": key_point,
                    "day": "",
                    "importance": topic.get("importance", 5),
                    "type": "flashcard"
                }
                if insert_document(plan_id, flashcard_content, metadata, collection_name):
                    flashcard_count += 1
        
        # Store schedule activities
        print(f"📅 Processing schedule with {len(detailed_schedule)} days...")
        for day_idx, day in enumerate(detailed_schedule):
            day_date = day.get("formatted_date", f"Day {day_idx + 1}")
            day_activities = day.get("activities", [])
            
            for activity in day_activities:
                activity_title = activity.get("title", "Activity")
                activity_type = activity.get("type", "")
                
                # Extract topic from activity title if it's a study activity
                activity_topic = ""
                if "Study:" in activity_title:
                    activity_topic = activity_title.split("Study:")[1].strip()
                
                activity_content = (
                    f"Activity: {activity_title}\n"
                    f"Day: {day_date}\n"
                    f"Time: {activity.get('start_time', '')} - {activity.get('end_time', '')}\n"
                    f"Notes: {activity.get('notes', '')}"
                )
                
                # Create a hash for this content to avoid duplicates
                content_hash = hashlib.md5(activity_content.encode('utf-8')).hexdigest()
                
                # Skip if we've already processed identical content in this batch
                if content_hash in processed_content_hashes:
                    print(f"    ⏩ Skipping duplicate activity: '{activity_title}'")
                    continue
                    
                processed_content_hashes.add(content_hash)
                
                metadata = {
                    "topic": activity_topic,
                    "subtopic": "",
                    "day": day_date,
                    "importance": 5,  # Default importance for schedule items
                    "type": "schedule_activity"
                }
                
                if insert_document(plan_id, activity_content, metadata, collection_name):
                    activity_count += 1
        
        success = True
        print(f"✅ Successfully stored study plan {plan_id} in Qdrant for user {user_id}")
        print(f"   - {topic_count} topics stored")
        print(f"   - {flashcard_count} flashcards stored")
        print(f"   - {activity_count} schedule activities stored")
        print(f"   - Total: {topic_count + flashcard_count + activity_count} embeddings created")
        
    except Exception as e:
        print(f"❌ Error storing study plan in Qdrant: {e}")
    
    return success

def query_study_plan(user_id, query, filters=None, top_k=5):
    """Query a user's study plans using hybrid search"""
    collection_name = get_collection_name(user_id)
    
    # Check if collection exists
    if qdrant_client is not None:
        try:
            print(f"🔍 Looking for Qdrant collection: {collection_name}")
            collections = qdrant_client.get_collections().collections
            if not any(collection.name == collection_name for collection in collections):
                print(f"⚠️ Collection {collection_name} does not exist. User has no RAG data.")
                return []
            else:
                print(f"✅ Found collection: {collection_name}")
                
                # Get collection info
                try:
                    collection_info = qdrant_client.get_collection(collection_name)
                    vector_size = collection_info.config.params.vectors.size
                    vector_distance = collection_info.config.params.vectors.distance
                    points_count = collection_info.points_count
                    print(f"📊 Collection stats: {points_count} points, {vector_size}d vectors, {vector_distance} distance")
                except Exception as info_error:
                    print(f"⚠️ Could not get collection info: {info_error}")
                
        except Exception as e:
            print(f"❌ Error checking collections: {e}")
            return []
    else:
        print("⚠️ Qdrant client not available")
        return []
    
    # Create filter description for logging
    filter_desc = ""
    if filters:
        filter_items = [f"{k}='{v}'" for k, v in filters.items()]
        filter_desc = f" with filters: {', '.join(filter_items)}"
    
    print(f"🔎 Performing hybrid search for '{query}'{filter_desc} (top {top_k} results)")
    
    # Perform hybrid search
    return hybrid_search(query, collection_name, filters, top_k)

# API for RAG-based question answering
@study_plan.route('/api/study-answer', methods=['POST'])
@login_required
def study_answer_api():
    """API to answer questions about study plans using RAG"""
    start_time = time.time()
    data = request.json
    
    if not data or 'query' not in data:
        return jsonify({
            'success': False,
            'error': 'Missing query parameter'
        }), 400
    
    query = data.get('query')
    plan_id = data.get('plan_id')  # Optional filter for specific plan
    
    print("=" * 60)
    print(f"🔎 RAG QUERY: \"{query}\"")
    print("-" * 60)
    print(f"👤 User ID: {current_user.id}")
    if plan_id:
        print(f"📝 Plan ID filter: {plan_id}")
    
    # Check if Qdrant is available
    if qdrant_client is None or embedding_model is None:
        print("❌ RAG functionality not available - Qdrant or embedding model missing")
        return jsonify({
            'success': False,
            'error': 'RAG functionality not available. Please check Qdrant configuration.'
        }), 503
    
    # Prepare filters if plan_id provided
    filters = {}
    if plan_id:
        filters['plan_id'] = str(plan_id)
    
    try:
        # Get relevant context using hybrid search
        print(f"🔄 Retrieving context from Qdrant collection: studyplan_{current_user.id}")
        search_start = time.time()
        search_results = query_study_plan(
            user_id=current_user.id,
            query=query,
            filters=filters,
            top_k=5  # Get top 5 relevant chunks
        )
        search_time = time.time() - search_start
        print(f"⏱️ Search time: {search_time:.2f}s")
        
        # If no results, handle gracefully
        if not search_results:
            print("⚠️ No results found with filters, trying again without filters...")
            if filters:
                # Try again without filters
                search_results = query_study_plan(
                    user_id=current_user.id,
                    query=query,
                    filters=None,
                    top_k=3
                )
                
                if search_results:
                    print(f"✅ Found {len(search_results)} results without filters")
            
            if not search_results:
                # If still no results, use fallback to direct Gemini generation
                print("⚠️ No context found in user's study plans, falling back to direct AI generation")
                try:
                    # Try to create a model with the API key from main application
                    try:
                        model = genai.GenerativeModel('gemini-2.5-flash-lite')
                    except Exception as e:
                        print(f"Error creating Gemini model for fallback: {e}")
                        return jsonify({
                            'success': False,
                            'error': f"Could not initialize AI model: {str(e)}"
                        }), 500
                        
                    prompt = f"""
                    You are a helpful study assistant. The student asked: 
                    
                    "{query}"
                    
                    Please provide a helpful response based on general knowledge.
                    """
                    
                    gen_start = time.time()
                    response = model.generate_content(prompt)
                    gen_time = time.time() - gen_start
                    
                    print(f"✅ Generated direct AI response (no RAG) in {gen_time:.2f}s")
                    total_time = time.time() - start_time
                    print(f"⏱️ Total request time: {total_time:.2f}s")
                    print("=" * 60)
                    
                    return jsonify({
                        'success': True,
                        'answer': response.text,
                        'source': 'ai_generated',
                        'context': []
                    })
                except Exception as e:
                    print(f"❌ Error with fallback Gemini generation: {e}")
                    return jsonify({
                        'success': False,
                        'error': 'Could not find relevant study materials and AI generation failed.'
                    }), 404
        
        # Report on retrieved context
        print(f"✅ Retrieved {len(search_results)} relevant chunks from RAG:")
        for idx, result in enumerate(search_results[:3], 1):  # Show top 3 for brevity
            score = result.get('score', 0.0)
            doc_type = result.get('metadata', {}).get('type', 'unknown')
            topic = result.get('metadata', {}).get('topic', '')
            print(f"  {idx}. {doc_type}: '{topic}' (score: {score:.3f})")
        if len(search_results) > 3:
            print(f"     ... and {len(search_results) - 3} more")
            
        # Build context for Gemini from search results
        context_texts = []
        for result in search_results:
            context_texts.append(result['content'])
        
        context_str = "\n\n".join(context_texts)
        context_length = len(context_str)
        print(f"📚 Total context size: {context_length} characters")
        
        # Generate answer using Gemini with RAG context
        try:
            print("🧠 Generating answer using Gemini with RAG context...")
            
            # The genai module is already configured in the main application
            # Try to create a model with the API key configured there
            try:
                model = genai.GenerativeModel('gemini-2.5-flash-lite')
            except Exception as e:
                print(f"Error creating Gemini model for RAG: {e}")
                return jsonify({
                    'success': False,
                    'error': f"Could not initialize AI model: {str(e)}"
                }), 500
                
            prompt = f"""
            You are a helpful study assistant. The student asked:
            
            "{query}"
            
            Based on their study materials and plans, here is the relevant information:
            
            {context_str}
            
            Please provide a helpful, concise response that answers their question using the provided context.
            Make sure to focus only on information present in the context. If the context doesn't fully answer the question,
            acknowledge that and provide what you can from the available information.
            """
            
            gen_start = time.time()
            response = model.generate_content(prompt)
            gen_time = time.time() - gen_start
            
            answer = response.text
            answer_preview = answer[:100] + "..." if len(answer) > 100 else answer
            
            print(f"✅ Generated answer in {gen_time:.2f}s")
            print(f"📝 Answer preview: {answer_preview}")
            
            # Calculate total time
            total_time = time.time() - start_time
            print(f"⏱️ Total RAG request time: {total_time:.2f}s")
            print("=" * 60)
            
            # Return the answer along with sources
            return jsonify({
                'success': True,
                'answer': answer,
                'source': 'rag',
                'context': [{'content': r['content'], 'metadata': r['metadata']} for r in search_results]
            })
            
        except Exception as e:
            print(f"❌ Error generating answer: {e}")
            return jsonify({
                'success': False,
                'error': f"Error generating answer: {str(e)}"
            }), 500
            
    except Exception as e:
        print(f"❌ Error in study answer API: {e}")
        return jsonify({
            'success': False,
            'error': f"Error: {str(e)}"
        }), 500

# PDF extraction functions
def extract_text_from_pdf(pdf_file):
    """Extract text from a PDF file"""
    try:
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page_num in range(len(pdf_reader.pages)):
            text += pdf_reader.pages[page_num].extract_text()
        return text
    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
        return ""

# PDF processing function
def process_pdf_files(files):
    """Process PDF files and extract text content"""
    pdf_contents = ""
    pdf_documents = []
    collection_name = f"study_docs_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    try:
        # Extract text directly from the PDFs
        for pdf_file in files:
            if pdf_file and pdf_file.filename:
                filename = secure_filename(pdf_file.filename)
                pdf_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                pdf_file.save(pdf_path)
                
                # Extract text using PyPDF2
                try:
                    with open(pdf_path, 'rb') as f:
                        pdf_reader = PyPDF2.PdfReader(f)
                        for page_num in range(len(pdf_reader.pages)):
                            page = pdf_reader.pages[page_num]
                            text = page.extract_text() or ""  # Handle None returns
                            pdf_contents += text + "\n\n"
                            pdf_documents.append({"content": text, "page": page_num})
                    
                    print(f"Successfully extracted text from {filename}, got {len(pdf_contents)} characters")
                except Exception as e:
                    print(f"Error extracting text from {filename}: {e}")
        
        # Return what we have
        return pdf_contents, pdf_documents, collection_name
    except Exception as e:
        print(f"Error processing PDFs: {e}")
        return pdf_contents, pdf_documents, collection_name  # Return what we have even if there was an error

# Sentinel value posted by the "+ Add a class..." option in the class picker
NEW_CLASS_SENTINEL = '__new__'

def resolve_selected_class(form):
    """Return the StudyClass this plan belongs to, creating it when the student
    picked "+ Add a class...". Returns None when no class was selected."""
    selected = (form.get('classId') or '').strip()
    if not selected:
        return None

    if selected == NEW_CLASS_SENTINEL:
        name = (form.get('newClassName') or '').strip()
        if not name:
            return None
        code = (form.get('newClassCode') or '').strip() or None

        # Re-use a class of the same name rather than tripping the unique constraint
        existing = StudyClass.query.filter_by(user_id=current_user.id, name=name).first()
        if existing:
            return existing

        study_class = StudyClass(user_id=current_user.id, code=code, name=name)
        db.session.add(study_class)
        db.session.commit()
        print(f"Created class {study_class.label} for user {current_user.id}")
        return study_class

    # Scope the lookup to the current user so a forged id can't reach someone else's class
    try:
        selected_id = int(selected)
    except (TypeError, ValueError):
        print(f"Ignoring unparseable classId: {selected!r}")
        return None

    return StudyClass.query.filter_by(id=selected_id, user_id=current_user.id).first()

def store_class_materials(study_class, exam_name, files):
    """Save uploaded PDFs for one exam of a class, on disk and in the DB."""
    # Files sit under the class, but each row records the exam it was uploaded
    # for, so one class's midterm and final keep separate material lists.
    class_dir = os.path.join(
        current_app.config['UPLOAD_FOLDER'],
        f'user_{study_class.user_id}',
        f'class_{study_class.id}'
    )
    os.makedirs(class_dir, exist_ok=True)

    stored = []
    for upload in files:
        original = upload.filename
        # secure_filename can return '' for names that are entirely unsafe
        safe_name = secure_filename(original) or 'material.pdf'
        # Prefix with a random hex so re-uploading the same name doesn't clobber
        # the earlier copy, and so two students can't collide in UPLOAD_FOLDER
        stored_name = f'{uuid.uuid4().hex[:8]}_{safe_name}'
        path = os.path.join(class_dir, stored_name)
        upload.save(path)

        db.session.add(ClassMaterial(
            class_id=study_class.id,
            user_id=study_class.user_id,
            exam_name=exam_name[:255] if exam_name else None,
            original_filename=original[:255],
            stored_filename=stored_name[:255],
            file_path=path[:512]
        ))
        stored.append(stored_name)

    db.session.commit()
    print(f"Stored {len(stored)} material(s) for {study_class.label} / {exam_name}")
    return stored

def extract_text_from_paths(paths):
    """Pull text out of stored materials - PDFs, or .txt imported from Google Docs."""
    pdf_contents = ""
    pdf_documents = []

    for path in paths:
        if not os.path.exists(path):
            print(f"Class material missing from disk, skipping: {path}")
            continue
        try:
            if path.lower().endswith('.txt'):
                # Google Doc exports are already plain text
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    text = f.read()
                pdf_contents += text + "\n\n"
                pdf_documents.append({"content": text, "page": 0})
                continue

            with open(path, 'rb') as f:
                pdf_reader = PyPDF2.PdfReader(f)
                for page_num, page in enumerate(pdf_reader.pages):
                    text = page.extract_text() or ""
                    pdf_contents += text + "\n\n"
                    pdf_documents.append({"content": text, "page": page_num})
        except Exception as e:
            print(f"Error extracting text from {path}: {e}")

    return pdf_contents, pdf_documents


# Exam time is optional. When the student doesn't give one, the scheduler still
# needs a cutoff for the last day's study blocks - this is that fallback only,
# never shown to the student as if it were their real exam time.
DEFAULT_EXAM_TIME = '09:00'

# Preparation start time is optional too. Unlike the exam time this one can't be
# skipped: it's the daily wake time that anchors bedtime and the first study
# block, so every day needs a value.
DEFAULT_PREP_START_TIME = '07:00'

# Accepts the /document/d/<id>/ and ?id=<id> URL shapes Google hands out
GOOGLE_DOC_ID_PATTERNS = [
    re.compile(r'docs\.google\.com/document/d/([a-zA-Z0-9_-]{10,})'),
    re.compile(r'docs\.google\.com/document/u/\d+/d/([a-zA-Z0-9_-]{10,})'),
    re.compile(r'docs\.google\.com/.*[?&]id=([a-zA-Z0-9_-]{10,})'),
]

# A Google Doc big enough to blow past this isn't a study material
MAX_GOOGLE_DOC_BYTES = 5 * 1024 * 1024


class GoogleDocError(Exception):
    """Raised when a Google Doc link can't be read, with a student-facing message."""


def parse_google_doc_id(url):
    """Pull the document id out of a Google Docs URL, or None if it isn't one."""
    for pattern in GOOGLE_DOC_ID_PATTERNS:
        match = pattern.search(url or '')
        if match:
            return match.group(1)
    return None


def fetch_google_doc_text(url):
    """Fetch a link-shared Google Doc as plain text. Returns (doc_id, text).

    Only the document id is taken from the student's URL - the address we
    actually request is built here against a fixed docs.google.com endpoint, so
    a pasted link can't point the server at an arbitrary host.
    """
    doc_id = parse_google_doc_id(url)
    if not doc_id:
        raise GoogleDocError(
            "That doesn't look like a Google Doc link. Copy the URL from the address bar."
        )

    export_url = f'https://docs.google.com/document/d/{doc_id}/export?format=txt'
    try:
        response = requests.get(export_url, timeout=15, allow_redirects=True)
    except requests.RequestException as e:
        raise GoogleDocError(f"Couldn't reach Google Docs: {e}")

    # A doc that isn't link-shared bounces to a sign-in page rather than 403ing
    if 'accounts.google.com' in response.url:
        raise GoogleDocError(
            "That Google Doc isn't shared. Set it to \"Anyone with the link can view\" and try again."
        )
    if response.status_code != 200:
        raise GoogleDocError(
            f"Google Docs returned {response.status_code} for that link."
        )
    if len(response.content) > MAX_GOOGLE_DOC_BYTES:
        raise GoogleDocError("That Google Doc is too large to import.")

    text = response.text.strip()
    if not text:
        raise GoogleDocError("That Google Doc looks empty.")

    return doc_id, text


def store_google_doc_material(study_class, exam_name, url):
    """Import a Google Doc as a material for one exam of a class."""
    doc_id, text = fetch_google_doc_text(url)

    class_dir = os.path.join(
        current_app.config['UPLOAD_FOLDER'],
        f'user_{study_class.user_id}',
        f'class_{study_class.id}'
    )
    os.makedirs(class_dir, exist_ok=True)

    stored_name = f'{uuid.uuid4().hex[:8]}_gdoc_{doc_id[:20]}.txt'
    path = os.path.join(class_dir, stored_name)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)

    # The export endpoint doesn't give us the title, so show the first non-empty
    # line - which for a study doc is almost always its heading.
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), '')
    display_name = (first_line[:80] or f'Google Doc {doc_id[:8]}')

    material = ClassMaterial(
        class_id=study_class.id,
        user_id=study_class.user_id,
        exam_name=exam_name[:255] if exam_name else None,
        source_type='gdoc',
        source_url=url[:512],
        original_filename=display_name[:255],
        stored_filename=stored_name[:255],
        file_path=path[:512]
    )
    db.session.add(material)
    db.session.commit()
    print(f"Imported Google Doc {doc_id} for {study_class.label} / {exam_name}")
    return material

# Topic extraction using Gemini
def extract_important_topics(pdf_content):
    """Extract important topics from PDF content using Gemini AI"""
    try:
        # The genai module is already configured in the main application
        # No need to check API key here
        try:
            model = genai.GenerativeModel('gemini-2.5-flash')
        except Exception as e:
            print(f"Error creating Gemini model for topic extraction: {e}")
            return {"topics": [{"name": "Model Creation Failed", "importance": 5, "explanation": str(e), "recommended_time_minutes": 30, "key_points": ["Please check API key configuration"]}]}
            
        prompt = f"""
        You are an expert academic analyzer and study plan creator. Based on the provided study material, create a comprehensive study plan. 
        Identify the most important 8-12 topics that a student should focus on when preparing for an exam on this material.
        
        For each topic:
        1. Assign an importance score from 1-10 (10 being most important)
        2. Provide a brief explanation of why it's important
        3. Recommend specific study time in minutes
        4. Include 2-3 subtopics or key points to focus on
        
        Return the result as a JSON object with this exact structure:
        {{
            "topics": [
                {{
                    "name": "Topic Name",
                    "importance": 8,
                    "explanation": "Brief explanation of importance and how it relates to the overall subject",
                    "recommended_time_minutes": 60,
                    "key_points": ["Key point 1", "Key point 2", "Key point 3"]
                }},
                ...
            ]
        }}
        
        Study material:
        {pdf_content[:10000]}
        """
        
        response = model.generate_content(prompt)
        response_text = response.text
        
        # Extract JSON data from response
        json_pattern = r'```json\s*([\s\S]*?)\s*```'
        json_match = re.search(json_pattern, response_text)
        
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find JSON without the code block markers
            json_pattern = r'({[\s\S]*})'
            json_match = re.search(json_pattern, response_text)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = response_text
        
        topics_data = json.loads(json_str)
        return topics_data
    except Exception as e:
        print(f"Error extracting topics: {str(e)}")
        return {"topics": [{"name": "Error extracting topics", "importance": 5, "explanation": str(e), "recommended_time_minutes": 30, "key_points": ["Please try again"]}]}

# Study schedule generator
def create_enhanced_study_schedule(form_data, topics_data):
    """Create an enhanced study schedule using ReAct framework (Reason → Act → Observe → Final Answer)"""
    try:
        # The genai module is already configured in the main application
        try:
            model = genai.GenerativeModel('gemini-2.5-flash')
        except Exception as e:
            print(f"Error creating Gemini model: {e}")
            return None
        
        # Format the input data for Gemini
        topics_json = json.dumps(topics_data)
        form_json = json.dumps(form_data)
        
        # ReAct framework-based prompt with improved reasoning
        prompt = f"""
        You are an AI Study Planner Agent.
        Use the ReAct framework: Reason → Act → Observe → Final Answer.
        
        Your goal is to create an efficient and realistic daily study plan based on:
        FORM DATA:
        {form_json}
        
        TOPICS TO STUDY (with importance scores):
        {topics_json}
        
        --- Reasoning Steps ---
        1. First analyze all constraints carefully:
           - Calculate days between preparation start date and exam date
           - Consider the exam time and any day-of-exam study time
           - Account for sleep hours requirements
           - Respect meal times (breakfast, lunch, snack, dinner)
           - Use the specified break interval and duration
        
        2. Calculate how many TOTAL STUDY HOURS are needed to cover all topics
           - Sum up recommended_time_minutes for all topics
           - Add time for reviews and practice
        
        3. Determine how many ACTUAL STUDY DAYS are needed
           - Not every day between start and exam needs study activities
           - Some days can be rest days or light review days
           - More intensive study earlier, tapering to review closer to exam
        
        4. Distribute topics intelligently:
           - Prioritize topics with higher importance scores
           - Study more difficult/important topics when energy is highest
           - Group related topics in the same study session
           - Schedule reviews of previous topics
           - Include short breaks between study sessions
        
        5. Create a complete daily schedule for each study day:
           - Wake up time and sleep time
           - All meals at their specified times
           - Study sessions with specific topics
           - Breaks between study sessions
           - Review periods
        
        --- Output Format ---
        Return only the JSON object with this structure:
        {{
            "plan_summary": "Brief overview of the study plan approach with key insights",
            "day_schedules": [
                {{
                    "date": "YYYY-MM-DD",
                    "formatted_date": "Month Day, Year",
                    "is_rest_day": boolean, 
                    "activities": [
                        {{
                            "title": "Activity name (Study: Topic Name or Break, etc.)",
                            "start_time": "HH:MM",
                            "end_time": "HH:MM",
                            "duration": minutes (as integer),
                            "type": "study|break|meal|rest|review",
                            "notes": "Optional notes for this activity"
                        }},
                        ... more activities ...
                    ]
                }},
                ... more days ...
            ]
        }}
        
        VERY IMPORTANT:
        - Do NOT assume the user studies every day
        - Calculate how many days are actually needed to finish all topics
        - Space out study days between preparation start and exam date
        - Some days can be marked as rest days (only meals + sleep)
        - Ensure each study day has appropriate breaks and follows all constraints
        - Include all meal times from the form data
        - Prioritize higher importance topics earlier in the schedule
        """
        
        print("Sending schedule generation prompt to Gemini")
        response = model.generate_content(prompt)
        response_text = response.text
        print(f"Received response with length: {len(response_text)}")
        
        # Extract JSON with improved parsing
        try:
            # First try to extract JSON from code block
            json_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
            json_match = re.search(json_pattern, response_text)
            
            if json_match:
                json_str = json_match.group(1)
                print("Found JSON in code block")
            else:
                # Then try to find JSON without the code block markers
                json_pattern = r'({[\s\S]*})'
                json_match = re.search(json_pattern, response_text)
                if json_match:
                    json_str = json_match.group(1)
                    print("Found JSON without code block")
                else:
                    json_str = response_text
                    print("Using full response as JSON")
            
            enhanced_schedule = json.loads(json_str)
            
            # Validate schedule structure
            if "day_schedules" not in enhanced_schedule:
                print("ERROR: No day_schedules in the response")
                # Fix the structure
                if "detailed_schedule" in enhanced_schedule:
                    enhanced_schedule["day_schedules"] = enhanced_schedule["detailed_schedule"]
                else:
                    # Create a simplified schedule as fallback
                    enhanced_schedule["day_schedules"] = create_fallback_schedule(form_data, topics_data)
            
            # Check each day for activities
            for day_idx, day in enumerate(enhanced_schedule["day_schedules"]):
                # If day has items but not activities, rename the field
                if "items" in day and "activities" not in day:
                    day["activities"] = day.pop("items")
                    print(f"Renamed 'items' to 'activities' for day {day_idx}")
                
                # If day doesn't have activities, create some
                if "activities" not in day or not day["activities"]:
                    print(f"FIXING: Day {day_idx} has no activities")
                    day["activities"] = create_fallback_activities(topics_data["topics"], day_idx, form_data)
                    print(f"Added {len(day['activities'])} intelligent activities with ReAct framework")
            
            day_schedules = enhanced_schedule.get('day_schedules', [])
            print(f"Schedule processed with {len(day_schedules)} days")
            return enhanced_schedule
            
        except json.JSONDecodeError as e:
            print(f"ERROR parsing JSON from response: {e}")
            print("JSON content that failed to parse:")
            print(json_str[:500])  # Print first 500 chars for debugging
            fallback = create_fallback_schedule(form_data, topics_data)
            return fallback
            
    except Exception as e:
        print(f"Error generating enhanced schedule: {str(e)}")
        # Create fallback schedule
        fallback = create_fallback_schedule(form_data, topics_data)
        return fallback

# ReAct Framework helper functions
def topic_ranker_tool(topics):
    """Orders topics by importance and difficulty"""
    if not topics:
        return []
    
    # Sort topics by importance (highest first)
    sorted_topics = sorted(topics, key=lambda x: x.get('importance', 0), reverse=True)
    return sorted_topics

def calculate_total_study_hours(topics):
    """Calculates total hours needed to study all topics"""
    total_minutes = 0
    for topic in topics:
        # Get recommended time, default to 45 minutes if not specified
        minutes = topic.get('recommended_time_minutes', 45)
        total_minutes += minutes
    
    # Add 20% for review time
    total_minutes = total_minutes * 1.2
    total_hours = total_minutes / 60
    return total_hours

def calculate_study_days_needed(topics, available_days, hours_per_day):
    """Calculate how many actual study days are needed"""
    total_hours = calculate_total_study_hours(topics)
    
    # Determine days needed based on available study hours per day
    days_needed = total_hours / hours_per_day
    days_needed = min(available_days, round(days_needed))
    
    # Ensure at least 1 day and no more than available days
    days_needed = max(1, min(days_needed, available_days))
    return days_needed

def distribute_days_evenly(start_date, exam_date, study_days_needed):
    """Distribute study days evenly between start date and exam date"""
    days_available = (exam_date - start_date).days + 1
    
    # If we need all days, return all days
    if study_days_needed >= days_available:
        return [start_date + timedelta(days=i) for i in range(days_available)]
    
    # Otherwise, distribute days evenly
    if study_days_needed <= 1:
        # If only one day needed, choose the day after start (or start if that's all we have)
        if days_available > 1:
            return [start_date + timedelta(days=1)]
        return [start_date]
    
    # Calculate spacing between study days
    spacing = max(1, days_available // study_days_needed)
    study_dates = []
    
    # Generate study days with even spacing
    for i in range(study_days_needed):
        day_idx = min(i * spacing, days_available - 1)
        study_dates.append(start_date + timedelta(days=day_idx))
    
    # Always include the day before exam for review if possible
    day_before_exam = exam_date - timedelta(days=1)
    if day_before_exam >= start_date and day_before_exam not in study_dates:
        # Replace the last study day before exam day with the day before exam
        for i in range(len(study_dates) - 1, -1, -1):
            if study_dates[i] < day_before_exam:
                study_dates[i] = day_before_exam
                break
    
    return sorted(list(set(study_dates)))  # Remove duplicates and sort

def create_fallback_schedule(form_data, topics_data):
    """Create a more intelligent fallback schedule if the AI fails"""
    try:
        print("Creating intelligent fallback schedule with ReAct framework")
        fallback_days = []
        
        # Parse dates and times
        try:
            # Extract date information
            exam_date_str = form_data.get('examDate')
            start_date_str = form_data.get('startPrep')
            exam_time_str = form_data.get('examTime') or DEFAULT_EXAM_TIME
            wake_time_str = form_data.get('startTime') or DEFAULT_PREP_START_TIME
            
            # Get meal times
            breakfast_time = form_data.get('breakfastTime', '08:00')
            lunch_time = form_data.get('lunchTime', '13:00')
            snack_time = form_data.get('snackTime', '16:00')
            dinner_time = form_data.get('dinnerTime', '19:00')
            
            # Get break preferences
            break_duration = int(form_data.get('breakDuration', 15))
            # Convert breakInterval to float first, then to minutes as int
            break_interval_hours = float(form_data.get('breakInterval', 1))
            break_interval = int(break_interval_hours * 60)  # Convert hours to minutes
            
            # Get sleep hours
            sleep_hours = int(form_data.get('sleepHours', 8))
            
            # Default to today and tomorrow if parsing fails
            today = datetime.now()
            
            if exam_date_str:
                exam_date = datetime.strptime(exam_date_str, '%Y-%m-%d').date()
            else:
                exam_date = (today + timedelta(days=1)).date()
                
            if start_date_str:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            else:
                start_date = today.date()
            
            # Calculate days available
            days_available = (exam_date - start_date).days + 1
            days_available = max(1, days_available)
            
            # Rank topics by importance
            sorted_topics = topic_ranker_tool(topics_data.get('topics', []))
            
            # Calculate available study hours per day (rough estimate)
            # Assuming 8 hours for sleep, 3 hours for meals and other activities
            available_hours_per_day = 24 - sleep_hours - 3
            
            # Determine how many days are actually needed for study
            study_days_needed = calculate_study_days_needed(sorted_topics, days_available, available_hours_per_day)
            
            # Distribute study days evenly between start date and exam date
            study_dates = distribute_days_evenly(start_date, exam_date, study_days_needed)
            
            # Create complete schedule for all days between start and exam
            for day_idx in range(days_available):
                current_date = start_date + timedelta(days=day_idx)
                formatted_date = current_date.strftime("%B %d, %Y")
                
                # Determine if this is a study day
                is_study_day = current_date in study_dates
                is_exam_day = current_date == exam_date
                
                day_activities = []
                
                # Add wake-up
                day_activities.append({
                    "title": "Wake up",
                    "start_time": wake_time_str,
                    "end_time": wake_time_str,
                    "duration": 0,
                    "type": "rest",
                    "notes": "Start of day"
                })
                
                # Add breakfast
                breakfast_start_time = breakfast_time
                breakfast_end_time_obj = datetime.strptime(breakfast_time, "%H:%M")
                breakfast_end_time_obj += timedelta(minutes=30)  # 30 min for breakfast
                breakfast_end_time = breakfast_end_time_obj.strftime("%H:%M")
                
                day_activities.append({
                    "title": "Breakfast",
                    "start_time": breakfast_start_time,
                    "end_time": breakfast_end_time,
                    "duration": 30,
                    "type": "meal",
                    "notes": "Breakfast time"
                })
                
                # If this is a study day, add study activities
                if is_study_day and not is_exam_day:
                    # Calculate how many topics to cover this day
                    topics_per_day = max(1, len(sorted_topics) // len(study_dates))
                    
                    # Get topics for this specific day
                    day_index = study_dates.index(current_date)
                    start_idx = day_index * topics_per_day
                    end_idx = min(start_idx + topics_per_day, len(sorted_topics))
                    day_topics = sorted_topics[start_idx:end_idx]
                    
                    # If no topics left, use review
                    if not day_topics:
                        day_topics = sorted_topics[:topics_per_day]
                    
                    # Start study 30 mins after breakfast
                    current_time_obj = breakfast_end_time_obj + timedelta(minutes=30)
                    
                    # Add morning study sessions
                    for topic in day_topics[:2]:  # Morning topics
                        start_time = current_time_obj.strftime("%H:%M")
                        study_duration = min(90, max(30, topic.get('recommended_time_minutes', 60)))
                        end_time_obj = current_time_obj + timedelta(minutes=study_duration)
                        end_time = end_time_obj.strftime("%H:%M")
                        
                        # Add the study activity
                        day_activities.append({
                            "title": f"Study: {topic['name']}",
                            "start_time": start_time,
                            "end_time": end_time,
                            "duration": study_duration,
                            "type": "study",
                            "notes": f"Focus on: {', '.join(topic.get('key_points', [])[:2])}"
                        })
                        
                        current_time_obj = end_time_obj
                        
                        # Add a break after study if not the last topic and not too close to lunch
                        lunch_time_obj = datetime.strptime(lunch_time, "%H:%M")
                        if topic != day_topics[-1] and (lunch_time_obj - current_time_obj).seconds / 60 > break_duration + 15:
                            break_start_time = current_time_obj.strftime("%H:%M")
                            break_end_time_obj = current_time_obj + timedelta(minutes=break_duration)
                            break_end_time = break_end_time_obj.strftime("%H:%M")
                            
                            day_activities.append({
                                "title": "Short Break",
                                "start_time": break_start_time,
                                "end_time": break_end_time,
                                "duration": break_duration,
                                "type": "break",
                                "notes": "Rest and recharge"
                            })
                            
                            current_time_obj = break_end_time_obj
                
                # Add lunch
                lunch_start_time = lunch_time
                lunch_end_time_obj = datetime.strptime(lunch_time, "%H:%M")
                lunch_end_time_obj += timedelta(minutes=60)  # 60 min for lunch
                lunch_end_time = lunch_end_time_obj.strftime("%H:%M")
                
                day_activities.append({
                    "title": "Lunch",
                    "start_time": lunch_start_time,
                    "end_time": lunch_end_time,
                    "duration": 60,
                    "type": "meal",
                    "notes": "Lunch time"
                })
                
                # If this is a study day, add afternoon study sessions
                if is_study_day and not is_exam_day:
                    # Start study 30 mins after lunch
                    current_time_obj = lunch_end_time_obj + timedelta(minutes=30)
                    
                    # Add afternoon study sessions
                    for topic in day_topics[2:]:  # Afternoon topics
                        start_time = current_time_obj.strftime("%H:%M")
                        study_duration = min(90, max(30, topic.get('recommended_time_minutes', 60)))
                        end_time_obj = current_time_obj + timedelta(minutes=study_duration)
                        end_time = end_time_obj.strftime("%H:%M")
                        
                        # Add the study activity
                        day_activities.append({
                            "title": f"Study: {topic['name']}",
                            "start_time": start_time,
                            "end_time": end_time,
                            "duration": study_duration,
                            "type": "study",
                            "notes": f"Focus on: {', '.join(topic.get('key_points', [])[:2])}"
                        })
                        
                        current_time_obj = end_time_obj
                        
                        # Add a break after study if not the last topic and not too close to snack time
                        snack_time_obj = datetime.strptime(snack_time, "%H:%M")
                        if topic != day_topics[-1] and (snack_time_obj - current_time_obj).seconds / 60 > break_duration + 15:
                            break_start_time = current_time_obj.strftime("%H:%M")
                            break_end_time_obj = current_time_obj + timedelta(minutes=break_duration)
                            break_end_time = break_end_time_obj.strftime("%H:%M")
                            
                            day_activities.append({
                                "title": "Short Break",
                                "start_time": break_start_time,
                                "end_time": break_end_time,
                                "duration": break_duration,
                                "type": "break",
                                "notes": "Rest and recharge"
                            })
                            
                            current_time_obj = break_end_time_obj
                
                # Add snack time
                snack_start_time = snack_time
                snack_end_time_obj = datetime.strptime(snack_time, "%H:%M")
                snack_end_time_obj += timedelta(minutes=30)  # 30 min for snack
                snack_end_time = snack_end_time_obj.strftime("%H:%M")
                
                day_activities.append({
                    "title": "Snack Break",
                    "start_time": snack_start_time,
                    "end_time": snack_end_time,
                    "duration": 30,
                    "type": "meal",
                    "notes": "Afternoon snack"
                })
                
                # If this is a study day, add evening review session
                if is_study_day and not is_exam_day:
                    # Start review 30 mins after snack
                    current_time_obj = snack_end_time_obj + timedelta(minutes=30)
                    
                    review_start_time = current_time_obj.strftime("%H:%M")
                    review_duration = 60  # 1 hour review
                    review_end_time_obj = current_time_obj + timedelta(minutes=review_duration)
                    review_end_time = review_end_time_obj.strftime("%H:%M")
                    
                    day_activities.append({
                        "title": "Review Session",
                        "start_time": review_start_time,
                        "end_time": review_end_time,
                        "duration": review_duration,
                        "type": "review",
                        "notes": "Review material studied today and consolidate learning"
                    })
                
                # Add dinner
                dinner_start_time = dinner_time
                dinner_end_time_obj = datetime.strptime(dinner_time, "%H:%M")
                dinner_end_time_obj += timedelta(minutes=60)  # 60 min for dinner
                dinner_end_time = dinner_end_time_obj.strftime("%H:%M")
                
                day_activities.append({
                    "title": "Dinner",
                    "start_time": dinner_start_time,
                    "end_time": dinner_end_time,
                    "duration": 60,
                    "type": "meal",
                    "notes": "Dinner time"
                })
                
                # Add bedtime (based on wake time and sleep hours)
                wake_time_obj = datetime.strptime(wake_time_str, "%H:%M")
                # Calculate bedtime properly without using modulo
                bedtime_obj = wake_time_obj - timedelta(hours=sleep_hours)
                # If bedtime is on the previous day, add 24 hours to keep it on the same day
                if bedtime_obj > wake_time_obj:
                    bedtime_obj = bedtime_obj - timedelta(days=1)
                bedtime = bedtime_obj.strftime("%H:%M")
                
                day_activities.append({
                    "title": "Sleep Time",
                    "start_time": bedtime,
                    "end_time": wake_time_str,
                    "duration": sleep_hours * 60,
                    "type": "rest",
                    "notes": f"{sleep_hours} hours of sleep"
                })
                
                # If it's exam day and we know when the exam is, block it out.
                # Without a time we'd be inventing one, so the slot is skipped
                # rather than showing the student a sitting time they never gave.
                if is_exam_day and form_data.get('examTime'):
                    exam_time = exam_time_str
                    exam_prep_start_obj = datetime.strptime(exam_time, "%H:%M") - timedelta(hours=2)
                    exam_prep_start = exam_prep_start_obj.strftime("%H:%M")
                    
                    day_activities.append({
                        "title": "Exam Preparation",
                        "start_time": exam_prep_start,
                        "end_time": exam_time,
                        "duration": 120,
                        "type": "review",
                        "notes": "Final review and preparation before exam"
                    })
                    
                    # Add the exam itself (assume 3 hours)
                    exam_start_time = exam_time
                    exam_end_time_obj = datetime.strptime(exam_time, "%H:%M") + timedelta(hours=3)
                    exam_end_time = exam_end_time_obj.strftime("%H:%M")
                    
                    day_activities.append({
                        "title": f"Exam: {form_data.get('examName', 'Examination')}",
                        "start_time": exam_start_time,
                        "end_time": exam_end_time,
                        "duration": 180,
                        "type": "exam",
                        "notes": "Good luck!"
                    })
                
                # Sort activities by start time
                day_activities.sort(key=lambda x: datetime.strptime(x["start_time"], "%H:%M"))
                
                day_schedule = {
                    "date": current_date.isoformat(),
                    "formatted_date": formatted_date,
                    "is_rest_day": not is_study_day and not is_exam_day,
                    "activities": day_activities
                }
                fallback_days.append(day_schedule)
            
            print(f"Created intelligent fallback schedule with {len(fallback_days)} days")
            
            # Create a summary
            study_days_count = sum(1 for day in fallback_days if not day.get('is_rest_day', False))
            plan_summary = (
                f"This study plan spans {len(fallback_days)} days with {study_days_count} active study days. "
                f"It prioritizes {len(sorted_topics)} topics based on importance, with adequate breaks and meal times. "
                "Each study day includes focused study sessions and a review period to consolidate learning."
            )
            
            return {"day_schedules": fallback_days, "plan_summary": plan_summary}
            
        except Exception as e:
            print(f"Error in schedule creation: {e}")
            # Continue to basic fallback if date parsing fails
            fallback_days = []
            days_count = 3  # Default to 3 days
            
    except Exception as e:
        print(f"Error in fallback schedule creation: {e}")
    
    # Return absolute minimum schedule if all else fails
    return {
        "plan_summary": "Basic fallback study plan due to error in schedule creation",
        "day_schedules": [{
            "date": datetime.now().date().isoformat(),
            "formatted_date": datetime.now().strftime("%B %d, %Y"),
            "is_rest_day": False,
            "activities": [
                {
                    "title": "General Study Session",
                    "start_time": "09:00",
                    "end_time": "10:30", 
                    "duration": 90,
                    "type": "study",
                    "notes": "Focus on main concepts and take notes"
                },
                {
                    "title": "Break",
                    "start_time": "10:30",
                    "end_time": "11:00",
                    "duration": 30,
                    "type": "break",
                    "notes": "Take a short break"
                },
                {
                    "title": "Review Session",
                    "start_time": "11:00",
                    "end_time": "12:30",
                    "duration": 90,
                    "type": "review",
                    "notes": "Review material and practice problems"
                }
            ]
        }]
    }

def create_fallback_activities(topics, day_idx, form_data=None):
    """Create intelligent activities for a day based on topics and ReAct framework"""
    activities = []
    
    # Set defaults if form_data is not provided
    if not form_data:
        form_data = {
            'startTime': '07:00',
            'breakfastTime': '08:00',
            'lunchTime': '13:00', 
            'snackTime': '16:00',
            'dinnerTime': '19:00',
            'sleepHours': 8,
            'breakDuration': 15,
            'breakInterval': 60
        }
    
    # Extract time preferences or use defaults
    wake_time = form_data.get('startTime') or DEFAULT_PREP_START_TIME
    breakfast_time = form_data.get('breakfastTime', '08:00')
    lunch_time = form_data.get('lunchTime', '13:00')
    snack_time = form_data.get('snackTime', '16:00')
    dinner_time = form_data.get('dinnerTime', '19:00')
    break_duration = int(form_data.get('breakDuration', 15))
    # Convert breakInterval to float first, then to minutes as int
    break_interval_hours = float(form_data.get('breakInterval', 1))
    break_interval = int(break_interval_hours * 60)  # Convert hours to minutes
    
    # Calculate best times for study based on chronobiology
    # Most people are most productive in the morning and early afternoon
    morning_start = datetime.strptime(breakfast_time, "%H:%M") + timedelta(minutes=30)
    afternoon_start = datetime.strptime(lunch_time, "%H:%M") + timedelta(minutes=30)
    evening_start = datetime.strptime(dinner_time, "%H:%M") + timedelta(minutes=30)
    
    # Sort topics by importance
    sorted_topics = sorted(topics, key=lambda x: x.get('importance', 0), reverse=True) if topics else []
    
    if not sorted_topics:
        # If no topics, create a generic schedule
        return [
            {
                "title": "General Study Session",
                "start_time": morning_start.strftime("%H:%M"),
                "end_time": (morning_start + timedelta(minutes=90)).strftime("%H:%M"),
                "duration": 90,
                "type": "study",
                "notes": "Focus on core concepts"
            },
            {
                "title": "Break",
                "start_time": (morning_start + timedelta(minutes=90)).strftime("%H:%M"),
                "end_time": (morning_start + timedelta(minutes=90+break_duration)).strftime("%H:%M"),
                "duration": break_duration,
                "type": "break",
                "notes": "Take a short break"
            },
            {
                "title": "Review Session",
                "start_time": (morning_start + timedelta(minutes=90+break_duration)).strftime("%H:%M"),
                "end_time": (morning_start + timedelta(minutes=90+break_duration+60)).strftime("%H:%M"),
                "duration": 60,
                "type": "review",
                "notes": "Review and consolidate learning"
            }
        ]
    
    # Get topics for this specific day (distribute across days)
    total_days = max(1, len(sorted_topics) // 2)  # Assume at least 1 day, aim for 2 topics per day
    day_idx = day_idx % total_days  # Ensure we cycle back if needed
    
    # Prioritize more important topics earlier in the study plan
    topics_per_day = max(2, min(4, len(sorted_topics) // total_days))
    start_idx = day_idx * topics_per_day
    end_idx = min(start_idx + topics_per_day, len(sorted_topics))
    
    day_topics = sorted_topics[start_idx:end_idx]
    if not day_topics:  # If we run out of topics, use the most important ones
        day_topics = sorted_topics[:min(topics_per_day, len(sorted_topics))]
    
    # Generate a more intelligent schedule
    activities = []
    
    # Add wake-up
    activities.append({
        "title": "Wake up",
        "start_time": wake_time,
        "end_time": wake_time,
        "duration": 0,
        "type": "rest",
        "notes": "Start of day"
    })
    
    # Add breakfast
    breakfast_end = datetime.strptime(breakfast_time, "%H:%M") + timedelta(minutes=30)
    activities.append({
        "title": "Breakfast",
        "start_time": breakfast_time,
        "end_time": breakfast_end.strftime("%H:%M"),
        "duration": 30,
        "type": "meal",
        "notes": "Breakfast time"
    })
    
    # Morning study session (highest priority topics)
    current_time = morning_start
    for topic_idx, topic in enumerate(day_topics[:len(day_topics)//2 + 1]):
        # Calculate optimal study duration based on topic importance and recommended time
        importance = topic.get('importance', 5)
        base_duration = topic.get('recommended_time_minutes', 45)
        # More important topics get more time, but cap at 90 minutes
        study_duration = min(90, max(30, int(base_duration * (0.8 + importance / 20))))
        
        start_time = current_time
        end_time = current_time + timedelta(minutes=study_duration)
        
        # Add study session
        activities.append({
            "title": f"Study: {topic['name']}",
            "start_time": start_time.strftime("%H:%M"),
            "end_time": end_time.strftime("%H:%M"),
            "duration": study_duration,
            "type": "study",
            "notes": f"Focus on: {', '.join(topic.get('key_points', [])[:2])}"
        })
        
        current_time = end_time
        
        # Add a break after each topic (except before lunch)
        lunch_time_obj = datetime.strptime(lunch_time, "%H:%M")
        if topic_idx < len(day_topics)//2 and (lunch_time_obj - current_time).total_seconds() / 60 > break_duration + 15:
            break_end = current_time + timedelta(minutes=break_duration)
            
            activities.append({
                "title": "Short Break",
                "start_time": current_time.strftime("%H:%M"),
                "end_time": break_end.strftime("%H:%M"),
                "duration": break_duration,
                "type": "break",
                "notes": "Rest and recharge"
            })
            
            current_time = break_end
    
    # Add lunch
    lunch_time_obj = datetime.strptime(lunch_time, "%H:%M")
    lunch_end = lunch_time_obj + timedelta(minutes=60)
    
    activities.append({
        "title": "Lunch",
        "start_time": lunch_time,
        "end_time": lunch_end.strftime("%H:%M"),
        "duration": 60,
        "type": "meal",
        "notes": "Lunch break"
    })
    
    # Afternoon study sessions
    current_time = afternoon_start
    for topic_idx, topic in enumerate(day_topics[len(day_topics)//2 + 1:]):
        # Calculate optimal study duration
        importance = topic.get('importance', 5)
        base_duration = topic.get('recommended_time_minutes', 45)
        study_duration = min(90, max(30, int(base_duration * (0.8 + importance / 20))))
        
        start_time = current_time
        end_time = current_time + timedelta(minutes=study_duration)
        
        # Add study session
        activities.append({
            "title": f"Study: {topic['name']}",
            "start_time": start_time.strftime("%H:%M"),
            "end_time": end_time.strftime("%H:%M"),
            "duration": study_duration,
            "type": "study",
            "notes": f"Focus on: {', '.join(topic.get('key_points', [])[:2])}"
        })
        
        current_time = end_time
        
        # Add a break after study if not too close to snack time
        snack_time_obj = datetime.strptime(snack_time, "%H:%M")
        if (snack_time_obj - current_time).total_seconds() / 60 > break_duration + 15:
            break_end = current_time + timedelta(minutes=break_duration)
            
            activities.append({
                "title": "Short Break",
                "start_time": current_time.strftime("%H:%M"),
                "end_time": break_end.strftime("%H:%M"),
                "duration": break_duration,
                "type": "break",
                "notes": "Rest and recharge"
            })
            
            current_time = break_end
    
    # Add snack time
    snack_time_obj = datetime.strptime(snack_time, "%H:%M")
    snack_end = snack_time_obj + timedelta(minutes=30)
    
    activities.append({
        "title": "Snack Break",
        "start_time": snack_time,
        "end_time": snack_end.strftime("%H:%M"),
        "duration": 30,
        "type": "meal",
        "notes": "Afternoon snack"
    })
    
    # Add review session
    review_start = snack_end + timedelta(minutes=30)
    review_end = review_start + timedelta(minutes=60)
    
    activities.append({
        "title": "Review Session",
        "start_time": review_start.strftime("%H:%M"),
        "end_time": review_end.strftime("%H:%M"),
        "duration": 60,
        "type": "review",
        "notes": f"Review today's topics: {', '.join([t['name'] for t in day_topics[:2]])}"
    })
    
    # Add dinner
    dinner_time_obj = datetime.strptime(dinner_time, "%H:%M")
    dinner_end = dinner_time_obj + timedelta(minutes=60)
    
    activities.append({
        "title": "Dinner",
        "start_time": dinner_time,
        "end_time": dinner_end.strftime("%H:%M"),
        "duration": 60,
        "type": "meal",
        "notes": "Dinner time"
    })
    
    # Sort activities by start time
    activities.sort(key=lambda x: datetime.strptime(x["start_time"], "%H:%M"))
    
    return activities

# Roughly the amount of material text worth sending in one summary request
MAX_SUMMARY_INPUT_CHARS = 200000


def get_exams_with_materials(user_id):
    """Every (class, exam) that has uploaded materials, with a count.

    Driven by class_material rows rather than saved study plans - materials are
    uploaded when the planner form is submitted, well before the plan row is
    written, so keying off plans would hide anything not yet saved.
    """
    materials = ClassMaterial.query.filter_by(user_id=user_id).all()
    if not materials:
        return []

    counts = {}
    for material in materials:
        key = (material.class_id, material.exam_name)
        counts[key] = counts.get(key, 0) + 1

    classes_by_id = {
        c.id: c for c in StudyClass.query.filter_by(user_id=user_id).all()
    }
    plans_by_key = {
        (p.class_id, p.title): p
        for p in StudyPlan.query.filter(
            StudyPlan.user_id == user_id,
            StudyPlan.class_id.isnot(None)
        ).all()
    }

    exams = []
    for (class_id, exam_name), count in counts.items():
        study_class = classes_by_id.get(class_id)
        if not study_class:
            continue  # class was deleted, or isn't this student's
        exam_label = exam_name or 'Unassigned'
        exams.append({
            'class_id': class_id,
            'exam_name': exam_name,
            # class_id is an integer, so the first colon is always the separator
            # no matter what punctuation the student used in the exam name
            'key': f'{class_id}:{exam_name or ""}',
            'plan': plans_by_key.get((class_id, exam_name)),
            'material_count': count,
            'label': f'{study_class.label} - {exam_label}',
        })

    exams.sort(key=lambda e: e['label'])
    return exams


def summarise_exam_materials(user_id, class_id, exam_name):
    """Ask Gemini for a study summary of one exam's materials.

    Returns (summary_text, material_list, truncated).
    """
    # Confirm the class belongs to this student before reading anything
    study_class = StudyClass.query.filter_by(id=class_id, user_id=user_id).first()
    if not study_class:
        raise ValueError("That exam couldn't be found.")

    materials = ClassMaterial.query.filter_by(
        class_id=class_id, exam_name=exam_name
    ).order_by(ClassMaterial.uploaded_at).all()

    if not materials:
        raise ValueError("There are no materials uploaded for this exam yet.")

    exam_label = exam_name or 'Unassigned'

    contents, _ = extract_text_from_paths([m.file_path for m in materials])
    contents = (contents or '').strip()
    if len(contents) < 100:
        raise ValueError(
            "Couldn't read enough text from this exam's materials to summarise them. "
            "Scanned PDFs without selectable text won't work."
        )

    truncated = len(contents) > MAX_SUMMARY_INPUT_CHARS
    if truncated:
        contents = contents[:MAX_SUMMARY_INPUT_CHARS]

    prompt = f"""You are helping a student revise for "{exam_label}".

Summarise the study material below into a revision summary. Use this structure,
in Markdown:

## Overview
Two or three sentences on what this material covers.

## Key Topics
For each major topic: a bold heading, then 2-4 bullets of the essential points.

## Formulas & Definitions
Anything worth memorising verbatim. Omit this section if there is nothing.

## Likely Exam Focus
The 3-5 areas most worth the student's time, and why.

Work only from the material provided. Do not invent facts. If the material is
fragmentary, say so rather than filling gaps.

STUDY MATERIAL:
{contents}
"""

    model = genai.GenerativeModel('gemini-2.5-flash-lite')
    response = model.generate_content(prompt)
    summary = (getattr(response, 'text', '') or '').strip()
    if not summary:
        raise ValueError("The AI returned an empty summary. Please try again.")

    return summary, materials, truncated


def _inline_markdown(text):
    """Convert **bold** runs. Input is already HTML-escaped."""
    return re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)


def render_simple_markdown(text):
    """Render the small Markdown subset the summary prompt asks for.

    Everything is HTML-escaped before any tags are added, so model output can't
    inject markup. Avoids pulling in a Markdown dependency or a client-side
    renderer that would need innerHTML.
    """
    html = []
    in_list = False

    for raw_line in str(escape(text)).splitlines():
        line = raw_line.strip()

        if not line:
            if in_list:
                html.append('</ul>')
                in_list = False
            continue

        if line.startswith(('- ', '* ')):
            if not in_list:
                html.append('<ul>')
                in_list = True
            html.append(f'<li>{_inline_markdown(line[2:])}</li>')
            continue

        if in_list:
            html.append('</ul>')
            in_list = False

        if line.startswith('### '):
            html.append(f'<h4>{_inline_markdown(line[4:])}</h4>')
        elif line.startswith('## '):
            html.append(f'<h3>{_inline_markdown(line[3:])}</h3>')
        elif line.startswith('# '):
            html.append(f'<h3>{_inline_markdown(line[2:])}</h3>')
        else:
            html.append(f'<p>{_inline_markdown(line)}</p>')

    if in_list:
        html.append('</ul>')

    return '\n'.join(html)


@study_plan.route('/summarize', methods=['GET', 'POST'])
@login_required
def summarize_materials():
    """Generate a revision summary from the materials uploaded for one exam."""
    exams = get_exams_with_materials(current_user.id)
    summary = None
    materials = []
    truncated = False
    selected_key = None
    selected_label = None

    if request.method == 'POST':
        # Keyed on (class, exam) rather than a plan id, because materials exist
        # before the study plan is saved. class_id is an int, so splitting on
        # the first colon is safe whatever punctuation is in the exam name.
        selected_key = (request.form.get('examKey') or '').strip()
        raw_class_id, _, exam_name = selected_key.partition(':')
        exam_name = exam_name or None

        try:
            class_id = int(raw_class_id)
        except (TypeError, ValueError):
            class_id = None

        if class_id is None:
            flash('Please choose an exam to summarise.')
        else:
            selected_label = next(
                (e['label'] for e in exams if e['key'] == selected_key), None
            )
            try:
                summary, materials, truncated = summarise_exam_materials(
                    current_user.id, class_id, exam_name
                )
            except ValueError as e:
                flash(str(e))
            except Exception as e:
                print(f"Error summarising materials for class {class_id} / {exam_name}: {e}")
                import traceback
                traceback.print_exc()
                flash("Couldn't generate the summary. Please try again.")

    return render_template(
        'summarize.html',
        exams=exams,
        summary=render_simple_markdown(summary) if summary else None,
        materials=materials,
        truncated=truncated,
        selected_key=selected_key,
        selected_label=selected_label
    )


@study_plan.route('/forms')
@login_required
def forms():
    classes = StudyClass.query.filter_by(
        user_id=current_user.id, is_archived=False
    ).order_by(StudyClass.code, StudyClass.name).all()
    return render_template('forms.html', classes=classes)

@study_plan.route('/create-study-plan', methods=['GET', 'POST'])
@login_required
def create_study_plan():
    if request.method != 'POST':
        # Allow GET requests to redirect to forms page
        return redirect(url_for('study_plan.forms'))
        
    try:
        # Debug the incoming form data
        print("=" * 50)
        print("FORM DATA RECEIVED:")
        print(f"Form data: {request.form}")
        
        # Get form data
        form_data = {
            # Normalised here (not just defaulted) so the plan title and the
            # exam_name stamped on each upload are always the same string -
            # the dashboard joins materials to exams on it.
            'examName': (request.form.get('examName') or '').strip() or 'Study Plan',
            'examDate': request.form.get('examDate'),
            # Exam time is optional - normalise blank to None so the difference
            # between "not given" and a real time stays visible downstream
            'examTime': (request.form.get('examTime') or '').strip() or None,
            'startPrep': request.form.get('startPrep', ''),
            # Optional - normalised to None so the scheduler's default applies
            'startTime': (request.form.get('startTime') or '').strip() or None,
        }

        # Rest & meal preferences live on the student's profile, not this form
        form_data.update(get_student_profile(current_user.id).to_form_data())
        
        print("Form data processed:", form_data)
        
        # Check if start date is the same as exam date
        exam_date = form_data['examDate']
        start_date = form_data['startPrep']
        exam_time = form_data['examTime']
        start_time = form_data['startTime']
        
        # Check if starting on exam day
        is_exam_day = exam_date == start_date
        is_revision_only = False

        if is_exam_day:
            if not exam_time or not start_time:
                # Both times are optional, and without them there's no way to
                # know how many hours are left. Still a same-day plan, so treat
                # it as revision rather than rejecting it over a time the
                # student was never asked to provide.
                is_revision_only = True
                form_data['is_revision_only'] = True
            else:
                # Calculate hours between start time and exam time
                exam_hours, exam_minutes = map(int, exam_time.split(':'))
                start_hours, start_minutes = map(int, start_time.split(':'))

                # Convert to minutes for comparison
                exam_total_minutes = exam_hours * 60 + exam_minutes
                start_total_minutes = start_hours * 60 + start_minutes

                # Calculate time difference in hours
                hours_difference = (exam_total_minutes - start_total_minutes) / 60

                # If less than 3 hours before exam, reject the submission
                if hours_difference < 3:
                    flash('Cannot create a study plan on exam day with less than 3 hours before the exam!')
                    return redirect(url_for('study_plan.forms'))
                else:
                    # Set flag for revision only mode
                    is_revision_only = True
                    form_data['is_revision_only'] = True
        
        # Check for PDF files
        pdf_contents = ""
        pdf_documents = []
        collection_name = ""
        pdf_files = []

        study_class = resolve_selected_class(request.form)
        if 'studyMaterials' in request.files:
            pdf_files = [f for f in request.files.getlist('studyMaterials') if f and f.filename]

        google_doc_url = (request.form.get('googleDocUrl') or '').strip()

        if study_class:
            # Uploads are scoped to this exam within the class, so the plan is
            # built only from the material for this exam - not the whole class.
            exam_name = form_data.get('examName') or 'Study Plan'
            if pdf_files:
                store_class_materials(study_class, exam_name, pdf_files)

            if google_doc_url:
                try:
                    store_google_doc_material(study_class, exam_name, google_doc_url)
                except GoogleDocError as e:
                    # A bad link shouldn't throw away the PDFs or the whole plan
                    flash(str(e))
                except Exception as e:
                    print(f"Unexpected error importing Google Doc: {e}")
                    flash("Couldn't import that Google Doc. The plan was built without it.")

            materials = ClassMaterial.query.filter_by(
                class_id=study_class.id, exam_name=exam_name
            ).all()
            pdf_contents, pdf_documents = extract_text_from_paths([m.file_path for m in materials])
            collection_name = f"class_{study_class.id}_exam_{secure_filename(exam_name)}"
            print(f"Studying {len(materials)} material(s) for {study_class.label} / {exam_name}")
        elif pdf_files or google_doc_url:
            if pdf_files:
                print(f"Found files in studyMaterials field")
                pdf_contents, pdf_documents, collection_name = process_pdf_files(pdf_files)

            # No class selected, so there's nothing to file the doc under - just
            # read it straight into this plan's content.
            if google_doc_url:
                try:
                    _, doc_text = fetch_google_doc_text(google_doc_url)
                    pdf_contents += doc_text + "\n\n"
                    pdf_documents.append({"content": doc_text, "page": 0})
                except GoogleDocError as e:
                    flash(str(e))
                except Exception as e:
                    print(f"Unexpected error reading Google Doc: {e}")
                    flash("Couldn't import that Google Doc. The plan was built without it.")
        
        # Determine if we have usable PDF content
        has_pdf_content = pdf_contents and len(pdf_contents.strip()) > 100
        
        if has_pdf_content:
            print(f"Extracted {len(pdf_contents)} characters of text from PDFs")
            try:
                # Extract important topics using Gemini 2.0
                topics_data = extract_important_topics(pdf_contents)
                print("Successfully extracted topics from PDF with Gemini AI")
            except Exception as e:
                print(f"Error with Gemini API: {e}")
                # Use fallback if Gemini fails
                topics_data = {
                    "topics": [
                        {
                            "name": "General Study Topic 1",
                            "importance": 8,
                            "explanation": "We couldn't analyze your PDF with our AI. This is a generic topic.",
                            "recommended_time_minutes": 60,
                            "key_points": ["Study the main concepts", "Take practice tests", "Review fundamentals"]
                        }
                    ]
                }
        else:
            # If no usable content found, create a simple study plan without PDF content
            print("No usable PDF content found. Creating a basic plan.")
            
            # Use fallback content
            topics_data = {
                "topics": [
                    {
                        "name": "Study Topic 1 (No PDF Content)",
                        "importance": 8,
                        "explanation": "This is a placeholder topic since we couldn't extract content from your PDF",
                        "recommended_time_minutes": 60,
                        "key_points": ["Review basic concepts", "Practice exercises", "Apply to real problems"]
                    },
                    {
                        "name": "Study Topic 2 (No PDF Content)",
                        "importance": 7,
                        "explanation": "This is a placeholder topic since we couldn't extract content from your PDF",
                        "recommended_time_minutes": 45,
                        "key_points": ["Focus on fundamentals", "Take notes", "Create flashcards"]
                    }
                ]
            }
        
        # Create the enhanced study schedule, passing the revision_only flag
        form_data['is_revision_only'] = is_revision_only  # Add the flag to form data
        
        try:
            print("Attempting to create enhanced schedule...")
            enhanced_schedule = create_enhanced_study_schedule(form_data, topics_data)
            
            if not enhanced_schedule or not isinstance(enhanced_schedule, dict):
                print("Error: Enhanced schedule creation failed to return a valid schedule")
                # Fall back to a simple schedule
                enhanced_schedule = create_fallback_schedule(form_data, topics_data)
                if not enhanced_schedule:
                    # Create an absolute minimum fallback
                    enhanced_schedule = {
                        "plan_summary": "Basic study plan created due to scheduling errors",
                        "day_schedules": []
                    }
        except Exception as e:
            print(f"Error creating enhanced schedule: {e}")
            # Fall back to a simple schedule
            enhanced_schedule = create_fallback_schedule(form_data, topics_data)
            if not enhanced_schedule:
                # Create an absolute minimum fallback
                enhanced_schedule = {
                    "plan_summary": "Basic study plan created due to scheduling errors",
                    "day_schedules": []
                }
        
        # Debug the schedule response
        day_schedules = enhanced_schedule.get('day_schedules', [])
        print(f"Schedule generated with {len(day_schedules)} days")
        if day_schedules and len(day_schedules) > 0:
            first_day = day_schedules[0]
            print(f"First day: {first_day.get('formatted_date')}")
            activities = first_day.get('activities', [])
            print(f"Activities count: {len(activities)}")
            if activities:
                print(f"First activity: {activities[0].get('title')}")
        else:
            print("Warning: No day schedules were generated in the enhanced schedule")

        # Define the study plan structure with the revision flag
        study_plan_data = {
            "title": form_data.get('examName', 'Study Plan'),  # Use exam name as title
            "topics": topics_data.get("topics", []),
            "detailed_schedule": enhanced_schedule.get("day_schedules", []),
            "plan_summary": enhanced_schedule.get("plan_summary", ""),
            "is_revision_only": is_revision_only,
            "exam_date": form_data['examDate'],  # Consistent field name for exam date
            "prep_start_date": form_data['startPrep'],  # Changed to match the model field name
            "class_id": study_class.id if study_class else None
        }
        
        # Add debug output to verify the data
        print(f"DEBUG - Adding to session: exam_date={study_plan_data['exam_date']}, prep_start_date={study_plan_data['prep_start_date']}")
        
        # Save study plan to session
        session['study_plan'] = study_plan_data
        
        flash('Study plan created successfully!')
        return redirect(url_for('study_plan.study_plan_list'))
    
    except Exception as e:
        import traceback
        print("Exception in create_study_plan:")
        traceback.print_exc()
        flash(f'Error creating study plan: {str(e)}')
        return redirect(url_for('study_plan.forms'))

@study_plan.route('/studyplan')
@login_required
def study_plan_list():
    # Check if we have a newly created plan in the session
    if 'study_plan' in session:
        study_plan_data = session['study_plan']
        # Clear it from session after retrieving
        session.pop('study_plan', None)
        
        # Add debug to see what we're rendering
        print(f"Rendering study plan with {len(study_plan_data.get('topics', []))} topics")
        print(f"Schedule has {len(study_plan_data.get('detailed_schedule', []))} days")
        
        # Prepare data for the template
        template_data = prepare_study_plan_data_for_template(
            study_plan_data.get('topics', []),
            study_plan_data.get('detailed_schedule', [])
        )
        
        # Check for empty days and add fallback activities if needed
        for day in study_plan_data.get('detailed_schedule', []):
            if not day.get('activities') and 'items' in day:
                print(f"Converting 'items' to 'activities' for day {day.get('formatted_date')}")
                day['activities'] = day.pop('items')
            
            if not day.get('activities'):
                print(f"Day {day.get('formatted_date')} has no activities, adding fallback")
                day['activities'] = [
                    {
                        "title": "Study Session",
                        "start_time": "09:00",
                        "end_time": "10:30",
                        "duration": 90,
                        "type": "study",
                        "notes": "Focus on main topics and take notes"
                    },
                    {
                        "title": "Break",
                        "start_time": "10:30",
                        "end_time": "11:00",
                        "duration": 30,
                        "type": "break",
                        "notes": "Take a short break"
                    },
                    {
                        "title": "Review Session",
                        "start_time": "11:00",
                        "end_time": "12:30",
                        "duration": 90,
                        "type": "review",
                        "notes": "Review material and practice problems"
                    }
                ]
        
        return render_template('studyplan.html', study_plan=study_plan_data, can_save=True, user=current_user, **template_data)
    
    # Otherwise, get saved plans
    plans = StudyPlan.query.filter_by(user_id=current_user.id).all()
    # Make sure we pass an empty study_plan dict to avoid template errors
    return render_template('studyplan.html', plans=plans, study_plan={}, show_list=True)

@study_plan.route('/studyplan/<int:plan_id>')
@login_required
def view_study_plan(plan_id):
    """Display a saved study plan"""
    # Get the requested study plan - updated to SQLAlchemy 2.0 style
    study_plan_entry = db.session.get(StudyPlan, plan_id)
    
    if not study_plan_entry:
        flash('Study plan not found')
        return redirect(url_for('study_plan.study_plan_list'))
    
    # Check if the plan belongs to the logged-in user
    if study_plan_entry.user_id != current_user.id:
        flash('You do not have permission to view this study plan')
        return redirect(url_for('study_plan.study_plan_list'))
    
    # Convert database format to template format
    study_plan_data = {
        "id": study_plan_entry.id,
        "title": study_plan_entry.title,
        "topics": study_plan_entry.topics_data,
        "detailed_schedule": study_plan_entry.schedule_data,
        "plan_summary": study_plan_entry.plan_summary,
        "is_revision_only": study_plan_entry.is_revision_only,
        "exam_date": study_plan_entry.exam_date.strftime('%Y-%m-%d') if study_plan_entry.exam_date else None,
        "prep_start_date": study_plan_entry.prep_start_date.strftime('%Y-%m-%d') if study_plan_entry.prep_start_date else None
    }
    
    # Prepare template data including JSON string versions of topics and schedule
    template_data = prepare_study_plan_data_for_template(
        study_plan_data.get('topics', []),
        study_plan_data.get('detailed_schedule', [])
    )
    
    # Render the studyplan template with the saved plan data
    return render_template('studyplan.html', 
                          study_plan=study_plan_data, 
                          can_save=False,  # It's already saved
                          user=current_user, 
                          **template_data)

# Add a dedicated studyplan route to match the provided implementation
@study_plan.route('/studyplan')
@login_required
def studyplan(plan_id=None):
    """Display all study plans or a specific plan"""
    # If plan_id is provided via query parameter
    plan_id = request.args.get('plan_id')
    
    if plan_id:
        try:
            plan_id = int(plan_id)
            return view_study_plan(plan_id)
        except (ValueError, TypeError):
            flash('Invalid study plan ID')
            return redirect(url_for('study_plan.study_plan_list'))
    
    # Otherwise, show all plans
    return study_plan_list()

@study_plan.route('/api/save_study_plan', methods=['POST'])
@login_required
@db_operation
def save_study_plan_api():  # Renamed from save_study_plan to save_study_plan_api
    data = request.json
    print(f"DEBUG - Save Study Plan API - Received data: {data}")
    
    # Special case handling for the "studyplan" string plan_id error
    if data and data.get('plan_id') == 'studyplan':
        print("WARNING: Received 'studyplan' as plan_id instead of actual study plan data.")
        print("This typically happens when the form submission is incorrect.")
        
        # Check if we have a study plan in the session we can recover
        if 'study_plan' in session:
            print("Found study plan data in session, attempting to use that instead")
            data = session.get('study_plan')
            print(f"Using session data: {data}")
            # Don't remove from session yet in case this fails
        else:
            return jsonify({
                'success': False, 
                'error': 'Invalid study plan data. Got "studyplan" as plan_id.',
                'help': 'Please return to the form and try again with complete data.'
            }), 400
    
    # Check if we have a properly structured request
    if not data or (not data.get('topics') and not data.get('detailed_schedule')):
        # This might be a different type of request (like checked activities)
        # Extract plan_id
        plan_id = data.get('plan_id')
        print(f"DEBUG - Missing essential plan data. Plan ID: {plan_id}, Type: {type(plan_id)}")
        
        # Handle case where plan_id is a digit string (update existing plan)
        if plan_id and isinstance(plan_id, str) and plan_id.isdigit():
            print(f"DEBUG - Attempting to update existing plan with ID: {plan_id}")
            # Update to SQLAlchemy 2.0 style
            plan = db.session.get(StudyPlan, int(plan_id))
            
            if plan and plan.user_id == current_user.id:
                # Update checked activities or other simple updates
                if 'checked_activities' in data:
                    print(f"DEBUG - Updating checked activities for plan {plan_id}")
                    # Logic to update checked activities would go here
                    # For now, just acknowledge the request
                    return jsonify({'success': True, 'message': 'Study plan activities updated'})
                
                return jsonify({'success': True, 'message': 'Study plan updated'})
            else:
                return jsonify({'success': False, 'error': f'Plan with ID {plan_id} not found or not owned by you'}), 404
        
        return jsonify({
            'success': False, 
            'error': 'Invalid study plan data',
            'received_data': data
        }), 400
    
    # Extract data from request for a full study plan
    topics = data.get('topics', [])
    detailed_schedule = data.get('detailed_schedule', [])
    is_revision_only = data.get('is_revision_only', False)
    plan_summary = data.get('plan_summary', '')
    title = data.get('title', 'Study Plan')
    
    # Extract form inputs to store as JSON
    form_inputs = {}
    for key, value in data.items():
        # Only store certain fields in form_inputs_json
        if key in ['examDate', 'examTime', 'startPrep', 'startTime', 
                  'sleepHours', 'breakDuration', 'breakInterval',
                  'breakfastTime', 'lunchTime', 'snackTime', 'dinnerTime']:
            form_inputs[key] = value
    
    # Extract dates - look in different places
    exam_date_str = data.get('exam_date') or data.get('examDate') or data.get('exam_date_str') or ''
    start_date_str = data.get('prep_start_date') or data.get('startPrep') or data.get('start_date') or ''
    
    print(f"DEBUG - Dates extracted: exam_date={exam_date_str}, prep_start_date={start_date_str}")
    
    # Enhanced date parsing with better error handling
    exam_date = None
    if exam_date_str:
        try:
            exam_date = datetime.strptime(exam_date_str, '%Y-%m-%d').date()
            print(f"DEBUG - Successfully parsed exam_date: {exam_date}")
        except ValueError as e:
            print(f"ERROR - Failed to parse exam_date '{exam_date_str}': {e}")
            # Try an alternative date format if the primary format fails
            try:
                exam_date = datetime.strptime(exam_date_str, '%m/%d/%Y').date()
                print(f"DEBUG - Parsed exam_date with alternate format: {exam_date}")
            except ValueError:
                print(f"ERROR - Failed to parse exam_date with alternate format too")
    
    # Enhanced prep_start_date parsing
    prep_start_date = None
    if start_date_str:
        try:
            prep_start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            print(f"DEBUG - Successfully parsed prep_start_date: {prep_start_date}")
        except ValueError as e:
            print(f"ERROR - Failed to parse prep_start_date '{start_date_str}': {e}")
            # Try an alternative date format if the primary format fails
            try:
                prep_start_date = datetime.strptime(start_date_str, '%m/%d/%Y').date()
                print(f"DEBUG - Parsed prep_start_date with alternate format: {prep_start_date}")
            except ValueError:
                print(f"ERROR - Failed to parse prep_start_date with alternate format too")
    
    # If there's no plan summary, create a basic one
    if not plan_summary:
        if exam_date and prep_start_date:
            days = (exam_date - prep_start_date).days
            plan_summary = f"Study plan for {days} day(s) preparing for exam on {exam_date.strftime('%Y-%m-%d')}"
        else:
            plan_summary = "Custom study plan"
    
    print(f"DEBUG - Creating StudyPlan with: exam_date={exam_date}, prep_start_date={prep_start_date}, plan_summary='{plan_summary}'")
    
    # Only accept a class the current user actually owns
    class_id = data.get('class_id')
    if class_id is not None:
        owned = StudyClass.query.filter_by(id=class_id, user_id=current_user.id).first()
        class_id = owned.id if owned else None

    # Create new study plan with Text fields
    new_plan = StudyPlan(
        user_id=current_user.id,
        class_id=class_id,
        title=title,
        is_revision_only=is_revision_only,
        plan_summary=plan_summary,
        exam_date=exam_date,
        prep_start_date=prep_start_date,
        form_inputs_json=form_inputs
    )
    
    # Set topics and schedule using properties to handle JSON conversion
    new_plan.topics_data = topics
    new_plan.schedule_data = detailed_schedule
    
    # Add additional debugging before committing
    print(f"DEBUG - About to save StudyPlan with: exam_date={new_plan.exam_date}, prep_start_date={new_plan.prep_start_date}")
    
    db.session.add(new_plan)
    
    # Commit with error handling
    try:
        db.session.commit()
        plan_id = new_plan.id
        print("=" * 60)
        print(f"✅ Successfully saved StudyPlan with id: {plan_id}")
        
        # After successful save, store plan in Qdrant for RAG retrieval
        if qdrant_client is not None and embedding_model is not None:
            print("-" * 60)
            print(f"📊 STORING STUDY PLAN IN QDRANT")
            print("-" * 60)
            
            try:
                print(f"🔄 Processing {len(topics)} topics and {len(detailed_schedule)} days")
                
                # Calculate the total embeddings that will be created
                total_key_points = sum(len(topic.get('key_points', [])) for topic in topics)
                total_activities = sum(len(day.get('activities', [])) for day in detailed_schedule)
                expected_embeddings = len(topics) + total_key_points + total_activities
                
                print(f"📝 Expected embeddings: {expected_embeddings}")
                print(f"   - Topics: {len(topics)}")
                print(f"   - Key points: {total_key_points}")
                print(f"   - Activities: {total_activities}")
                
                # Store in Qdrant
                rag_success = store_study_plan_in_qdrant(
                    user_id=current_user.id,
                    plan_id=plan_id,
                    topics=topics,
                    detailed_schedule=detailed_schedule
                )
                
                if rag_success:
                    print("=" * 60)
                    print(f"✅ STUDY PLAN SUCCESSFULLY STORED IN QDRANT")
                    print("=" * 60)
                else:
                    print("⚠️ Failed to store study plan in Qdrant, but database save was successful")
            except Exception as rag_error:
                print(f"❌ Error storing study plan in Qdrant: {str(rag_error)}")
                # Don't fail the entire operation if Qdrant storage fails
        else:
            print("⚠️ Qdrant client or embedding model not available. To enable RAG:")
            print("   1. Set QDRANT_URL and QDRANT_API_KEY environment variables")
            print("   2. Install required packages: sentence-transformers, qdrant-client")
            
    except Exception as e:
        db.session.rollback()
        print(f"❌ ERROR - Failed to save StudyPlan: {str(e)}")
        return jsonify({
            'success': False,
            'error': f"Database error: {str(e)}"
        }), 500
    
    return jsonify({
        'success': True,
        'plan_id': new_plan.id,
        'redirect': url_for('study_plan.view_study_plan', plan_id=new_plan.id)
    })

# Replace the existing direct_save_study_plan route with a simplified version that calls save_study_plan
@study_plan.route('/direct-save-study-plan', methods=['POST'])
@login_required
def direct_save_study_plan():
    """Simplified direct save that uses the main save_study_plan route"""
    return save_study_plan_api()  # Updated to use save_study_plan_api instead

# Add the following helper function to format study plan data for the template
def prepare_study_plan_data_for_template(topics, schedule):
    """Prepare study plan data as strings for template rendering"""
    topics_str = json.dumps(topics)
    schedule_str = json.dumps(schedule)
    
    # Also create human-readable versions for display
    topics_readable = "\n".join([t.get("name", "Unnamed Topic") for t in topics]) if topics else ""
    
    # More robust approach to handle different activity structures
    schedule_readable_items = []
    if schedule:
        for day in schedule:
            day_activities = day.get('activities', [])
            for activity in day_activities:
                # Check for key existence and provide defaults
                title = activity.get('title', 'Unnamed Activity')
                start_time = activity.get('start_time', 'N/A')
                end_time = activity.get('end_time', 'N/A')
                schedule_readable_items.append(f"{title} ({start_time} - {end_time})")
    
    schedule_readable = "\n".join(schedule_readable_items)
    
    return {
        'topics_str': topics_str,
        'schedule_str': schedule_str,
        'topics_readable': topics_readable,
        'schedule_readable': schedule_readable
    }

@study_plan.route('/delete-empty-plans')
@login_required
def delete_empty_plans():
    """Delete empty study plans to clean up the database"""
    from models import StudyPlan
    from sqlalchemy import or_

    deleted = StudyPlan.query.filter(
        StudyPlan.user_id == current_user.id,
        StudyPlan.plan_summary == '',
        StudyPlan.topics == '[]',
        StudyPlan.detailed_schedule == '[]'
    ).delete()
    db.session.commit()
    return f"✅ Deleted {deleted} empty study plans"

# Add the missing function that's imported in app1.py
def get_study_plan_data_for_dashboard(active_plan_id=None):
    """Function to get study plan data for dashboard with optional active plan"""
    from flask_login import current_user
    from flask import current_app
    
    today = datetime.now().date()
    
    try:
        # Debug output
        print(f"DEBUG: Current user ID: {current_user.id}")
        print(f"DEBUG: Looking for active plan ID: {active_plan_id}, type: {type(active_plan_id)}")
        
        # Use current_app's context if needed
        with current_app.app_context():
            try:
                # Get active plan if requested
                active_plan = None
                if active_plan_id:
                    print(f"DEBUG: Trying to fetch StudyPlan with ID {active_plan_id}")
                    active_plan = db.session.get(StudyPlan, active_plan_id)
                    print(f"DEBUG: Query result: {active_plan}")
                    
                    if active_plan and active_plan.user_id == current_user.id:
                        print(f"DEBUG: Found active plan: {active_plan.title}")
                        # Convert to dict for the template
                        active_plan = {
                            "id": active_plan.id,
                            "title": active_plan.title,
                            "topics": active_plan.topics_data,
                            "detailed_schedule": active_plan.schedule_data,
                            "plan_summary": active_plan.plan_summary,
                            "is_revision_only": active_plan.is_revision_only,
                            "exam_date": active_plan.exam_date.strftime('%Y-%m-%d') if active_plan.exam_date else None,
                            "prep_start_date": active_plan.prep_start_date.strftime('%Y-%m-%d') if active_plan.prep_start_date else None
                        }
                    else:
                        if active_plan:
                            print(f"DEBUG: Plan found but not owned by user. Plan user_id: {active_plan.user_id}, Current user: {current_user.id}")
                        else:
                            print(f"DEBUG: No StudyPlan found with ID {active_plan_id}")
                
                # Get ongoing plans (where prep_start_date is today)
                ongoing_plans = StudyPlan.query.filter(
                    StudyPlan.user_id == current_user.id,
                    StudyPlan.prep_start_date == today
                ).all()
                
                # Get upcoming plans (where exam date is today or in the future)
                upcoming_plans = StudyPlan.query.filter(
                    StudyPlan.user_id == current_user.id,
                    StudyPlan.exam_date >= today
                ).order_by(StudyPlan.exam_date).all()
                
                # Add any plans without exam dates to a separate list
                unscheduled_plans = StudyPlan.query.filter(
                    StudyPlan.user_id == current_user.id,
                    StudyPlan.exam_date == None
                ).order_by(StudyPlan.id.desc()).all()
                
                # Combine lists if unscheduled plans exist
                if unscheduled_plans:
                    print(f"DEBUG: Found {len(unscheduled_plans)} unscheduled plans")
                    # Add unscheduled plans to the end of upcoming plans
                    upcoming_plans = upcoming_plans + unscheduled_plans
                
                # Get past plans (where exam date is in the past, limited to 5)
                past_plans = StudyPlan.query.filter(
                    StudyPlan.user_id == current_user.id,
                    StudyPlan.exam_date < today
                ).order_by(StudyPlan.exam_date.desc()).limit(5).all()
                
                # Convert plans to a format suitable for displaying in calendar
                calendar_plans = []
                for plan in upcoming_plans:
                    # Add both exam date and prep start date events
                    if plan.exam_date:
                        calendar_plans.append({
                            'id': f"exam_{plan.id}",
                            'title': f"{plan.title} (Exam)",
                            'date': plan.exam_date.strftime('%Y-%m-%d'),
                            'url': f'/dashboard?active_plan_id={plan.id}',
                            'color': '#ff85b4'  # Pink for exam dates
                        })
                    
                    if plan.prep_start_date:
                        calendar_plans.append({
                            'id': f"prep_{plan.id}",
                            'title': f"{plan.title} (Start)",
                            'date': plan.prep_start_date.strftime('%Y-%m-%d'),
                            'url': f'/dashboard?active_plan_id={plan.id}',
                            'color': '#85c1ff'  # Blue for prep start dates
                        })
                
                # Debug output to trace the issue
                print(f"DEBUG: Found {len(upcoming_plans)} upcoming plans for dashboard")
                
                return {
                    'ongoing_plans': ongoing_plans,
                    'upcoming_plans': upcoming_plans,
                    'past_plans': past_plans,
                    'calendar_plans': json.dumps(calendar_plans),
                    'active_plan': active_plan,  # Add active plan to the context
                    'today': today,
                    'now': datetime.now()
                }
                
            except Exception as e:
                print(f"ERROR in get_study_plan_data_for_dashboard: {str(e)}")
                import traceback
                traceback.print_exc()
                
                # Return empty data as fallback
                return {
                    'ongoing_plans': [],
                    'upcoming_plans': [],
                    'past_plans': [],
                    'calendar_plans': "[]",
                    'today': today,
                    'now': datetime.now()
                }
    except Exception as outer_e:
        print(f"OUTER ERROR in get_study_plan_data_for_dashboard: {str(outer_e)}")
        import traceback
        traceback.print_exc()
        return {
            'ongoing_plans': [],
            'upcoming_plans': [],
            'past_plans': [],
            'calendar_plans': "[]",
            'today': today,
            'now': datetime.now()
        }

# Replace the existing save_study_plan route with this more robust version
@study_plan.route('/save-study-plan', methods=['POST'])
@login_required
def save_study_plan():
    """Handle form submission for saving study plan with improved validation"""
    from datetime import datetime
    
    start_time = datetime.now()
    print(f"🔄 Starting to save study plan at {start_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
    print(f"   - User: {current_user.id} ({current_user.username})")
    
    form = request.form

    # Early exit if empty
    if not form.get('topics') or not form.get('detailed_schedule'):
        print("❌ Study plan submission is empty. Aborting.")
        flash("❌ Study plan cannot be empty.", "danger")
        return redirect(url_for('study_plan.studyplan'))

    try:
        # Parse JSON data from form
        topics_data = json.loads(form.get('topics', '[]'))
        schedule_data = json.loads(form.get('detailed_schedule', '[]'))
        title = form.get('title', 'Study Plan')
        plan_summary = form.get('plan_summary', '')
        exam_date = form.get('exam_date') or None
        prep_start_date = form.get('prep_start_date') or None
        
        print(f"📋 Study plan submission details:")
        print(f"   - Title: {title}")
        print(f"   - Topics: {len(topics_data)}")
        print(f"   - Schedule days: {len(schedule_data)}")
        print(f"   - Exam date: {exam_date}")
        print(f"   - Prep start date: {prep_start_date}")
        
        # Create a content signature to check for duplicate plans more accurately 
        import hashlib
        content_signature = hashlib.md5(
            (title + str(len(topics_data)) + str(len(schedule_data)) + (exam_date or '') + (prep_start_date or '')).encode('utf-8')
        ).hexdigest()
        print(f"   - Content signature: {content_signature[:8]}...")
        
        # Check for potential duplicate submission (plan created within last 60 seconds)
        current_time = datetime.now()
        time_threshold = current_time - timedelta(seconds=60)
        
        # Look for recent plans with the same title
        recent_plans = db.session.query(StudyPlan).filter(
            StudyPlan.user_id == current_user.id,
            StudyPlan.title == title,
            StudyPlan.created_at >= time_threshold
        ).all()
        
        if recent_plans:
            print(f"⚠️ Potential duplicate submission detected. Found {len(recent_plans)} similar plans created in the last 60 seconds.")
            print(f"   - Most recent: {recent_plans[0].created_at.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"   - Current time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"   - Time diff: {(current_time - recent_plans[0].created_at).total_seconds():.2f} seconds")
            flash("This plan appears to be a duplicate submission. The previous plan has been saved.", "warning")
            return redirect('/dashboard')
        
        # Only accept a class the current user actually owns
        class_id = None
        submitted_class_id = (form.get('class_id') or '').strip()
        if submitted_class_id:
            try:
                owned = StudyClass.query.filter_by(
                    id=int(submitted_class_id), user_id=current_user.id
                ).first()
                class_id = owned.id if owned else None
            except (TypeError, ValueError):
                print(f"Ignoring unparseable class_id: {submitted_class_id!r}")

        # Create new study plan in database
        new_plan = StudyPlan(
            user_id=current_user.id,
            class_id=class_id,
            title=title,
            plan_summary=plan_summary,
            topics=form.get('topics', ''),
            detailed_schedule=form.get('detailed_schedule', ''),
            exam_date=exam_date,
            prep_start_date=prep_start_date,
            is_revision_only=False,
        )
        db.session.add(new_plan)
        db.session.commit()
        
        # Store study plan in database with generated content signature
        new_plan.metadata = json.dumps({
            "content_signature": content_signature,
            "submission_time": current_time.strftime('%Y-%m-%d %H:%M:%S.%f')
        })
        db.session.commit()
        print(f"✅ Study plan saved to database with ID: {new_plan.id}")
        
        # Store the study plan in Qdrant for RAG retrieval
        print(f"🔄 Starting Qdrant indexing for plan {new_plan.id}")
        rag_success = store_study_plan_in_qdrant(
            user_id=current_user.id,
            plan_id=new_plan.id,
            topics=topics_data,
            detailed_schedule=schedule_data
        )
        
        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds()
        
        if rag_success:
            print(f"✅ Study plan saved and indexed for search successfully! (Time: {processing_time:.2f}s)")
            flash("✅ Study plan saved and indexed for search successfully!", "success")
        else:
            print(f"⚠️ Study plan saved to database, but Qdrant indexing failed. (Time: {processing_time:.2f}s)")
            flash("✅ Study plan saved, but indexing for search failed.", "warning")
            
        # Use direct URL path instead of url_for to avoid errors
        return redirect('/dashboard')
    except Exception as e:
        print(f"❌ Error saving study plan: {e}")
        import traceback
        traceback.print_exc()
        flash("❌ Error saving plan.", "danger")
        return redirect(url_for('study_plan.studyplan'))

@study_plan.route('/studyplan/live/<int:plan_id>')
@login_required
def studyplan_live(plan_id):
    """Display an interactive version of a saved study plan for active use"""
    # Get the requested study plan - use query.filter().first_or_404() instead of get_or_404
    study_plan_entry = db.session.query(StudyPlan).filter(StudyPlan.id == plan_id).first_or_404()
    
    # Check if the plan belongs to the logged-in user
    if study_plan_entry.user_id != current_user.id:
        flash('You do not have permission to view this study plan')
        return redirect(url_for('study_plan.study_plan_list'))
    
    # Convert database format to template format
    study_plan_data = {
        "id": study_plan_entry.id,
        "title": study_plan_entry.title,
        "topics": study_plan_entry.topics_data,
        "detailed_schedule": study_plan_entry.schedule_data,
        "plan_summary": study_plan_entry.plan_summary,
        "is_revision_only": study_plan_entry.is_revision_only,
        "exam_date": study_plan_entry.exam_date.strftime('%Y-%m-%d') if study_plan_entry.exam_date else None,
        "prep_start_date": study_plan_entry.prep_start_date.strftime('%Y-%m-%d') if study_plan_entry.prep_start_date else None
    }
    
    # Format the data for the template
    template_data = prepare_study_plan_data_for_template(
        study_plan_data.get('topics', []),
        study_plan_data.get('detailed_schedule', [])
    )
    
    # Render the live study plan template
    return render_template('studyplan_live.html', 
                          study_plan=study_plan_data,
                          user=current_user,
                          **template_data)

@study_plan.route('/studyplan/delete/<int:plan_id>', methods=['POST', 'GET'])
@login_required
def delete_study_plan(plan_id):
    """Delete a study plan"""
    # Get the requested study plan
    study_plan_entry = db.session.query(StudyPlan).filter(StudyPlan.id == plan_id).first_or_404()
    
    # Check if the plan belongs to the logged-in user
    if study_plan_entry.user_id != current_user.id:
        flash('You do not have permission to delete this study plan')
        return redirect(url_for('study_plan.study_plan_list'))
    
    # Store the plan title for the success message
    plan_title = study_plan_entry.title
    
    # Delete the plan from database
    print("=" * 60)
    print(f"🗑️ DELETING STUDY PLAN: \"{plan_title}\" (ID: {plan_id})")
    print("-" * 60)
    
    db.session.delete(study_plan_entry)
    db.session.commit()
    print(f"✅ Deleted study plan from database")
    
    # Try to delete the plan from Qdrant too (if available)
    if qdrant_client is not None:
        try:
            collection_name = get_collection_name(current_user.id)
            print(f"🔄 Checking Qdrant collection: {collection_name}")
            
            # Check if collection exists
            collections = qdrant_client.get_collections().collections
            if any(collection.name == collection_name for collection in collections):
                print(f"🔍 Searching for plan documents in Qdrant...")
                
                # First, count how many documents we'll delete
                search_filter = qdrant_models.Filter(
                    must=[
                        qdrant_models.FieldCondition(
                            key="plan_id",
                            match=qdrant_models.MatchValue(value=str(plan_id))
                        )
                    ]
                )
                
                # Count points before deletion
                try:
                    count_result = qdrant_client.count(
                        collection_name=collection_name,
                        count_filter=search_filter
                    )
                    doc_count = count_result.count
                    print(f"📊 Found {doc_count} documents to delete from Qdrant")
                except Exception as count_error:
                    print(f"⚠️ Could not count documents: {count_error}")
                    doc_count = "unknown number of"
                
                # Delete points for this plan (filter by plan_id)
                delete_start = time.time()
                qdrant_client.delete(
                    collection_name=collection_name,
                    points_selector=qdrant_models.FilterSelector(
                        filter=search_filter
                    )
                )
                delete_time = time.time() - delete_start
                
                print(f"✅ Successfully deleted {doc_count} documents from Qdrant in {delete_time:.2f}s")
            else:
                print(f"ℹ️ No Qdrant collection exists for this user")
        except Exception as e:
            print(f"❌ Error deleting plan from Qdrant: {e}")
    else:
        print(f"ℹ️ Qdrant client not available, skipping RAG cleanup")
    
    print("=" * 60)
    flash(f'Study plan "{plan_title}" has been deleted successfully')
    return redirect(url_for('dashboard'))

# Debug route for RAG functionality
@study_plan.route('/studyplan/rag-debug')
@login_required
def rag_debug():
    """Debug route to check RAG functionality and Qdrant collections"""
    results = {
        'rag_enabled': qdrant_client is not None and embedding_model is not None,
        'embedding_model': str(embedding_model) if embedding_model else 'Not initialized',
        'collections': [],
        'user_collection': None,
        'user_collection_stats': None,
        'environment_vars': {
            'QDRANT_URL': os.getenv('QDRANT_URL', 'Not set'),
            'QDRANT_API_KEY': 'Set' if os.getenv('QDRANT_API_KEY') else 'Not set'
        }
    }
    
    # Check for Qdrant collections
    if qdrant_client:
        try:
            collections = qdrant_client.get_collections().collections
            results['collections'] = [c.name for c in collections]
            
            # Check user's specific collection
            user_collection_name = get_collection_name(current_user.id)
            results['user_collection'] = user_collection_name
            
            if any(c.name == user_collection_name for c in collections):
                # Get details about the user's collection
                collection_info = qdrant_client.get_collection(user_collection_name)
                results['user_collection_stats'] = {
                    'points_count': collection_info.points_count,
                    'vector_size': collection_info.config.params.vectors.size,
                    'vector_distance': str(collection_info.config.params.vectors.distance)
                }
        except Exception as e:
            results['error'] = str(e)
    
    return render_template('rag_debug.html', results=results)

# API endpoint to check study plans in RAG system
@study_plan.route('/studyplan/api/check-rag-storage/<int:plan_id>')
@login_required
def check_rag_storage(plan_id):
    """API to check if a study plan is stored in the RAG system"""
    if qdrant_client is None:
        return jsonify({
            'success': False,
            'error': 'RAG functionality not available. Qdrant client not initialized.'
        }), 503
        
    try:
        # Get the study plan
        plan = db.session.query(StudyPlan).filter(StudyPlan.id == plan_id).first()
        if not plan:
            return jsonify({
                'success': False,
                'error': f'Study plan with ID {plan_id} not found.'
            }), 404
            
        # Check if the plan belongs to the user
        if plan.user_id != current_user.id:
            return jsonify({
                'success': False,
                'error': 'You do not have permission to access this study plan.'
            }), 403
            
        # Try to find the plan in Qdrant
        collection_name = get_collection_name(current_user.id)
        try:
            # Check if the collection exists
            collections = qdrant_client.get_collections().collections
            if not any(c.name == collection_name for c in collections):
                return jsonify({
                    'success': False,
                    'storage_exists': False,
                    'error': f'Collection {collection_name} does not exist.'
                }), 200
                
            # Count points with plan_id filter
            search_filter = qdrant_models.Filter(
                must=[
                    qdrant_models.FieldCondition(
                        key="plan_id",
                        match=qdrant_models.MatchValue(value=str(plan_id))
                    )
                ]
            )
            
            # Count points
            count_result = qdrant_client.count(
                collection_name=collection_name,
                count_filter=search_filter
            )
            
            # Return the result
            return jsonify({
                'success': True,
                'storage_exists': count_result.count > 0,
                'points_count': count_result.count,
                'plan_id': plan_id,
                'collection_name': collection_name
            }), 200
                
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'Error checking RAG storage: {str(e)}'
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Error: {str(e)}'
        }), 500

# Add button to manually reindex a study plan
@study_plan.route('/studyplan/reindex-plan/<int:plan_id>', methods=['POST'])
@login_required
def reindex_plan(plan_id):
    """Manually reindex a study plan in Qdrant"""
    try:
        # Get the study plan
        plan = db.session.query(StudyPlan).filter(StudyPlan.id == plan_id).first_or_404()
        
        # Check if the plan belongs to the user
        if plan.user_id != current_user.id:
            flash('You do not have permission to reindex this study plan.', 'danger')
            return redirect(url_for('dashboard'))
            
        # Parse JSON data from plan
        topics_data = plan.topics_data
        schedule_data = plan.schedule_data
        
        # Store the study plan in Qdrant
        rag_success = store_study_plan_in_qdrant(
            user_id=current_user.id,
            plan_id=plan.id,
            topics=topics_data,
            detailed_schedule=schedule_data
        )
        
        if rag_success:
            flash("✅ Study plan successfully reindexed for search!", "success")
        else:
            flash("❌ Failed to reindex study plan.", "danger")
            
        # Redirect back to the debug page
        return redirect(url_for('study_plan.rag_debug'))
        
    except Exception as e:
        flash(f"❌ Error reindexing plan: {str(e)}", "danger")
        return redirect(url_for('study_plan.rag_debug'))
