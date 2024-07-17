from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user
from .models import Group, Expense
from . import db

views = Blueprint('views', __name__)

# ... (other imports)

@views.route('/')
@login_required
def dashboard():
    user_groups = current_user.groups
    return render_template('dashboard.html') 


@views.route('/create_group', methods=['GET', 'POST'])
@login_required
def create_group():
    if request.method == 'POST':
        group_name = request.form['group_name']
        group_description = request.form['group_description']

        # Create new group and add the current user as a member
        new_group = Group(name=group_name, description=group_description)
        new_group.members.append(current_user) 
        db.session.add(new_group)
        db.session.commit()

        flash('Group created successfully!', 'success')
        return redirect(url_for('views.dashboard'))

    return render_template('create_group.html') 

# ... (other routes for group creation, expense adding, etc.)
