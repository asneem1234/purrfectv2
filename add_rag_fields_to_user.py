"""
Script to add RAG fields to the User model in the database.

Usage:
python add_rag_fields_to_user.py
"""
import os
from dotenv import load_dotenv
from flask import Flask
from sqlalchemy import text
from models import db
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

def add_rag_fields():
    """Add RAG fields to User model if they don't exist"""
    try:
        # Check if columns exist
        check_sql = """
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'app_user'
        """
        result = db.session.execute(text(check_sql)).fetchall()
        columns = [row[0] for row in result]
        
        print(f"Existing columns in app_user table: {columns}")
        
        # Add missing columns
        if 'rag_short_term_quota' not in columns:
            print("Adding rag_short_term_quota column...")
            db.session.execute(text(
                "ALTER TABLE app_user ADD COLUMN rag_short_term_quota INTEGER DEFAULT 1000"
            ))
            print("✓ Added rag_short_term_quota column")
        
        if 'rag_long_term_quota' not in columns:
            print("Adding rag_long_term_quota column...")
            db.session.execute(text(
                "ALTER TABLE app_user ADD COLUMN rag_long_term_quota INTEGER DEFAULT 4"
            ))
            print("✓ Added rag_long_term_quota column")
        
        if 'rag_enabled' not in columns:
            print("Adding rag_enabled column...")
            db.session.execute(text(
                "ALTER TABLE app_user ADD COLUMN rag_enabled BOOLEAN DEFAULT TRUE"
            ))
            print("✓ Added rag_enabled column")
        
        # Create RAG tables
        db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS rag_ingest_event (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES app_user(id),
            source VARCHAR(50),
            content_id VARCHAR(100),
            chunk_count INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """))
        
        db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS rag_usage_log (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES app_user(id),
            query_type VARCHAR(50),
            tokens_used INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """))
        
        db.session.commit()
        print("✓ Created RAG tables")
        
        return True
    
    except Exception as e:
        db.session.rollback()
        print(f"Error adding RAG fields: {str(e)}")
        return False

def main():
    app = create_app()
    
    with app.app_context():
        print("\n=== Adding RAG Fields to User Model ===\n")
        
        success = add_rag_fields()
        
        if success:
            print("\n✅ RAG fields added successfully!")
        else:
            print("\n❌ Failed to add RAG fields.")
            sys.exit(1)

if __name__ == "__main__":
    main()
