"""
Database migration script to add RAG-related fields to existing database.
This script adds the necessary tables and fields for Qdrant-based RAG functionality.

Usage:
    python migrate_rag.py

This will:
1. Add RAG-related fields to the User model
2. Create the RAGIngestEvent and RAGUsageLog tables
3. Initialize default values for existing users
"""

import os
import sys
import datetime
from sqlalchemy import text

# Add parent directory to path for imports
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

# Import Flask and configure app
from flask import Flask
from db import db, init_app
from models import User, RAGIngestEvent, RAGUsageLog

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

def run_migration():
    """Execute the RAG database migration"""
    print("Starting RAG database migration...")
    
    # Check if tables exist
    try:
        # Check if RAGIngestEvent table exists
        db.session.execute(text("SELECT 1 FROM rag_ingest_event LIMIT 1"))
        print("RAGIngestEvent table already exists")
        ingest_table_exists = True
    except Exception:
        print("RAGIngestEvent table does not exist, will create")
        ingest_table_exists = False
    
    try:
        # Check if RAGUsageLog table exists
        db.session.execute(text("SELECT 1 FROM rag_usage_log LIMIT 1"))
        print("RAGUsageLog table already exists")
        usage_table_exists = True
    except Exception:
        print("RAGUsageLog table does not exist, will create")
        usage_table_exists = False
    
    # Check if User table has RAG fields
    try:
        db.session.execute(text("SELECT rag_enabled FROM app_user LIMIT 1"))
        print("User table already has RAG fields")
        user_fields_exist = True
    except Exception:
        print("User table does not have RAG fields, will add them")
        user_fields_exist = False
    
    # Create missing tables
    if not ingest_table_exists or not usage_table_exists:
        print("Creating RAG tables...")
        try:
            db.create_all()
            print("Tables created successfully")
        except Exception as e:
            print(f"Error creating tables: {str(e)}")
            return False
    
    # Add columns to User table if needed
    if not user_fields_exist:
        print("Adding RAG fields to User table...")
        try:
            # Add rag_enabled column
            db.session.execute(text("ALTER TABLE app_user ADD COLUMN rag_enabled BOOLEAN DEFAULT TRUE"))
            # Add rag_short_term_quota column
            db.session.execute(text("ALTER TABLE app_user ADD COLUMN rag_short_term_quota INTEGER DEFAULT 1000"))
            # Add rag_long_term_quota column
            db.session.execute(text("ALTER TABLE app_user ADD COLUMN rag_long_term_quota INTEGER DEFAULT 4"))
            
            # Commit changes
            db.session.commit()
            print("User table updated successfully")
        except Exception as e:
            print(f"Error updating User table: {str(e)}")
            db.session.rollback()
            return False
    
    # Initialize default values for existing users
    print("Initializing default values for existing users...")
    try:
        users = User.query.all()
        for user in users:
            if not hasattr(user, 'rag_enabled') or user.rag_enabled is None:
                user.rag_enabled = True
            if not hasattr(user, 'rag_short_term_quota') or user.rag_short_term_quota is None:
                user.rag_short_term_quota = 1000
            if not hasattr(user, 'rag_long_term_quota') or user.rag_long_term_quota is None:
                user.rag_long_term_quota = 4
        
        db.session.commit()
        print(f"Default values set for {len(users)} users")
    except Exception as e:
        print(f"Error setting default values: {str(e)}")
        db.session.rollback()
        return False
    
    print("RAG database migration completed successfully")
    return True

if __name__ == "__main__":
    # Create app context for database operations
    app = create_app()
    with app.app_context():
        success = run_migration()
        if success:
            print("Migration completed successfully")
        else:
            print("Migration failed")
            sys.exit(1)
