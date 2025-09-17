# Core Deployment for Purrfect Study Buddy

This document explains the core deployment of the Purrfect Study Buddy application to Render, which uses a minimal set of dependencies to ensure successful deployment.

## What's Included in Core Deployment

The core deployment includes:
- Basic Flask application functionality
- Authentication and session management
- Database interactions
- Basic templating and frontend rendering

## What's Excluded

The core deployment excludes:
- AI/ML features (Gemini, embeddings, RAG)
- Advanced NLP capabilities
- Vector database integration (Qdrant)

## Files Modified for Core Deployment

1. `requirements.core.txt` - A minimal set of dependencies
2. `utils/ai_placeholder.py` - Mock implementations of AI functionality
3. `start.sh` - Initialization script for the application
4. `render.yaml` - Updated configuration for Render deployment

## Accessing the Deployed Application

The core deployment is accessible at: https://purrfect-study-buddy.onrender.com

## Adding Full Functionality Later

To restore full functionality after successful deployment:
1. Add the ML/AI dependencies incrementally
2. Test each feature before adding more dependencies
3. Replace placeholder implementations with actual code

## Environment Variables

The following environment variables must be set in the Render dashboard:
- DATABASE_URL (automatically set by Render)
- SECRET_KEY (automatically generated)
- FLASK_APP=app1.py
- FLASK_ENV=production

For full functionality, these additional variables would be needed:
- GEMINI_API_KEY
- QDRANT_URL
- QDRANT_API_KEY
