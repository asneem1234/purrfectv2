import os
import uuid

from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    flash,
    current_app
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from werkzeug.utils import secure_filename

from flask_login import (
    login_user,
    logout_user,
    login_required
)

from models import User, db

auth = Blueprint("auth", __name__)

ALLOWED_SCHEDULE_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "doc", "docx"}


def allowed_schedule_file(filename):
    return (
        filename
        and "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in ALLOWED_SCHEDULE_EXTENSIONS
    )


@auth.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        username = request.form.get("username", "").strip()

        password = request.form.get("password", "")
        confirm_password = request.form.get(
            "confirm_password",
            ""
        )

        school_name = request.form.get(
            "school_name",
            ""
        ).strip()

        course_name = request.form.get(
            "course_name",
            ""
        ).strip()

        semester = request.form.get(
            "semester",
            ""
        ).strip()

        schedule_file = request.files.get(
            "enrollment_schedule"
        )

        if not email or not username or not password:
            flash("Please complete all required account fields.")
            return redirect(url_for("auth.register"))

        if password != confirm_password:
            flash("Passwords do not match.")
            return redirect(url_for("auth.register"))

        if not school_name:
            flash("Please enter your school name.")
            return redirect(url_for("auth.register"))

        if not course_name:
            flash("Please enter your course name.")
            return redirect(url_for("auth.register"))

        if not semester:
            flash("Please select your semester.")
            return redirect(url_for("auth.register"))

        user_email = User.query.filter_by(
            email=email
        ).first()

        user_username = User.query.filter_by(
            username=username
        ).first()

        if user_email:
            flash("Email already exists.")
            return redirect(url_for("auth.register"))

        if user_username:
            flash("Username already exists.")
            return redirect(url_for("auth.register"))

        schedule_filename = None

        if schedule_file and schedule_file.filename:
            original_filename = secure_filename(
                schedule_file.filename
            )

            allowed_extensions = {
                "pdf",
                "png",
                "jpg",
                "jpeg",
                "doc",
                "docx"
            }

            extension = original_filename.rsplit(
                ".",
                1
            )[-1].lower()

            if extension not in allowed_extensions:
                flash("Invalid schedule file type.")
                return redirect(url_for("auth.register"))

            schedule_filename = (
                f"{uuid.uuid4().hex}.{extension}"
            )

            upload_folder = os.path.join(
                current_app.root_path,
                "uploads",
                "enrollment_schedules"
            )

            os.makedirs(
                upload_folder,
                exist_ok=True
            )

            schedule_file.save(
                os.path.join(
                    upload_folder,
                    schedule_filename
                )
            )

        new_user = User(
            email=email,
            username=username,
            password_hash=generate_password_hash(
                password,
                method="pbkdf2:sha256"
            ),
            school_name=school_name,
            course_name=course_name,
            semester=semester,
            enrollment_schedule_filename=schedule_filename
        )

        db.session.add(new_user)
        db.session.commit()

        flash("Account created successfully.")
        return redirect(url_for("auth.login"))

    return render_template("register.html")