"""
AI functionality placeholder for core deployment.
This module provides mock implementations of AI functions to allow 
the application to run without the heavy ML dependencies.
"""

class MockEmbeddingModel:
    """Mock implementation of the embedding model."""
    
    def __init__(self):
        self.name = "Mock Embedding Model"
    
    def encode(self, texts, *args, **kwargs):
        """Return mock embeddings."""
        # Return a list of mock embeddings (vectors of zeros)
        if isinstance(texts, str):
            texts = [texts]
        return [[0.0] * 384 for _ in texts]  # 384-dimensional vector of zeros

def get_embedding_model():
    """Return a mock embedding model."""
    return MockEmbeddingModel()

def get_qdrant_client():
    """Return a mock Qdrant client."""
    return None

def ensure_collection_exists(collection_name, vector_size=384):
    """Mock function for ensuring a collection exists."""
    print(f"Mock: Ensuring collection {collection_name} exists with vector size {vector_size}")
    return True
