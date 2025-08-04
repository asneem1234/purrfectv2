"""
Simplified embedding utilities for RAG implementation with Qdrant.
This module provides functions to work with Qdrant without requiring ML libraries.
This is useful for environments where you can't install all the ML dependencies.
"""
import os
import json
import uuid
import datetime
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def get_qdrant_url():
    """Get the Qdrant URL from environment variables"""
    qdrant_url = os.environ.get('QDRANT_URL', 'http://localhost:6333')
    
    # If URL doesn't include http/https, add it
    if not qdrant_url.startswith('http'):
        qdrant_url = 'http://' + qdrant_url
        
    # Make sure URL doesn't end with a slash
    return qdrant_url.rstrip('/')

def get_auth_headers():
    """Get authentication headers for Qdrant API requests"""
    api_key = os.environ.get('QDRANT_API_KEY', None)
    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['api-key'] = api_key
    return headers

def ensure_collection_exists(collection_name, vector_size=384):
    """
    Ensure that a collection exists in Qdrant, creating it if needed.
    
    Args:
        collection_name (str): Name of the collection
        vector_size (int): Size of embedding vectors
        
    Returns:
        bool: True if successful
    """
    qdrant_url = get_qdrant_url()
    headers = get_auth_headers()
    
    # Check if collection exists
    collection_url = f"{qdrant_url}/collections/{collection_name}"
    try:
        response = requests.get(collection_url, headers=headers)
        if response.status_code == 200:
            return True
    except Exception:
        pass
    
    # Collection doesn't exist, create it
    config = {
        "vectors": {
            "size": vector_size,
            "distance": "Cosine"
        }
    }
    
    try:
        response = requests.put(collection_url, headers=headers, json=config)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Error creating collection: {str(e)}")
        return False

def add_text_to_qdrant(text, payload, collection_name, vector, point_id=None):
    """
    Add text with its vector to Qdrant
    
    Args:
        text (str): The text content
        payload (dict): Additional metadata about the text
        collection_name (str): Name of the collection
        vector (list): The embedding vector
        point_id (str, optional): Specific ID for the point
        
    Returns:
        str: ID of the inserted point or None if failed
    """
    qdrant_url = get_qdrant_url()
    headers = get_auth_headers()
    
    # Ensure collection exists
    if not ensure_collection_exists(collection_name):
        print(f"Failed to ensure collection exists: {collection_name}")
        return None
    
    # Generate ID if not provided
    if point_id is None:
        point_id = str(uuid.uuid4())
    
    # Merge text into payload
    full_payload = {
        "text": text,
        "created_at": datetime.datetime.now().isoformat(),
        **payload
    }
    
    # Create the point
    point = {
        "id": point_id,
        "vector": vector,
        "payload": full_payload
    }
    
    # Upload to Qdrant
    url = f"{qdrant_url}/collections/{collection_name}/points"
    try:
        response = requests.put(
            url, 
            headers=headers, 
            json={
                "points": [point]
            }
        )
        response.raise_for_status()
        return point_id
    except Exception as e:
        print(f"Error adding text to Qdrant: {str(e)}")
        return None

def search_qdrant(vector, collection_name, filter_criteria=None, limit=5):
    """
    Search for similar vectors in Qdrant
    
    Args:
        vector (list): Query vector
        collection_name (str): Name of the collection
        filter_criteria (dict, optional): Filter criteria
        limit (int): Maximum number of results
        
    Returns:
        list: List of search results or None if failed
    """
    qdrant_url = get_qdrant_url()
    headers = get_auth_headers()
    
    # Prepare search request
    search_data = {
        "vector": vector,
        "limit": limit
    }
    
    # Add filter if provided
    if filter_criteria:
        search_data["filter"] = filter_criteria
    
    # Send search request
    url = f"{qdrant_url}/collections/{collection_name}/points/search"
    try:
        response = requests.post(url, headers=headers, json=search_data)
        response.raise_for_status()
        return response.json().get('result', [])
    except Exception as e:
        print(f"Error searching Qdrant: {str(e)}")
        return None

def delete_point(point_id, collection_name):
    """
    Delete a point from Qdrant
    
    Args:
        point_id (str): ID of the point to delete
        collection_name (str): Name of the collection
        
    Returns:
        bool: True if successful
    """
    qdrant_url = get_qdrant_url()
    headers = get_auth_headers()
    
    url = f"{qdrant_url}/collections/{collection_name}/points/delete"
    try:
        response = requests.post(
            url, 
            headers=headers, 
            json={
                "points": [point_id]
            }
        )
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Error deleting point: {str(e)}")
        return False

def get_collection_info(collection_name):
    """
    Get information about a collection
    
    Args:
        collection_name (str): Name of the collection
        
    Returns:
        dict: Collection information or None if failed
    """
    qdrant_url = get_qdrant_url()
    headers = get_auth_headers()
    
    url = f"{qdrant_url}/collections/{collection_name}"
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error getting collection info: {str(e)}")
        return None
