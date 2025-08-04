from app1 import app, db, User
from werkzeug.security import generate_password_hash
import getpass

def reset_passwords():
    """Utility to reset passwords for users with incompatible hashes"""
    with app.app_context():
        users = User.query.all()
        print(f"Found {len(users)} user(s)")
        
        for user in users:
            print(f"\nUser: {user.username}")
            choice = input("Reset password for this user? (y/n): ").lower()
            
            if choice == 'y':
                new_password = getpass.getpass("Enter new password: ")
                confirm_password = getpass.getpass("Confirm password: ")
                
                if new_password != confirm_password:
                    print("Passwords don't match! Skipping this user.")
                    continue
                
                # Update with compatible hash
                user.password_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
                db.session.commit()
                print(f"Password updated for {user.username}")
            else:
                print(f"Skipping {user.username}")

if __name__ == "__main__":
    reset_passwords()
