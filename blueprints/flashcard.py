from flask import Blueprint, render_template, request, redirect, url_for, jsonify, current_app, session, flash
from flask_login import login_required, current_user
import os
import logging
from werkzeug.utils import secure_filename
import PyPDF2
import re
import json
import datetime
import time
import google.generativeai as genai
import uuid
import hashlib

# Lazy loading for heavy ML libraries (sentence-transformers requires torch)
_sentence_transformers = None
_SentenceTransformer = None

def _get_sentence_transformer():
    """Lazy load sentence-transformers module only when needed"""
    global _sentence_transformers, _SentenceTransformer
    if _sentence_transformers is None:
        try:
            from sentence_transformers import SentenceTransformer
            _sentence_transformers = True
            _SentenceTransformer = SentenceTransformer
            print("sentence-transformers module loaded successfully")
        except ImportError as e:
            print(f"Warning: sentence-transformers not available - embedding features disabled: {e}")
            _sentence_transformers = False
            _SentenceTransformer = None
    return _SentenceTransformer

from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
from qdrant_client.http.models import PointStruct, Distance

# Set up logging
logger = logging.getLogger(__name__)

# Create flashcard blueprint
flashcard_bp = Blueprint('flashcard', __name__)

# Initialize sentence transformer model for embeddings (lazy loaded)
embedding_model = None

def get_embedding_model():
    """Get or initialize the embedding model (lazy loaded)"""
    global embedding_model
    if embedding_model is None:
        SentenceTransformer = _get_sentence_transformer()
        if SentenceTransformer is None:
            logger.warning("sentence-transformers not available. Embedding features disabled.")
            return None
        try:
            embedding_model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
            logger.info("Sentence transformer model loaded successfully")
        except Exception as e:
            logger.error(f"Error loading sentence transformer model: {e}")
            return None
    return embedding_model

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
        logger.warning("QDRANT_URL or QDRANT_API_KEY not provided. Vector storage functionality will be disabled.")
        qdrant_client = None
except Exception as e:
    logger.error(f"Error initializing Qdrant client: {e}")
    qdrant_client = None

def get_gemini_model():
    """Get the Gemini generative model"""
    return genai.GenerativeModel('gemini-2.5-flash-lite')

# Qdrant Utility Functions
def get_collection_name(user_id):
    """Generate collection name for a specific user's flashcards"""
    if not user_id:
        print("⚠️ Warning: Empty user_id provided to get_collection_name")
        raise ValueError("user_id cannot be empty or None")
    return f"flashcards_{user_id}"

def create_embedding(text):
    """Create embedding for text using sentence-transformers (lazy loaded)"""
    model = get_embedding_model()
    if model is None:
        logger.warning("Embedding model not available. Cannot create embeddings.")
        return None
    
    try:
        embedding = model.encode(text)
        return embedding.tolist()
    except Exception as e:
        logger.error(f"Error creating embedding: {e}")
        return None

def create_collection(user_id, vector_size=384):
    """Create or recreate a Qdrant collection for flashcards"""
    if qdrant_client is None:
        logger.warning("Qdrant client not available. Cannot create collection.")
        return False
    
    collection_name = get_collection_name(user_id)
    
    try:
        # Check if collection exists and delete it if recreate is True
        collections = qdrant_client.get_collections().collections
        if any(collection.name == collection_name for collection in collections):
            print(f"Collection {collection_name} already exists.")
        else:
            # Create collection with vector config and payload indexes
            qdrant_client.create_collection(
                collection_name=collection_name,
                vectors_config=qdrant_models.VectorParams(
                    size=vector_size,
                    distance=Distance.COSINE
                ),
                optimizers_config=qdrant_models.OptimizersConfigDiff(
                    indexing_threshold=0  # Index immediately
                )
            )
            
            # Add payload indexes for efficient filtering
            for field in ["card_type", "topic", "difficulty", "source"]:
                qdrant_client.create_payload_index(
                    collection_name=collection_name,
                    field_name=field,
                    field_schema=qdrant_models.PayloadSchemaType.KEYWORD
                )
            
            # Add numeric index for difficulty
            qdrant_client.create_payload_index(
                collection_name=collection_name,
                field_name="difficulty",
                field_schema=qdrant_models.PayloadSchemaType.INTEGER
            )
            
            logger.info(f"Created collection: {collection_name} with payload indexes")
        
        return True
    except Exception as e:
        logger.error(f"Error creating collection: {e}")
        return False

def ensure_collection_exists(user_id):
    """Ensure a collection exists for the given user ID"""
    if qdrant_client is None:
        return False
        
    collection_name = get_collection_name(user_id)
    try:
        collections = qdrant_client.get_collections().collections
        if not any(collection.name == collection_name for collection in collections):
            return create_collection(user_id)
        return True
    except Exception as e:
        logger.error(f"Error checking collections: {e}")
        return False

def insert_flashcards(user_id, flashcards, metadata=None):
    """Insert flashcards into Qdrant with embeddings and metadata"""
    if qdrant_client is None or embedding_model is None:
        print("⚠️ Qdrant client or embedding model not available. Cannot insert flashcards.")
        return False
        
    if metadata is None:
        metadata = {}
        
    collection_name = get_collection_name(user_id)
    
    # Ensure collection exists
    if not ensure_collection_exists(user_id):
        print(f"❌ Failed to ensure collection exists: {collection_name}")
        return False
    
    try:
        card_count = 0
        card_type = metadata.get('card_type', 'unknown')
        topic = metadata.get('topic', 'Unknown Topic')
        difficulty = metadata.get('difficulty', 5)
        source = metadata.get('source', 'topic')
        
        print(f"🔄 Inserting {len(flashcards)} {card_type} flashcards about '{topic}' into Qdrant")
        
        # Track content hashes to avoid duplicates
        processed_content_hashes = set()
        
        # Batch points for more efficient insertion
        points = []
        
        for idx, flashcard in enumerate(flashcards):
            # Determine the primary content text for embedding based on card type
            if card_type == 'qna':
                question = flashcard.get('question', '')
                answer = flashcard.get('answer', '')
                content_text = f"Question: {question}\nAnswer: {answer}"
                card_front = question
                card_back = answer
            elif card_type == 'definition':
                term = flashcard.get('term', '')
                definition = flashcard.get('definition', '')
                content_text = f"Term: {term}\nDefinition: {definition}"
                card_front = term
                card_back = definition
            else:  # bullet
                concept = flashcard.get('concept', '')
                bullets = flashcard.get('bullets', [])
                bullets_text = "\n".join([f"• {bullet}" for bullet in bullets])
                content_text = f"Concept: {concept}\n{bullets_text}"
                card_front = concept
                card_back = bullets_text
            
            # Create a content hash for duplicate detection
            content_hash = hashlib.md5(content_text.encode('utf-8')).hexdigest()
            
            # Skip if we've already processed identical content in this batch
            if content_hash in processed_content_hashes:
                print(f"    ⏩ Skipping duplicate flashcard")
                continue
                
            processed_content_hashes.add(content_hash)
            
            # Create embedding for the content
            embedding_start = time.time()
            embedding = create_embedding(content_text)
            embedding_time = time.time() - embedding_start
            
            if embedding is None:
                print(f"    ❌ Failed to create embedding for flashcard {idx+1}")
                continue
                
            # Generate a deterministic ID based on content hash
            unique_key = f"{user_id}:{card_type}:{content_hash}"
            point_id = str(uuid.uuid5(uuid.NAMESPACE_OID, unique_key))
            
            # Prepare payload with all required fields
            payload = {
                "user_id": str(user_id),
                "card_type": card_type,
                "topic": topic,
                "difficulty": difficulty,
                "source": source,
                "content": content_text,
                "card_front": card_front,
                "card_back": card_back,
                "content_hash": content_hash,
                "timestamp": datetime.datetime.now().isoformat()
            }
            
            # Add raw flashcard data to payload
            payload["raw_data"] = flashcard
            
            # Create a point structure
            points.append(
                PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload=payload
                )
            )
            
            card_count += 1
            
            # Insert in batches of 100 or when reaching the end
            if len(points) >= 100 or idx == len(flashcards) - 1:
                if points:  # Only insert if there are points to insert
                    qdrant_client.upsert(
                        collection_name=collection_name,
                        points=points
                    )
                    print(f"    ✅ Inserted batch of {len(points)} flashcards")
                    points = []  # Reset points after insertion
        
        print(f"✅ Successfully inserted {card_count} flashcards into Qdrant collection: {collection_name}")
        return True
    except Exception as e:
        import traceback
        print(f"❌ Error inserting flashcards: {e}")
        traceback.print_exc()
        return False

def semantic_search(user_id, query, top_k=5, filters=None):
    """Search for semantically similar flashcards using embeddings"""
    if qdrant_client is None or embedding_model is None:
        print("⚠️ Qdrant client or embedding model not available. Cannot perform semantic search.")
        return []
    
    collection_name = get_collection_name(user_id)
    
    try:
        # Create embedding for query
        print(f"🔍 Creating vector embedding for query: \"{query}\"")
        query_embedding = create_embedding(query)
        if query_embedding is None:
            print("❌ Failed to create query embedding")
            return []
        
        # Convert filters to Qdrant filter format
        qdrant_filter = None
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
            
            qdrant_filter = qdrant_models.Filter(
                must=filter_conditions
            )
            print(f"🔍 Applied {len(filter_conditions)} search filters")
        
        # Always add user_id filter for security
        if qdrant_filter:
            # Add user_id to existing filter
            qdrant_filter.must.append(
                qdrant_models.FieldCondition(
                    key="user_id",
                    match=qdrant_models.MatchValue(value=str(user_id))
                )
            )
        else:
            # Create new filter with just user_id
            qdrant_filter = qdrant_models.Filter(
                must=[
                    qdrant_models.FieldCondition(
                        key="user_id",
                        match=qdrant_models.MatchValue(value=str(user_id))
                    )
                ]
            )
        
        # Perform search
        print(f"🔎 Executing semantic search on {collection_name}")
        search_start = time.time()
        search_results = qdrant_client.search(
            collection_name=collection_name,
            query_vector=query_embedding,
            query_filter=qdrant_filter,
            limit=top_k,
            with_payload=True
        )
        search_time = time.time() - search_start
        
        # Format results
        results = []
        for result in search_results:
            payload = result.payload
            results.append({
                "score": result.score,
                "card_type": payload.get("card_type", "unknown"),
                "card_front": payload.get("card_front", ""),
                "card_back": payload.get("card_back", ""),
                "topic": payload.get("topic", ""),
                "difficulty": payload.get("difficulty", 5),
                "raw_data": payload.get("raw_data", {})
            })
        
        print(f"✅ Semantic search completed in {search_time:.2f}s, found {len(results)} results")
        return results
    except Exception as e:
        import traceback
        print(f"❌ Error in semantic search: {e}")
        traceback.print_exc()
        return []

def hybrid_search(user_id, query, top_k=5, filters=None):
    """Perform hybrid search (vector + keyword) in Qdrant collection"""
    if qdrant_client is None or embedding_model is None:
        print("⚠️ Qdrant client or embedding model not available. Cannot perform hybrid search.")
        return []
    
    collection_name = get_collection_name(user_id)
    
    try:
        # Create embedding for query
        print(f"🧠 Creating vector embedding for hybrid search: \"{query}\"")
        query_embedding = create_embedding(query)
        if query_embedding is None:
            print("❌ Failed to create query embedding")
            return []
        
        # Convert filters to Qdrant filter format
        qdrant_filter = None
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
            
            qdrant_filter = qdrant_models.Filter(
                must=filter_conditions
            )
        
        # Always add user_id filter for security
        if qdrant_filter:
            # Add user_id to existing filter
            qdrant_filter.must.append(
                qdrant_models.FieldCondition(
                    key="user_id",
                    match=qdrant_models.MatchValue(value=str(user_id))
                )
            )
        else:
            # Create new filter with just user_id
            qdrant_filter = qdrant_models.Filter(
                must=[
                    qdrant_models.FieldCondition(
                        key="user_id",
                        match=qdrant_models.MatchValue(value=str(user_id))
                    )
                ]
            )
        
        # Perform hybrid search with both vector and text
        print(f"🔎 Executing hybrid search on {collection_name}")
        search_start = time.time()
        search_results = qdrant_client.search(
            collection_name=collection_name,
            query_vector=query_embedding,
            query_filter=qdrant_filter,
            limit=top_k,
            with_payload=True,
            search_params=qdrant_models.SearchParams(
                hnsw_ef=128,  # Increased for better recall
                exact=False
            )
        )
        search_time = time.time() - search_start
        
        # Format results
        results = []
        for result in search_results:
            payload = result.payload
            results.append({
                "score": result.score,
                "card_type": payload.get("card_type", "unknown"),
                "card_front": payload.get("card_front", ""),
                "card_back": payload.get("card_back", ""),
                "topic": payload.get("topic", ""),
                "difficulty": payload.get("difficulty", 5),
                "raw_data": payload.get("raw_data", {})
            })
        
        print(f"✅ Hybrid search completed in {search_time:.2f}s, found {len(results)} results")
        return results
    except Exception as e:
        import traceback
        print(f"❌ Error in hybrid search: {e}")
        traceback.print_exc()
        return []

# Function to generate flashcards with Gemini
def generate_flashcards_with_gemini(topic, card_type, card_count, pdf_text=''):
    model = get_gemini_model()
    
    try:
        # Determine the primary source of content
        source_type = "topic"
        if pdf_text and len(pdf_text.strip()) > 100:
            source_type = "pdf"
            print(f"Using PDF content ({len(pdf_text)} chars) as primary source")
        else:
            print(f"Using topic '{topic}' as primary source")
        
        # Prepare context from different sources
        context = ""
        if source_type == "pdf":
            # Limit PDF content to prevent token limit issues
            context += f"PDF Content: {pdf_text[:5000]}\n"
        
        # Create appropriate prompt based on flashcard type and source
        if card_type == 'qna':
            prompt = f"""
            Create {card_count} educational flashcards in question and answer format about: {topic}.
            
            {"Use ONLY information from the following content:" if source_type != "topic" else ""}
            {context}
            
            Format each flashcard as a JSON object with "question" and "answer" fields.
            Return the result as a JSON array containing all flashcards.
            Make sure the answers are informative, educational, and not too long (max 200 words per answer).
            
            IMPORTANT: Return your response as valid JSON only, with no additional text or explanations outside the JSON structure.
            
            Example format:
            ```json
            [
              {{
                "question": "What is photosynthesis?",
                "answer": "Photosynthesis is the process by which green plants and some other organisms use sunlight to synthesize foods with carbon dioxide and water."
              }}
            ]
            ```
            """
        elif card_type == 'definition':
            prompt = f"""
            Create {card_count} educational flashcards in term-definition format about: {topic}.
            
            {"Use ONLY information from the following content:" if source_type != "topic" else ""}
            {context}
            
            Format each flashcard as a JSON object with "term" and "definition" fields.
            Return the result as a JSON array containing all flashcards.
            Make sure the definitions are informative, clear, and not too long (max 200 words per definition).
            
            IMPORTANT: Return your response as valid JSON only, with no additional text or explanations outside the JSON structure.
            
            Example format:
            ```json
            [
              {{
                "term": "Photosynthesis",
                "definition": "The process by which green plants and some other organisms use sunlight to synthesize foods with carbon dioxide and water."
              }}
            ]
            ```
            """
        else:  # bullet points
            prompt = f"""
            Create {card_count} educational flashcards with concepts and bullet point explanations about: {topic}.
            
            {"Use ONLY information from the following content:" if source_type != "topic" else ""}
            {context}
            
            Format each flashcard as a JSON object with "concept" and "bullets" fields.
            The "bullets" field should be an array of strings, with each string being a key point about the concept.
            Return the result as a JSON array containing all flashcards.
            Include 3-5 bullet points for each concept.
            
            IMPORTANT: Return your response as valid JSON only, with no additional text or explanations outside the JSON structure.
            
            Example format:
            ```json
            [
              {{
                "concept": "Photosynthesis",
                "bullets": [
                  "Process where plants convert sunlight to energy",
                  "Requires chlorophyll, sunlight, water, and CO2",
                  "Produces oxygen as a byproduct",
                  "Takes place in the chloroplasts of plant cells"
                ]
              }}
            ]
            ```
            """
        
        print(f"Sending prompt to Gemini for topic: {topic}, card type: {card_type}")
        response = model.generate_content(prompt)
        response_text = response.text
        print(f"Received response from Gemini: ```json\n{response_text[:100]}...")
        
        # Extract JSON data from response
        json_str = response_text
        # Try to find JSON code block
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find raw JSON array
            json_match = re.search(r'(\[\s*\{.*\}\s*\])', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
        
        # Clean up the JSON string - common issues
        json_str = json_str.strip()
        json_str = re.sub(r',\s*}', '}', json_str)  # Remove trailing commas in objects
        json_str = re.sub(r',\s*]', ']', json_str)  # Remove trailing commas in arrays
        
        try:
            # Parse JSON
            flashcards = json.loads(json_str)
            print(f"Successfully parsed {len(flashcards)} flashcards")
            return flashcards
        except json.JSONDecodeError as json_error:
            print(f"JSON parse error: {json_error}")
            print(f"Problematic JSON string: {json_str}")
            # Fall back to regex-based extraction for individual cards
            if card_type == 'qna':
                questions = re.findall(r'"question"\s*:\s*"([^"]*)"', json_str)
                answers = re.findall(r'"answer"\s*:\s*"([^"]*)"', json_str)
                if questions and answers and len(questions) == len(answers):
                    return [{"question": q, "answer": a} for q, a in zip(questions, answers)]
            # If regex extraction fails too, return fallback cards
            raise
    except Exception as e:
        print(f"Error generating flashcards: {str(e)}")
        # Return sample flashcards if generation fails
        if card_type == 'qna':
            return [
                {"question": f"Sample question about {topic}?", 
                 "answer": "This is a sample answer. Flashcard generation failed. Please try again."}
            ]
        elif card_type == 'definition':
            return [
                {"term": f"{topic} term", 
                 "definition": "This is a sample definition. Flashcard generation failed. Please try again."}
            ]
        else:
            return [
                {"concept": f"{topic} concept", 
                 "bullets": ["Sample bullet point", "Flashcard generation failed", "Please try again"]}
            ]

# Function kept for backwards compatibility, but now uses Qdrant
def save_to_chroma(user_id, content_type, content_data, metadata=None):
    """Legacy function that now routes to Qdrant for storage"""
    try:
        if content_type != 'flashcards':
            print(f"Warning: Only 'flashcards' content type is supported for Qdrant storage. Got: {content_type}")
            return False
            
        if metadata is None:
            metadata = {}
        
        # Extract card_type from metadata or default to 'qna'
        card_type = metadata.get('card_type', 'qna')
        topic = metadata.get('topic', 'Unknown Topic')
        difficulty = metadata.get('difficulty', 5)
        source = metadata.get('source', 'topic')
        
        # Forward to new Qdrant storage function
        return insert_flashcards(
            user_id=user_id, 
            flashcards=content_data,
            metadata={
                'card_type': card_type,
                'topic': topic,
                'difficulty': difficulty,
                'source': source,
                'timestamp': datetime.datetime.now().isoformat()
            }
        )
        
    except Exception as e:
        import traceback
        print(f"Error saving to storage: {e}")
        traceback.print_exc()
        return False

# Route handlers
@flashcard_bp.route('/flashcardgenerator')
@login_required
def flashcardgenerator():
    """Display the flashcard generator page"""
    return render_template('flashcardgenerator.html', user=current_user)

@flashcard_bp.route('/generate-flashcards', methods=['POST'])
@login_required
def generate_flashcards():
    """Generate flashcards from provided content and store in Qdrant"""
    try:
        # Get form data
        source_type = request.form.get('sourceType', 'topic')
        topic = request.form.get('topic', '')
        card_count = int(request.form.get('cardCount', 10))
        card_type = request.form.get('cardType', 'qna')
        difficulty = int(request.form.get('difficulty', 5))
        
        print(f"🎲 Processing flashcard request - type: {card_type}, source: {source_type}, topic: '{topic}'")
        
        # Process PDF if uploaded
        pdf_text = ''
        if source_type == 'pdf' and 'pdfUpload' in request.files and request.files['pdfUpload'].filename:
            pdf_file = request.files['pdfUpload']
            filename = secure_filename(pdf_file.filename)
            pdf_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            pdf_file.save(pdf_path)
            
            # Extract text from PDF
            try:
                with open(pdf_path, 'rb') as f:
                    pdf_reader = PyPDF2.PdfReader(f)
                    for page_num in range(len(pdf_reader.pages)):
                        page_text = pdf_reader.pages[page_num].extract_text()
                        if page_text:
                            pdf_text += page_text + "\n\n"
                
                print(f"📄 Extracted {len(pdf_text)} characters from PDF")
                
                # Use filename as topic if not provided
                if not topic:
                    topic = "PDF Content: " + filename.replace('.pdf', '')
            except Exception as e:
                print(f"❌ Error extracting PDF text: {e}")
                flash(f"Error extracting text from PDF: {str(e)}")
                return redirect(url_for('flashcard.flashcardgenerator'))
        
        # Ensure we have content for the PDF source
        if source_type == 'pdf' and not pdf_text:
            flash('Could not extract text from the PDF. Please try another file.')
            return redirect(url_for('flashcard.flashcardgenerator'))
        
        # Ensure we have a topic if using topic source
        if source_type == 'topic' and not topic:
            flash('Please enter a topic for your flashcards.')
            return redirect(url_for('flashcard.flashcardgenerator'))
            
        # Log the topic we're going to use
        if topic:
            print(f"📝 Using topic: '{topic}'")
        else:
            print("⚠️ Warning: No topic provided")
        
        # Generate flashcards with Gemini
        try:
            print(f"🧠 Generating {card_count} {card_type} flashcards about {topic}")
            flashcards = generate_flashcards_with_gemini(
                topic, 
                card_type, 
                card_count, 
                pdf_text
            )
            print(f"✅ Successfully generated {len(flashcards)} flashcards")
            
            # Provide detailed logging of the first card for debugging
            if flashcards and len(flashcards) > 0:
                first_card = flashcards[0]
                print(f"🔍 First card sample: {str(first_card)[:200]}...")
                
                # Verify the expected structure for the card type
                if card_type == 'qna' and ('question' not in first_card or 'answer' not in first_card):
                    print("⚠️ WARNING: QnA card missing expected fields!")
                elif card_type == 'definition' and ('term' not in first_card or 'definition' not in first_card):
                    print("⚠️ WARNING: Definition card missing expected fields!")
                elif card_type == 'bullet' and ('concept' not in first_card or 'bullets' not in first_card):
                    print("⚠️ WARNING: Bullet card missing expected fields!")
        except Exception as e:
            print(f"❌ Gemini error: {str(e)}")
            # Basic fallback flashcards if Gemini fails
            if card_type == 'qna':
                flashcards = [{"question": f"What is {topic}?", "answer": "Unable to generate content. Please try again."}]
            elif card_type == 'definition':
                flashcards = [{"term": topic, "definition": "Unable to generate content. Please try again."}]
            else:  # bullet
                flashcards = [{"concept": topic, "bullets": ["Unable to generate content.", "Please try again."]}]
        
        # Store in session for retrieval
        session['flashcards'] = flashcards
        session['flashcard_topic'] = topic
        session['flashcard_type'] = card_type
        session['source_type'] = source_type
        
        # Store metadata for automatic Qdrant storage
        metadata = {
            "topic": topic,
            "card_type": card_type,
            "difficulty": difficulty,
            "source": source_type,
            "timestamp": datetime.datetime.now().isoformat()
        }
        
        # Immediately save to Qdrant if possible
        if qdrant_client is not None and embedding_model is not None:
            try:
                print(f"💾 Automatically saving flashcards to Qdrant...")
                storage_success = insert_flashcards(
                    user_id=current_user.id,
                    flashcards=flashcards,
                    metadata=metadata
                )
                
                if storage_success:
                    print(f"✅ Flashcards successfully saved to Qdrant")
                    flash(f"Generated {len(flashcards)} flashcards and saved to your library.", "success")
                else:
                    print(f"⚠️ Failed to save flashcards to Qdrant - will use session only")
                    flash(f"Generated {len(flashcards)} flashcards, but couldn't save to your library.", "warning")
            except Exception as storage_error:
                print(f"❌ Error during automatic Qdrant storage: {storage_error}")
                # Continue to flashcard view regardless of storage error
        else:
            print(f"⚠️ Qdrant storage unavailable - using session only")
        
        # Redirect to the flashcard view page
        return redirect(url_for('flashcard.flashcard_view'))
    except Exception as e:
        import traceback
        print(f"Error generating flashcards: {str(e)}")
        traceback.print_exc()
        flash(f'Error generating flashcards: {str(e)}')
        return redirect(url_for('flashcard.flashcardgenerator'))

@flashcard_bp.route('/flashcard')
@login_required
def flashcard_view():
    """Display generated flashcards"""
    # Check if we have flashcards in session
    if 'flashcards' not in session or not session['flashcards']:
        flash('No flashcards found. Please generate some first.')
        return redirect(url_for('flashcard_bp.flashcardgenerator'))
    
    # Get flashcard data from session
    flashcards = session['flashcards']
    topic = session['flashcard_topic']
    card_type = session['flashcard_type']
    
    # Ensure we have JSON string representation for the template
    # Force regenerate the JSON string to avoid stale data
    flashcards_json = json.dumps(flashcards)
    session['flashcards_json'] = flashcards_json
    
    print(f"Rendering flashcard template with {len(flashcards)} {card_type} cards for topic '{topic}'")
    print(f"First card preview: {str(flashcards[0])[:100]}...")
    
    return render_template('flashcard.html', 
                          flashcards=flashcards,
                          flashcards_json=flashcards_json,
                          topic=topic,
                          card_type=card_type,
                          user=current_user)

@flashcard_bp.route('/save-flashcards', methods=['POST'])
@login_required
def save_flashcards():
    """Save flashcards to Qdrant for the current user"""
    try:
        # Verify user is authenticated
        if not current_user.is_authenticated:
            return jsonify({"success": False, "error": "User not authenticated"}), 401
            
        data = request.json
        
        # Get flashcards data from request or session
        if data and 'flashcards' in data:
            flashcards = data['flashcards']
            topic = data.get('topic') or session.get('flashcard_topic', 'Unknown Topic')
            card_type = data.get('card_type') or session.get('flashcard_type', 'unknown')
            difficulty = data.get('difficulty', 5)
            source = data.get('source', 'topic')
        else:
            flashcards = session.get('flashcards')
            topic = session.get('flashcard_topic', 'Unknown Topic')
            card_type = session.get('flashcard_type', 'unknown')
            difficulty = 5
            source = session.get('source_type', 'topic')
        
        if not flashcards:
            return jsonify({"success": False, "error": "No flashcards found"}), 400
            
        print(f"💾 Saving {len(flashcards)} {card_type} flashcards on '{topic}' to Qdrant...")
        
        # Create metadata for storage
        metadata = {
            "topic": topic,
            "card_type": card_type,
            "card_count": len(flashcards),
            "difficulty": difficulty,
            "source": source,
            "timestamp": datetime.datetime.now().isoformat()
        }
        
        # Check if Qdrant is available
        if qdrant_client is None or embedding_model is None:
            print("⚠️ Qdrant or embedding model not available. Using session-only storage.")
            flash("Flashcards saved to session only. Vector database storage is unavailable.", "warning")
            return jsonify({
                "success": True,
                "message": f"Flashcards saved to session only (vector database unavailable)",
                "storage_type": "session"
            })
        
        # Save directly to Qdrant
        try:
            success = insert_flashcards(
                user_id=current_user.id,
                flashcards=flashcards,
                metadata=metadata
            )
        except Exception as e:
            import traceback
            print(f"❌ Error in insert_flashcards: {e}")
            traceback.print_exc()
            success = False
        
        if success:
            return jsonify({
                "success": True,
                "message": f"Successfully saved {len(flashcards)} flashcards on {topic} to vector database",
                "storage_type": "qdrant"
            })
        else:
            # Fall back to session-only if Qdrant fails
            print("⚠️ Failed to save to Qdrant. Using session-only storage as fallback.")
            flash("Flashcards saved to session only. Could not store in vector database.", "warning")
            return jsonify({
                "success": True,
                "message": f"Flashcards saved to session only (vector database error)",
                "storage_type": "session"
            })
            
    except Exception as e:
        import traceback
        print(f"Error saving flashcards: {str(e)}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@flashcard_bp.route('/reset-flashcards')
@login_required
def reset_flashcards():
    """Reset flashcard session data and redirect to generator page"""
    try:
        # Clear all flashcard-related session data
        session.pop('flashcards', None)
        session.pop('flashcard_topic', None)
        session.pop('flashcard_type', None)
        session.pop('flashcards_json', None)
        session.pop('source_type', None)
        
        # Add a message to confirm reset
        flash('Flashcard session has been reset')
        
        # Always redirect to the generator page after reset
        return redirect(url_for('flashcard.flashcardgenerator'))
    except Exception as e:
        print(f"Error in reset_flashcards: {str(e)}")
        flash(f"Error resetting flashcards: {str(e)}")
        return redirect(url_for('flashcard.flashcardgenerator'))

@flashcard_bp.route('/api/search-flashcards', methods=['POST'])
@login_required
def search_flashcards_api():
    """Search for flashcards semantically"""
    try:
        data = request.json
        if not data or 'query' not in data:
            return jsonify({
                'success': False,
                'error': 'Missing query parameter'
            }), 400
        
        query = data.get('query')
        search_type = data.get('search_type', 'semantic')  # 'semantic' or 'hybrid'
        top_k = int(data.get('top_k', 5))
        
        # Process filter parameters
        filters = {}
        if 'card_type' in data and data['card_type']:
            filters['card_type'] = data['card_type']
        if 'topic' in data and data['topic']:
            filters['topic'] = data['topic']
        if 'difficulty' in data and data['difficulty']:
            filters['difficulty'] = data['difficulty']
            
        print(f"🔎 Performing {search_type} search for: '{query}' with filters: {filters}")
        
        # Perform search
        if qdrant_client is None or embedding_model is None:
            return jsonify({
                'success': False,
                'error': 'Vector database not available'
            }), 503
        
        if search_type == 'hybrid':
            results = hybrid_search(
                user_id=current_user.id,
                query=query,
                top_k=top_k,
                filters=filters
            )
        else:  # Default to semantic
            results = semantic_search(
                user_id=current_user.id,
                query=query,
                top_k=top_k,
                filters=filters
            )
            
        return jsonify({
            'success': True,
            'results': results,
            'count': len(results)
        })
        
    except Exception as e:
        import traceback
        print(f"❌ Error searching flashcards: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@flashcard_bp.route('/search-flashcards')
@login_required
def search_flashcards_page():
    """Render flashcard search page"""
    # Get user's available topics and card types for filters
    topics = []
    card_types = []
    
    try:
        if qdrant_client is not None:
            collection_name = get_collection_name(current_user.id)
            
            # Check if collection exists
            collections = qdrant_client.get_collections().collections
            if any(collection.name == collection_name for collection in collections):
                # Get sample records to extract unique topics and card types
                results = qdrant_client.scroll(
                    collection_name=collection_name,
                    limit=100,  # Get a reasonable sample
                    with_payload=True
                )[0]
                
                # Extract unique topics and card types
                topic_set = set()
                card_type_set = set()
                
                for item in results:
                    payload = item.payload
                    if 'topic' in payload and payload['topic']:
                        topic_set.add(payload['topic'])
                    if 'card_type' in payload and payload['card_type']:
                        card_type_set.add(payload['card_type'])
                
                topics = sorted(list(topic_set))
                card_types = sorted(list(card_type_set))
    except Exception as e:
        print(f"❌ Error getting flashcard metadata: {str(e)}")
    
    return render_template(
        'flashcard_search.html',  # Create this template
        user=current_user,
        topics=topics,
        card_types=card_types
    )
