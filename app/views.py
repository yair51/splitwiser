from flask import Blueprint, render_template, redirect, url_for, request, flash, abort, session, jsonify
from flask_login import login_required, current_user
from flask_mail import Message
from .models import Group, Expense, Invitation, User, RecurrenceFrequency
from app.helpers import send_email
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
        is_recurring = request.form.get('is_recurring') == 'on'  # Convert to boolean
        recurrence_frequency = RecurrenceFrequency(request.form.get('recurrence_frequency')) if is_recurring else None


        # Basic input validation (you can add more as needed)
        if not description or amount <= 0:
            flash('Please enter a valid description and amount.', 'danger')
            return render_template('add_expense.html', group=group)

        new_expense = Expense(
            description=description,
            amount=amount,
            date=datetime.datetime.utcnow(),  # Use UTC time for consistency
            group_id=group_id,
            paid_by_id=paid_by_id,
            is_recurring=is_recurring,
            recurrence_frequency=recurrence_frequency
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

        send_email(
        'Splitwiser Group Invitation', 
        [email], 
        'email/invitation.html', 
        group=group, 
        token=token
    )
            # print(e.message)
        # msg = Message('Splitwiser Group Invitation', recipients=[email])
        # msg.body = render_template('email/invitation.html', group=group, token=token)
        # mail.send(msg)

        flash('Invitation sent successfully!', 'success')
        return redirect(url_for('views.group_details', group_id=group_id))

    return render_template('invite_to_group.html', group=group)

@views.route('/join/<token>')
def join_group(token):
    # Get the invitation and group
    invitation = Invitation.query.filter_by(token=token).first_or_404()
    group = invitation.group

    # Handle Logged-In User
    if current_user.is_authenticated:
        # Check if user is already in the group
        if current_user in group.members:
            flash(f'You are already a member of {group.name}.', 'info')
        else:
            group.members.append(current_user)
            db.session.delete(invitation)  # Delete the used invitation
            db.session.commit()
            flash(f'You have successfully joined {group.name}!', 'success')
        return redirect(url_for('views.group_details', group_id=group.id))

    # Handle Non-Logged-In User
    user = User.query.filter_by(email=invitation.email).first()
    if user:  # Email already registered
        flash('Please log in to join the group.', 'info')
        return redirect(url_for('auth.login'))
    else:  # Email not registered
       # Store the token in the session to be used after registration
        session['invitation_token'] = token  
        flash('Please create an account to join the group.', 'info')
        return redirect(url_for('auth.register'))


@views.route('/api/leave_group/<int:group_id>', methods=['POST'])
@login_required
def leave_group(group_id):
    group = Group.query.get_or_404(group_id)
    if current_user in group.members:
        group.members.remove(current_user)
        db.session.commit()
        flash('You have left the group.', 'success')
        return 'Success', 200
    else:
        abort(403)  # Forbidden - not a member of the group

@views.route('/api/group/<int:group_id>/expenses')
@login_required
def get_expenses(group_id):
   group = Group.query.get_or_404(group_id)
   if current_user not in group.members:
       abort(403)
  
   expenses = Expense.query.filter_by(group_id=group_id).all()
  
   # Convert expenses to dictionaries for JSON serialization
   expense_list = [
       {
           'description': expense.description,
           'amount': expense.amount,
           'date': expense.date.strftime('%Y-%m-%d'),
           'paid_by': expense.paid_by.first_name + ' ' + expense.paid_by.last_name,
           'is_recurring': expense.is_recurring,
           'recurrence_frequency': expense.recurrence_frequency.value if expense.recurrence_frequency else None,
       } for expense in expenses
   ]
  
   return jsonify(expense_list)
