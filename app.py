"""
Redirector module for Render compatibility.
This file simply imports the app from app1.py to maintain compatibility
with platforms that expect the main Flask app to be in app.py.
"""

# Import the application
from app1 import app, socketio
