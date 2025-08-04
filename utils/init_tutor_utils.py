"""
Initialization script for Pawfessor Meowkins Tutor Agent utilities.
This handles setting up Qdrant collections and other required resources.
"""

import os
import sys
import argparse

# Ensure the parent directory is in the path for imports
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from utils.tutor_utils import (
    get_qdrant_client,
    ensure_collection_exists,
    DEFAULT_COLLECTION
)

def setup_qdrant_collections(url=None):
    """Setup Qdrant collections needed for the tutor agent.
    
    Args:
        url: Optional Qdrant server URL. If None, uses local in-memory storage.
    """
    print(f"Setting up Qdrant collections for Pawfessor Meowkins Tutor Agent...")
    
    client = get_qdrant_client(url)
    collection_name = DEFAULT_COLLECTION
    
    # Ensure the main collection exists
    success = ensure_collection_exists(client, collection_name)
    if success:
        print(f"Successfully set up collection '{collection_name}'")
    else:
        print(f"Failed to set up collection '{collection_name}'")
    
    return success

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize Pawfessor Meowkins Tutor Agent")
    parser.add_argument("--url", help="URL for Qdrant server (if not using local storage)")
    args = parser.parse_args()
    
    setup_qdrant_collections(args.url)
