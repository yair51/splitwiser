from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content
from . import app
from flask import render_template, current_app, flash
import json
from openai import OpenAI
import pytesseract
import os
from langdetect import detect


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
    print(current_app.config)
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

    
def extract_data_from_receipt(image_data, language="eng", prompt_language="English"):
    """Extract data from receipt image using OCR and LLM."""

    text = ""

    # Extract text using Tesseract OCR with the detected language
    try:
        text = pytesseract.image_to_string(image_data, lang=language)
        print(text)
    except pytesseract.TesseractError as e:
        print("Error")
    prompt = (f"Extract items and their prices from the following receipt text in {language}. "
            f"If an item name appears to be misspelled and you are confident about the correction, correct the spelling."
            f"Ensure that you capture the item name and price accurately:\n\n"
            f"{text}\n\n"
            "Return the result as a JSON object with the following format:\n"
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
            model="gpt-3.5-turbo",
        )
        response = response.choices[0].message.content

        # remove json formatting information if present
        cleaned_response = response.strip('```json').strip('```')

        extracted_data = json.loads(cleaned_response)
        # Remove the triple backticks and 'json' identifier
        # cleaned_response = response.strip('```json').strip('```')
        return extracted_data

    except Exception as e:
        current_app.logger.error("Error parsing receipt text: %s", e)
        flash('Failed to parse receipt data. Please try again or enter manually.', 'danger')
        return None  # Return None to indicate failure