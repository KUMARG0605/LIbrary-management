"""
Email Service Module
Comprehensive email handling for all library notifications
"""

from flask import render_template, current_app
from flask_mail import Message
from threading import Thread
from datetime import datetime, timedelta
import random
import string
import traceback
import os
from models import db, User, EmailLog


def generate_verification_code(length=6):
    """Generate a random verification code"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


def create_transaction_verification(user_id, borrowing_id, transaction_type):
    """Create a verification record for a transaction"""
    from models import TransactionVerification
    
    code = generate_verification_code()
    expires_at = datetime.utcnow() + timedelta(hours=24)
    
    verification = TransactionVerification(
        user_id=user_id,
        borrowing_id=borrowing_id,
        transaction_type=transaction_type,
        verification_code=code,
        expires_at=expires_at
    )
    
    db.session.add(verification)
    db.session.commit()
    
    return code


def send_async_email(app, msg):
    """Send email asynchronously"""
    with app.app_context():
        try:
            from app_new import mail
            print(f"[email_service] Sending email to: {msg.recipients} subject: {msg.subject}")
            mail.send(msg)
            print(f"[email_service] mail.send() succeeded for: {msg.recipients}")
            # Update EmailLog entries for these recipients to 'sent'
            try:
                from models import EmailLog
                from datetime import datetime, timedelta
                cutoff = datetime.utcnow() - timedelta(minutes=10)
                for recipient in msg.recipients:
                    logs = EmailLog.query.filter(EmailLog.recipient == recipient,
                                                 EmailLog.subject == msg.subject,
                                                 EmailLog.status == 'pending',
                                                 EmailLog.created_at >= cutoff).all()
                    for l in logs:
                        l.status = 'sent'
                        l.sent_at = datetime.utcnow()
                db.session.commit()
            except Exception:
                # Don't fail the whole send if logging update fails
                db.session.rollback()
            return True
        except Exception as e:
            print(f"Error sending email: {str(e)}")
            traceback.print_exc()
            # mark pending logs as failed
            try:
                from models import EmailLog
                from datetime import datetime, timedelta
                cutoff = datetime.utcnow() - timedelta(minutes=10)
                for recipient in msg.recipients:
                    logs = EmailLog.query.filter(EmailLog.recipient == recipient,
                                                 EmailLog.subject == msg.subject,
                                                 EmailLog.status == 'pending',
                                                 EmailLog.created_at >= cutoff).all()
                    for l in logs:
                        l.status = 'failed'
                        l.error_message = str(e)
                        l.sent_at = datetime.utcnow()
                db.session.commit()
            except Exception:
                db.session.rollback()
            return False


def send_email(subject, recipients, text_body=None, html_body=None, attachments=None):
    """
    Send email with logging
    
    Args:
        subject: Email subject
        recipients: List of recipient email addresses
        text_body: Plain text body
        html_body: HTML body
        attachments: List of (filename, content_type, data) tuples
    """
    from flask import current_app
    
    # Prepare recipients list
    to_list = recipients if isinstance(recipients, list) else [recipients]

    # If in debug and TEST_EMAIL is set, BCC that address for testing
    bcc_list = None
    try:
        test_email = os.environ.get('TEST_EMAIL') or current_app.config.get('TEST_EMAIL')
        if current_app.config.get('DEBUG') and test_email:
            bcc_list = [test_email]
            print(f"[email_service] DEBUG mode: will BCC test email {test_email} for subject '{subject}'")
    except Exception:
        bcc_list = None

    msg = Message(
        subject=subject,
        sender=current_app.config['MAIL_DEFAULT_SENDER'],
        recipients=to_list,
        bcc=bcc_list
    )
    
    msg.body = text_body
    msg.html = html_body
    
    if attachments:
        for filename, content_type, data in attachments:
            msg.attach(filename, content_type, data)
    
    # Log email
    for recipient in msg.recipients:
        email_log = EmailLog(
            recipient=recipient,
            subject=subject,
            status='pending'
        )
        db.session.add(email_log)
    db.session.commit()
    
    # Send asynchronously
    Thread(
        target=send_async_email,
        args=(current_app._get_current_object(), msg)
    ).start()


def send_verification_email(user, verification_url):
    """Send email verification code"""
    subject = "Verify Your Email - Digital Learning Library"
    
    html_body = render_template(
        'emails/verification.html',
        user=user,
        verification_url=verification_url
    )
    
    text_body = f"""
    Hello {user.full_name},
    
    Welcome to Digital Learning Library!
    
    Please verify your email address by clicking the link below:
    {verification_url}
    
    This link will expire in 24 hours.
    
    If you didn't create an account, please ignore this email.
    
    Best regards,
    Digital Learning Library Team
    """
    
    send_email(subject, user.email, text_body, html_body)


def send_welcome_email(user):
    """Send welcome email after successful registration"""
    subject = "Welcome to Digital Learning Library! 🎉"
    
    html_body = render_template(
        'emails/welcome.html',
        user=user
    )
    
    text_body = f"""
    Hello {user.full_name},
    
    Welcome to Digital Learning Library! We're excited to have you join our community.
    
    Your account has been successfully created:
    - User ID: {user.user_id}
    - Email: {user.email}
    - Role: {user.role.title()}
    
    You can now:
    ✓ Browse thousands of books across various categories
    ✓ Borrow physical books (up to {user.subscription.max_books if hasattr(user, 'subscription') else 5} at a time)
    ✓ Access digital books online
    ✓ Reserve books and get notifications
    ✓ Write reviews and rate books
    
    Get started: {current_app.config.get('BASE_URL', 'http://localhost:5000')}/books
    
    Need help? Contact us at bothackerr03@gmail.com
    
    Happy Reading!
    Digital Learning Library Team
    """
    
    send_email(subject, user.email, text_body, html_body)


def send_login_alert(user, ip_address, device_info):
    """Send login notification email"""
    subject = "New Login to Your Account"
    
    html_body = render_template(
        'emails/login_alert.html',
        user=user,
        ip_address=ip_address,
        device_info=device_info,
        login_time=datetime.utcnow()
    )
    
    text_body = f"""
    Hello {user.full_name},
    
    We detected a new login to your account:
    
    Time: {datetime.utcnow().strftime('%B %d, %Y at %I:%M %p UTC')}
    IP Address: {ip_address}
    Device: {device_info}
    
    If this was you, no action is needed.
    
    If you don't recognize this activity, please:
    1. Change your password immediately
    2. Contact us at bothackerr03@gmail.com
    
    Stay secure!
    Digital Learning Library Team
    """
    
    send_email(subject, user.email, text_body, html_body)


def send_password_reset_email(user, reset_url):
    """Send password reset email"""
    subject = "Reset Your Password - Digital Learning Library"
    
    html_body = render_template(
        'emails/password_reset.html',
        user=user,
        reset_url=reset_url
    )
    
    text_body = f"""
    Hello {user.full_name},
    
    You requested to reset your password.
    
    Click the link below to reset your password:
    {reset_url}
    
    This link will expire in 1 hour.
    
    If you didn't request this, please ignore this email and your password will remain unchanged.
    
    Best regards,
    Digital Learning Library Team
    """
    
    send_email(subject, user.email, text_body, html_body)


def send_book_due_reminder(user, borrowing):
    """Send reminder for due date approaching"""
    subject = "Book Due Date Reminder 📚"
    
    html_body = render_template(
        'emails/due_reminder.html',
        user=user,
        borrowing=borrowing
    )
    
    text_body = f"""
    Hello {user.full_name},
    
    This is a reminder that your borrowed book is due soon:
    
    Book: {borrowing.book.title}
    Author: {borrowing.book.author}
    Due Date: {borrowing.due_date.strftime('%B %d, %Y')}
    
    Please return the book on time to avoid fines (₹5 per day).
    
    You can renew the book if needed from your dashboard.
    
    Happy Reading!
    Digital Learning Library Team
    """
    
    send_email(subject, user.email, text_body, html_body)


def send_overdue_notice(user, borrowing):
    """Send overdue notice with fine calculation"""
    subject = "Book Overdue Notice - Fine Applicable ⚠️"
    
    fine_amount = borrowing.calculate_fine()
    
    html_body = render_template(
        'emails/overdue_notice.html',
        user=user,
        borrowing=borrowing,
        fine_amount=fine_amount
    )
    
    text_body = f"""
    Hello {user.full_name},
    
    Your borrowed book is overdue:
    
    Book: {borrowing.book.title}
    Due Date: {borrowing.due_date.strftime('%B %d, %Y')}
    Days Overdue: {borrowing.days_overdue()}
    Fine Amount: ₹{fine_amount}
    
    Please return the book as soon as possible to avoid additional fines.
    
    You can pay the fine online through your dashboard.
    
    Digital Learning Library Team
    """
    
    send_email(subject, user.email, text_body, html_body)


def send_reservation_available(user, reservation):
    """Notify user when reserved book is available"""
    subject = "Your Reserved Book is Now Available! 📖"
    
    html_body = render_template(
        'emails/reservation_available.html',
        user=user,
        reservation=reservation
    )
    
    text_body = f"""
    Hello {user.full_name},
    
    Great news! Your reserved book is now available:
    
    Book: {reservation.book.title}
    Author: {reservation.book.author}
    
    Please visit the library within 3 days to collect your book.
    
    After 3 days, the reservation will expire and the book will be available to others.
    
    Happy Reading!
    Digital Learning Library Team
    """
    
    send_email(subject, user.email, text_body, html_body)


def send_new_book_notification(users, book):
    """Notify users about new book additions"""
    subject = f"New Book Added: {book.title} 📚"
    
    for user in users:
        html_body = render_template(
            'emails/new_book.html',
            user=user,
            book=book
        )
        
        text_body = f"""
        Hello {user.full_name},
        
        A new book has been added to our collection:
        
        Title: {book.title}
        Author: {book.author}
        Category: {book.category}
        Department: {book.department}
        
        {book.description[:200] if book.description else ''}...
        
        Browse now: {current_app.config.get('BASE_URL', 'http://localhost:5000')}/books/{book.id}
        
        Happy Reading!
        Digital Learning Library Team
        """
        
        send_email(subject, user.email, text_body, html_body)


def send_admin_announcement(recipients, announcement_title, announcement_body):
    """Send announcement from admin to users"""
    subject = f"📢 Announcement: {announcement_title}"
    
    for recipient in recipients:
        user = User.query.filter_by(email=recipient).first()
        
        html_body = render_template(
            'emails/announcement.html',
            user=user,
            title=announcement_title,
            content=announcement_body
        )
        
        text_body = f"""
        Hello {user.full_name if user else 'Library Member'},
        
        ANNOUNCEMENT: {announcement_title}
        
        {announcement_body}
        
        ---
        This is an official announcement from Digital Learning Library.
        For questions, contact us at bothackerr03@gmail.com
        
        Best regards,
        Digital Learning Library Team
        """
        
        send_email(subject, recipient, text_body, html_body)


def send_subscription_confirmation(user, subscription, payment_id):
    """Send subscription purchase confirmation"""
    subject = f"Subscription Confirmed - {subscription.plan.name} Plan 🎉"
    
    html_body = render_template(
        'emails/subscription_confirmation.html',
        user=user,
        subscription=subscription,
        payment_id=payment_id
    )
    
    text_body = f"""
    Hello {user.full_name},
    
    Your subscription has been successfully activated!
    
    Plan: {subscription.plan.name}
    Duration: {subscription.duration_months} months
    Amount Paid: ₹{subscription.amount_paid}
    Payment ID: {payment_id}
    Valid Until: {subscription.end_date.strftime('%B %d, %Y')}
    
    Benefits:
    ✓ Borrow up to {subscription.plan.max_books} books
    ✓ {subscription.plan.digital_access} digital books
    ✓ Priority reservations
    ✓ No late fees (as per plan)
    
    Thank you for choosing Digital Learning Library!
    
    Best regards,
    Digital Learning Library Team
    """
    
    send_email(subject, user.email, text_body, html_body)


def send_subscription_expiry_reminder(user, subscription):
    """Remind user about subscription expiry"""
    subject = "Your Subscription is Expiring Soon"
    
    days_left = (subscription.end_date - datetime.utcnow()).days
    
    html_body = render_template(
        'emails/subscription_expiry.html',
        user=user,
        subscription=subscription,
        days_left=days_left
    )
    
    text_body = f"""
    Hello {user.full_name},
    
    Your {subscription.plan.name} subscription will expire in {days_left} days.
    
    Expiry Date: {subscription.end_date.strftime('%B %d, %Y')}
    
    Renew now to continue enjoying premium benefits:
    ✓ Extended borrowing limits
    ✓ Digital book access
    ✓ Priority support
    
    Renew Now: {current_app.config.get('BASE_URL', 'http://localhost:5000')}/user/subscription/renew
    
    Best regards,
    Digital Learning Library Team
    """
    
    send_email(subject, user.email, text_body, html_body)


def send_payment_receipt(user, payment):
    """Send payment receipt via email"""
    subject = f"Payment Receipt - Transaction #{payment.transaction_id}"
    
    html_body = render_template(
        'emails/payment_receipt.html',
        user=user,
        payment=payment
    )
    
    text_body = f"""
    Hello {user.full_name},
    
    Payment Receipt
    
    Transaction ID: {payment.transaction_id}
    Date: {payment.created_at.strftime('%B %d, %Y at %I:%M %p')}
    Amount: ₹{payment.amount}
    Payment Method: {payment.payment_method}
    Purpose: {payment.purpose}
    Status: {payment.status.upper()}
    
    Thank you for your payment!
    
    For any queries, contact us at bothackerr03@gmail.com
    
    Best regards,
    Digital Learning Library Team
    """
    
    send_email(subject, user.email, text_body, html_body)


def send_bulk_email(subject, content, recipient_filter=None):
    """
    Send bulk email to users based on filter
    
    Args:
        subject: Email subject
        content: Email content (HTML)
        recipient_filter: Dict with filter criteria (role, department, subscription_type, etc.)
    """
    query = User.query.filter_by(is_active=True, is_verified=True)
    
    if recipient_filter:
        if recipient_filter.get('role'):
            query = query.filter_by(role=recipient_filter['role'])
        if recipient_filter.get('department'):
            query = query.filter_by(department=recipient_filter['department'])
        if recipient_filter.get('subscription_type'):
            query = query.join(User.subscription).filter_by(
                plan_id=recipient_filter['subscription_type']
            )
    
    users = query.all()
    recipients = [user.email for user in users]
    
    send_admin_announcement(recipients, subject, content)
    
    return len(recipients)
