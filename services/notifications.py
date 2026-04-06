import smtplib
from email.mime.text import MIMEText
import os

def send_email_notification(recipient, subject, message):
    try:
        print(f"✉️ [EMAIL DEBUG] Attempting to send email")
        print(f"   To: {recipient}")
        print(f"   Subject: {subject}")
        msg = MIMEText(message)
        msg['Subject'] = subject
        msg['From'] = os.getenv("EMAIL_USER", "noreply@anonymousstudio.com")
        msg['To'] = recipient

        email_user = os.getenv("EMAIL_USER")
        email_pass = os.getenv("EMAIL_PASS")
        
        if not email_user or not email_pass:
            print(f"❌ [EMAIL DEBUG] Missing EMAIL_USER or EMAIL_PASS environment variables!")
            print(f"   EMAIL_USER: {'SET' if email_user else 'NOT SET'}")
            print(f"   EMAIL_PASS: {'SET' if email_pass else 'NOT SET'}")
            return
        
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(email_user, email_pass)
            server.send_message(msg)
            print(f"✅ [EMAIL DEBUG] Email sent successfully!")

    except Exception as e:
        print(f"❌ [EMAIL DEBUG] Failed to send email: {e}")
        

