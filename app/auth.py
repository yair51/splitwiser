from flask import Blueprint, render_template, redirect, url_for, request, flash, session, abort, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from .models import User, Invitation
from . import db
from app.helpers import send_email
from app import login_manager
from itsdangerous import URLSafeTimedSerializer  # For generating and verifying tokens
from datetime import datetime


auth = Blueprint('auth', __name__)


@login_manager.user_loader  # Add this decorator
def load_user(user_id):
    """User loader callback for Flask-Login."""
    return User.query.get(int(user_id))

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user, remember=True)
            return redirect(url_for('views.dashboard'))
        else:
            flash('Invalid email or password', 'danger')
    return render_template('login.html')


@auth.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))


@auth.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        password = request.form['password']
        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'danger')
        else:
            new_user = User(email=email, first_name=first_name, last_name=last_name, password=generate_password_hash(password, method='pbkdf2:sha256'))
            db.session.add(new_user)
            db.session.commit()
            # Check for invitation token in the session
        invitation_token = session.pop('invitation_token', None)  
        if invitation_token:
            invitation = Invitation.query.filter_by(token=invitation_token).first()
            if invitation:
                # If found an invitation, log in user and add them to the group
                login_user(new_user, remember=True)
                group = invitation.group
                group.members.append(new_user)
                db.session.delete(invitation)  # Delete the used invitation
                db.session.commit()
                flash(f'Account created and you have been added to {group.name}!', 'success')
                return redirect(url_for('views.group_details', group_id=group.id))
        # If no token, or invalid token, redirect to dashboard
        else:
            login_user(new_user, remember=True)
            flash('Account created successfully!', 'success')
        return redirect(url_for('views.dashboard'))

    return render_template('register.html')


@auth.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        user = User.query.filter_by(email=email).first()
        # Send email 
        if user:
            token = generate_reset_token(user.id)
            send_email('Splitwiser Password Reset', [email], 'email/reset_password.html', user=user, token=token)
            flash('A password reset link has been sent to your email.', 'info')
        else:
            flash('Email not found.', 'danger')
    return render_template('forgot_password.html')


# Generates a reset token
def generate_reset_token(user_id):
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    return serializer.dumps(user_id, salt='password-reset-salt')


@auth.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        user_id = serializer.loads(token, salt='password-reset-salt', max_age=3600)  # 1 hour expiration
    except:
        flash('Invalid or expired token.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    user = User.query.get(user_id)
    if not user:
        abort(404)  # User not found

    if request.method == 'POST':
        new_password = request.form['new_password']
        # (Add password validation here)
        user.password = generate_password_hash(new_password, method='pbkdf2:sha256')
        db.session.commit()
        flash('Your password has been updated. You can now log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('reset_password.html', token=token)

