"""
Redirector module for Render compatibility.
This file simply imports the app from app1.py to maintain compatibility
with platforms that expect the main Flask app to be in app.py.
"""

# Import necessary modules
import os

# Import the application
from app1 import app, socketio

# This is needed for Render's default gunicorn command (gunicorn app:app)
if __name__ == "__main__":
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
