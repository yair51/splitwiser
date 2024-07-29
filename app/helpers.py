from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content
from . import app
from flask import render_template, current_app, flash
import json
from openai import OpenAI
import pytesseract
import os


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

    
def extract_data_from_receipt(image_data):
    """Extract data from receipt image using OCR and LLM."""

    # Extract text using Tesseract OCR
    try:
        text = pytesseract.image_to_string(image_data)
        print(text)
    except Exception as e:
        current_app.logger.error("Error performing OCR: %s", e)
        flash('Failed to extract text from receipt. Please try again.', 'danger')
        return None

    # Parse text with OpenAI GPT
    # openai.api_key = os.environ.get("OPENAI_API_KEY")
    prompt = (f"Extract items, subtotal, total, cash, and change from this receipt text:\n\n{text}\n\n"
                "Return the result as a JSON object with the following format:\n"
                '{"items": [{"name": "item_name", "price": item_price}, ...], "subtotal": ..., "total": ..., "cash": ..., "change": ...}')
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
        print(response)
        extracted_data = json.loads(response.choices[0].message.content)
        print(extracted_data)
        return extracted_data

    # try:
    #     response = openai.ChatCompletion.create(
    #         model="gpt-3.5-turbo",
            # messages=[
            #     {"role": "system", "content": "You are an AI assistant that helps extract structured data from receipt text."},
            #     {"role": "user", "content": prompt},
            # ]
    #     )
    #     extracted_data = json.loads(response["choices"][0]["message"]["content"])
    #     return extracted_data
    except Exception as e:
        current_app.logger.error("Error parsing receipt text: %s", e)
        flash('Failed to parse receipt data. Please try again or enter manually.', 'danger')
        return None  # Return None to indicate failure