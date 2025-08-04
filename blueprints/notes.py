from flask import Blueprint, render_template, request, redirect, url_for, jsonify, flash
from flask_login import login_required, current_user
import json
from datetime import datetime

# Remove url_prefix since we're specifying it in app1.py registration
notes_bp = Blueprint('notes', __name__)

@notes_bp.route('/')
@login_required
def notes_home():
    """Display the notes home page with all notes"""
    # Render the notes-coming-soon page
    return render_template('notes-coming-soon.html', user=current_user)

# Since notes_home now renders create-note.html directly, we can remove this separate route
# or keep it as an alias
@notes_bp.route('/create-note', methods=['GET', 'POST'])
@login_required
def create_note():
    """Handle note creation"""
    if request.method == 'POST':
        # Handle note saving logic here
        title = request.form.get('title')
        content = request.form.get('content')
        canvas_data = request.form.get('canvas-data', '{}')
        
        # In a real application, you'd save this to a database
        # Return to the same page but with success message
        flash('Note created successfully!', 'success')
        return render_template('create-note.html', user=current_user)
        
    # GET request - show the create note page
    return render_template('create-note.html', user=current_user)

@notes_bp.route('/save', methods=['POST'])
@login_required
def save_note():
    """API endpoint to save a note via AJAX"""
    # Get the request data
    data = request.get_json()
    
    if not data:
        return jsonify({'status': 'error', 'message': 'No data provided'}), 400
    
    # In a real application, you'd save this to a database
    # For demonstration, just return success
    note_saved = True
    
    # Process for RAG if enabled
    if note_saved and hasattr(current_user, 'rag_enabled') and current_user.rag_enabled:
        try:
            import requests
            from flask import url_for
            
            # Extract note content and title
            title = data.get('title', 'Untitled Note')
            content = data.get('content', '')
            
            # Only process if there's content
            if content:
                # Combine title and content for context
                note_text = f"Title: {title}\n\n{content}"
                
                # Send to RAG system for ingestion
                requests.post(
                    url_for('purrrag.ingest_text', _external=True),
                    json={
                        'text': note_text,
                        'source': 'notes',
                        'content_id': f"note_{datetime.now().timestamp()}"
                    },
                    headers={'Content-Type': 'application/json'}
                )
        except Exception as e:
            print(f"Error ingesting note to RAG: {e}")
            # Don't fail the main note-saving flow if RAG ingestion fails
    
    return jsonify({
        'status': 'success', 
        'message': 'Note saved successfully',
        'timestamp': datetime.now().isoformat()
    })

@notes_bp.route('/<int:note_id>')
@login_required
def view_note(note_id):
    """View a specific note"""
    # In a real application, you'd fetch the note from a database
    # For now, just render the create-note template directly
    return render_template('create-note.html', user=current_user)
