from flask import Blueprint, render_template, redirect, url_for, request, flash, abort, session, current_app, jsonify
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from flask_mail import Message
from .models import Group, Expense, Invitation, User, expense_participants, RecurrenceFrequency
from app.helpers import send_email, extract_data_from_receipt
from . import db, mail
import datetime
import secrets
from werkzeug.utils import secure_filename
import io
import json
from openai import OpenAI
import pytesseract
import os
from PIL import Image
import io



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

    settlements = calculate_optimal_settlements(balances)
    return render_template('group.html', group=group, expenses=expenses, balances=balances, settlements=settlements)

def calculate_balances(group):
    """Calculates the balances for each member in a group, considering participants and payments, with zero division check."""

    balances = {member.id: 0 for member in group.members}

    for expense in group.expenses:
        num_participants = len(expense.participants)

        # Check for zero participants (shouldn't happen, but it's a good safety measure)
        if num_participants == 0:
            print(f"Expense {expense.id} has no participants. Skipping.")  
            continue  # Skip this expense
        
        share_per_participant = expense.amount / num_participants

        for participant in expense.participants:
            balances[participant.id] -= share_per_participant

        balances[expense.paid_by_id] += expense.amount

    return balances



# @views.route('/group/<int:group_id>/add_expense', methods=['GET', 'POST'])
# @login_required
# def add_expense(group_id):
#     group = Group.query.get_or_404(group_id)

#     # Check if the user is a member of the group
#     if current_user not in group.members:
#         abort(403)  # Forbidden access

#     if request.method == 'POST':
#         description = request.form['description']
#         amount = float(request.form['amount'])
#         paid_by_id = current_user.id  # The currently logged-in user paid the expense
#         is_recurring = request.form.get('is_recurring') == 'on'  # Convert to boolean
#         recurrence_frequency = RecurrenceFrequency(request.form.get('recurrence_frequency')) if is_recurring else None


#         # Basic input validation (you can add more as needed)
#         if not description or amount <= 0:
#             flash('Please enter a valid description and amount.', 'danger')
#             return render_template('add_expense.html', group=group)

#         new_expense = Expense(
#             description=description,
#             amount=amount,
#             date=datetime.datetime.utcnow(),  # Use UTC time for consistency
#             group_id=group_id,
#             paid_by_id=paid_by_id,
#             is_recurring=is_recurring,
#             recurrence_frequency=recurrence_frequency
#         )
#         db.session.add(new_expense)
#         db.session.commit()



#         # Basic input validation (you can add more as needed)
#         if not description or amount <= 0:
#             flash('Please enter a valid description and amount.', 'danger')
#             return render_template('add_expense.html', group=group)

#         new_expense = Expense(
#             description=description,
#             amount=amount,
#             date=datetime.datetime.utcnow(),  # Use UTC time for consistency
#             group_id=group_id,
#             paid_by_id=paid_by_id
#         )
#         db.session.add(new_expense)
#         db.session.commit()

#         flash('Expense added successfully!', 'success')
#         return redirect(url_for('views.group_details', group_id=group_id))

#     return render_template('add_expense.html', group=group)



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



@views.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        # Update user information
        current_user.first_name = request.form['first_name']
        current_user.last_name = request.form['last_name']
        # ... (Handle other profile data updates)

        if request.form['password']:
            current_user.password = generate_password_hash(
                request.form['password'], method='pbkdf2:sha256'
            )

        db.session.commit()
        flash('Profile updated successfully!', 'success')

    # Calculate expense statistics
    total_expenses = sum(expense.amount for group in current_user.groups for expense in group.expenses if expense.paid_by == current_user)
    # You can calculate other statistics like average expense, most frequent category, etc.

    return render_template('profile.html', total_expenses=total_expenses)  # Add more statistics as needed


ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS




@views.route('/group/<int:group_id>/add_expense', methods=['GET', 'POST'])
@login_required
def add_expense(group_id):
    group = Group.query.get_or_404(group_id)

    # Check if user is a member of the group
    if current_user not in group.members:
        abort(403)  # Forbidden access


    if request.method == 'POST':
        items_data = request.get_json()['items']  # Get items as JSON array
        print(items_data)

        for item in items_data:
            description = item["name"]
            amount = float(item["price"])
            participant_ids = [int(p) for p in item.get("participants", [])]
            # Create new expense object
            expense = Expense(
                description=description,
                amount=amount,
                date=datetime.datetime.utcnow(),
                group_id=group_id,
                paid_by=current_user  
            )
            # Associate participants with the expense (using the new relationship)
            for participant_id in participant_ids:
                participant = User.query.get(participant_id)
                # Add the user to the expense's participants
                if participant and participant in group.members:
                    print(participant)
                    expense.participants.append(participant)

            db.session.add(expense)

        db.session.commit()

        flash('Expense(s) added successfully!', 'success')
        return jsonify({"success": True, "redirect_url": url_for('views.group_details', group_id=group_id)})

    return render_template('add_expense.html', group=group)



# @views.route('/group/<int:group_id>/add_expense', methods=['GET', 'POST'])
# @login_required
# def add_expense(group_id):
    # group = Group.query.get_or_404(group_id)

#     # Check if user is a member of the group
#     if current_user not in group.members:
#         abort(403)  # Forbidden access

#     if request.method == 'POST':
#         item_data = request.get_json()['items']  # Get items as JSON array
#         print(item_data)

#         for item in item_data:
#             description = item["name"]
#             amount = float(item["price"])
#             participant_ids = [int(p) for p in item.get("participants", [])]
#             # ... (Add error handling for invalid data here)

#             # Create the Expense object
#             expense = Expense(
#                 description=description,
#                 amount=amount,
#                 date=datetime.utcnow(),
#                 group=group,
#                 paid_by=current_user  
#             )

#             # Associate participants with the expense
#             if participant_ids:  # If participants are selected
#                 for participant_id in participant_ids:
#                     participant = User.query.get(participant_id)
#                     if participant:  # Check if user exists (for security)
#                         expense.participants.append(participant)

#             db.session.add(expense)

#         db.session.commit()

#         flash('Expense(s) added successfully!', 'success')
#         return redirect(url_for('views.group_details', group_id=group_id))

#     return render_template('add_expense.html', group=group)

# @views.route('/group/<int:group_id>/add_expense', methods=['GET', 'POST'])
# @login_required
# def add_expense(group_id):
#     group = Group.query.get_or_404(group_id)

#     # Check if the user is a member of the group
#     if current_user not in group.members:
#         abort(403)  # Forbidden access

#     # if request.method == 'POST':
#     #     # Extract items if receipt image is uploaded
#     #     receipt_image = request.files.get('receipt_image')
#     #     if receipt_image and allowed_file(receipt_image.filename):
#     #         try:
#     #             image_data = receipt_image.read()
#     #             img = Image.open(io.BytesIO(image_data))
#     #             extracted_items = extract_data_from_receipt(img)["items"]  # Extract items from the receipt
#     #         except Exception as e:
#     #             current_app.logger.error("Error extracting items from receipt: %s", e)
#     #             flash('Failed to extract items from the receipt.', 'danger')
#     #             return render_template('add_expense.html', group=group)
#     #     else:
#     #         # Get items from manual input (JSON array)
#     #         extracted_items = json.loads(request.form.get("item_data", "[]"))


#     #     # Create expenses based on the extracted/input items
#     #     for item_data in extracted_items:
#     #         item_name = item_data["name"]
#     #         item_price = float(item_data["price"])
#     #         # participant_ids = item_data.get("participants", [])  # Assuming a list of user IDs

#     #         print(item_data)
#     #         # Create the Expense object
#     #         new_expense = Expense(
#     #             description=item_name,
#     #             amount=item_price,
#     #             date=datetime.datetime.utcnow(),
#     #             group_id=group_id,
#     #             paid_by=current_user,
#     #             # participants=[User.query.get(int(user_id)) for user_id in participant_ids if User.query.get(int(user_id)) in group.members]
#     #         )

#     #         db.session.add(new_expense)

#     #     db.session.commit()

#     #     flash('Expense(s) added successfully!', 'success')
#     #     return redirect(url_for('views.group_details', group_id=group_id))

#     return render_template('add_expense.html', group=group)
    


@views.route('/upload_receipt', methods=['POST'])
@login_required
def upload_receipt():
    if 'receipt_image' not in request.files:
        return jsonify({"success": False, "error": "No file part"})

    file = request.files['receipt_image']

    if file.filename == '':
        return jsonify({"success": False, "error": "No selected file"})
    
    if not allowed_file(file.filename):
        return jsonify({"success": False, "error": "Invalid file type. Please upload an image."})

    try:
        image_data = file.read()
        img = Image.open(io.BytesIO(image_data))
        extracted_data = extract_data_from_receipt(img)
        print(extracted_data)
        return jsonify({"success": True, "items": extracted_data['items']})
    except Exception as e:
        current_app.logger.error("Error processing receipt: %s", e)
        return jsonify({"success": False, "error": "Error processing receipt"})
      
      
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
           'id': expense.id,
           'description': expense.description,
           'amount': f"{expense.amount:.2f}",
           'date': expense.date.strftime('%Y-%m-%d'),
           'paid_by': expense.paid_by.first_name + ' ' + expense.paid_by.last_name,
           'is_recurring': expense.is_recurring,
           'recurrence_frequency': expense.recurrence_frequency.value if expense.recurrence_frequency else None,
           'participants': [{'id': participant.id, 'name': participant.first_name + ' ' + participant.last_name} for participant in expense.participants]
       } for expense in expenses
   ]
  
   return jsonify(expense_list)

@views.route('/settings', methods=['GET', 'POST'])
@login_required
def update_settings():
    if request.method == 'POST':
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        dark_mode = request.form.get('dark_mode') == 'on'  # Convert to boolean

        # Validate input data

        current_user.first_name = first_name
        current_user.last_name = last_name
        current_user.email = email
        current_user.dark_mode = dark_mode
        db.session.commit()

        flash('Settings updated successfully!', 'success')
        return redirect(url_for('views.update_settings'))

    return render_template('settings.html')

@views.route('/group/<int:group_id>/expense/<int:expense_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_expense(group_id, expense_id):
    group = Group.query.get_or_404(group_id)
    expense = Expense.query.get_or_404(expense_id)

    # Authorization check: Ensure the current user is a member of the group and 
    #  is either the payer or an admin (you'll need to define admin logic)
    if current_user not in group.members or (expense.paid_by != current_user): 
        abort(403)  # Forbidden access

    if request.method == 'POST':
        try:
            form_data = request.form  
            expense.description = form_data.get('description')
            expense.amount = float(form_data.get('amount'))

            # Update participants
            participant_ids = [int(p_id) for p_id in form_data.getlist('participants')]
            expense.participants = User.query.filter(User.id.in_(participant_ids)).all()

            db.session.commit()

            # Recalculate balances for the group after updating the expense
            calculate_balances(expense.group)

            flash('Expense updated successfully!', 'success')
            jsonify({"success": True, "redirect_url": url_for('views.group_details', group_id=group_id)})

        except ValueError:  # Handle potential conversion errors (e.g., if 'amount' is not a valid float)
            flash('Invalid input. Please check the amount.', 'error')

    return redirect(url_for('views.group_details', group_id=group_id))


@views.route('/api/expense/<int:expense_id>', methods=['DELETE'])
@login_required
def delete_expense(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    group_id = expense.group_id  # Store the group ID before deleting
    group = Group.query.get_or_404(group_id)
    if current_user not in group.members or (expense.paid_by != current_user): 
        abort(403)  # Forbidden access
    if request.method == 'DELETE':
        db.session.delete(expense)
        db.session.commit()
        # Recalculate balances for the group after deleting the expense
        calculate_balances(Group.query.get(group_id))  # Fetch the group again after deletion
        return jsonify({"success": True})
    return redirect(url_for('views.group_details', group_id=group_id))
    # ... (handle other methods or errors if needed)
@views.route('/api/group/<int:group_id>/balance')
@login_required
def get_group_balance(group_id):
    group = Group.query.get_or_404(group_id)
    if current_user not in group.members:
        abort(403) 

    balances = calculate_balances(group)
    user_balance = balances.get(current_user.id, 0)  # Get balance for current user or default to 0

    return jsonify({'balance': user_balance})

def get_user_name_by_id(user_id):
    """Helper function to get the full name of a user by their ID."""
    user = User.query.get(user_id)
    return f"{user.first_name} {user.last_name}" if user else "Unknown User"

def calculate_optimal_settlements(balances):
    """
    Calculates optimal settlements, preserving user IDs and minimizing transactions.
    """

    # Create lists of tuples (user_id, balance) for positive and negative balances
    positive_balances = [(user_id, balance) for user_id, balance in balances.items() if balance > 0]
    negative_balances = [(user_id, balance) for user_id, balance in balances.items() if balance < 0]

    settlements = []
    while positive_balances and negative_balances:
        # Get the user with the highest positive balance and the user with the lowest negative balance
        payer_id, payer_balance = max(positive_balances, key=lambda x: x[1])
        payee_id, payee_balance = min(negative_balances, key=lambda x: x[1])

        amount_to_settle = min(payer_balance, -payee_balance)
        settlements.append((payer_id, get_user_name_by_id(payer_id), payee_id, get_user_name_by_id(payee_id), amount_to_settle))

        # Update the balances without removing entries
        positive_balances = [(uid, bal - amount_to_settle if uid == payer_id else bal) for uid, bal in positive_balances]
        negative_balances = [(uid, bal + amount_to_settle if uid == payee_id else bal) for uid, bal in negative_balances]

        # Remove entries with zero balance
        positive_balances = [(uid, bal) for uid, bal in positive_balances if bal != 0]
        negative_balances = [(uid, bal) for uid, bal in negative_balances if bal != 0]

    return settlements


def update_balances_for_settled_user(group, user_id):
    """
    Updates the database and creates settlement expenses.
    """

    balances = calculate_balances(group)
    settlements = calculate_optimal_settlements(balances)

    for payer_id, payer_name, payee_id, payee_name, amount in settlements:
        if payer_id == user_id or payee_id == user_id:
            # Create a new "settlement" expense
            settlement_expense = Expense(
                description=f"Settlement from {payer_name} to {payee_name}",
                amount=amount,
                date=datetime.datetime.utcnow().date(),
                group_id=group.id,
                paid_by_id=payer_id,
                settled=True
            )

            # Associate only the payer and payee with this settlement expense
            settlement_expense.participants.append(User.query.get(payer_id))
            settlement_expense.participants.append(User.query.get(payee_id))

            db.session.add(settlement_expense)

    db.session.commit()

@views.route('/api/group/<int:group_id>/settle_up', methods=['POST'])
@login_required
def settle_up(group_id):
    group = Group.query.get_or_404(group_id)
    if current_user not in group.members:
        abort(403)  # Forbidden access

    try:
        balances = calculate_balances(group)
        settlements = calculate_optimal_settlements(balances)

        # Optimization: Fetch all required users in one query (if not already done in calculate_balances)
        user_ids = set(balances.keys()) 
        all_users = {user.id: user for user in User.query.filter(User.id.in_(user_ids)).all()}

        for payer_id, payer_name, payee_id, payee_name, amount in settlements:
            if payer_id == current_user.id: 
                continue

            if payee_id == current_user.id and amount > 0:
                # Create a new "settlement" expense (use payer_name and payee_name)
                settlement_expense = Expense(
                    description=f"Settlement to {payer_name}",
                    amount=amount,
                    date=datetime.datetime.utcnow().date(),
                    group_id=group_id,
                    paid_by_id=current_user.id
                )

                settlement_expense.participants.append(all_users[payer_id])
                db.session.add(settlement_expense)

        db.session.commit()

        # Recalculate balances after settlements
        calculate_balances(group)
        flash('Account Settled!', 'success')
        return jsonify({'success': True})

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": "An error occurred while settling up."}), 500
