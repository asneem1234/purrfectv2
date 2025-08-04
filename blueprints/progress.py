from flask import Blueprint, render_template, jsonify, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, User, Exam, StudyPlan
from datetime import datetime

progress = Blueprint('progress', __name__)

@progress.route('/progress')
@login_required
def show_progress():
    """
    Render the progress page displaying user's exam progress and study habits
    """
    # Get current date/time
    current_date = datetime.now()
    
    # Get all exams for the current user
    upcoming_exams = Exam.query.filter_by(user_id=current_user.id).filter(Exam.exam_date >= current_date).order_by(Exam.exam_date.asc()).all()
    past_exams = Exam.query.filter_by(user_id=current_user.id).filter(Exam.exam_date < current_date).order_by(Exam.exam_date.desc()).all()
    
    # Calculate days remaining and prepare additional data for upcoming exams
    for exam in upcoming_exams:
        # Calculate days remaining
        days_remaining = (exam.exam_date - current_date).days
        exam.days_remaining = days_remaining if days_remaining >= 0 else 0
        
        # Map database fields to template expected fields
        exam.exam_name = exam.name
        exam.hours_studied = exam.study_time_spent
        exam.target_hours = exam.study_time_target
        
        # Calculate study progress percentage
        if exam.study_time_target > 0:
            progress = (exam.study_time_spent / exam.study_time_target) * 100
            exam.study_progress = min(100, round(progress))
        else:
            exam.study_progress = 0
    
    return render_template(
        'progress.html', 
        user=current_user, 
        upcoming_exams=upcoming_exams, 
        past_exams=past_exams,
        current_date=current_date
    )

@progress.route('/add_exam', methods=['POST'])
@login_required
def add_exam():
    """
    Add a new exam to the database
    """
    if request.method == 'POST':
        exam_name = request.form.get('exam_name')
        subject = request.form.get('subject')
        exam_date_str = request.form.get('exam_date')
        confidence_level = request.form.get('confidence_level')
        study_time_target = request.form.get('study_time_target')
        
        # Validate form data
        if not exam_name or not subject or not exam_date_str:
            flash('Please fill in all required fields', 'danger')
            return redirect(url_for('progress.show_progress'))
        
        try:
            # Parse the date string
            exam_date = datetime.strptime(exam_date_str, '%Y-%m-%d')
            
            # Create a new exam
            new_exam = Exam(
                name=exam_name,
                subject=subject,
                exam_date=exam_date,
                user_id=current_user.id,
                confidence_level=confidence_level or 50,  # Default 50% if not provided
                study_time_target=study_time_target or 10, # Default 10 hours if not provided
                study_time_spent=0  # Start with 0 hours spent
            )
            
            # Add to database
            db.session.add(new_exam)
            db.session.commit()
            
            flash('Exam added successfully!', 'success')
            return redirect(url_for('progress.show_progress'))
        
        except Exception as e:
            flash(f'Error adding exam: {str(e)}', 'danger')
            return redirect(url_for('progress.show_progress'))
    
    return redirect(url_for('progress.show_progress'))

@progress.route('/update_exam/<int:exam_id>', methods=['POST'])
@login_required
def update_exam(exam_id):
    """
    Update an existing exam
    """
    exam = Exam.query.get_or_404(exam_id)
    
    # Check if exam belongs to current user
    if exam.user_id != current_user.id:
        flash('You do not have permission to modify this exam', 'danger')
        return redirect(url_for('progress.show_progress'))
    
    if request.method == 'POST':
        exam.name = request.form.get('exam_name', exam.name)
        exam.subject = request.form.get('subject', exam.subject)
        
        exam_date_str = request.form.get('exam_date')
        if exam_date_str:
            try:
                exam.exam_date = datetime.strptime(exam_date_str, '%Y-%m-%d')
            except:
                flash('Invalid date format', 'danger')
                return redirect(url_for('progress.show_progress'))
        
        confidence_level = request.form.get('confidence_level')
        if confidence_level:
            exam.confidence_level = int(confidence_level)
        
        study_time_spent = request.form.get('study_time_spent')
        if study_time_spent:
            exam.study_time_spent = float(study_time_spent)
        
        study_time_target = request.form.get('study_time_target')
        if study_time_target:
            exam.study_time_target = float(study_time_target)
        
        # If exam is past, update score
        if exam.exam_date < datetime.now():
            score = request.form.get('score')
            if score:
                exam.score = float(score)
        
        db.session.commit()
        flash('Exam updated successfully!', 'success')
        
    return redirect(url_for('progress.show_progress'))

@progress.route('/delete_exam/<int:exam_id>', methods=['POST'])
@login_required
def delete_exam(exam_id):
    """
    Delete an exam
    """
    exam = Exam.query.get_or_404(exam_id)
    
    # Check if exam belongs to current user
    if exam.user_id != current_user.id:
        flash('You do not have permission to delete this exam', 'danger')
        return redirect(url_for('progress.show_progress'))
    
    db.session.delete(exam)
    db.session.commit()
    
    flash('Exam deleted successfully!', 'success')
    return redirect(url_for('progress.show_progress'))
