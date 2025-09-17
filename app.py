"""
Redirector module for Render compatibility.
This file simply imports the app from app1.py to maintain compatibility
with platforms that expect the main Flask app to be in app.py.
"""

# Set up mock imports before importing the actual application
import os
import sys

# Add the current directory to sys.path to ensure utils can be imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set up mocks for heavy ML dependencies
try:
    from utils.mock_imports import setup_mock_imports
    setup_mock_imports()
    print("Successfully set up mock imports for ML dependencies")
except Exception as e:
    print(f"Warning: Failed to set up mock imports: {e}")

# Now import the actual application
from app1 import app, socketio
