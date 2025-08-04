from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required

main = Blueprint('main', __name__)

@main.route('/')
def landing():
    return render_template('landingpage.html')

@main.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@main.route('/features')
def features():
    return render_template('features.html')

@main.route('/planning')
@login_required
def planning():
    return render_template('planning.html')

@main.route('/progress')
@login_required
def progress():
    return render_template('progress.html')

@main.route('/notes-coming-soon')
@login_required
def notes_coming_soon():
    return render_template('notes-coming-soon.html')
