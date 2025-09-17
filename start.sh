#!/bin/bash
# This script is used for deploying on Render

# Install only the minimal dependencies
pip install -r requirements.minimal.txt

# Print versions of installed packages
pip freeze

echo "Starting application with eventlet..."
gunicorn app1:socketio.run --worker-class eventlet --bind 0.0.0.0:$PORT --log-file -