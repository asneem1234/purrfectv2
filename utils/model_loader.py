"""
Utility module for lazy-loading of ML models.
This helps reduce memory usage during application startup
and allows models to be loaded only when needed.
"""
import os
import logging
from functools import lru_cache

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='purr_rag.log'
)
logger = logging.getLogger('model_loader')

# Model instances
_embedding_model = None
_cross_encoder = None

@lru_cache(maxsize=2)
def get_embedding_model():
    """
    Lazily loads the embedding model only when needed.
    Uses lru_cache to avoid reloading after first use.
    """
    global _embedding_model
    
    if _embedding_model is None:
        try:
            # Import here to avoid loading all dependencies at startup
            from sentence_transformers import SentenceTransformer
            
            # Use a smaller model for Render deployment
            logger.info("Loading embedding model...")
            _embedding_model = SentenceTransformer('sentence-transformers/paraphrase-MiniLM-L3-v2')
            logger.info("Embedding model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load embedding model: {str(e)}")
            # Return a simple mock if model fails to load
            _embedding_model = MockEmbeddingModel()
    
    return _embedding_model

@lru_cache(maxsize=2)
def get_cross_encoder():
    """
    Lazily loads the cross-encoder model only when needed.
    Uses lru_cache to avoid reloading after first use.
    """
    global _cross_encoder
    
    if _cross_encoder is None:
        try:
            # Import here to avoid loading all dependencies at startup
            from sentence_transformers import CrossEncoder
            
            logger.info("Loading cross-encoder model...")
            _cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-2-v2')
            logger.info("Cross-encoder model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load cross-encoder model: {str(e)}")
            # Return a simple mock if model fails to load
            _cross_encoder = MockCrossEncoder()
    
    return _cross_encoder

# Mock implementations as fallbacks
class MockEmbeddingModel:
    """Mock embedding model for fallback"""
    def encode(self, texts, **kwargs):
        """Return random embeddings of the correct size"""
        import numpy as np
        if isinstance(texts, str):
            return np.random.rand(384)  # Smaller embedding size
        else:
            return np.random.rand(len(texts), 384)

class MockCrossEncoder:
    """Mock cross-encoder for fallback"""
    def predict(self, pairs, **kwargs):
        """Return random relevance scores"""
        import numpy as np
        if isinstance(pairs[0], str):
            return np.random.rand()
        else:
            return np.random.rand(len(pairs))
