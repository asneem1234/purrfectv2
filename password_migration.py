from app1 import app, db, User
from flask import Flask
from werkzeug.security import generate_password_hash
import getpass

def migrate_user_passwords():
    """
    Utility to help reset passwords for users with incompatible password hashes.
    Run this script directly to update passwords.
    """
    with app.app_context():
        print("Password Migration Utility")
        print("=========================")
        
        # Get all users
        users = User.query.all()
        print(f"Found {len(users)} users in the database")
        
        for user in users:
            print(f"\nUser: {user.username} (Email: {user.email})")
            print("Options:")
            print("1. Reset password")
            print("2. Skip this user")
            choice = input("Enter option (1/2): ")
            
            if choice == "1":
                # Reset the password using pbkdf2
                new_password = getpass.getpass("Enter new password: ")
                confirm_password = getpass.getpass("Confirm new password: ")
                
                if new_password != confirm_password:
                    print("Passwords don't match. Skipping this user.")
                    continue
                
                # Update password with the compatible hashing method
                user.password_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
                db.session.commit()
                print(f"Password for {user.username} has been updated.")
            else:
                print(f"Skipping {user.username}")
        
        print("\nPassword migration completed.")

if __name__ == "__main__":
    migrate_user_passwords()
