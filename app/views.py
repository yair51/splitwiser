from flask import Blueprint, render_template, redirect, url_for, request, flash, abort, session, current_app, jsonify
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from flask_mail import Message
from .models import Group, Expense, Invitation, User
from app.helpers import send_email, extract_data_from_receipt
from . import db
import datetime
import secrets
import io
from PIL import Image, ExifTags
import io
import pillow_heif
import json

views = Blueprint('views', __name__)


@views.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('views.dashboard'))
    # Sample testimonials data (replace with your actual data)
    testimonials = [
        { 'quote': "WeSplit has made splitting bills with my roommates so much easier! No more arguments or confusion.", 'author': "Sarah M." },
        { 'quote': "The receipt scanning feature is a game-changer! I love how it automatically adds expenses for me.", 'author': "David L." },
        { 'quote': "WeSplit has saved me so much time and stress. I highly recommend it to anyone sharing expenses.", 'author': "Emily K." }
    ]
    return render_template('index.html', testimonials=testimonials) 




@views.route('/dashboard')  # Or @views.route('/dashboard')
@login_required
def dashboard():
    # 1. Recent Activity Summary (Placeholder - you'll need to implement the actual logic)
    new_expenses_count = 0  # Replace with actual count of new expenses
    groups_with_balances = []  # Replace with actual list of groups with outstanding balances
    upcoming_expenses = []   # Replace with actual list of upcoming recurring expenses

    # 2. Recent Groups and Balances
    recent_groups = current_user.groups  # Get 3 most recent groups
    balances = calculate_balances_for_user(current_user)

    # 3. Personalized Insights (Optional)
    show_insights = False  # Set to True if you have insights to display
    # ... (Add logic to fetch and prepare insights data if needed)

    # 4. Render the template
    return render_template('dashboard.html',
                            new_expenses_count=new_expenses_count, 
                           groups_with_balances=groups_with_balances,
                           upcoming_expenses=upcoming_expenses,
                           recent_groups=recent_groups,
                           balances=balances,
                           show_insights=show_insights)

# Helper function to calculate balances for a specific user across all their groups
def calculate_balances_for_user(user):
    balances = {}
    for group in user.groups:
        group_balances = calculate_balances(group)
        balances[group.id] = group_balances.get(user.id, 0)  # Get the user's balance for this group
    return balances

@views.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        subject = request.form['subject']
        message = request.form['message']

        # Basic input validation (you might want to add more robust validation)
        if not name or not email or not message:
            flash('Please fill in all required fields.', 'danger')
            return render_template('contact.html')

        # Send email to your support address
        msg = Message(f'WeSplit Contact Form - {subject}', 
                      sender='yairgritzman@gmail.com', 
                      recipients=[current_app.config['MAIL_DEFAULT_SENDER']])  # Use your support email here
        msg.html = f"From: {name} <{email}>\n\n{message}"
        # mail.send(msg)
        send_email(subject, [current_app.config['MAIL_DEFAULT_SENDER']], 'email/contact_form_submission.html', name=name, email=email, subject2=subject, message=message)

        flash('Your message has been sent. Thank you!', 'success')
        return redirect(url_for('views.contact'))  # Redirect back to the contact page

    return render_template('contact.html')  



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



ITEMS_PER_PAGE = 10 


@views.route('/group/<int:group_id>')
@login_required
def group_details(group_id):
    group = Group.query.get_or_404(group_id)

    if current_user not in group.members:
        abort(403)

    page = request.args.get('page', 1, type=int) 
    expenses = Expense.query.filter_by(group_id=group_id).order_by(Expense.id.desc())
    # expenses = Expense.query.filter_by(group_id=group_id).order_by(Expense.id.desc()).paginate(page=page, per_page=ITEMS_PER_PAGE)

    balances = calculate_balances(group)
    settlements = calculate_optimal_settlements(balances)
    return render_template(
        'group.html', 
        group=group, 
        expenses=expenses, 
        balances=balances,
        settlements=settlements,
        # more_expenses=expenses.has_next
    )

@views.route('/group/<int:group_id>/expenses')
@login_required
def get_group_expenses(group_id):
    group = Group.query.get_or_404(group_id)

    if current_user not in group.members:
        abort(403)

    # Paginates the expenses
    page = request.args.get('page', 1, type=int)
    expenses = Expense.query.filter_by(group_id=group_id).order_by(Expense.date.desc()).paginate(page=page, per_page=ITEMS_PER_PAGE)

    expenses_data = [
        {
            "id": expense.id,
            "description": expense.description,
            "amount": expense.amount,
            "date": expense.date.strftime('%Y-%m-%d'),
            "paid_by": {
                "first_name": expense.paid_by.first_name,
                "last_name": expense.paid_by.last_name
            },
            "participants": [
                {
                    "first_name": participant.first_name,
                    "last_name": participant.last_name
                } for participant in expense.participants
            ]
        } for expense in expenses.items
    ]

    return jsonify({"expenses": expenses_data})



@views.route('/expense/<int:expense_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_expense(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    group = expense.group

    # Check if the user is a member of the group and the one who paid for the expense
    if (current_user not in group.members):
        abort(403)  # Forbidden access

    if request.method == 'POST':
        description = request.form['description']
        amount = float(request.form['amount'])
        participant_ids = [int(p) for p in request.form.getlist('participants')]

        # Basic validation (you can add more as needed)
        if not description or amount <= 0:
            flash('Please enter a valid description and amount.', 'danger')
            return redirect(url_for('views.edit_expense', expense_id=expense_id))

        print(description)
        # Update expense details
        expense.description = description
        expense.amount = amount

        # Update participants
        expense.participants = []
        for participant_id in participant_ids:
            participant = User.query.get(participant_id)
            if participant and participant in group.members: 
                expense.participants.append(participant)

        db.session.commit()
        flash('Expense updated successfully!', 'success')
        return redirect(url_for('views.group_details', group_id=group.id))

    return render_template('edit_expense_modal.html', expense=expense, group=group) 



@views.route('/expense/<int:expense_id>/delete', methods=['POST']) 
@login_required
def delete_expense(expense_id):
    expense = Expense.query.get_or_404(expense_id)

    group = expense.group

    # Check if the user is a member of the group and the one who paid for the expense
    if (current_user not in group.members) or (expense.paid_by != current_user):
        abort(403) 

    db.session.delete(expense)
    db.session.commit()
    flash('Expense deleted successfully!', 'success')
    return redirect(url_for('views.group_details', group_id=group.id))



def calculate_balances(group):
    """Calculates the balances for each member in a group, considering participants and payments, with zero division check."""
    max_id = max(member.id for member in group.members)
    balances = {i: 0 for i in range(max_id + 1)}
    for expense in group.expenses:
        num_participants = len(expense.participants)
        # Check for zero participants (shouldn't happen, but it's a good safety measure)
        if num_participants == 0:
            # print(f"Expense {expense.id} has no participants. Skipping.")  
            continue  # Skip this expense
        
        share_per_participant = expense.amount / num_participants
        for participant in expense.participants:
            if participant.id not in balances:
                print(f"Warning: Participant {participant.id} not found in group. Skipping.")
                continue  # Or handle this case differently based on your application logic
            balances[participant.id] -= share_per_participant 
        if expense.paid_by_id not in balances:
                print(f"Warning: Participant {expense.paid_by_id} not found in group. Skipping.")
        else:
            balances[expense.paid_by_id] += expense.amount
    for member_id in balances:
        if -0.001 < balances[member_id] < 0.001:
            balances[member_id] = 0 
    return balances




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
        'WeSplit Group Invitation', 
        [email], 
        'email/invitation.html', 
        group=group, 
        token=token
    )

        flash('Invitation sent successfully!', 'success')
        return redirect(url_for('views.group_details', group_id=group_id))

    return render_template('invite_to_group.html', group=group)


# Handle invitation acceptance
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


ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'heic'}

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
        print("items data", items_data)

        for item in items_data:
            description = item["name"]
            amount = float(item["price"])
            participant_ids = [int(p) for p in item.get("participants", [])]
            paid_by_id = int(item.get("paidById", current_user.id))


             # Get the paid_by user object
            paid_by = User.query.get(paid_by_id)
            if not paid_by:
                flash(f'Paid By user with ID {paid_by_id} not found.', 'danger')
                return jsonify({"success": False, "error": "Invalid paid_by user"})
            
            # Create new expense object
            expense = Expense(
                description=description,
                amount=amount,
                date=datetime.datetime.utcnow(),
                group_id=group_id,
                paid_by=paid_by
            )
            # Associate participants with the expense (using the new relationship)
            for participant_id in participant_ids:
                participant = User.query.get(participant_id)
                # Add the user to the expense's participants
                if participant and participant in group.members:
                    expense.participants.append(participant)

            db.session.add(expense)

        db.session.commit()
        
        flash('Expense(s) added successfully!', 'success')
        return jsonify({"success": True, "redirect_url": url_for('views.group_details', group_id=group_id)})

    return render_template('add_expense.html', group=group)
    


@views.route('/upload_receipt', methods=['POST'])
@login_required
def upload_receipt():
    if 'receipt_image' not in request.files:
        return jsonify({"success": False, "error": "No file part"})
    
    file = request.files['receipt_image']
    language = request.form.get('receipt_language', 'eng')  # Get language, default to English

        # Adjust the prompt based on detected language
    if language == 'heb':  # Hebrew
        prompt_language = "Hebrew"
    elif language == 'eng':  # English
        prompt_language = "English"
    elif language == 'nor':
        prompt_language = "Norwegian"
    else:
        prompt_language = "the language in the text"

    file = request.files['receipt_image']

    if file.filename == '':
        return jsonify({"success": False, "error": "No selected file"})
    
    if not allowed_file(file.filename):
        return jsonify({"success": False, "error": "Invalid file type. Please upload an image."})

    try:
        # Check if the file is a HEIC image
        if file.filename.lower().endswith('.heic'):
            # Read the image file using pillow_heif
            heif_file = pillow_heif.read_heif(file)
            # Convert the HEIF file to a PIL Image
            img = Image.frombytes(
                heif_file.mode,
                heif_file.size,
                heif_file.data,
                "raw",
                heif_file.mode,
                heif_file.stride)  
        else:
            # Read the image file
            image_data = file.read()
            print("image_data type", type(image_data))
            # Open the image using PIL
            img = Image.open(io.BytesIO(image_data))
            
            # Correct the orientation based on EXIF data (common issue with mobile photos)
            try:
                for orientation in ExifTags.TAGS.keys():
                    if ExifTags.TAGS[orientation] == 'Orientation':
                        break
                exif = img.getexif()
                if exif is not None:
                    print(f"exif data: {exif}")
                    orientation = exif[orientation]
                    if orientation == 3:
                        img = img.rotate(180, expand=True)
                    elif orientation == 6:
                        img = img.rotate(270, expand=True)
                    elif orientation == 8:
                        img = img.rotate(90, expand=True)
            except (AttributeError, KeyError, IndexError):
                # Cases: image don't have getexif
                pass
        
        print("Image opened successfully:", img)  # Add this line
        extracted_data = extract_data_from_receipt(img, language, prompt_language)
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
        #    'is_recurring': expense.is_recurring,
        #    'recurrence_frequency': expense.recurrence_frequency.value if expense.recurrence_frequency else None,
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


# Handles quick add button to add expenses to a group
@views.route('/quick_add_expense', methods=['POST'])
@login_required
def quick_add_expense():
    description = request.form['description']
    amount = float(request.form['amount'])
    group_id = int(request.form['group_id'])
    paid_by_id = int(request.form['paid_by'])
    participant_ids = json.loads(request.form['participants'])

    group = Group.query.get_or_404(group_id)
    paid_by = User.query.get_or_404(paid_by_id)

    # Basic validation
    if not description or amount <= 0:
        flash('Please enter a valid description and amount.', 'danger')
        return jsonify({"success": False, "error": "Invalid item data"})

    # Create the Expense object
    expense = Expense(
        description=description,
        amount=amount,
        date=datetime.datetime.utcnow(),
        group=group,
        paid_by=paid_by 
    )

    # Associate participants with the expense 
    for participant_id in participant_ids:
        participant = User.query.get(participant_id)
        if participant and participant in group.members:
            expense.participants.append(participant)

    db.session.add(expense)
    db.session.commit()

    flash('Expense added successfully!', 'success')
    # return(redirect(url_for('views.group_details', group_id=group.id)))
    return jsonify({"success": True, "redirect_url": url_for('views.group_details', group_id=group_id)})


# Returns JSON list of group members
@views.route('/group/<int:group_id>/members')
@login_required
def get_group_members(group_id):
    group = Group.query.get_or_404(group_id)

    if current_user not in group.members:
        abort(403) 

    members_data = [
        {
            "id": member.id,
            "first_name": member.first_name,
            "last_name": member.last_name
        } for member in group.members
    ]

    return jsonify({"success": True, "members": members_data})

@views.route('/generate_invitation_token/<int:group_id>', methods=['GET'])
@login_required
def generate_invitation_token(group_id):
    group = Group.query.get_or_404(group_id)
    if current_user not in group.members:
        abort(403) 

    # Check if an invitation already exists for this group
    invitation = Invitation.query.filter_by(group_id=group_id, email='Invitation_link').first()
    if invitation:
        token = invitation.token
    else:
        token = secrets.token_hex(16)
        invitation = Invitation(email='Invitation_link', group_id=group_id, token=token)
        db.session.add(invitation)
        db.session.commit()

    return jsonify({"success": True, "token": token})
# @views.route('/generate_invitation_token/<int:group_id>', methods=['GET'])
# @login_required
# def generate_invitation_token(group_id):
#     group = Group.query.get_or_404(group_id)
#     if current_user not in group.members:
#         abort(403)  # Forbidden access

#     token = secrets.token_hex(16)  # Generate a unique token

#     invitation = Invitation(email='Invitation_link', group_id=group_id, token=token)  
#     db.session.add(invitation)
#     db.session.commit()

#     # Construct the full invitation link
#     invitation_link = url_for('views.join_group', token=token, _external=True)

#     return jsonify({'invitation_link': invitation_link})