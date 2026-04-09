# utils/email_service.py - Email Notifications
from flask_mail import Mail, Message
from flask import render_template
from threading import Thread
import os

mail = Mail()

def send_async_email(app, msg):
    """Send email asynchronously"""
    with app.app_context():
        mail.send(msg)

def send_email(app, recipient, subject, template, **kwargs):
    """Send email using template"""
    try:
        msg = Message(
            subject=subject,
            recipients=[recipient],
            html=render_template(f'emails/{template}.html', **kwargs)
        )
        
        # Send asynchronously to avoid blocking
        Thread(target=send_async_email, args=(app, msg)).start()
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False

def send_notification(app, user_id, notification_type, data):
    """Send notification and email"""
    from app import db, users_collection
    
    # Store notification in database
    notification = {
        'user_id': user_id,
        'type': notification_type,
        'data': data,
        'read': False,
        'created_at': datetime.now()
    }
    
    if db is not None:
        db.notifications.insert_one(notification)
    
    # Get user email
    user = users_collection.find_one({'_id': ObjectId(user_id)}) if users_collection else None
    
    if user and 'email' in user:
        # Send email based on type
        templates = {
            'application_received': {
                'subject': 'Application Received - ResumeMind AI',
                'template': 'application_received'
            },
            'candidate_selected': {
                'subject': 'Congratulations! You have been selected',
                'template': 'candidate_selected'
            },
            'job_posted': {
                'subject': 'New Job Posted - ResumeMind AI',
                'template': 'job_posted'
            },
            'new_application': {
                'subject': 'New Application Received',
                'template': 'new_application'
            }
        }
        
        if notification_type in templates:
            tmpl = templates[notification_type]
            send_email(
                app, user['email'],
                tmpl['subject'],
                tmpl['template'],
                **data
            )