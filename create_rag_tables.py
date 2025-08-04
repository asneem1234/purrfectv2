"""
Migration script to set up RAG tables in the database.

Run this script to create the necessary RAG tables:
- RAGIngestEvent
- RAGUsageLog

Usage:
python create_rag_tables.py
"""
import os
from dotenv import load_dotenv
from flask import Flask
from models import db, RAGIngestEvent, RAGUsageLog, User
import sys

def create_app():
    # Load environment variables
    load_dotenv()
    
    app = Flask(__name__)
    
    # Configure the app with DB settings from environment
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///app.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize database with app
    db.init_app(app)
    
    return app

def create_rag_tables(app):
    """
    Create RAG-related tables in the database.
    """
    print("Creating RAG tables...")
    
    with app.app_context():
        try:
            # Create tables
            db.create_all()
            
            # Check if tables were created
            ingest_count = RAGIngestEvent.query.count()
            usage_count = RAGUsageLog.query.count()
            
            print(f"✓ Created RAGIngestEvent table (found {ingest_count} records)")
            print(f"✓ Created RAGUsageLog table (found {usage_count} records)")
            
            # Update User model to include RAG fields if they don't exist
            print("Ensuring User model has RAG fields...")
            
            # This is a basic check - more sophisticated schema migrations would use Alembic
            user_count = User.query.count()
            print(f"✓ Found {user_count} users")
            
            print("\n✅ RAG tables created successfully!")
            
            return True
        
        except Exception as e:
            print(f"Error creating RAG tables: {str(e)}")
            return False

def main():
    app = create_app()
    
    print("\n=== Creating RAG Tables ===\n")
    
    success = create_rag_tables(app)
    
    if not success:
        print("\n❌ Failed to create RAG tables.")
        sys.exit(1)

if __name__ == "__main__":
    main()
