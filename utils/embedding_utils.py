"""
Embedding utilities for RAG implementation with Qdrant.
This module provides functions to split text into chunks and create embeddings.
"""
import os
import re
import time
import uuid
import traceback
from sentence_transformers import SentenceTransformer
import numpy as np
from flask import current_app
import qdrant_client
from qdrant_client.http.models import Distance, VectorParams, PointStruct

# Initialize the embedding model
def get_embedding_model():
    """
    Get or initialize the sentence transformer model for embeddings.
    Uses 'sentence-transformers/all-MiniLM-L6-v2' for efficient embeddings.
    With fallbacks for environment issues.
    """
    if hasattr(current_app, 'embedding_model'):
        return current_app.embedding_model
    
    # If no model exists in app context, try to create a new one
    try:
        # Try the primary model
        model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
        print("Successfully loaded sentence-transformers/all-MiniLM-L6-v2 model")
    except Exception as e:
        print(f"Error loading primary model: {e}")
        try:
            # Try a simpler model as fallback
            print("Trying fallback model...")
            model = SentenceTransformer('paraphrase-MiniLM-L3-v2')
            print("Successfully loaded fallback model: paraphrase-MiniLM-L3-v2")
        except Exception as fallback_error:
            print(f"Error loading fallback model: {fallback_error}")
            print("Using mock embedding model for testing")
            # Create a mock model that returns random vectors for testing
            class MockEmbeddingModel:
                def encode(self, text, **kwargs):
                    print(f"WARNING: Using mock embeddings for: {text[:30]}...")
                    if isinstance(text, list):
                        return [np.random.rand(384).astype(np.float32) for _ in text]
                    return np.random.rand(384).astype(np.float32)
            model = MockEmbeddingModel()
    
    # Store in app context if available
    if current_app:
        current_app.embedding_model = model
    
    return model

def split_text(text, chunk_size=500, overlap=50):
    """
    Split text into chunks with specified size and overlap.
    
    Args:
        text (str): The input text to be split
        chunk_size (int): Maximum characters per chunk
        overlap (int): Number of characters to overlap between chunks
        
    Returns:
        list: List of text chunks
    """
    if not text or len(text) < chunk_size:
        return [text] if text else []
    
    chunks = []
    start = 0
    
    while start < len(text):
        # Get chunk of specified size
        end = min(start + chunk_size, len(text))
        
        # If not at the end of text, try to find a good break point
        if end < len(text):
            # Try to find sentence end (., !, ?)
            sentence_end = max(
                text.rfind('.', start, end),
                text.rfind('!', start, end),
                text.rfind('?', start, end)
            )
            
            # If found a sentence end, use it
            if sentence_end > start and sentence_end > start + chunk_size // 2:
                end = sentence_end + 1
            else:
                # Otherwise look for paragraph or space
                paragraph_end = text.rfind('\n\n', start, end)
                if paragraph_end > start and paragraph_end > start + chunk_size // 2:
                    end = paragraph_end + 2
                else:
                    # Fall back to space
                    space_end = text.rfind(' ', start + chunk_size // 2, end)
                    if space_end > start:
                        end = space_end + 1
        
        # Get the chunk and add to list
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        
        # Move start with overlap
        start = end - overlap
        
        # Make sure we're making progress
        if start >= len(text) or (len(chunks) > 1 and chunks[-1] == chunks[-2]):
            break
    
    return chunks

def create_embedding(text):
    """
    Create embedding vector for text using sentence transformer.
    
    Args:
        text (str): Input text
        
    Returns:
        numpy.ndarray: Embedding vector
    """
    if not text or len(text.strip()) == 0:
        print("WARNING: Received empty text for embedding, returning zero vector")
        return np.zeros(384, dtype=np.float32)  # Return zero vector for empty text
    
    try:
        model = get_embedding_model()
        embedding = model.encode(text)
        
        # Verify embedding shape and content
        if not isinstance(embedding, np.ndarray):
            print(f"WARNING: Embedding is not a numpy array, converting from {type(embedding)}")
            embedding = np.array(embedding, dtype=np.float32)
        
        # Check for NaN or Infinity
        if np.isnan(embedding).any() or np.isinf(embedding).any():
            print("WARNING: Embedding contains NaN or Infinity values, replacing with random vector")
            embedding = np.random.rand(384).astype(np.float32)  # Use random vector instead
        
        # Log embedding details for debugging
        print(f"Generated embedding for text: '{text[:50]}...' - Shape: {embedding.shape}, Type: {type(embedding)}, First few values: {embedding[:5]}")
        
        return embedding
    except Exception as e:
        print(f"ERROR creating embedding: {str(e)}")
        # Return random vector as fallback for testing
        random_vector = np.random.rand(384).astype(np.float32)
        print(f"Returning random fallback vector with shape {random_vector.shape}")
        return random_vector

def create_embeddings(texts):
    """
    Create embeddings for multiple texts.
    
    Args:
        texts (list): List of text strings
        
    Returns:
        list: List of embedding vectors
    """
    model = get_embedding_model()
    return model.encode(texts)

# Qdrant client management
def get_qdrant_client():
    """
    Get or initialize the Qdrant client.
    
    Returns:
        qdrant_client.QdrantClient: Configured Qdrant client
    """
    # Use cached client if available and app context exists
    if current_app and hasattr(current_app, 'qdrant_client'):
        print("Using cached Qdrant client from application context")
        return current_app.qdrant_client
    
    # Get configuration from environment with better defaults and logging
    qdrant_url = os.environ.get('QDRANT_URL', 'localhost')
    qdrant_port = os.environ.get('QDRANT_PORT', '6333')
    qdrant_api_key = os.environ.get('QDRANT_API_KEY', None)
    
    # Better port handling
    try:
        qdrant_port = int(qdrant_port)
    except (ValueError, TypeError):
        print(f"WARNING: Invalid QDRANT_PORT value: '{qdrant_port}'. Using default 6333.")
        qdrant_port = 6333
    
    # Log connection details (without showing full API key)
    if qdrant_api_key:
        key_preview = qdrant_api_key[:4] + "..." if len(qdrant_api_key) > 4 else "****"
        print(f"Connecting to Qdrant at {qdrant_url}" + 
              (f":{qdrant_port}" if qdrant_url == 'localhost' else "") +
              f" with API key: {key_preview}")
    else:
        print(f"Connecting to Qdrant at {qdrant_url}" + 
              (f":{qdrant_port}" if qdrant_url == 'localhost' else "") + 
              " without API key")
    
    # Determine if using cloud or local with better error handling
    try:
        if qdrant_url != 'localhost':
            # Cloud setup
            client = qdrant_client.QdrantClient(
                url=qdrant_url,
                api_key=qdrant_api_key,
                timeout=60  # Increase timeout for better reliability
            )
        else:
            # Local setup
            client = qdrant_client.QdrantClient(
                host=qdrant_url,
                port=qdrant_port,
                timeout=30  # Timeout for local connections
            )
            
        # Test connection with quick health check
        try:
            # Use collection list as a health check instead of the deprecated health() method
            collections = client.get_collections()
            print(f"Qdrant connection successful! Found {len(collections.collections)} collections")
        except Exception as health_err:
            print(f"WARNING: Qdrant connection check failed: {str(health_err)}")
            print("Continuing with potentially unreliable connection...")
        
        # Store in app context if available
        if current_app:
            current_app.qdrant_client = client
        
        return client
    except Exception as e:
        print(f"ERROR creating Qdrant client: {str(e)}")
        import traceback
        traceback.print_exc()
        # Create a dummy client to prevent application crashes, but this will fail on operations
        print("Creating fallback client - operations will likely fail!")
        return qdrant_client.QdrantClient(host="localhost", port=6333)

def ensure_collection_exists(collection_name, vector_size=384):
    """
    Ensure that a collection exists in Qdrant, creating it if needed.
    
    Args:
        collection_name (str): Name of the collection
        vector_size (int): Size of embedding vectors
        
    Returns:
        bool: True if successful
    """
    client = get_qdrant_client()
    
    # Check if collection exists
    try:
        collections = client.get_collections().collections
        collection_names = [collection.name for collection in collections]
        
        print(f"Available collections in Qdrant: {collection_names}")
        
        if collection_name not in collection_names:
            # Create new collection
            print(f"Creating new collection '{collection_name}' with vector size {vector_size}")
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=Distance.COSINE
                )
            )
            print(f"Collection '{collection_name}' created successfully")
            
            # Verify creation by checking if the collection appears in the list
            updated_collections = client.get_collections().collections
            updated_names = [collection.name for collection in updated_collections]
            if collection_name in updated_names:
                print(f"Verified collection creation: {collection_name} is in the collection list")
            else:
                print(f"ERROR: Collection {collection_name} was not found after creation")
                return False
        else:
            # Collection exists, just confirm
            print(f"Collection '{collection_name}' already exists")
            
            try:
                # Try to get more info if available, but don't rely on format
                collection_info = client.get_collection(collection_name=collection_name)
                if hasattr(collection_info, 'vectors_count'):
                    print(f"Collection has {collection_info.vectors_count} vectors")
            except Exception as info_err:
                # If this fails due to API changes, just continue
                print(f"Note: Could not get detailed collection info: {str(info_err)}")
                pass
        
        return True
    except Exception as e:
        print(f"ERROR creating/accessing collection '{collection_name}': {str(e)}")
        import traceback
        traceback.print_exc()
        return False  # Return False instead of raising to prevent application failures

def upsert_points(collection_name, points, user_id=None):
    """
    Insert or update vectors in a collection.
    
    Args:
        collection_name (str): Name of the collection
        points (list): List of point dictionaries with id, vector, and payload
        user_id (int, optional): User ID for filtering
        
    Returns:
        bool: True if successful
    """
    client = get_qdrant_client()
    
    # Print basic client info
    print(f"Using Qdrant client to upsert points to {collection_name}")
    
    # Use user-specific collection if user_id is provided
    if user_id is not None and user_id != 0:
        collection_name = f"{collection_name}_{user_id}"
        print(f"Using user-specific collection: {collection_name}")
    
    # Get initial vector count for verification
    try:
        initial_info = client.get_collection(collection_name)
        initial_count = initial_info.vectors_count
        print(f"Initial vector count in '{collection_name}': {initial_count}")
    except Exception as e:
        print(f"Collection '{collection_name}' doesn't exist yet. Will create it.")
        initial_count = 0
    
    # Ensure collection exists
    ensure_collection_exists(collection_name)
    
    try:
        # Create PointStruct objects
        point_objects = []
        for i, point in enumerate(points):
            # Validate vector shape and content
            vector = point['vector']
            
            # Convert to numpy if not already
            if not isinstance(vector, np.ndarray):
                vector = np.array(vector, dtype=np.float32)
                point['vector'] = vector
            
            # Check for NaN or infinity values in vector
            if np.isnan(vector).any() or np.isinf(vector).any():
                print(f"WARNING: Vector {i} contains NaN or Inf values. Skipping.")
                continue
                
            # Check vector dimensions
            if vector.shape[0] != 384:  # Expected dimension for all-MiniLM-L6-v2
                print(f"WARNING: Vector {i} has wrong dimensions: {vector.shape}. Expected (384,). Skipping.")
                continue
            
            # Ensure point has a unique ID (use UUID if not provided or is None/empty)
            if 'id' not in point or not point['id']:
                import uuid
                point['id'] = str(uuid.uuid4())
                print(f"Generated new UUID for point {i}: {point['id']}")
            
            # Convert non-string IDs to strings
            if not isinstance(point['id'], str):
                point['id'] = str(point['id'])
            
            # Log point details for debugging
            point_id = point['id']
            payload_preview = {k: str(v)[:30] for k, v in point['payload'].items()}
            print(f"Creating point {i}: ID={point_id}, Vector shape={vector.shape}, Payload={payload_preview}")
            
            point_struct = PointStruct(
                id=point_id,
                vector=vector.tolist(),  # Convert numpy array to list for JSON serialization
                payload=point['payload']
            )
            point_objects.append(point_struct)
        
        print(f"Upserting {len(point_objects)} points to collection '{collection_name}'")
        
        if not point_objects:
            print("WARNING: No valid points to upsert")
            return False
        
        # Upload to Qdrant
        result = client.upsert(
            collection_name=collection_name,
            points=point_objects,
            wait=True  # Wait for operation to complete
        )
        
        # Verify the upload with count after a small delay to allow indexing
        import time
        time.sleep(1)  # Give Qdrant a moment to update counts
        collection_info = client.get_collection(collection_name)
        final_count = getattr(collection_info, 'vectors_count', None)
        
        if final_count is not None and initial_count is not None:
            print(f"After upsert: Collection '{collection_name}' has {final_count} vectors (added {final_count - initial_count})")
            
            if final_count <= initial_count:
                print("WARNING: Vector count did not increase after upsert!")
        else:
            print(f"After upsert: Collection '{collection_name}' updated successfully (vector counts not available)")
            # Let's verify a specific point was inserted
            if point_objects:
                try:
                    # Check if the first point exists
                    first_id = point_objects[0].id
                    check = client.retrieve(collection_name=collection_name, ids=[first_id])
                    if check:
                        print(f"Point with ID {first_id} was found in collection - likely overwritten existing point.")
                    else:
                        print(f"ERROR: Point with ID {first_id} was not found in collection after upsert!")
                except Exception as verify_err:
                    print(f"Error verifying point: {verify_err}")
        
        return True
    except Exception as e:
        print(f"ERROR during vector upsert to collection '{collection_name}': {str(e)}")
        import traceback
        traceback.print_exc()
        return False  # Return False instead of raising to prevent application failures

def search_vectors(collection_name, query_vector, limit=5, filter_payload=None, user_id=None):
    """
    Search for similar vectors in Qdrant.
    
    Args:
        collection_name (str): Name of the collection
        query_vector (list): Query vector
        limit (int): Number of results to return
        filter_payload (dict, optional): Filter conditions
        user_id (int, optional): User ID for filtering
        
    Returns:
        list: List of search results with payload and score
    """
    client = get_qdrant_client()
    
    # Use user-specific collection if user_id is provided
    if user_id is not None and user_id != 0:
        collection_name = f"{collection_name}_{user_id}"
        print(f"Searching in user-specific collection: {collection_name}")
    
    # Ensure vector is properly formatted
    if isinstance(query_vector, np.ndarray):
        query_vector = query_vector.tolist()
    
    try:
        # Search collection
        search_results = client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            limit=limit,
            query_filter=filter_payload
        )
        
        print(f"Found {len(search_results)} results in collection '{collection_name}'")
        return search_results
    except Exception as e:
        print(f"ERROR searching vectors in '{collection_name}': {str(e)}")
        return []

def diagnose_qdrant_setup():
    """
    Run diagnostics on Qdrant setup to help troubleshoot connection and configuration issues.
    
    Returns:
        dict: Diagnostic results
    """
    results = {
        "status": "unknown",
        "connection": False,
        "collections": [],
        "test_collection_created": False,
        "test_vector_inserted": False,
        "errors": []
    }
    
    try:
        # Test 1: Get client and check connection
        print("Testing Qdrant connection...")
        client = get_qdrant_client()
        
        try:
            # Use collection list as a health check instead of the deprecated health() method
            collections_info = client.get_collections()
            results["connection"] = True
            results["health"] = "ok"
            print(f"✅ Connection successful! Found {len(collections_info.collections)} collections")
        except Exception as e:
            results["errors"].append(f"Connection error: {str(e)}")
            print(f"❌ Connection failed: {str(e)}")
            return results
        
        # Test 2: List collections
        try:
            collections = client.get_collections().collections
            collection_names = [collection.name for collection in collections]
            results["collections"] = collection_names
            print(f"✅ Found {len(collection_names)} collections: {collection_names}")
        except Exception as e:
            results["errors"].append(f"Failed to list collections: {str(e)}")
            print(f"❌ Failed to list collections: {str(e)}")
        
        # Test 3: Create test collection
        test_collection = f"test_collection_{int(time.time())}"
        try:
            client.create_collection(
                collection_name=test_collection,
                vectors_config=VectorParams(
                    size=384,
                    distance=Distance.COSINE
                )
            )
            results["test_collection_created"] = True
            print(f"✅ Created test collection: {test_collection}")
        except Exception as e:
            results["errors"].append(f"Failed to create test collection: {str(e)}")
            print(f"❌ Failed to create test collection: {str(e)}")
            return results
        
        # Test 4: Insert a test vector
        try:
            test_vector = np.random.rand(384).astype(np.float32)
            test_id = str(uuid.uuid4())
            
            client.upsert(
                collection_name=test_collection,
                points=[
                    PointStruct(
                        id=test_id,
                        vector=test_vector.tolist(),
                        payload={"test": "payload"}
                    )
                ],
                wait=True
            )
            
            # Verify vector was inserted by retrieving it directly
            time.sleep(1)  # Give Qdrant time to update
            
            # Try to retrieve the vector directly
            try:
                retrieved = client.retrieve(collection_name=test_collection, ids=[test_id])
                if retrieved and len(retrieved) > 0:
                    results["test_vector_inserted"] = True
                    print(f"✅ Test vector inserted successfully - verified by retrieval")
                else:
                    results["errors"].append("Vector was not found after insertion")
                    print(f"❌ Vector was not found after insertion")
            except Exception as retrieve_err:
                results["errors"].append(f"Could not verify vector insertion: {str(retrieve_err)}")
                print(f"❌ Could not verify vector insertion: {str(retrieve_err)}")
            
            # Try to retrieve the vector
            retrieved = client.retrieve(collection_name=test_collection, ids=[test_id])
            if retrieved and len(retrieved) > 0:
                print(f"✅ Successfully retrieved test vector")
            else:
                results["errors"].append("Could not retrieve inserted vector")
                print(f"❌ Could not retrieve inserted vector")
            
        except Exception as e:
            results["errors"].append(f"Failed to insert test vector: {str(e)}")
            print(f"❌ Failed to insert test vector: {str(e)}")
        
        # Clean up test collection
        try:
            client.delete_collection(test_collection)
            print(f"✅ Cleaned up test collection")
        except Exception as e:
            print(f"⚠️ Failed to clean up test collection: {str(e)}")
        
        # Set final status
        if results["connection"] and results["test_collection_created"] and results["test_vector_inserted"]:
            results["status"] = "ok"
            print("🎉 All Qdrant tests passed successfully!")
        else:
            results["status"] = "issues_detected"
            print("⚠️ Some Qdrant tests failed - see errors for details")
            
    except Exception as e:
        results["status"] = "error"
        results["errors"].append(f"Diagnostic error: {str(e)}")
        print(f"❌ Diagnostic error: {str(e)}")
        import traceback
        traceback.print_exc()
    
    return results
