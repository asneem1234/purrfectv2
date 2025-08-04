from flask_sqlalchemy import SQLAlchemy
from flask import current_app
import contextlib
from functools import wraps

# Create a single SQLAlchemy instance
db = SQLAlchemy()

# Simple initialization function that doesn't require global app reference
def init_app(app):
    """Initialize database with the Flask app"""
    db.init_app(app)
    
    # Create tables within app context
    with app.app_context():
        db.create_all()
        print("Database initialized successfully")
        
        # Store app in config for access by other functions
        app.config['_SQLALCHEMY_APP'] = app

# Simplified context manager that uses current_app
@contextlib.contextmanager
def get_db_context():
    """Context manager to ensure database operations occur within app context"""
    try:
        # Check if we're already in an app context
        current_app._get_current_object()
        # Already in app context, yield control
        yield
    except RuntimeError:
        # Not in app context, use app from flask's current_app if possible
        try:
            # Get the app from the current request context if available
            with current_app.app_context():
                yield
        except RuntimeError:
            # Last resort - just let the error happen since we can't find any app
            raise RuntimeError("No Flask app context found and no app available. "
                              "Make sure to call within a Flask request or app context.")

# Simplified decorator that doesn't rely on _app global
def db_operation(f):
    """Decorator to ensure database operations run in app context"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            # Try to run directly - this works if we're already in app context
            return f(*args, **kwargs)
        except RuntimeError:
            # If that fails, try to establish an app context
            with get_db_context():
                return f(*args, **kwargs)
    return decorated_function
