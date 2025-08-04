"""
Summarization scheduler for RAG implementation.
This script processes short-term memories and generates summaries for long-term storage.
Run this script as a scheduled task (cron job) to periodically summarize user interactions.
"""
import os
import sys
import datetime
from flask import Flask
from sqlalchemy import text

# Add parent directory to path for imports
sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

# Import app-related modules
from db import db, init_app
from models import User, RAGIngestEvent, RAGUsageLog
from utils.embedding_utils import (
    get_qdrant_client, create_embedding, ensure_collection_exists, 
    upsert_points, search_vectors
)
from utils.gemini_utils import get_gemini_model

# Configure Flask app for database access
def create_app():
    app = Flask(__name__)
    
    # Load configuration from environment variables
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
        'DATABASE_URL', 'sqlite:///../instance/app.db'
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize database
    init_app(app)
    
    return app

def get_users_with_short_term_memories():
    """Get users who have short-term memories to process"""
    # Find users with recent RAG ingest events
    cutoff_date = datetime.datetime.now() - datetime.timedelta(hours=48)
    
    users_with_data = db.session.execute(
        text("""
        SELECT DISTINCT user_id FROM rag_ingest_event
        WHERE created_at > :cutoff_date
        """),
        {"cutoff_date": cutoff_date}
    ).fetchall()
    
    return [user_id for (user_id,) in users_with_data]

def get_short_term_memories(user_id):
    """Get short-term memories for a user from Qdrant"""
    client = get_qdrant_client()
    collection_name = f"short_term_{user_id}"
    
    # Check if collection exists
    collections = client.get_collections().collections
    collection_names = [collection.name for collection in collections]
    
    if collection_name not in collection_names:
        return []
    
    # Get all points from the collection
    points = client.scroll(
        collection_name=collection_name,
        limit=1000  # Adjust based on expected volume
    )[0]
    
    return points

def generate_summary(memories):
    """Generate a summary of memories using LLM"""
    model = get_gemini_model()
    
    if not memories or len(memories) == 0:
        return None
    
    # Extract text from memory payloads
    memory_texts = []
    for point in memories:
        text = point.payload.get('text', '')
        source = point.payload.get('source', 'unknown')
        timestamp = point.payload.get('timestamp', '')
        memory_texts.append(f"[{source} at {timestamp}]: {text}")
    
    # Join memory texts, limiting to reasonable size
    memory_context = "\n\n".join(memory_texts[:50])  # Limit to 50 memories
    
    # Create summary prompt
    prompt = f"""
    Analyze the following user learning activities and interactions:
    
    {memory_context}
    
    Create a concise but comprehensive summary of what the student is learning, 
    their strengths, challenges, and patterns. Include key concepts they've engaged with.
    Keep the summary under 500 words and focus on educational insights that would be 
    helpful for future tutoring or personalized learning recommendations.
    """
    
    try:
        response = model.generate_content(prompt)
        summary = response.text
        return summary
    except Exception as e:
        print(f"Error generating summary: {e}")
        return None

def store_long_term_memory(user_id, summary):
    """Store a summary as long-term memory in Qdrant"""
    if not summary:
        return False
    
    # Create embedding for summary
    summary_vector = create_embedding(summary)
    
    # Prepare collection name
    collection_name = f"long_term_{user_id}"
    
    # Ensure collection exists
    ensure_collection_exists(collection_name)
    
    # Create point
    point = {
        'id': str(int(datetime.datetime.now().timestamp())),
        'vector': summary_vector.tolist(),
        'payload': {
            'text': summary,
            'type': 'summary',
            'created_at': datetime.datetime.now().isoformat(),
        }
    }
    
    # Store in Qdrant
    upsert_points(collection_name, [point])
    
    # Check collection size and enforce quota if needed
    enforce_long_term_quota(user_id)
    
    return True

def enforce_long_term_quota(user_id, max_summaries=4):
    """Enforce quota on long-term memories, keeping only most recent summaries"""
    client = get_qdrant_client()
    collection_name = f"long_term_{user_id}"
    
    # Get all points
    points = client.scroll(
        collection_name=collection_name,
        limit=100
    )[0]
    
    # If under quota, no action needed
    if len(points) <= max_summaries:
        return
    
    # Sort by timestamp (newest first)
    sorted_points = sorted(
        points, 
        key=lambda p: p.payload.get('created_at', ''),
        reverse=True
    )
    
    # Delete oldest points beyond quota
    points_to_delete = sorted_points[max_summaries:]
    ids_to_delete = [point.id for point in points_to_delete]
    
    if ids_to_delete:
        client.delete(
            collection_name=collection_name,
            points_selector=ids_to_delete
        )

def cleanup_short_term_memories(user_id):
    """Clean up short-term memories after summarization"""
    client = get_qdrant_client()
    collection_name = f"short_term_{user_id}"
    
    # Get older points (over 48 hours old)
    cutoff_time = (datetime.datetime.now() - datetime.timedelta(hours=48)).isoformat()
    
    # Delete older points by scrolling and filtering
    old_points = client.scroll(
        collection_name=collection_name,
        filter={
            "must_not": {
                "key": "timestamp",
                "range": {
                    "gt": cutoff_time
                }
            }
        },
        limit=1000
    )[0]
    
    # Delete old points
    if old_points:
        ids_to_delete = [point.id for point in old_points]
        client.delete(
            collection_name=collection_name,
            points_selector=ids_to_delete
        )
    
    # Also clean up database records
    RAGIngestEvent.query.filter(
        RAGIngestEvent.user_id == user_id,
        RAGIngestEvent.created_at < cutoff_time
    ).delete()
    db.session.commit()

def process_user_memories(user_id):
    """Process memories for a single user"""
    print(f"Processing memories for user {user_id}")
    
    # Get short-term memories
    memories = get_short_term_memories(user_id)
    
    if not memories or len(memories) == 0:
        print(f"No memories found for user {user_id}")
        return
    
    print(f"Found {len(memories)} memories for user {user_id}")
    
    # Generate summary
    summary = generate_summary(memories)
    
    if summary:
        print(f"Generated summary for user {user_id}")
        
        # Store as long-term memory
        store_long_term_memory(user_id, summary)
        
        # Clean up processed memories
        cleanup_short_term_memories(user_id)
    else:
        print(f"Failed to generate summary for user {user_id}")

def main():
    """Main function to run the summarizer"""
    print("Starting RAG summarization process")
    
    # Create app context for database operations
    app = create_app()
    with app.app_context():
        # Get users with short-term memories
        users = get_users_with_short_term_memories()
        print(f"Found {len(users)} users with short-term memories")
        
        # Process each user
        for user_id in users:
            try:
                process_user_memories(user_id)
            except Exception as e:
                print(f"Error processing user {user_id}: {e}")

if __name__ == "__main__":
    main()
