from flask import Blueprint, render_template, redirect, url_for, request, flash, abort, session, current_app, jsonify
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from flask_mail import Message
from .models import Group, Expense, Invitation, User, expense_participants
from app.helpers import send_email, extract_data_from_receipt
from . import db, mail
import datetime
import secrets
from werkzeug.utils import secure_filename
import io
from PIL import Image, ExifTags
import io
import pillow_heif
import pytesseract


views = Blueprint('views', __name__)


@views.route('/')
def index():
    # Sample testimonials data (replace with your actual data)
    testimonials = [
        { 'quote': "Splitwiser has made splitting bills with my roommates so much easier! No more arguments or confusion.", 'author': "Sarah M." },
        { 'quote': "The receipt scanning feature is a game-changer! I love how it automatically adds expenses for me.", 'author': "David L." },
        { 'quote': "Splitwiser has saved me so much time and stress. I highly recommend it to anyone sharing expenses.", 'author': "Emily K." }
    ]
    return render_template('index.html', testimonials=testimonials) 

@views.route('/dashboard')
@login_required
def dashboard():
    user_groups = current_user.groups
    return render_template('dashboard.html', groups=user_groups) 

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
        msg = Message(f'Splitwiser Contact Form - {subject}', 
                      sender=email, 
                      recipients=[current_app.config['MAIL_DEFAULT_SENDER']])  # Use your support email here
        msg.body = f"From: {name} <{email}>\n\n{message}"
        mail.send(msg)

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
    expenses = Expense.query.filter_by(group_id=group_id).order_by(Expense.id.desc()).paginate(page=page, per_page=ITEMS_PER_PAGE)

    balances = calculate_balances(group)
    return render_template(
        'group2.html', 
        group=group, 
        expenses=expenses, 
        balances=balances,
        more_expenses=expenses.has_next
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
    """
    Calculates the balances for each member in the given group.
    
    Returns a dictionary where keys are user IDs and values are their balances (positive if owed, negative if owing).
    """

    balances = {member.id: 0 for member in group.members}

    for expense in group.expenses:
        total_participants = len(expense.participants)  # No need to add 1 for the payer
        share_per_person = expense.amount / total_participants

        # Deduct the payer's share from their balance
        balances[expense.paid_by.id] -= share_per_person

        # Add the share to each participant's balance (excluding the payer)
        for participant in expense.participants:
            if participant != expense.paid_by:  # Exclude the payer
                balances[participant.id] += share_per_person

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
        'Splitwiser Group Invitation', 
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

    available_languages = pytesseract.get_languages(config='')


    print(available_languages)

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
