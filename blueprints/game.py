from flask import Blueprint, render_template, session, redirect, url_for, flash
from flask_login import login_required, current_user

# Create game blueprint
game_bp = Blueprint('game', __name__)

@game_bp.route('/game')
@login_required  # This decorator will use the login_manager.login_view value
def game_page():
    """Display the game interface"""
    return render_template('game.html', user=current_user)
