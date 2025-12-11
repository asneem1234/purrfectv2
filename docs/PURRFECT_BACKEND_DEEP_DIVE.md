# 🐱 Purrfect AI - Comprehensive Backend & System Design Documentation

> **Last Updated:** December 2025  
> **Version:** 2.0  
> **Author:** System Analysis

---

## 📑 Table of Contents

1. [Executive Summary](#executive-summary)
2. [High-Level Architecture](#high-level-architecture)
3. [Application Entry Point (app1.py)](#application-entry-point-app1py)
4. [Database Layer](#database-layer)
5. [Authentication System](#authentication-system)
6. [Blueprint Architecture](#blueprint-architecture)
7. [AI/ML Pipeline](#aiml-pipeline)
8. [RAG (Retrieval Augmented Generation) System](#rag-system)
9. [Real-Time Features](#real-time-features)
10. [Utility Modules](#utility-modules)
11. [Security Implementation](#security-implementation)
12. [Data Flow Diagrams](#data-flow-diagrams)
13. [File-by-File Analysis](#file-by-file-analysis)
14. [API Endpoints Reference](#api-endpoints-reference)
15. [Deployment Configuration](#deployment-configuration)

---

## Executive Summary

**Purrfect AI** is a comprehensive AI-powered educational platform built using a **Flask-based microservices architecture** with **multi-agent AI orchestration**. The platform combines:

- **Google Gemini 2.0 Flash** for natural language understanding and content generation
- **Qdrant Vector Database** for semantic search and RAG capabilities
- **Sentence Transformers** for text embeddings
- **Real-time WebSockets** for collaborative study rooms
- **PostgreSQL** for relational data with SQLite fallback

### Key Statistics
- **Total Python Files:** 30+
- **Total Lines of Code:** ~15,000+
- **Blueprints:** 12 modular components
- **AI Models Used:** 3 (Gemini, SentenceTransformer, CrossEncoder)
- **Database Models:** 10+

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND LAYER                                  │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │Dashboard│ │Study    │ │Flashcard│ │ExamBot  │ │StudyRoom│ │Progress │   │
│  │         │ │Planner  │ │Generator│ │         │ │         │ │Tracker  │   │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘   │
└───────┼──────────┼──────────┼──────────┼──────────┼──────────┼─────────────┘
        │          │          │          │          │          │
        ▼          ▼          ▼          ▼          ▼          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              API LAYER (Flask Blueprints)                    │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │bot_bp   │ │study_   │ │flashcard│ │exambot  │ │studyroom│ │progress │   │
│  │         │ │plan     │ │_bp      │ │_bp      │ │_bp      │ │         │   │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘   │
└───────┼──────────┼──────────┼──────────┼──────────┼──────────┼─────────────┘
        │          │          │          │          │          │
        ▼          ▼          ▼          ▼          ▼          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ORCHESTRATION LAYER                                │
│  ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐    │
│  │ Pawfessor Meowkins │  │ RAG Pipeline       │  │ Session Manager    │    │
│  │ (Teaching Agent)   │  │ (Context Retrieval)│  │ (State Tracking)   │    │
│  └─────────┬──────────┘  └─────────┬──────────┘  └─────────┬──────────┘    │
└────────────┼────────────────────────┼────────────────────────┼──────────────┘
             │                        │                        │
             ▼                        ▼                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              AI/ML LAYER                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │ Google Gemini   │  │ SentenceTransf. │  │ EasyOCR         │             │
│  │ 2.0 Flash       │  │ all-MiniLM-L6-v2│  │ (Image→Text)    │             │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘             │
└───────────┼────────────────────┼────────────────────┼───────────────────────┘
            │                    │                    │
            ▼                    ▼                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DATA LAYER                                      │
│  ┌─────────────────────────┐  ┌─────────────────────────┐                  │
│  │     PostgreSQL          │  │     Qdrant (Vector DB)  │                  │
│  │  ┌─────┐ ┌─────────┐    │  │  ┌─────────┐ ┌───────┐  │                  │
│  │  │User │ │StudyPlan│    │  │  │chat_{id}│ │flash- │  │                  │
│  │  ├─────┤ ├─────────┤    │  │  │         │ │cards_ │  │                  │
│  │  │Exam │ │StudyRoom│    │  │  │studyplan│ │{id}   │  │                  │
│  │  └─────┘ └─────────┘    │  │  │_{id}    │ └───────┘  │                  │
│  └─────────────────────────┘  └─────────────────────────┘                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Application Entry Point (app1.py)

### Overview
`app1.py` is the **main application entry point** (984 lines). It initializes the Flask application, configures all services, and orchestrates the entire platform.

### Initialization Sequence

```python
# 1. COMPATIBILITY PATCHES (Lines 1-30)
import compatibility_patch  # Fixes collections.MutableMapping for Python 3.10+
import eventlet_patch       # Fixes eventlet for Python 3.11+ and Windows
import eventlet

# WHY: Python 3.10+ removed direct access to collections.MutableMapping,
# breaking older packages. The patch restores this for backward compatibility.
```

**Why Eventlet?**
- Eventlet enables **asynchronous I/O** without threading complexity
- Required for **Socket.IO** real-time communication
- Monkey-patching makes blocking calls non-blocking

```python
# 2. MINIMAL MONKEY PATCHING (Lines 20-27)
eventlet.monkey_patch(os=False, thread=False, time=False, socket=False, select=False)

# WHY: Full monkey patching causes issues on Windows. Minimal patching
# provides just enough async support for Socket.IO without breaking
# file operations or threading.
```

### CSRF Protection Strategy

```python
# 3. CSRF CONFIGURATION (Lines 54-115)
csrf = CSRFProtect(app)

def csrf_check_function():
    # Exempt specific server-to-server API endpoints
    if request_path in ['/rag/ingest', '/rag/query', '/direct-rag-ingest']:
        api_key = request.headers.get('X-API-Key')
        if api_key == os.environ.get('SERVER_API_KEY'):
            return False  # Skip CSRF for authenticated API calls
    return True  # Enforce CSRF for all other routes

# WHY: Browser-based forms need CSRF protection against cross-site attacks.
# But server-to-server API calls can't use CSRF tokens, so they use
# API key authentication instead.
```

### Database Configuration

```python
# 4. DATABASE SETUP (Lines 140-200)
try:
    # Primary: PostgreSQL (Supabase)
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
    
    # Connection test with timeout
    conn = psycopg2.connect(..., connect_timeout=10)
    conn.close()
    
    # Connection pooling for production
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_size': 5,
        'pool_timeout': 10,
        'pool_recycle': 1800,  # Recycle connections every 30 mins
        'max_overflow': 10,
        'connect_args': {
            'keepalives': 1,
            'keepalives_idle': 30,
        }
    }
except KeyError:
    # Fallback: SQLite for local development
    sqlite_path = os.path.join(os.path.dirname(__file__), 'app.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{sqlite_path}'

# WHY: Production uses PostgreSQL for scalability and reliability.
# SQLite fallback enables offline development without database setup.
# Connection pooling prevents exhausting database connections under load.
```

### Session Management

```python
# 5. SESSION CONFIGURATION (Lines 220-245)
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1)
app.config['SESSION_COOKIE_SECURE'] = is_production
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Production: Redis for sessions
if is_production and os.environ.get('REDIS_URL'):
    app.config['SESSION_TYPE'] = 'redis'
else:
    app.config['SESSION_TYPE'] = 'filesystem'

# WHY:
# - PERMANENT: Sessions persist across browser restarts
# - SECURE: Cookies only sent over HTTPS in production
# - HTTPONLY: JavaScript can't access cookies (prevents XSS)
# - SAMESITE: Prevents CSRF by restricting cookie sending
# - Redis: Enables session sharing across multiple server instances
```

### Blueprint Registration

```python
# 6. BLUEPRINT REGISTRATION (Lines 370-395)
app.register_blueprint(study_plan)        # Study plan generation
app.register_blueprint(bot_bp)            # AI tutor (Pawfessor Meowkins)
app.register_blueprint(flashcard_bp)      # Flashcard generation
app.register_blueprint(exambot_bp)        # Exam preparation bot
app.register_blueprint(game_bp)           # Educational games
app.register_blueprint(planning_bp)       # Exam planning
app.register_blueprint(studyroom_bp)      # Collaborative study rooms
app.register_blueprint(notes_bp, url_prefix='/notes')
app.register_blueprint(progress)          # Progress tracking
app.register_blueprint(purrrag_bp, url_prefix='/rag')  # RAG API

# WHY: Blueprints modularize the application into logical components.
# Each blueprint handles a specific domain (flashcards, exams, etc.)
# making the code maintainable and testable.
```

### User Loader

```python
# 7. USER LOADING (Lines 320-360)
@login_manager.user_loader
def load_user(user_id):
    try:
        with app.app_context():
            user = db.session.get(User, int(user_id))
            if user:
                return user
            
            # Auto-create debug user if none exist (development only)
            if User.query.count() == 0:
                debug_user = User(username="debuguser", email="debug@example.com")
                debug_user.set_password("password123")
                db.session.add(debug_user)
                db.session.commit()
            return None
    except Exception as e:
        # Return None on errors to force logout gracefully
        return None

# WHY: Flask-Login calls this on every request to identify the logged-in user.
# Error handling ensures database issues don't crash the application.
# Debug user creation simplifies development setup.
```

---

## Database Layer

### db.py - Database Configuration

```python
# SQLAlchemy instance creation
db = SQLAlchemy()

@contextmanager
def get_db_context():
    """Ensures database operations occur within Flask app context"""
    try:
        current_app._get_current_object()
        yield  # Already in context
    except RuntimeError:
        with current_app.app_context():
            yield

# WHY: SQLAlchemy requires Flask's application context for database operations.
# This context manager ensures operations always have the required context,
# whether called from a request handler or a background task.
```

### models.py - Data Models

#### User Model
```python
class User(UserMixin, db.Model):
    __tablename__ = 'app_user'  # Avoid PostgreSQL reserved word 'user'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    
    # RAG Configuration
    rag_short_term_quota = db.Column(db.Integer, default=1000)
    rag_long_term_quota = db.Column(db.Integer, default=4)
    rag_enabled = db.Column(db.Boolean, default=True)
    
    def set_password(self, password):
        # pbkdf2:sha256 for cross-platform compatibility
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# WHY:
# - UserMixin provides Flask-Login integration (is_authenticated, etc.)
# - pbkdf2:sha256 works across all platforms (scrypt has issues on some systems)
# - RAG quotas enable per-user resource limiting
```

#### StudyPlan Model
```python
class StudyPlan(db.Model):
    __tablename__ = 'study_plan'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('app_user.id'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    
    # JSON stored as Text for PostgreSQL compatibility
    topics = db.Column(db.Text, default='[]')
    detailed_schedule = db.Column(db.Text, default='[]')
    form_inputs_json = db.Column(db.JSON, default=lambda: {})
    
    is_revision_only = db.Column(db.Boolean, default=False)
    plan_summary = db.Column(db.Text, default='')
    exam_date = db.Column(db.Date, nullable=True)
    prep_start_date = db.Column(db.Date, nullable=True)
    
    @property
    def topics_data(self):
        """Deserialize JSON topics"""
        return json.loads(self.topics) if self.topics else []
    
    @topics_data.setter
    def topics_data(self, value):
        """Serialize topics to JSON"""
        self.topics = json.dumps(value) if value else None

# WHY:
# - Text columns for JSON data ensure PostgreSQL compatibility
# - Property decorators provide clean Python interface for JSON fields
# - Date fields enable calendar integration
```

#### StudyRoom & Real-time Models
```python
class StudyRoom(db.Model):
    __tablename__ = 'study_rooms'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    is_public = db.Column(db.Boolean, default=True)
    shared_notes = db.Column(db.Text, default="")
    timer_seconds = db.Column(db.Integer, default=0)
    
    # Relationships for real-time features
    snapshots = db.relationship('WhiteboardSnapshot', backref='room')
    logs = db.relationship('UserLog', backref='room')
    chat_messages = db.relationship('ChatMessage', back_populates='study_room')

class WhiteboardSnapshot(db.Model):
    __tablename__ = 'whiteboard_snapshots'
    
    id = db.Column(db.Integer, primary_key=True)
    snapshot = db.Column(db.JSON, nullable=False)  # Canvas state as JSON
    room_id = db.Column(db.Integer, db.ForeignKey('study_rooms.id', ondelete='CASCADE'))

# WHY:
# - Snapshots preserve whiteboard state for session recovery
# - CASCADE ensures orphan records are deleted when rooms are removed
# - Shared notes enable real-time collaborative editing
```

#### RAG Tracking Models
```python
class RAGIngestEvent(db.Model):
    """Tracks what content was ingested into the RAG system"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('app_user.id'))
    source = db.Column(db.String(50))  # chat, notes, study_plan
    content_id = db.Column(db.String(100), nullable=True)
    chunk_count = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class RAGUsageLog(db.Model):
    """Tracks RAG usage for quota enforcement"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('app_user.id'))
    query_type = db.Column(db.String(50))  # query, ingest, summarize
    tokens_used = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# WHY:
# - Audit trail for debugging RAG issues
# - Enable per-user usage quotas
# - Analytics for system optimization
```

---

## Authentication System

### Login Flow (app1.py)

```python
@app.route('/login', methods=['GET', 'POST'])
def login():
    # Store next parameter for post-login redirect
    next_page = request.args.get('next')
    if next_page:
        session['next_page'] = next_page
    
    if request.method == 'POST':
        username_or_email = request.form.get('username') or request.form.get('email')
        password = request.form.get('password')
        
        # Query by username OR email
        user = User.query.filter(
            (User.username == username_or_email) | (User.email == username_or_email)
        ).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user, remember=True)
            
            # Handle pending study plan data
            if 'next_page' in session:
                next_page = session.pop('next_page')
                if next_page == '/save-study-plan' and 'pending_study_plan' in session:
                    pending_data = session.pop('pending_study_plan')
                    session['study_plan'] = pending_data
                return redirect(next_page)
            
            return redirect('/dashboard')
        
        flash('Incorrect password. Please try again.')
    
    return render_template('login.html')

# WHY:
# - Flexible login: accepts username OR email
# - remember=True: creates persistent session cookie
# - next_page handling: preserves user intent through login flow
# - pending_study_plan: preserves unauthenticated work (great UX)
```

### Registration Flow

```python
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Check for duplicates
        if User.query.filter_by(email=email).first():
            flash('Email already exists.')
            return redirect(url_for('register'))
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists.')
            return redirect(url_for('register'))
        
        # Create user with secure password hashing
        new_user = User(email=email, username=username)
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()
        
        return redirect(url_for('login'))
    
    return render_template('register.html')

# WHY:
# - Duplicate checking prevents data integrity issues
# - set_password() centralizes hashing logic
# - Redirect to login after registration (common pattern)
```

---

## Blueprint Architecture

### Blueprint Overview

| Blueprint | File | Lines | Primary Functions |
|-----------|------|-------|-------------------|
| `bot_bp` | `blueprints/bot.py` | 2,740 | AI tutoring, RAG, PDF processing |
| `study_plan` | `blueprints/study_plan.py` | 2,857 | Study plan generation |
| `flashcard_bp` | `blueprints/flashcard.py` | 1,027 | Flashcard creation & search |
| `exambot_bp` | `blueprints/exambot.py` | 609 | Exam paper analysis with OCR |
| `studyroom_bp` | `blueprints/studyroom.py` | 355 | Real-time collaboration |
| `progress` | `blueprints/progress.py` | 159 | Progress tracking |
| `planning_bp` | `planning.py` | 163 | Exam date planning |
| `purrrag_bp` | `blueprints/purrrag_routes.py` | 393 | RAG API endpoints |
| `notes_bp` | `blueprints/notes.py` | ~80 | Note management |
| `game_bp` | `blueprints/game.py` | ~15 | Educational games |

---

## AI/ML Pipeline

### blueprints/bot.py - The Teaching Engine

#### Pawfessor Meowkins - The AI Tutor

```python
def generate_teaching_response(content, content_type, previous_context=None, session_id=None):
    """
    Core teaching engine using ReAct (Reason-Act-Observe) framework
    
    Content Types:
    - init_study_session: Start a new learning topic
    - chat: General tutoring questions
    - pdf: Teach from uploaded PDF
    - pdf_continuation: Continue teaching PDF content
    - code: Explain programming concepts
    - question: Answer specific questions
    - continuation: Continue previous topic
    """
    model = get_gemini_model()  # Gemini 2.0 Flash
    
    if content_type == "init_study_session":
        prompt = f"""
        You are Pawfessor Meowkins, a friendly AI tutor cat 🐾.
        
        --- GUARDRAILS FOR SUBJECT VALIDATION ---
        1. VALIDATE SUBJECT APPROPRIATENESS
        2. CHECK SUBJECT SPECIFICITY
        3. EDUCATIONAL FOCUS ASSURANCE
        
        --- INTRODUCTION FRAMEWORK ---
        Create an engaging introduction...
        
        Format your final response as JSON:
        {{
          "response": "...",
          "buttons": ["Continue Learning", "I Have a Question"],
          "context": {{
            "current_section": "Introduction",
            "next_section": "Core Concepts",
            "subject": "{content}"
          }}
        }}
        """

# WHY this structure:
# - Guardrails prevent misuse (inappropriate requests)
# - ReAct framework ensures systematic teaching
# - JSON response enables structured UI rendering
# - Buttons guide user interaction (wizard-like flow)
```

#### PDF Progress Management

```python
def manage_pdf_progress(session_id, action, content=None, response=None, topic=None):
    """
    Manages chunked reading of PDFs for continuous teaching
    
    Actions:
    - 'init': Start new PDF session, chunk content
    - 'get': Retrieve current progress
    - 'update': Store AI response for context
    - 'advance': Move to next chunk
    """
    global pdf_progress  # Session-based storage
    
    if action == 'init':
        chunk_size = 3000  # Characters per chunk
        overlap = 500      # Overlap for context continuity
        
        pdf_progress[session_id] = {
            "topic": topic,
            "content": content,
            "offset": 0,
            "chunk_size": chunk_size,
            "overlap": overlap,
            "previous_responses": [],  # For context window
            "extracted_topics": [],
            "current_section": "Introduction"
        }
        return content[:chunk_size]  # Return first chunk
    
    elif action == 'advance':
        info = pdf_progress[session_id]
        next_offset = info["offset"] + info["chunk_size"] - info["overlap"]
        
        if next_offset >= len(info["content"]):
            return None  # End of document
        
        pdf_progress[session_id]["offset"] = next_offset
        next_chunk = info["content"][next_offset:next_offset + info["chunk_size"]]
        
        # Auto-detect section headings
        section_patterns = [
            r'#+\s+(.*?)\n',           # Markdown headers
            r'(.*?)\n[=\-]{3,}',        # Underlined headers
            r'(?i)^(?:chapter|section)\s+\d+'  # Chapter markers
        ]
        # ... pattern matching ...
        
        return next_chunk

# WHY:
# - Chunking prevents context window overflow
# - Overlap maintains continuity between chunks
# - Response history provides conversation context
# - Section detection enables progress tracking
```

#### Roadmap Tool (Content Structuring)

```python
def roadmap_tool(document, session_id=None):
    """
    Creates a teaching roadmap by detecting document structure
    """
    # Detect sections using multiple patterns
    section_patterns = [
        r'#+\s+(.*?)\n',                    # Markdown: # Header
        r'(.*?)\n[=\-]{3,}',                # Underlined headers
        r'(?i)^(?:chapter|section)\s+\d+',  # Chapter 1: ...
        r'(?i)^\d+\.\d*\s+(.*?)$'           # 1.2 Topic
    ]
    
    # If no sections found, create artificial chunks
    if not matches:
        chunk_size = 3000
        sections = [{
            "title": f"Section {i+1}",
            "chunks": [document[i:i+chunk_size]]
        } for i in range(0, len(document), chunk_size)]
    
    # Store roadmap in session
    if session_id in pdf_progress:
        pdf_progress[session_id]["roadmap"] = {
            "sections": sections,
            "current_section_index": 0,
            "current_chunk_index": 0
        }
    
    return {"sections": sections}

# WHY:
# - Structured navigation improves learning experience
# - Multiple patterns handle various document formats
# - Fallback chunking ensures any document can be taught
```

### RAG (Retrieval Augmented Generation) System

#### Qdrant Vector Storage

```python
# blueprints/bot.py - Collection Creation
def create_chat_collection(user_id):
    """Create per-user vector collection"""
    collection_name = f"chat_{user_id}"
    vector_size = 384  # MiniLM embedding dimension
    
    qdrant_client.create_collection(
        collection_name=collection_name,
        vectors_config=models.VectorParams(
            size=vector_size,
            distance=models.Distance.COSINE
        ),
        sparse_vectors_config={
            "text": models.SparseVectorParams(
                index=models.SparseIndexParams(on_disk=True),
            ),
        }
    )
    
    # Create indexes for fast filtering
    qdrant_client.create_payload_index(collection_name, "timestamp", PayloadSchemaType.DATETIME)
    qdrant_client.create_payload_index(collection_name, "role", PayloadSchemaType.KEYWORD)
    qdrant_client.create_payload_index(collection_name, "topic", PayloadSchemaType.KEYWORD)

# WHY:
# - Per-user collections ensure data isolation
# - COSINE distance is standard for text similarity
# - Sparse vectors enable keyword search alongside semantic search
# - Indexes accelerate filtered queries
```

#### Embedding Creation

```python
# utils/embedding_utils.py
def create_embedding(text):
    """Create vector embedding for text"""
    if not text or len(text.strip()) == 0:
        return np.zeros(384, dtype=np.float32)  # Zero vector for empty text
    
    model = get_embedding_model()  # SentenceTransformer
    embedding = model.encode(text)
    
    # Validation
    if np.isnan(embedding).any() or np.isinf(embedding).any():
        embedding = np.random.rand(384).astype(np.float32)  # Fallback
    
    return embedding

def split_text(text, chunk_size=500, overlap=50):
    """Split text into semantically meaningful chunks"""
    chunks = []
    start = 0
    
    while start < len(text):
        end = min(start + chunk_size, len(text))
        
        # Find sentence boundary (., !, ?)
        sentence_end = max(
            text.rfind('.', start, end),
            text.rfind('!', start, end),
            text.rfind('?', start, end)
        )
        
        if sentence_end > start + chunk_size // 2:
            end = sentence_end + 1
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        
        start = end - overlap  # Overlap for context
    
    return chunks

# WHY:
# - Sentence boundaries preserve semantic meaning
# - Overlap ensures no information is lost between chunks
# - Zero vectors handle edge cases gracefully
# - Validation prevents NaN/Inf corrupting the index
```

#### Semantic Search

```python
def semantic_search_chat(user_id, query, top_k=5, filters=None):
    """Search chat history using vector similarity"""
    collection_name = f"chat_{user_id}"
    
    # Create query embedding
    query_embedding = embedding_model.encode(query).tolist()
    
    # Build filter for Qdrant
    filter_obj = None
    if filters:
        conditions = [
            FieldCondition(key=field, match=MatchValue(value=value))
            for field, value in filters.items()
        ]
        filter_obj = Filter(must=conditions)
    
    # Execute search
    results = qdrant_client.search(
        collection_name=collection_name,
        query_vector=query_embedding,
        query_filter=filter_obj,
        limit=top_k,
        with_payload=True
    )
    
    return [{
        "score": r.score,
        "role": r.payload.get("role"),
        "message": r.payload.get("message"),
        "summary": r.payload.get("summary"),
        "topic": r.payload.get("topic")
    } for r in results]

# WHY:
# - Semantic search finds relevant context even with different wording
# - Filters enable scoping (e.g., only assistant responses)
# - Payload includes all metadata for context reconstruction
```

---

## Flashcard System

### blueprints/flashcard.py

```python
def generate_flashcards_with_gemini(topic, card_type, card_count, pdf_text=''):
    """Generate flashcards using Gemini AI"""
    model = get_gemini_model()
    
    # Determine content source
    source_type = "pdf" if pdf_text and len(pdf_text) > 100 else "topic"
    
    if card_type == 'qna':
        prompt = f"""
        Create {card_count} educational flashcards in Q&A format about: {topic}.
        
        {"Use ONLY information from:" if source_type == "pdf" else ""}
        {pdf_text[:5000] if source_type == "pdf" else ""}
        
        Format as JSON array:
        [
          {{"question": "...", "answer": "..."}}
        ]
        """
    elif card_type == 'definition':
        prompt = f"""
        Create {card_count} term-definition flashcards about: {topic}.
        Format: [{{"term": "...", "definition": "..."}}]
        """
    elif card_type == 'bullet':
        prompt = f"""
        Create {card_count} concept-bullets flashcards about: {topic}.
        Format: [{{"concept": "...", "bullets": ["...", "..."]}}]
        """
    
    response = model.generate_content(prompt)
    return parse_flashcards_json(response.text)

# WHY:
# - Multiple card types suit different learning styles
# - PDF integration creates personalized cards
# - JSON format ensures structured, parseable output
```

#### Flashcard Storage in Qdrant

```python
def insert_flashcards(user_id, flashcards, metadata=None):
    """Store flashcards with embeddings for semantic search"""
    collection_name = get_collection_name(user_id)  # flashcards_{user_id}
    
    for flashcard in flashcards:
        # Create searchable text from card content
        if card_type == 'qna':
            content_text = f"Q: {flashcard['question']}\nA: {flashcard['answer']}"
        elif card_type == 'definition':
            content_text = f"Term: {flashcard['term']}\nDef: {flashcard['definition']}"
        
        # Generate embedding
        embedding = create_embedding(content_text)
        
        # Deduplication via content hash
        content_hash = hashlib.md5(content_text.encode()).hexdigest()
        point_id = str(uuid.uuid5(uuid.NAMESPACE_OID, f"{user_id}:{content_hash}"))
        
        # Store in Qdrant
        qdrant_client.upsert(
            collection_name=collection_name,
            points=[PointStruct(
                id=point_id,
                vector=embedding,
                payload={
                    "user_id": str(user_id),
                    "card_type": card_type,
                    "topic": metadata.get('topic'),
                    "card_front": card_front,
                    "card_back": card_back,
                    "content_hash": content_hash
                }
            )]
        )

# WHY:
# - Embeddings enable "find similar cards" functionality
# - Content hashing prevents duplicate cards
# - Deterministic IDs allow upserts (update or insert)
```

---

## ExamBot - Exam Paper Analysis

### blueprints/exambot.py

```python
@exambot_bp.route('/process_exam', methods=['POST'])
@login_required
def process_exam():
    """Process uploaded exam paper (PDF or image)"""
    file = request.files['exam_file']
    file_type = file.filename.split('.')[-1].lower()
    
    if file_type == 'pdf':
        # Try PyMuPDF first (better quality)
        try:
            pdf_document = fitz.open(file_path)
            for page in pdf_document:
                exam_text += page.get_text() + "\n\n"
        except:
            # Fallback to PyPDF2
            reader = PyPDF2.PdfReader(file_path)
            for page in reader.pages:
                exam_text += page.extract_text() + "\n\n"
        
        # If minimal text, PDF is likely scanned - use OCR
        if len(exam_text.strip()) < 100:
            for page in pdf_document:
                # Render page as image
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom
                pix.save(img_path)
                
                # OCR the rendered page
                exam_text += extract_text_from_image(img_path) + "\n\n"
    
    elif file_type in ['jpg', 'jpeg', 'png']:
        exam_text = extract_text_from_image(file_path)
    
    # Create session for conversation
    session_id = f"exam_{uuid.uuid4().hex}"
    exam_sessions[session_id] = {
        'subject': subject,
        'exam_text': exam_text,
        'chat_history': [],
        'ocr_used': True
    }
    
    return jsonify({
        "success": True,
        "session_id": session_id,
        "extractedText": exam_text
    })

# WHY:
# - Multiple extraction methods handle different PDF types
# - OCR fallback handles scanned documents
# - Session storage enables conversational exam analysis
```

#### EasyOCR Integration

```python
# Global reader for reuse (initialization is expensive)
_ocr_reader = None

def get_ocr_reader():
    global _ocr_reader
    if _ocr_reader is None:
        _ocr_reader = easyocr.Reader(['en'], gpu=False)
    return _ocr_reader

def extract_text_from_image(image_path):
    """Extract text from image using EasyOCR"""
    img = Image.open(image_path)
    if img.mode != 'RGB':
        img = img.convert('RGB')
    
    reader = get_ocr_reader()
    results = reader.readtext(np.array(img))
    
    extracted_text = ""
    for detection in results:
        text, confidence = detection[1], detection[2]
        if confidence > 0.3:  # Filter low-confidence results
            extracted_text += text + " "
    
    return extracted_text.strip()

# WHY:
# - Global reader avoids repeated model loading
# - Confidence threshold filters noise
# - RGB conversion ensures compatibility
# - gpu=False ensures CPU-only operation (deployment compatibility)
```

---

## Real-Time Features

### blueprints/studyroom.py

```python
def register_studyroom_socket_events(socketio):
    """Register WebSocket event handlers for study rooms"""
    
    @socketio.on('join_room')
    def handle_join(data):
        room_name = data['room']
        username = data.get('username', current_user.username)
        
        join_room(room_name)
        
        room = StudyRoom.query.filter_by(name=room_name).first()
        if room:
            # Send existing state to new user
            emit('load_shared_notes', {'content': room.shared_notes}, room=request.sid)
            
            # Load whiteboard snapshot
            last_snapshot = WhiteboardSnapshot.query.filter_by(room_id=room.id)\
                .order_by(WhiteboardSnapshot.timestamp.desc()).first()
            if last_snapshot:
                emit('load_whiteboard', {'snapshot': last_snapshot.snapshot['image']}, 
                     room=request.sid)
            
            # Load chat history
            messages = ChatMessage.query.filter_by(room_id=room.id)\
                .order_by(ChatMessage.timestamp.asc()).limit(50).all()
            emit('chat_history', [msg.to_dict() for msg in messages], room=request.sid)
            
            # Log join event
            log = UserLog(username=username, room_id=room.id, action='join')
            db.session.add(log)
            db.session.commit()
            
            # Broadcast to others
            emit('user_event', {'username': username, 'event': 'joined'}, room=room_name)
    
    @socketio.on('notes_update')
    def handle_notes_update(data):
        """Broadcast note changes to all room members"""
        room_name = data['room']
        content = data['content']
        
        # Persist to database
        room = StudyRoom.query.filter_by(name=room_name).first()
        if room:
            room.shared_notes = content
            db.session.commit()
        
        # Broadcast to all clients in room
        emit('notes_update', {'content': content}, room=room_name)
    
    @socketio.on('draw')
    def handle_draw(data):
        """Broadcast whiteboard drawing events"""
        emit('draw', data, room=data['room'])
    
    @socketio.on('save_snapshot')
    def handle_save_snapshot(data):
        """Persist whiteboard state"""
        room = StudyRoom.query.filter_by(name=data['room']).first()
        if room:
            snapshot = WhiteboardSnapshot(
                room_id=room.id,
                snapshot={'image': data['snapshot']}
            )
            db.session.add(snapshot)
            db.session.commit()

# WHY:
# - Socket.IO enables real-time bidirectional communication
# - Room-based broadcasting limits message scope
# - Database persistence enables session recovery
# - User logging creates activity audit trail
```

---

## Study Plan Generation

### blueprints/study_plan.py

```python
def store_study_plan_in_qdrant(user_id, plan_id, topics, detailed_schedule):
    """Store study plan in vector database for RAG"""
    collection_name = get_collection_name(user_id)  # studyplan_{user_id}
    
    # Check for duplicates
    search_filter = Filter(must=[
        FieldCondition(key="plan_id", match=MatchValue(value=str(plan_id)))
    ])
    existing = qdrant_client.count(collection_name, count_filter=search_filter)
    if existing.count > 0:
        return True  # Already indexed
    
    # Index topics
    for topic in topics:
        content = f"""
        Topic: {topic['name']}
        Importance: {topic['importance']}/10
        Key points: {', '.join(topic.get('key_points', []))}
        """
        
        embedding = create_embedding(content)
        qdrant_client.upsert(collection_name, points=[
            PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload={
                    "plan_id": str(plan_id),
                    "type": "topic",
                    "topic": topic['name'],
                    "importance": topic['importance']
                }
            )
        ])
    
    # Index schedule activities
    for day in detailed_schedule:
        for activity in day.get('activities', []):
            content = f"""
            Activity: {activity['title']}
            Day: {day['date']}
            Time: {activity.get('time_slot', '')}
            """
            
            embedding = create_embedding(content)
            qdrant_client.upsert(collection_name, points=[
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=embedding,
                    payload={
                        "plan_id": str(plan_id),
                        "type": "schedule_activity",
                        "day": day['date'],
                        "topic": activity.get('topic', '')
                    }
                )
            ])

# WHY:
# - Vector storage enables "What should I study today?" queries
# - Duplicate checking prevents index bloat
# - Structured payloads enable filtered searches
```

### Study Tools Module

```python
# blueprints/study_tools.py

def topic_ranker_tool(topics, ranking_method='importance'):
    """Order topics by importance for study prioritization"""
    if ranking_method == 'importance':
        return sorted(topics, key=lambda x: x.get('importance', 0), reverse=True)
    elif ranking_method == 'difficulty':
        return sorted(topics, key=lambda x: x.get('difficulty', 0), reverse=True)
    elif ranking_method == 'combined':
        return sorted(topics, 
            key=lambda x: x.get('importance', 5) * 0.7 + x.get('difficulty', 5) * 0.3,
            reverse=True)

def topic_time_estimator(inputs):
    """Estimate study time per topic"""
    base_times = {
        1: 20, 2: 25, 3: 30, 4: 35, 5: 45,
        6: 55, 7: 65, 8: 80, 9: 95, 10: 120
    }  # Minutes based on importance
    
    for topic in inputs.get('topics', []):
        importance = topic.get('importance', 5)
        base_time = base_times.get(importance, 45)
        
        # Adjust for user-provided difficulty
        if user_difficulty := inputs.get('user_difficulty_ratings', {}).get(topic['name']):
            difficulty_multiplier = 0.7 + (user_difficulty / 10 * 0.6)
            base_time *= difficulty_multiplier
        
        topic['estimated_minutes'] = int(base_time)
    
    return inputs['topics']

def schedule_tool(topics, start_date, end_date, hours_per_day=4):
    """Create daily study schedule"""
    # Calculate available days
    days = (end_date - start_date).days
    total_minutes = days * hours_per_day * 60
    
    # Distribute time across topics
    schedule = []
    for day in range(days):
        date = start_date + timedelta(days=day)
        daily_activities = []
        
        # Assign topics to time slots
        # ... scheduling logic ...
        
        schedule.append({
            "date": date.strftime('%Y-%m-%d'),
            "activities": daily_activities
        })
    
    return schedule

# WHY:
# - Time estimation creates realistic expectations
# - Difficulty adjustment personalizes the experience
# - Combined ranking balances importance and difficulty
```

---

## Utility Modules

### utils/model_loader.py - Lazy Loading

```python
from functools import lru_cache

_embedding_model = None

@lru_cache(maxsize=2)
def get_embedding_model():
    """Lazily load embedding model on first use"""
    global _embedding_model
    
    if _embedding_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _embedding_model = SentenceTransformer('paraphrase-MiniLM-L3-v2')
        except Exception as e:
            _embedding_model = MockEmbeddingModel()
    
    return _embedding_model

class MockEmbeddingModel:
    """Fallback for when real model fails to load"""
    def encode(self, texts, **kwargs):
        import numpy as np
        if isinstance(texts, str):
            return np.random.rand(384)
        return np.random.rand(len(texts), 384)

# WHY:
# - Lazy loading reduces startup time
# - lru_cache prevents repeated loading
# - Mock fallback ensures graceful degradation
```

### utils/gemini_utils.py

```python
def get_gemini_model():
    """Get configured Gemini model instance"""
    from flask import current_app
    try:
        if hasattr(current_app, 'genai'):
            return current_app.genai.GenerativeModel('gemini-2.0-flash')
        else:
            import google.generativeai as genai
            api_key = os.environ.get('GEMINI_API_KEY')
            genai.configure(api_key=api_key)
            return genai.GenerativeModel('gemini-2.0-flash')
    except Exception as e:
        return None

def generate_teaching_response(content, content_type, previous_context=None, session_id=None):
    """Generate AI teaching response based on content type"""
    model = get_gemini_model()
    
    prompts = {
        "chat": f"""
            Act as Pawfessor Meowkins...
            Topic: {content}
            Use analogies, keep under 200 words...
        """,
        "pdf": f"""
            Teach from this PDF content...
            {content[:3000]}
        """,
        # ... more prompt templates ...
    }
    
    response = model.generate_content(prompts.get(content_type, prompts['chat']))
    return response.text

# WHY:
# - App context caching avoids repeated API configuration
# - Content-type routing enables specialized prompts
# - Character limiting prevents token overflow
```

### Compatibility Patches

```python
# compatibility_patch.py
import collections
import collections.abc

# Fix for Python 3.10+ where collections.MutableMapping was removed
if not hasattr(collections, 'MutableMapping'):
    collections.MutableMapping = collections.abc.MutableMapping

for name in ['Mapping', 'Sequence', 'Iterable', 'Iterator', 'Container']:
    if hasattr(collections.abc, name) and not hasattr(collections, name):
        setattr(collections, name, getattr(collections.abc, name))

# WHY: Many older packages (especially those Flask depends on) still
# import from collections instead of collections.abc. This patch
# maintains backward compatibility.
```

```python
# eventlet_patch.py
import sys
import eventlet

if sys.version_info >= (3, 11):
    # Fix TimeoutError immutability issue
    class SocketTimeoutWrapper(socket.timeout):
        is_timeout = True
    
    original_wrap = eventlet.timeout.wrap_is_timeout
    
    def patched_wrap_is_timeout(base):
        if base is TimeoutError:
            return SocketTimeoutWrapper
        return original_wrap(base)
    
    eventlet.timeout.wrap_is_timeout = patched_wrap_is_timeout

# WHY: Python 3.11 made TimeoutError immutable, breaking eventlet's
# monkey-patching. This creates a wrapper class instead.
```

---

## Security Implementation

### CSRF Protection

```python
# app1.py
csrf = CSRFProtect(app)

# Exempt server-to-server APIs (they use API key auth)
csrf.exempt('purrrag.ingest_text')
csrf.exempt('purrrag.query_rag')

# Custom check function
def csrf_check_function():
    if request.path in ['/rag/ingest', '/rag/query']:
        api_key = request.headers.get('X-API-Key')
        if api_key == os.environ.get('SERVER_API_KEY'):
            return False  # Skip CSRF
    return True

app.config['WTF_CSRF_METHODS'] = ['POST', 'PUT', 'PATCH', 'DELETE']
app.config['WTF_CSRF_TIME_LIMIT'] = 3600  # 1 hour token lifetime
```

### API Key Authentication

```python
@app.before_request
def api_authentication_for_exempt_routes():
    if request.path in ['/rag/ingest', '/rag/query', '/direct-rag-ingest']:
        api_key = request.headers.get('X-API-Key')
        expected_key = os.environ.get('SERVER_API_KEY')
        
        # Allow localhost in development
        if not expected_key and request.remote_addr in ['127.0.0.1', 'localhost']:
            return None
        
        if not api_key or api_key != expected_key:
            return jsonify({"error": "Unauthorized"}), 401
    
    return None
```

### Security Headers

```python
@app.after_request
def add_security_headers(response):
    if os.environ.get('FLASK_ENV') == 'production':
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response

# Session security
app.config['SESSION_COOKIE_SECURE'] = is_production  # HTTPS only
app.config['SESSION_COOKIE_HTTPONLY'] = True         # No JS access
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'        # CSRF protection
```

---

## API Endpoints Reference

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET/POST | `/login` | User login |
| GET/POST | `/register` | User registration |
| GET | `/logout` | User logout |

### Dashboard & Navigation
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Landing page |
| GET | `/dashboard` | User dashboard |
| GET | `/features` | Features page |
| GET | `/profile` | User profile |

### AI Tutor (bot_bp)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/bot` | Bot interface |
| POST | `/bot/chat` | Send message to AI tutor |
| POST | `/bot/upload-pdf` | Upload PDF for teaching |
| POST | `/bot/continue` | Continue learning session |

### Study Plans (study_plan)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/studyplan` | Study plan interface |
| POST | `/generate-plan` | Generate new study plan |
| GET | `/studyplan-live/<id>` | Live study plan view |
| POST | `/save-study-plan` | Save generated plan |

### Flashcards (flashcard_bp)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/flashcard` | Flashcard interface |
| POST | `/flashcard/generate` | Generate flashcards |
| GET | `/flashcard/search` | Search flashcards |
| POST | `/flashcard/search-api` | API search endpoint |

### ExamBot (exambot_bp)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/exambot` | ExamBot interface |
| POST | `/process_exam` | Upload exam paper |
| POST | `/exam_chat` | Chat about exam |

### Study Rooms (studyroom_bp)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/rooms` | List study rooms |
| GET | `/room/<name>` | Join specific room |
| POST | `/create-room` | Create new room |

### RAG API (purrrag_bp)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/rag/ingest` | Ingest content |
| POST | `/rag/query` | Query RAG system |

### Progress (progress)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/progress` | Progress dashboard |
| POST | `/add_exam` | Add exam to tracker |
| POST | `/update_exam/<id>` | Update exam progress |

---

## Deployment Configuration

### requirements.txt (Key Dependencies)
```
Flask==2.2.3
flask-socketio
Flask-Login==0.6.2
Flask-SQLAlchemy==3.0.3
gunicorn==20.1.0
eventlet==0.33.3
psycopg2-binary
google-generativeai==0.3.1
sentence-transformers>=2.7.0
qdrant-client
PyPDF2==3.0.1
PyMuPDF==1.22.3
easyocr==1.7.1
torch>=2.0.1
```

### Environment Variables
```bash
# Required
DATABASE_URL=postgresql://user:pass@host:5432/db
GEMINI_API_KEY=your_gemini_api_key
SECRET_KEY=your_secret_key

# Optional
QDRANT_URL=https://your-qdrant-cluster.aws.cloud.qdrant.io
QDRANT_API_KEY=your_qdrant_api_key
REDIS_URL=redis://localhost:6379
SERVER_API_KEY=your_api_key_for_server_to_server
FLASK_ENV=production
```

### Render Deployment (render.yaml)
```yaml
services:
  - type: web
    name: purrfect
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn --worker-class eventlet -w 1 app1:app
```

---

## Summary

Purrfect AI is a sophisticated educational platform that demonstrates:

1. **Modular Architecture**: 12 Flask blueprints for maintainability
2. **Multi-Model AI Pipeline**: Gemini for generation, SentenceTransformers for embeddings
3. **RAG Implementation**: Qdrant vector database for semantic search
4. **Real-Time Collaboration**: Socket.IO for study rooms
5. **Robust Security**: CSRF, API keys, secure sessions
6. **Graceful Degradation**: Fallbacks for database, models, and services
7. **Cross-Platform Compatibility**: Patches for Python 3.10+/3.11+ and Windows

The system successfully combines these technologies to deliver a unified studying experience that replaces multiple standalone tools (ChatGPT, Notion, Quizlet) with a single, personalized platform.
