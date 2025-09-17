"""
Embedding utilities for RAG implementation with Qdrant.
This module provides simplified mock implementations to avoid heavy dependencies.
"""
import os
import re
import time
import uuid
import logging
import numpy as np
from flask import current_app

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("embedding_utils")

# Mock implementation of SentenceTransformer to avoid dependency on torch
class MockSentenceTransformer:
    """Mock implementation of SentenceTransformer."""
    
    def __init__(self, model_name="all-MiniLM-L6-v2"):
        self.model_name = model_name
        logger.info(f"Initialized mock SentenceTransformer with model: {model_name}")
    
    def encode(self, texts, convert_to_tensor=False, normalize_embeddings=True):
        """Return mock embeddings."""
        # Return a list of mock embeddings (vectors of zeros)
        if isinstance(texts, str):
            texts = [texts]
            
        # Generate consistent but random-looking embeddings based on text length
        embeddings = []
        for text in texts:
            # Use text length as a seed for reproducible "embeddings"
            seed = sum(ord(c) for c in text[:20])  # Use first 20 chars to create seed
            np.random.seed(seed)
            
            # Create a 384-dimensional vector (common size for sentence embeddings)
            embed = np.random.normal(0, 0.1, 384).astype(np.float32)
            
            # Normalize if requested
            if normalize_embeddings:
                embed = embed / np.linalg.norm(embed)
                
            embeddings.append(embed)
            
        if len(texts) == 1:
            return embeddings[0]
        return np.array(embeddings)

# Initialize the embedding model
def get_embedding_model():
    """
    Get or initialize the sentence transformer model for embeddings.
    Uses a mock implementation to avoid heavy dependencies.
    """
    logger.info("Using mock embedding model")
    return MockSentenceTransformer()

# Mock Qdrant client
class MockQdrantClient:
    """Mock implementation of QdrantClient."""
    
    def __init__(self, url=None, api_key=None):
        self.url = url
        self.collections = {}
        logger.info(f"Initialized mock Qdrant client with URL: {url}")
    
    def create_collection(self, collection_name, vectors_config=None):
        """Mock creating a collection."""
        self.collections[collection_name] = {"config": vectors_config, "points": []}
        logger.info(f"Created mock collection: {collection_name}")
        return True
    
    def get_collections(self):
        """Return list of collections."""
        return {"collections": [{"name": name} for name in self.collections.keys()]}
    
    def upsert(self, collection_name, points):
        """Mock inserting points."""
        if collection_name not in self.collections:
            self.create_collection(collection_name)
        # Simply store the points
        logger.info(f"Inserted {len(points)} points into mock collection: {collection_name}")
        return {"status": "ok"}
    
    def search(self, collection_name, query_vector, limit=5):
        """Mock search function."""
        logger.info(f"Searching mock collection: {collection_name}")
        # Return empty results
        return []

def get_qdrant_client():
    """Return a mock Qdrant client."""
    url = os.environ.get('QDRANT_URL', 'mock://qdrant')
    api_key = os.environ.get('QDRANT_API_KEY', '')
    logger.info("Using mock Qdrant client")
    return MockQdrantClient(url=url, api_key=api_key)

def ensure_collection_exists(collection_name, vector_size=384):
    """Mock function for ensuring a collection exists."""
    logger.info(f"Ensuring mock collection {collection_name} exists with vector size {vector_size}")
    client = get_qdrant_client()
    return True

def split_text(text, chunk_size=1000, overlap=100):
    """
    Split text into chunks with specified size and overlap.
    
    Args:
        text (str): The input text to be split
        chunk_size (int): Maximum characters per chunk
        overlap (int): Number of characters to overlap between chunks
        
    Returns:
        list: List of text chunks
    """
    # Simple chunking by character count with overlap
    if not text:
        return []
    
    chunks = []
    start = 0
    text_len = len(text)
    
    while start < text_len:
        end = min(start + chunk_size, text_len)
        if end < text_len and end - start < chunk_size:
            end = text_len
            
        # Find a good breaking point (end of sentence or paragraph)
        if end < text_len:
            # Try to find the end of a sentence
            sentence_end = text.rfind('. ', start, end)
            paragraph_end = text.rfind('\n', start, end)
            
            # Use the closest end point
            if sentence_end > start + chunk_size // 2:
                end = sentence_end + 2  # Include the period and space
            elif paragraph_end > start + chunk_size // 2:
                end = paragraph_end + 1  # Include the newline
        
        # Add the chunk
        chunks.append(text[start:end])
        
        # Move start position for next chunk, considering overlap
        start = end - overlap
        if start < 0 or start >= text_len:
            break
    
    return chunks