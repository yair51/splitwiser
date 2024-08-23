from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content
from . import app, db
from flask import render_template, current_app, flash, redirect, url_for
from flask_login import current_user
from app.models import Invitation
import json
from openai import OpenAI
import pytesseract
import os
from langdetect import detect
from PIL import ImageEnhance, ImageFilter, Image
import cv2 as cv
import numpy as np

# Send Email Function
def send_email(subject, recipients, template, **kwargs):
    import ssl

    try:
        _create_unverified_https_context = ssl._create_unverified_context
    except AttributeError:
        pass
    else:
        ssl._create_default_https_context = _create_unverified_https_context
    """Sends an email using the SendGrid API."""
    if not current_app.config['MAIL_PASSWORD']:
        app.logger.warning('SENDGRID_API_KEY not set. Emails will not be sent.')
        return

    sg = SendGridAPIClient(api_key=current_app.config['MAIL_PASSWORD'])
    from_email = Email(app.config['MAIL_USERNAME'])
    to_emails = [To(email) for email in recipients]

    html_content = render_template(template, **kwargs)
    mail = Mail(from_email, to_emails, subject, Content("text/html", html_content))

    try:
        response = sg.send(mail)
        app.logger.info("Email sent with status code: %s", response.status_code)
    except Exception as e:
        print(f"Failed {e}")
        app.logger.error("Error sending email: %s", e)


def process_invitation(token):
    """Processes an invitation token and adds the user to the group. Returns a group_id if user is added to the group."""
    invitation = Invitation.query.filter_by(token=token).first()
    if invitation:
        print("group", invitation.group)
        group = invitation.group
        if current_user not in group.members:
            group.members.append(current_user)
            # db.session.delete(invitation) 
            db.session.commit()
            flash(f'You have successfully joined {group.name}!', 'success')
            return invitation.group_id
        else:
            return None


# Preprocess image for OCR
def preprocess_image(img):
    # Convert PIL Image to a NumPy array
    open_cv_image = np.array(img)

    # Apply GaussianBlur to reduce noise
    blur = cv.GaussianBlur(open_cv_image, (5, 5), 0)

    # Apply Canny edge detection
    edged_no_thresh = cv.Canny(blur, 100, 200)

    # Apply dilation operations
    kernel = np.ones((3,3),np.uint8) # Adjust kernel size if needed
    dilated_img = cv.dilate(edged_no_thresh, kernel, iterations = 1)

    # Invert the colors of dialated image
    inverted_img = cv.bitwise_not(dilated_img)

    # Otsu thresholding
    ret4,thresh = cv.threshold(inverted_img,0,255,cv.THRESH_BINARY+cv.THRESH_OTSU)
    # Convert to RGB for display
    rgb_img = cv.cvtColor(thresh, cv.COLOR_BGR2RGB)
    # Convert to PIL Image
    pil_img = Image.fromarray(rgb_img)
    return pil_img
    

def extract_data_from_receipt(image_data, language="eng", prompt_language="English"):
    """Extract data from receipt image using OCR and LLM."""

    text = ""

    preprocessed_img = preprocess_image(image_data)

    # Extract text using Tesseract OCR with the detected language
    try:
        config = '--oem 1 --psm 4'  # Set OEM to 1 (Neural nets LSTM engine only)
        text = pytesseract.image_to_string(preprocessed_img, lang=language, config=config)
        print("OCR text", text)
    except pytesseract.TesseractError as e:
        print("Error with OCR extraction: ", e)
    prompt = (f"Extract items and their prices from the following receipt text in {prompt_language}. "
            f"If an item name appears to be misspelled and you are confident about the correction, correct the spelling."
            f"Ensure that you capture the item name and price accurately:\n\n"
            f"{text}\n\n"
            "Return ONLY the JSON object with the following format, even if you are uncertain about the results. DO NOT include any additional text or explanations:\n"
            '{"items": [{"name": "item_name", "price": item_price}, ...]}\n'
            "Example:\n"
            'Receipt Text: "Milk 3.50, Bread 2.30, Tomatoes 5.90"\n'
            'Output: {"items": [{"name": "Milk", "price": 3.50}, {"name": "Bread", "price": 2.30}, {"name": "Tomatoes", "price": 5.90}]}\n')
    try:
        client = OpenAI(
            # This is the default and can be omitted
            api_key=os.environ.get("OPENAI_API_KEY"),
        )

        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are an AI assistant that helps extract structured data from receipt text."},
                {"role": "user", "content": prompt},
            ],
            model="gpt-4o-mini",
        )
        response = response.choices[0].message.content

        print("Response from GPT:", response)

        # remove json formatting information if present
        cleaned_response = response.strip('```json').strip('```')

        extracted_data = json.loads(cleaned_response)
        # Remove the triple backticks and 'json' identifier
        # cleaned_response = response.strip('```json').strip('```')
        return extracted_data

    except Exception as e:
        current_app.logger.error("Error parsing receipt text: %s", e)
        # flash('Failed to parse receipt data. Please try again or enter manually.', 'danger')
        return None  # Return None to indicate failure