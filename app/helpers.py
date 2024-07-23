from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content
from . import app
from flask import render_template, current_app


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