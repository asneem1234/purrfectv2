from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from flask_socketio import emit, join_room, leave_room as socketio_leave_room
from models import db, StudyRoom, UserLog, WhiteboardSnapshot, ChatMessage
import uuid
from datetime import datetime

studyroom_bp = Blueprint('studyroom', __name__, template_folder='templates')

# Function to register SocketIO event handlers
def register_studyroom_socket_events(socketio):
    
    @socketio.on('join_room')
    def handle_join(data):
        room_name = data['room']
        username = data.get('username', current_user.username if hasattr(current_user, 'username') else 'Anonymous')
        
        join_room(room_name)

        room = StudyRoom.query.filter_by(name=room_name).first()
        if room:
            # Load shared notes
            emit('load_shared_notes', {'content': room.shared_notes}, room=request.sid)
            
            # Load last whiteboard snapshot
            last = WhiteboardSnapshot.query.filter_by(room_id=room.id).order_by(WhiteboardSnapshot.timestamp.desc()).first()
            if last:
                emit('load_whiteboard', {'snapshot': last.snapshot.get("image")}, room=request.sid)
            
            # Fetch last 50 messages
            msgs = ChatMessage.query.filter_by(room_id=room.id).order_by(ChatMessage.timestamp.asc()).limit(50).all()
            chat_dump = [{'username': m.username, 'message': m.message, 'timestamp': m.timestamp.isoformat()} for m in msgs]
            emit('chat_history', chat_dump, room=request.sid)
            
            # Log user joining the room
            log = UserLog(
                username=username,
                room_id=room.id,
                action='join',
                timestamp=datetime.utcnow()
            )
            db.session.add(log)
            db.session.commit()
            
            # Broadcast to others that a user has joined
            emit('user_event', {'username': username, 'event': 'joined'}, room=room_name)

    @socketio.on('leave_room')
    def handle_leave(data):
        room_name = data['room']
        username = data.get('username', current_user.username if hasattr(current_user, 'username') else 'Anonymous')

        socketio_leave_room(room_name)

        room = StudyRoom.query.filter_by(name=room_name).first()
        if room:
            log = UserLog(
                username=username, 
                room_id=room.id, 
                action='leave',
                timestamp=datetime.utcnow()
            )
            db.session.add(log)
            db.session.commit()

            # Broadcast to others that a user has left
            emit('user_event', {'username': username, 'event': 'left'}, room=room_name)
    
    @socketio.on('notes_update')
    def handle_notes_update(data):
        room_name = data['room']
        content = data['content']

        print(f"[notes_update] Room: {room_name}, Content: {content[:50]}..." if len(content) > 50 else f"[notes_update] Room: {room_name}, Content: {content}")

        room = StudyRoom.query.filter_by(name=room_name).first()
        if room:
            room.shared_notes = content
            db.session.commit()

        emit('notes_update', {'content': content}, room=room_name)
        
    @socketio.on('draw')
    def handle_draw(data):
        emit('draw', data, room=data['room'])

    @socketio.on('save_snapshot')
    def handle_save_snapshot(data):
        room_name = data['room']
        snapshot_base64 = data['snapshot']

        room = StudyRoom.query.filter_by(name=room_name).first()
        if room:
            snapshot = WhiteboardSnapshot(room_id=room.id, snapshot={"image": snapshot_base64})
            db.session.add(snapshot)
            db.session.commit()
        
    @socketio.on('whiteboard_update')
    def handle_whiteboard_update(data):
        room_name = data['room']
        snapshot = data['snapshot']
        
        room = StudyRoom.query.filter_by(name=room_name).first()
        if room:
            # Create a snapshot record
            whiteboard_snapshot = WhiteboardSnapshot(
                room_id=room.id,
                snapshot=snapshot,
                timestamp=datetime.utcnow()
            )
            db.session.add(whiteboard_snapshot)
            
            # Log the whiteboard update
            log = UserLog(
                username=current_user.username if hasattr(current_user, 'username') else 'Anonymous',
                room_id=room.id,
                action='whiteboard_update',
                extra_data={'snapshot_id': whiteboard_snapshot.id}
            )
            db.session.add(log)
            db.session.commit()
            
        emit('whiteboard_update', {'snapshot': snapshot}, room=room_name, include_self=False)
        
    @socketio.on('timer_update')
    def handle_timer_update(data):
        room_name = data['room']
        action = data['action']  # start, pause, reset
        value = data.get('value')  # only sent for pause/reset

        room = StudyRoom.query.filter_by(name=room_name).first()
        if not room:
            return

        if action in ['pause', 'reset']:
            room.timer_seconds = value
            db.session.commit()

        emit('timer_update', {'action': action, 'value': value}, room=room_name)
        
    @socketio.on('request_timer_state')
    def handle_timer_request(data):
        room_name = data['room']
        room = StudyRoom.query.filter_by(name=room_name).first()
        if room:
            emit('timer_state', {'value': room.timer_seconds}, room=request.sid)

    # WebRTC signaling handlers for audio communication
    @socketio.on('join-audio-room')
    def join_audio_room(data):
        room = data['room']
        join_room(room)
        emit('new-peer', {'peer_id': request.sid}, room=room, include_self=False)

    @socketio.on('peer-offer')
    def handle_peer_offer(data):
        peer_id = data['peer_id']
        offer = data['offer']
        emit('peer-offer', {'peer_id': request.sid, 'offer': offer}, room=peer_id)

    @socketio.on('peer-answer')
    def handle_peer_answer(data):
        peer_id = data['peer_id']
        answer = data['answer']
        emit('peer-answer', {'peer_id': request.sid, 'answer': answer}, room=peer_id)

    @socketio.on('peer-ice')
    def handle_peer_ice(data):
        peer_id = data['peer_id']
        candidate = data['candidate']
        emit('peer-ice', {'peer_id': request.sid, 'candidate': candidate}, room=peer_id)

    @socketio.on('chat')
    def handle_chat(data):
        room_name = data['room']
        username = data.get('username', current_user.username if hasattr(current_user, 'username') else 'Anonymous')
        message = data.get('message', '')
        
        if not message.strip():
            return
            
        room = StudyRoom.query.filter_by(name=room_name).first()
        if room:
            # Save message to database
            chat_message = ChatMessage(
                room_id=room.id,
                username=username,
                message=message,
                timestamp=datetime.utcnow()
            )
            db.session.add(chat_message)
            db.session.commit()
            
            # Broadcast to all clients in the room
            emit('chat', {
                'username': username, 
                'message': message,
                'timestamp': chat_message.timestamp.isoformat()
            }, room=room_name)
            
            # Send to RAG system for ingestion if user is authenticated
            try:
                if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated and \
                   hasattr(current_user, 'rag_enabled') and current_user.rag_enabled:
                    import requests
                    from flask import url_for
                    
                    # Build the context - include room name
                    context = f"Message in study room '{room_name}'"
                    
                    # Ingest the chat message
                    requests.post(
                        url_for('purrrag.ingest_text', _external=True),
                        json={
                            'text': message,
                            'source': 'studyroom_chat',
                            'content_id': f"{room.id}_{chat_message.id}"
                        },
                        headers={'Content-Type': 'application/json'}
                    )
            except Exception as e:
                print(f"Error ingesting studyroom chat to RAG: {e}")
                # Don't fail the main chat flow if RAG ingestion fails

# Existing routes but updated to use database models
@studyroom_bp.route('/create-room', methods=['GET', 'POST'])
@login_required
def create_room():
    if request.method == 'POST':
        room_name = request.form['room_name']
        is_public = request.form.get('is_public') == 'on'
        
        # Check if room exists
        existing_room = StudyRoom.query.filter_by(name=room_name).first()
        if existing_room:
            error = "Room already exists!"
            return render_template('create_room.html', error=error)
        
        # Create new room in database
        new_room = StudyRoom(
            name=room_name,
            is_public=is_public,
            created_at=datetime.utcnow(),
            shared_notes="",
            timer_seconds=0
        )
        db.session.add(new_room)
        db.session.commit()
        
        return redirect(url_for('studyroom.studyroom', room_name=room_name))
    
    return render_template('create_room.html')

@studyroom_bp.route('/studyroom/<room_name>')
@login_required
def studyroom(room_name):
    room = StudyRoom.query.filter_by(name=room_name).first()
    if not room:
        return f"Room '{room_name}' not found.", 404
    
    # Get room participants from logs
    recent_logs = UserLog.query.filter_by(
        room_id=room.id, 
        action='join'
    ).order_by(UserLog.timestamp.desc()).limit(10).all()
    
    participants = list(set([log.username for log in recent_logs]))
    
    return render_template('studyroom.html', 
        # Pass room_name and username directly
        room_name=room_name,
        username=current_user.username,
        # Also keep the data object for backward compatibility
        data={
            'room_name': room_name,
            'public': room.is_public,
            'participants': participants,
            'shared_notes': room.shared_notes,
            'timer_seconds': room.timer_seconds,
            'created_at': room.created_at  # Add creation date to the data
        }
    )

@studyroom_bp.route('/rooms')
@login_required
def room_list():
    # Get public rooms from database
    public_rooms = StudyRoom.query.filter_by(is_public=True).all()
    rooms_dict = {}
    
    for room in public_rooms:
        # Get recent participants for this room
        recent_logs = UserLog.query.filter_by(
            room_id=room.id, 
            action='join'
        ).order_by(UserLog.timestamp.desc()).limit(10).all()
        
        participants = list(set([log.username for log in recent_logs]))
        
        rooms_dict[room.name] = {
            'public': room.is_public,
            'created_at': room.created_at,
            'participants': participants
        }
    
    return render_template('room_list.html', rooms=rooms_dict)

# Add an alternative route with the name that's being looked up
@studyroom_bp.route('/list-rooms')
@login_required
def list_rooms():
    """Alias for room_list function to support both endpoint names"""
    return room_list()

@studyroom_bp.route('/leave-room/<room_name>')
@login_required
def leave_room(room_name):
    room = StudyRoom.query.filter_by(name=room_name).first()
    if room:
        # Log user leaving the room
        log = UserLog(
            username=current_user.username,
            room_id=room.id,
            action='leave',
            timestamp=datetime.utcnow()
        )
        db.session.add(log)
        db.session.commit()
    
    return redirect(url_for('studyroom.room_list'))

@studyroom_bp.route('/delete/<room_name>', methods=['POST'])
@studyroom_bp.route('/studyroom/delete/<room_name>', methods=['POST'])  # Add this extra route
@login_required
def delete_room(room_name):
    # Find the room in the database
    room = StudyRoom.query.filter_by(name=room_name).first_or_404()
    
    try:
        # Delete associated records (logs, whiteboard snapshots, etc.)
        UserLog.query.filter_by(room_id=room.id).delete()
        WhiteboardSnapshot.query.filter_by(room_id=room.id).delete()
        
        # Delete the room itself
        db.session.delete(room)
        db.session.commit()
        
        flash(f'Room "{room_name}" has been deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred while deleting the room: {str(e)}', 'error')
    
    # Redirect to dashboard instead of rooms list
    return redirect('/dashboard')
