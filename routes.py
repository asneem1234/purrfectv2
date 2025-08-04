from flask import Flask, request, jsonify, session
from datetime import datetime
from yourapp import db
from yourapp.models import User, StudyPlan

app = Flask(__name__)

# ... your existing routes and code ...

@app.route('/save-study-plan', methods=['POST'])
def save_study_plan():
    """Save the study plan and update the dashboard and calendar"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Please log in first'})
    
    data = request.json
    user_id = session['user_id']
    plan_id = data.get('plan_id')
    checked_activities = data.get('checked_activities', [])
    
    try:
        # Get the user and study plan
        user = db.session.get(User, user_id)
        
        # Create or update a saved study plan
        saved_plan = StudyPlan.query.filter_by(id=plan_id).first()
        
        if not saved_plan:
            # Create a new saved plan
            saved_plan = StudyPlan(
                user_id=user_id,
                created_at=datetime.now(),
                plan_data=data,
                status='active'
            )
            db.session.add(saved_plan)
        else:
            # Update existing plan
            saved_plan.updated_at = datetime.now()
            saved_plan.plan_data = data
            
            # Update activity completion status
            for activity in checked_activities:
                day_idx = activity['day']
                act_idx = activity['activity']
                completed = activity['completed']
                
                # Access the specific activity in the plan data and update it
                if 'detailed_schedule' in saved_plan.plan_data:
                    if day_idx < len(saved_plan.plan_data['detailed_schedule']):
                        day_schedule = saved_plan.plan_data['detailed_schedule'][day_idx]
                        if 'activities' in day_schedule:
                            if act_idx < len(day_schedule['activities']):
                                day_schedule['activities'][act_idx]['completed'] = completed
        
        db.session.commit()
        
        # Return success response
        return jsonify({
            'success': True,
            'message': 'Study plan saved successfully',
            'plan_id': saved_plan.id
        })
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error saving study plan: {str(e)}")
        return jsonify({'success': False, 'message': f"Error: {str(e)}"})

@app.route('/api/user-sessions', methods=['GET'])
def get_user_sessions():
    """Get the user's study sessions for dashboard and calendar"""
    if 'user_id' not in session:
        return jsonify({
            'sessions': [],
            'ongoing_sessions': [],
            'upcoming_sessions': []
        })
    
    user_id = session['user_id']
    today = datetime.now().date()
    
    try:
        # Get the user's active study plans
        study_plans = StudyPlan.query.filter_by(
            user_id=user_id,
            status='active'
        ).all()
        
        all_sessions = []
        ongoing_sessions = []
        upcoming_sessions = []
        
        for plan in study_plans:
            if 'detailed_schedule' not in plan.plan_data:
                continue
                
            for day_schedule in plan.plan_data['detailed_schedule']:
                try:
                    day_date = datetime.strptime(day_schedule['date'], '%Y-%m-%d').date();
                    
                    if 'activities' not in day_schedule:
                        continue
                        
                    for activity in day_schedule['activities']:
                        session_data = {
                            'date': day_schedule['date'],
                            'title': activity.get('title', 'Study Session'),
                            'time': f"{activity.get('start_time', '')} - {activity.get('end_time', '')}",
                            'duration': activity.get('duration', 0),
                            'type': activity.get('type', 'study'),
                            'completed': activity.get('completed', False),
                            'icon': '📚' if activity.get('type', '') == 'study' else '☕' if activity.get('type', '') == 'break' else '📝'
                        }
                        
                        all_sessions.append(session_data)
                        
                        # Check if the session is today (ongoing)
                        if day_date == today and not activity.get('completed', False):
                            ongoing_sessions.append(session_data)
                        
                        # Check if the session is in the future (upcoming)
                        if day_date > today:
                            # Only add if we don't have too many
                            if len(upcoming_sessions) < 5:
                                upcoming_sessions.append(session_data)
                
                except Exception as e:
                    app.logger.error(f"Error processing session day: {str(e)}")
                    continue
        
        # Sort upcoming sessions by date
        upcoming_sessions.sort(key=lambda x: x['date'])
        
        return jsonify({
            'sessions': all_sessions,
            'ongoing_sessions': ongoing_sessions,
            'upcoming_sessions': upcoming_sessions
        })
        
    except Exception as e:
        app.logger.error(f"Error retrieving user sessions: {str(e)}")
        return jsonify({
            'sessions': [],
            'ongoing_sessions': [],
            'upcoming_sessions': []
        })

# ... rest of your existing code ...