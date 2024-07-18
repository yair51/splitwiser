from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user
from flask_mail import Message
from .models import Group, Expense, Invitation
from . import db, mail
import datetime
import secrets

views = Blueprint('views', __name__)

# ... (other imports)

@views.route('/')
@login_required
def dashboard():
    user_groups = current_user.groups
    return render_template('dashboard.html', groups=user_groups) 


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



@views.route('/group/<int:group_id>')
@login_required
def group_details(group_id):
    group = Group.query.get_or_404(group_id)

    # Check if the user is a member of the group
    if current_user not in group.members:
        abort(403)  # Forbidden access

    # Get expenses for the group
    expenses = group.expenses

    # Calculate balances (you'll need to implement this based on your chosen algorithm)
    balances = calculate_balances(group)

    return render_template('group.html', group=group, expenses=expenses, balances=balances)

def calculate_balances(group):
    # ... (Your balance calculation logic here)
    # For now, you can use a simple equal split calculation
    total_expenses = sum(expense.amount for expense in group.expenses)
    num_members = len(group.members)
    share_per_person = total_expenses / num_members

    balances = {}
    for member in group.members:
        balances[member.id] = share_per_person - sum(
            expense.amount for expense in group.expenses if expense.paid_by_id == member.id
        )
    return balances



@views.route('/group/<int:group_id>/add_expense', methods=['GET', 'POST'])
@login_required
def add_expense(group_id):
    group = Group.query.get_or_404(group_id)

    # Check if the user is a member of the group
    if current_user not in group.members:
        abort(403)  # Forbidden access

    if request.method == 'POST':
        description = request.form['description']
        amount = float(request.form['amount'])
        paid_by_id = current_user.id  # The currently logged-in user paid the expense

        # Basic input validation (you can add more as needed)
        if not description or amount <= 0:
            flash('Please enter a valid description and amount.', 'danger')
            return render_template('add_expense.html', group=group)

        new_expense = Expense(
            description=description,
            amount=amount,
            date=datetime.datetime.utcnow(),  # Use UTC time for consistency
            group_id=group_id,
            paid_by_id=paid_by_id
        )
        db.session.add(new_expense)
        db.session.commit()

        flash('Expense added successfully!', 'success')
        return redirect(url_for('views.group_details', group_id=group_id))

    return render_template('add_expense.html', group=group)



@views.route('/group/<int:group_id>/invite', methods=['GET', 'POST'])
@login_required
def invite_to_group(group_id):
    group = Group.query.get_or_404(group_id)
    if current_user not in group.members:
        abort(403)  # Forbidden access

    if request.method == 'POST':
        email = request.form['email']
        token = secrets.token_hex(16)  # Generate a unique token

        invitation = Invitation(email=email, group_id=group_id, token=token)
        db.session.add(invitation)
        db.session.commit()

        msg = Message('Splitwiser Group Invitation', recipients=[email])
        msg.body = render_template('email/invitation.html', group=group, token=token)
        mail.send(msg)

        flash('Invitation sent successfully!', 'success')
        return redirect(url_for('views.group_details', group_id=group_id))

    return render_template('invite_to_group.html', group=group)

@views.route('/join/<token>')
def join_group(token):
    invitation = Invitation.query.filter_by(token=token).first_or_404()
    group = invitation.group
    # ... Logic to either log in or create account (if not logged in)
    # ... then add the user to the group
    return redirect(url_for('views.group_details', group_id=group.id))
# ... (other routes for group creation, expense adding, etc.)
