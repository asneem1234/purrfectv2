"""
Routes for RAG functionality in the Purrfect application.
"""
import json
import datetime
from flask import Blueprint, request, jsonify, current_app, g
from flask_login import login_required, current_user
from models import RAGIngestEvent, RAGUsageLog, User, db
# Import CSRF protection tools
from flask_wtf.csrf import CSRFProtect
from utils.embedding_utils import (
    split_text, create_embedding, get_qdrant_client, 
    ensure_collection_exists, upsert_points, search_vectors
)
from utils.gemini_utils import get_gemini_model

# Create blueprint
purrrag_bp = Blueprint('purrrag', __name__)

# Create a decorator to disable CSRF for specific routes
def csrf_exempt(view_function):
    """Decorator to exempt a route from CSRF protection"""
    def decorated_function(*args, **kwargs):
        # Set a flag in g to indicate this request should skip CSRF
        g._csrf_exempt = True
        return view_function(*args, **kwargs)
    
    # Preserve the endpoint name to avoid conflicts
    decorated_function.__name__ = view_function.__name__
    # Copy other attributes to preserve Flask's introspection
    decorated_function.__module__ = view_function.__module__
    decorated_function.__doc__ = view_function.__doc__
    if hasattr(view_function, '__annotations__'):
        decorated_function.__annotations__ = view_function.__annotations__
    
    return decorated_function

@purrrag_bp.route('/ingest', methods=['POST'])
@csrf_exempt
@login_required
def ingest_text():
    """
    Ingest text into the RAG system.
    Expects JSON with:
    - text: the text to ingest
    - source: where the text came from (chat, notes, study_plan)
    - content_id: optional ID of the source content
    """
    try:
        data = request.get_json()
        
        if not data or 'text' not in data or 'source' not in data:
            return jsonify({'error': 'Missing required fields'}), 400
        
        text = data['text']
        source = data['source']
        content_id = data.get('content_id', '')
        
        # Check if RAG is enabled for user
        if not current_user.rag_enabled:
            return jsonify({'error': 'RAG is not enabled for this user'}), 403
        
        # Split text into chunks
        chunks = split_text(text)
        
        if not chunks:
            return jsonify({'status': 'No content to ingest'}), 200
        
        # Create embeddings for chunks
        points = []
        for i, chunk in enumerate(chunks):
            # Create embedding
            embedding = create_embedding(chunk)
            
            # Create point
            point_id = f"{current_user.id}_{source}_{content_id}_{int(datetime.datetime.now().timestamp())}_{i}"
            point = {
                'id': point_id,
                'vector': embedding.tolist(),
                'payload': {
                    'text': chunk,
                    'source': source,
                    'content_id': content_id,
                    'user_id': current_user.id,
                    'timestamp': datetime.datetime.now().isoformat(),
                    'chunk_index': i,
                    'total_chunks': len(chunks)
                }
            }
            points.append(point)
        
        # Store in Qdrant
        collection_name = f"short_term_{current_user.id}"
        ensure_collection_exists(collection_name)
        upsert_points(collection_name, points)
        
        # Log ingest event
        ingest_event = RAGIngestEvent(
            user_id=current_user.id,
            source=source,
            content_id=content_id,
            chunk_count=len(chunks)
        )
        db.session.add(ingest_event)
        
        # Log usage
        usage_log = RAGUsageLog(
            user_id=current_user.id,
            query_type='ingest',
            tokens_used=sum(len(chunk.split()) for chunk in chunks)
        )
        db.session.add(usage_log)
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'chunks_processed': len(chunks),
            'collection': collection_name
        })
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error ingesting text: {str(e)}")
        return jsonify({'error': str(e)}), 500

@purrrag_bp.route('/query', methods=['POST'])
@csrf_exempt
@login_required
def query_rag():
    """
    Query the RAG system.
    Expects JSON with:
    - query: the question or query
    - context: optional additional context
    """
    try:
        data = request.get_json()
        
        if not data or 'query' not in data:
            return jsonify({'error': 'Missing query'}), 400
        
        query = data['query']
        context = data.get('context', '')
        
        # Check if RAG is enabled for user
        if not current_user.rag_enabled:
            return jsonify({'error': 'RAG is not enabled for this user'}), 403
        
        # Create embedding for query
        query_embedding = create_embedding(query)
        
        # Collections to search
        collections = [
            f"short_term_{current_user.id}",  # User's short-term memory
            f"long_term_{current_user.id}",   # User's long-term memory
            "global_materials"                # Global reference materials
        ]
        
        # Search each collection
        all_results = []
        for collection in collections:
            try:
                # Check if collection exists
                client = get_qdrant_client()
                all_collections = client.get_collections().collections
                collection_names = [c.name for c in all_collections]
                
                if collection not in collection_names:
                    continue
                
                # Search collection
                results = search_vectors(
                    collection_name=collection,
                    query_vector=query_embedding.tolist(),
                    limit=3
                )
                
                # Add to combined results
                all_results.extend(results)
            
            except Exception as e:
                current_app.logger.error(f"Error searching collection {collection}: {str(e)}")
        
        # Sort by score
        all_results.sort(key=lambda x: x.score, reverse=True)
        
        # Take top results
        top_results = all_results[:5]
        
        # Extract text from results
        context_texts = [result.payload['text'] for result in top_results]
        
        # Create combined context
        rag_context = "\n\n".join(context_texts)
        
        # Generate answer using LLM
        model = get_gemini_model()
        
        # Create prompt with context
        prompt = f"""
        You are a helpful AI tutor. Use the following context to answer the user's question.
        If the context doesn't contain relevant information, use your general knowledge but make it clear.
        
        Context:
        {rag_context}
        
        Additional context:
        {context}
        
        User question: {query}
        
        First, identify the key concepts in the question. Then analyze the relevant parts of the context.
        Provide a detailed but concise answer using information from the context where applicable.
        Explain any complex concepts in a way that helps with learning.
        """
        
        # Generate answer
        response = model.generate_content(prompt)
        answer = response.text
        
        # Log usage
        usage_log = RAGUsageLog(
            user_id=current_user.id,
            query_type='query',
            tokens_used=len(query.split()) + sum(len(text.split()) for text in context_texts)
        )
        db.session.add(usage_log)
        db.session.commit()
        
        return jsonify({
            'answer': answer,
            'sources': [
                {
                    'text': result.payload['text'][:100] + "...",
                    'source': result.payload.get('source', 'unknown'),
                    'score': round(result.score, 3)
                }
                for result in top_results
            ]
        })
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error querying RAG: {str(e)}")
        return jsonify({'error': str(e)}), 500

@purrrag_bp.route('/progress', methods=['GET'])
@csrf_exempt
@login_required
def get_rag_progress():
    """
    Get RAG usage statistics and progress for a user.
    """
    try:
        # Get ingest events
        ingest_events = RAGIngestEvent.query.filter_by(
            user_id=current_user.id
        ).order_by(RAGIngestEvent.created_at.desc()).limit(50).all()
        
        # Get usage logs
        usage_logs = RAGUsageLog.query.filter_by(
            user_id=current_user.id
        ).order_by(RAGUsageLog.created_at.desc()).limit(50).all()
        
        # Calculate statistics
        ingest_by_source = {}
        for event in ingest_events:
            if event.source not in ingest_by_source:
                ingest_by_source[event.source] = 0
            ingest_by_source[event.source] += event.chunk_count
        
        usage_by_type = {}
        for log in usage_logs:
            if log.query_type not in usage_by_type:
                usage_by_type[log.query_type] = 0
            usage_by_type[log.query_type] += log.tokens_used
        
        # Get Qdrant collection stats
        client = get_qdrant_client()
        short_term_count = 0
        long_term_count = 0
        
        try:
            collections = client.get_collections().collections
            collection_names = [c.name for c in collections]
            
            short_term_name = f"short_term_{current_user.id}"
            if short_term_name in collection_names:
                short_term_count = client.get_collection(short_term_name).vectors_count
            
            long_term_name = f"long_term_{current_user.id}"
            if long_term_name in collection_names:
                long_term_count = client.get_collection(long_term_name).vectors_count
        except Exception as e:
            current_app.logger.error(f"Error getting collection stats: {str(e)}")
        
        return jsonify({
            'rag_enabled': current_user.rag_enabled,
            'short_term': {
                'count': short_term_count,
                'quota': current_user.rag_short_term_quota
            },
            'long_term': {
                'count': long_term_count,
                'quota': current_user.rag_long_term_quota
            },
            'ingest_by_source': ingest_by_source,
            'usage_by_type': usage_by_type,
            'recent_events': [
                {
                    'id': event.id,
                    'source': event.source,
                    'content_id': event.content_id,
                    'chunk_count': event.chunk_count,
                    'created_at': event.created_at.isoformat()
                }
                for event in ingest_events[:10]  # Limit to most recent 10
            ]
        })
    
    except Exception as e:
        current_app.logger.error(f"Error getting RAG progress: {str(e)}")
        return jsonify({'error': str(e)}), 500
