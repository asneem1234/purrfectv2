from app1 import app
from models import db, Exam
from datetime import datetime

def migrate_exams_table():
    """
    Creates the exams table in the database if it doesn't exist
    """
    with app.app_context():
        # Check if table exists
        inspector = db.inspect(db.engine)
        if 'exams' not in inspector.get_table_names():
            print("Creating exams table...")
            db.create_all()
            print("Exams table created successfully!")
        else:
            print("Exams table already exists.")

if __name__ == "__main__":
    migrate_exams_table()
