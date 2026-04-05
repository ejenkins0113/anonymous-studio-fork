import smtplib
from email.mime.text import MIMEText
import os

def send_email_notification(recipient, subject, message):
    try:
        msg = MIMEText(message)
        msg['Subject'] = subject
        msg['From'] = os.getenv("EMAIL_USER", "noreply@anonymousstudio.com")
        msg['To'] = recipient

        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(
                os.getenv("EMAIL_USER"),
                os.getenv("EMAIL_PASS")
            )
            server.send_message(msg)

    except Exception as e:
        print(f"Email failed: {e}")
        

