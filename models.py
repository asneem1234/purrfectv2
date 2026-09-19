import datetime
import uuid
import json
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from db import db  # Import from our centralized db.py
from datetime import datetime

class RAGIngestEvent(db.Model):
    """Model to track RAG ingestion events."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('app_user.id'))
    source = db.Column(db.String(50))  # chat, notes, study_plan, etc.
    content_id = db.Column(db.String(100), nullable=True)  # Optional ID of the source content
    chunk_count = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<RAGIngestEvent {self.id} user:{self.user_id} source:{self.source}>'

class RAGUsageLog(db.Model):
    """Model to track RAG usage for quota enforcement."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('app_user.id'))
    query_type = db.Column(db.String(50))  # query, ingest, summarize
    tokens_used = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<RAGUsageLog {self.id} user:{self.user_id} type:{self.query_type}>'

class User(UserMixin, db.Model):
    __tablename__ = "app_user"

    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(
        db.String(80),
        unique=True,
        nullable=False
    )

    email = db.Column(
        db.String(120),
        unique=True,
        nullable=False
    )

    password_hash = db.Column(db.String(128))

    # Student profile details
    school_name = db.Column(
        db.String(200),
        nullable=True
    )

    course_name = db.Column(
        db.String(200),
        nullable=True
    )

    semester = db.Column(
        db.String(50),
        nullable=True
    )

    enrollment_schedule_filename = db.Column(
        db.String(255),
        nullable=True
    )

    # JSON-encoded list of course names extracted from the schedule image.
    # Example: ["Data Structures and Algorithms", "Database Systems"]
    enrollment_courses = db.Column(
        db.Text,
        nullable=True,
        default='[]'
    )

    # RAG-related fields
    rag_short_term_quota = db.Column(
        db.Integer,
        default=1000
    )

    rag_long_term_quota = db.Column(
        db.Integer,
        default=4
    )

    rag_enabled = db.Column(
        db.Boolean,
        default=True
    )

    @property
    def study_hours(self):
        return 0

    @property
    def flashcards(self):
        return 0

    @property
    def study_plans(self):
        return 0

    def set_password(self, password):
        self.password_hash = generate_password_hash(
            password,
            method="pbkdf2:sha256"
        )

    def check_password(self, password):
        try:
            return check_password_hash(
                self.password_hash,
                password
            )
        except ValueError as error:
            print(f"Password hash error: {error}")
            return False

    @property
    def activities(self):
        return []

    def __repr__(self):
        return f"<User {self.username}>"
        
class StudentProfile(db.Model):
    """Per-student rest and meal preferences.

    These used to be asked for on every study plan, but they rarely change,
    so they live on the profile and every new plan reads them from here.
    """
    __tablename__ = 'student_profile'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('app_user.id'), unique=True, nullable=False)

    sleep_hours = db.Column(db.Integer, default=6)
    break_duration = db.Column(db.Integer, default=15)   # minutes
    break_interval = db.Column(db.Float, default=1.5)    # hours of study between breaks

    # Kept as 'HH:MM' strings, matching what the time inputs post and what the
    # scheduler already expects to receive.
    breakfast_time = db.Column(db.String(5), default='08:00')
    lunch_time = db.Column(db.String(5), default='13:00')
    snack_time = db.Column(db.String(5), default='16:00')
    dinner_time = db.Column(db.String(5), default='19:00')

    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('profile', uselist=False))

    def to_form_data(self):
        """Shape the profile like the form fields the scheduler reads."""
        return {
            'sleepHours': self.sleep_hours,
            'breakDuration': self.break_duration,
            'breakInterval': self.break_interval,
            'breakfastTime': self.breakfast_time,
            'lunchTime': self.lunch_time,
            'snackTime': self.snack_time,
            'dinnerTime': self.dinner_time,
        }

    def __repr__(self):
        return f'<StudentProfile user:{self.user_id}>'


def get_student_profile(user_id):
    """Return a student's profile, creating one with defaults on first use."""
    profile = StudentProfile.query.filter_by(user_id=user_id).first()
    if profile is None:
        profile = StudentProfile(user_id=user_id)
        db.session.add(profile)
        db.session.commit()
    return profile


class StudyClass(db.Model):
    """A class/course the student is currently taking."""
    __tablename__ = 'study_class'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'name', name='uq_study_class_user_name'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('app_user.id'), nullable=False)
    code = db.Column(db.String(32), nullable=True)      # e.g. "CHEM 210"
    name = db.Column(db.String(120), nullable=False)    # e.g. "Organic Chemistry"
    is_archived = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('classes', lazy=True))
    materials = db.relationship('ClassMaterial', backref='study_class',
                                lazy=True, cascade='all, delete-orphan')

    @property
    def label(self):
        """Display name for the class picker, e.g. 'CHEM 210 - Organic Chemistry'"""
        return f'{self.code} - {self.name}' if self.code else self.name

    def __repr__(self):
        return f'<StudyClass {self.label} user:{self.user_id}>'


class ClassMaterial(db.Model):
    """A PDF uploaded for one exam within a class."""
    __tablename__ = 'class_material'

    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('study_class.id', ondelete='CASCADE'),
                         nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('app_user.id'), nullable=False)
    # The exam this upload is for. Held as the exam name rather than a study_plan
    # FK because the upload happens on the planner form, before the plan itself
    # is saved. StudyPlan.title is set from the same value, which is what the
    # dashboard joins on.
    exam_name = db.Column(db.String(255), nullable=True, index=True)
    # 'pdf' for an uploaded file, 'gdoc' for text imported from a Google Doc
    source_type = db.Column(db.String(16), default='pdf')
    source_url = db.Column(db.String(512), nullable=True)   # the original Google Doc link
    original_filename = db.Column(db.String(255), nullable=False)  # what the student named it
    stored_filename = db.Column(db.String(255), nullable=False)    # collision-free name on disk
    file_path = db.Column(db.String(512), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<ClassMaterial {self.original_filename} class:{self.class_id} exam:{self.exam_name}>'


class StudyPlan(db.Model):
    __tablename__ = 'study_plan'  # Keep the explicitly set table name

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('app_user.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('study_class.id'), nullable=True)
    title = db.Column(db.String(255), nullable=False, default='Study Plan')
    
    # Set default values for TEXT fields to prevent null errors
    topics = db.Column(db.Text, default='[]')
    detailed_schedule = db.Column(db.Text, default='[]')
    
    # Keep JSON field for form inputs, with a default for PostgreSQL
    form_inputs_json = db.Column(db.JSON, default=lambda: {})
    
    is_revision_only = db.Column(db.Boolean, default=False)
    plan_summary = db.Column(db.Text, default='')
    
    # Date fields
    exam_date = db.Column(db.Date, nullable=True)
    prep_start_date = db.Column(db.Date, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    study_class = db.relationship('StudyClass', backref=db.backref('study_plans', lazy=True))

    # Methods to handle JSON serialization/deserialization for Text fields
    @property
    def topics_data(self):
        """Get topics as Python object"""
        if self.topics:
            return json.loads(self.topics)
        return []
    
    @topics_data.setter
    def topics_data(self, value):
        """Set topics from Python object"""
        if value is None:
            self.topics = None
        else:
            self.topics = json.dumps(value)
    
    @property
    def schedule_data(self):
        """Get detailed_schedule as Python object"""
        if self.detailed_schedule:
            return json.loads(self.detailed_schedule)
        return []
    
    @schedule_data.setter
    def schedule_data(self, value):
        """Set detailed_schedule from Python object"""
        if value is None:
            self.detailed_schedule = None
        else:
            self.detailed_schedule = json.dumps(value)
    
    # Serialize plan to dictionary for JSON responses
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'class_id': self.class_id,
            'class_label': self.study_class.label if self.study_class else None,
            'title': self.title,
            'topics': self.topics_data,
            'detailed_schedule': self.schedule_data,
            'form_inputs_json': self.form_inputs_json,
            'is_revision_only': self.is_revision_only,
            'plan_summary': self.plan_summary,
            'exam_date': self.exam_date.strftime('%Y-%m-%d') if self.exam_date else None,
            'prep_start_date': self.prep_start_date.strftime('%Y-%m-%d') if self.prep_start_date else None,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }
    
    # Improved string representation with date information
    def __repr__(self):
        return f'<StudyPlan id={self.id}, title="{self.title}", exam_date={self.exam_date}, prep_start_date={self.prep_start_date}>'

# Updated Study Room models with exact schema as specified
class StudyRoom(db.Model):
    __tablename__ = 'study_rooms'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    is_public = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    shared_notes = db.Column(db.Text, default="")
    timer_seconds = db.Column(db.Integer, default=0)

    snapshots = db.relationship('WhiteboardSnapshot', backref='room', lazy=True)
    logs = db.relationship('UserLog', backref='room', lazy=True)
    chat_messages = db.relationship('ChatMessage', back_populates='study_room', lazy=True)


class UserLog(db.Model):
    __tablename__ = 'user_logs'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.Text)
    action = db.Column(db.String, nullable=False)  # join, leave, whiteboard_update
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    extra_data = db.Column(db.JSON)

    room_id = db.Column(db.Integer, db.ForeignKey('study_rooms.id', ondelete='CASCADE'))


class WhiteboardSnapshot(db.Model):
    __tablename__ = 'whiteboard_snapshots'

    id = db.Column(db.Integer, primary_key=True)
    snapshot = db.Column(db.JSON, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    room_id = db.Column(db.Integer, db.ForeignKey('study_rooms.id', ondelete='CASCADE'))

class Exam(db.Model):
    """Model for tracking exams and progress"""
    __tablename__ = 'exams'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    exam_date = db.Column(db.DateTime, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('app_user.id'), nullable=False)
    confidence_level = db.Column(db.Integer, default=50)  # 0-100%
    study_time_target = db.Column(db.Float, default=10.0)  # Target study hours
    study_time_spent = db.Column(db.Float, default=0.0)  # Actual hours spent
    score = db.Column(db.Float, nullable=True)  # Final exam score, can be null
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Add relationship to User model
    user = db.relationship('User', backref=db.backref('exams', lazy=True))
    
    def __repr__(self):
        return f'<Exam {self.name} on {self.exam_date}>'

class ExamPlan(db.Model):
    """Model for exam planning"""
    __tablename__ = 'exam_plan'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('app_user.id'), nullable=False)  # Reference app_user instead of users
    title = db.Column(db.String(255), nullable=False)
    exam_type = db.Column(db.String(50))
    priority = db.Column(db.String(20))
    exam_date = db.Column(db.DateTime)
    prep_start_date = db.Column(db.DateTime)
    study_goals = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Add relationship to User model
    user = db.relationship('User', backref=db.backref('exam_plans', lazy=True))
    
    def __repr__(self):
        return f'<ExamPlan {self.title} for user {self.user_id}>'

class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'
    
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('study_rooms.id'))
    username = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Use back_populates instead of defining a separate relationship
    # This ensures bidirectional consistency with StudyRoom.chat_messages
    study_room = db.relationship('StudyRoom', foreign_keys=[room_id], 
                               back_populates='chat_messages', overlaps="room")
