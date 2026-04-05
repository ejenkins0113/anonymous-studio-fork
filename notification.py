"""
notifications.py / scheduler.py — Compliance Review Notification System
Anonymous Studio | CPSC 4205 | Group 3

Overview
--------
Implements an automated notification system for scheduled compliance reviews.
This feature addresses the issue of users missing important review appointments
due to lack of reminders.

When a review is scheduled
--------------------------
1. A background job is registered using APScheduler.
2. The system calculates a reminder time (default: 24 hours before the review).
3. At the scheduled time:
   - An email notification is sent to all attendees.
   - (Optional) An in-app notification can be triggered.

Purpose
-------
Ensures compliance officers receive timely reminders so they do not miss
scheduled compliance activities, improving accountability and system reliability.

Key Features
------------
- Email notifications via SMTP (Gmail or configurable provider)
- Background scheduling using APScheduler (non-blocking)
- Supports multiple recipients (appointment attendees)
- Extensible for in-app notifications via Taipy `notify()`
- Designed to integrate with existing appointment and pipeline systems

Usage (in app.py)
-----------------
    from scheduler import scheduler
    from notifications import send_email_notification

    # When creating an appointment:
    appt = store.create_appointment(...)

    # Schedule reminder
    schedule_review_notification(appt)
"""

import smtplib
from email.mime.text import MIMEText
import os

def send_email_notification(recipient, subject, message):
    sender = os.getenv("EMAIL_USER")
    password = os.getenv("EMAIL_PASS")

    msg = MIMEText(message)
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = recipient

    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(sender, password)
            server.send_message(msg)
        print(f"Email sent to {recipient}")
    except Exception as e:
        print("Email failed:", e) 

