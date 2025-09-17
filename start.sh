#!/bin/bash
# start.sh - Initialize and start the Flask application for Render deployment

# Print Python version for debugging
python --version
echo "Using Python interpreter at: $(which python)"

# Create database tables if they don't exist
python -c "
from app1 import app, db
with app.app_context():
    print('Creating database tables...')
    db.create_all()
    print('Database tables created successfully')
"

# Start the application with gunicorn
echo "Starting application with gunicorn..."
gunicorn app1:socketio.run --worker-class eventlet --bind=0.0.0.0:$PORT
