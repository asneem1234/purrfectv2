# Deploying Purrfect Study Buddy to Render

This guide will help you deploy the Purrfect Study Buddy application to Render.

## Prerequisites

1. A Render account (https://render.com)
2. Your code pushed to a GitHub or GitLab repository

## Deployment Steps

1. Log in to your Render account
2. Go to the Dashboard and click "New+"
3. Select "Blueprint" from the dropdown menu
4. Connect your GitHub/GitLab account if you haven't already
5. Select the repository containing your application
6. Render will automatically detect the `render.yaml` file and configure your services
7. Click "Apply"
8. Render will create the necessary services (web service and PostgreSQL database)

## Environment Variables

The following environment variables need to be set in Render:

- `FLASK_APP`: app1.py
- `FLASK_ENV`: production
- `SECRET_KEY`: (will be automatically generated)
- `DATABASE_URL`: (will be automatically set to the PostgreSQL database)
- `GEMINI_API_KEY`: Your Google Gemini API key
- `GOOGLE_API_KEY`: Your Google API key (if different from Gemini)
- `SERVER_API_KEY`: (will be automatically generated)

## Post-Deployment

1. After deployment, you may need to initialize your database tables
2. Go to the web service in the Render dashboard
3. Navigate to the "Shell" tab
4. Run the following commands:

```
python
```

```python
from app1 import app, db
with app.app_context():
    db.create_all()
    exit()
```

5. Your application should now be fully deployed and ready to use!

## Troubleshooting

- If you encounter any errors, check the logs in the Render dashboard
- Ensure all required environment variables are set
- Make sure your database connection is properly configured
- If necessary, you can restart your service from the Render dashboard