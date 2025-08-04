from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, StudyPlan, ExamPlan  # Import ExamPlan model
from datetime import datetime, timedelta
import json
import os

# Create planning blueprint
planning_bp = Blueprint('planning', __name__, template_folder='templates')

@planning_bp.route('/planning')
@login_required
def planning_home():
    """Main planning page route"""
    return render_template('planning.html', user=current_user)

@planning_bp.route('/api/set-exam-date', methods=['POST'])
@login_required
def set_exam_date():
    """API endpoint to save exam date"""
    try:
        data = request.get_json()
        exam_date_str = data.get('exam_date')
        
        if not exam_date_str:
            return jsonify({'success': False, 'message': 'No exam date provided'}), 400
        
        # Convert string date to datetime object
        exam_date = datetime.strptime(exam_date_str, '%Y-%m-%d')
        
        # Save to user's settings or create a placeholder study plan
        # This is just a placeholder - you might want to save this to a user preferences table
        new_plan = StudyPlan(
            user_id=current_user.id,
            title="Exam Preparation",
            exam_date=exam_date,
            prep_start_date=datetime.now(),
            plan_summary="Exam date set through planning tool"
        )
        db.session.add(new_plan)
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Exam date saved successfully',
            'exam_date': exam_date_str
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@planning_bp.route('/exam-plan-creator')
@login_required
def exam_plan_creator():
    """Route for the detailed exam plan creator page"""
    # Render the exam plan creator template
    return render_template('exam_plan_creator.html', user=current_user)

# Add route alias for common misspelling
@planning_bp.route('/exam-plan-creater')
@login_required
def exam_plan_creater():
    """Route alias for the misspelled URL"""
    # Redirect to the correct URL
    return redirect(url_for('planning.exam_plan_creator'))

@planning_bp.route('/add-calender', methods=['POST'])
@login_required
def add_calendar():
    """Process exam plan form submission and add to calendar"""
    try:
        # Get form data
        exam_title = request.form.get('examTitle')
        exam_type = request.form.get('examType')
        priority = request.form.get('priority')
        start_date = request.form.get('startDate')
        exam_date = request.form.get('examDate')
        study_goals = request.form.get('studyGoals', '')
        
        # Validate required fields
        if not exam_title or not exam_date:
            # Remove flash message
            # flash('Exam title and date are required', 'error')
            return redirect(url_for('planning.exam_plan_creator'))
        
        # Parse dates
        try:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
            exam_date_obj = datetime.strptime(exam_date, '%Y-%m-%d')
        except ValueError:
            # Remove flash message
            # flash('Invalid date format', 'error')
            return redirect(url_for('planning.exam_plan_creator'))
        
        # Create new exam plan using the ExamPlan model
        new_plan = ExamPlan(
            user_id=current_user.id,
            title=exam_title,
            exam_type=exam_type,
            priority=priority,
            exam_date=exam_date_obj,
            prep_start_date=start_date_obj,
            study_goals=study_goals,
            created_at=datetime.now()
        )
        
        # Also create a study plan for calendar integration
        new_study_plan = StudyPlan(
            user_id=current_user.id,
            title=exam_title,
            exam_date=exam_date_obj,
            prep_start_date=start_date_obj,
            plan_summary=f"Type: {exam_type}, Priority: {priority}\n\n{study_goals}"
        )
        
        # Add both to database
        db.session.add(new_plan)
        db.session.add(new_study_plan)
        db.session.commit()
        
        # Remove flash message
        # flash(f'Exam plan "{exam_title}" has been added to your calendar!', 'success')
        return redirect(url_for('dashboard'))
        
    except Exception as e:
        db.session.rollback()
        # Remove flash message
        # flash(f'Error creating exam plan: {str(e)}', 'error')
        return redirect(url_for('planning.exam_plan_creator'))

@planning_bp.route('/delete-exam-plan/<int:plan_id>', methods=['POST'])
@login_required
def delete_exam_plan(plan_id):
    """Delete an exam plan by ID"""
    try:
        # Find the exam plan
        exam_plan = ExamPlan.query.filter_by(id=plan_id, user_id=current_user.id).first_or_404()
        
        # Also delete the corresponding study plan if it exists
        study_plan = StudyPlan.query.filter_by(
            user_id=current_user.id, 
            title=exam_plan.title,
            exam_date=exam_plan.exam_date
        ).first()
        
        if study_plan:
            db.session.delete(study_plan)
        
        # Delete the exam plan
        db.session.delete(exam_plan)
        db.session.commit()
        
        # Remove flash message
        # flash(f'Exam plan "{exam_plan.title}" has been deleted.', 'success')
        return jsonify({'success': True, 'message': 'Exam plan deleted successfully'})
        
    except Exception as e:
        db.session.rollback()
        # Remove flash message
        # flash(f'Error deleting exam plan: {str(e)}', 'error')
        return jsonify({'success': False, 'message': str(e)}), 500

# Additional routes can be added here as needed
