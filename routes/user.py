"""
User Routes - Dashboard, Profile, Borrowings, History
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
import os

from models import db, User, Book, Borrowing, Reservation, Review, Notification
from email_service import send_email

user_bp = Blueprint('user', __name__)


@user_bp.route('/dashboard')
@login_required
def dashboard():
    """User dashboard"""
    # Get borrowings by status
    active_borrowings = Borrowing.query.filter_by(
        user_id=current_user.id,
        status='borrowed'
    ).order_by(Borrowing.due_date).all()

    pending_borrowings = Borrowing.query.filter_by(
        user_id=current_user.id,
        status='pending'
    ).order_by(Borrowing.created_at.desc()).all()

    pending_returns = Borrowing.query.filter_by(
        user_id=current_user.id,
        status='pending_return'
    ).order_by(Borrowing.created_at.desc()).all()
    
    # Get pending reservations
    reservations = Reservation.query.filter_by(
        user_id=current_user.id,
        status='pending'
    ).order_by(Reservation.created_at.desc()).all()
    
    # Calculate total fines
    total_fine = current_user.get_total_fine()
    
    # Get recent notifications
    notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(Notification.created_at.desc()).limit(5).all()
    
    # Statistics
    total_borrowed = Borrowing.query.filter_by(user_id=current_user.id).count()
    currently_borrowed = len(active_borrowings)
    overdue = sum(1 for b in active_borrowings if b.is_overdue())

    return render_template('user/dashboard.html',
                          active_borrowings=active_borrowings,
                          pending_borrowings=pending_borrowings,
                          pending_returns=pending_returns,
                          reservations=reservations,
                          total_fine=total_fine,
                          notifications=notifications,
                          total_borrowed=total_borrowed,
                          currently_borrowed=currently_borrowed,
                          overdue=overdue)


@user_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """User profile"""
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        department = request.form.get('department', '')
        address = request.form.get('address', '').strip()
        
        # Validate required fields
        if not full_name:
            flash('Full name is required.', 'error')
            from models import Department
            departments = Department.query.filter_by(is_active=True).all()
            return render_template('user/profile.html', departments=departments)
        
        if not email:
            flash('Email is required.', 'error')
            from models import Department
            departments = Department.query.filter_by(is_active=True).all()
            return render_template('user/profile.html', departments=departments)
        
        # Check if email is already taken by another user
        if email != current_user.email:
            existing_user = User.query.filter_by(email=email).first()
            if existing_user:
                flash('Email already registered to another user.', 'error')
                from models import Department
                departments = Department.query.filter_by(is_active=True).all()
                return render_template('user/profile.html', departments=departments)
        
        # Update user fields
        current_user.full_name = full_name
        current_user.email = email
        current_user.phone = phone
        current_user.department = department
        current_user.address = address
        
        # Handle profile image upload
        if 'profile_image' in request.files:
            file = request.files['profile_image']
            if file and file.filename:
                filename = secure_filename(f"{current_user.user_id}_{file.filename}")
                filepath = os.path.join('static', 'uploads', 'profiles', filename)
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                file.save(filepath)
                current_user.profile_image = filename
        
        try:
            db.session.commit()
            flash('Profile updated successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating profile: {str(e)}', 'error')
        
        return redirect(url_for('user.profile'))
    
    from models import Department
    departments = Department.query.filter_by(is_active=True).all()
    return render_template('user/profile.html', departments=departments)


@user_bp.route('/borrowings')
@login_required
def borrowings():
    """User's borrowing history"""
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', '')
    
    query = Borrowing.query.filter_by(user_id=current_user.id)
    
    if status:
        query = query.filter_by(status=status)
    
    borrowings = query.order_by(Borrowing.borrow_date.desc())\
        .paginate(page=page, per_page=10)
    
    return render_template('user/borrowings.html',
                          borrowings=borrowings,
                          current_status=status)


@user_bp.route('/borrowings/<int:borrowing_id>/return', methods=['POST'])
@login_required
def return_book(borrowing_id):
    """Return a borrowed book"""
    borrowing = Borrowing.query.filter_by(
        id=borrowing_id,
        user_id=current_user.id,
        status='borrowed'
    ).first_or_404()
    # Instead of immediately returning, require verification code
    from email_service import create_transaction_verification

    # Create verification record
    verification_code = create_transaction_verification(current_user.id, borrowing.id, 'return')

    # Send email with code
    try:
        subject = f"Return Confirmation Required: {borrowing.book.title}"
        html_body = f"""
        <html><body>
        <h3>Return Confirmation</h3>
        <p>Dear {current_user.full_name},</p>
        <p>Please confirm the return of <strong>{borrowing.book.title}</strong> by entering the verification code below:</p>
        <h2>{verification_code}</h2>
        <p>This code is valid for 24 hours.</p>
        </body></html>
        """
        text_body = f"Return Confirmation for {borrowing.book.title}\n\nVerification Code: {verification_code}\nThis code is valid for 24 hours."
        send_email(subject, current_user.email, text_body, html_body)
    except Exception as e:
        print(f"Error sending return confirmation email: {e}")

    # Mark borrowing as pending return
    borrowing.status = 'pending_return'
    db.session.commit()

    flash('Return request created. Check your email for the verification code to complete the return.', 'info')
    return redirect(url_for('user.dashboard'))


@user_bp.route('/borrowings/<int:borrowing_id>/renew', methods=['POST'])
@login_required
def renew_book(borrowing_id):
    """Renew a borrowed book"""
    borrowing = Borrowing.query.filter_by(
        id=borrowing_id,
        user_id=current_user.id,
        status='borrowed'
    ).first_or_404()
    
    if borrowing.renew():
        db.session.commit()
        
        # Create notification with action URL
        notification = Notification(
            user_id=current_user.id,
            title=f'Book Renewed: {borrowing.book.title}',
            message=f'Your book "{borrowing.book.title}" has been renewed. New due date: {borrowing.due_date.strftime("%B %d, %Y")}',
            notification_type='renewal',
            related_id=borrowing.id,
            action_url=url_for('user.dashboard')
        )
        db.session.add(notification)
        db.session.commit()
        
        # Generate verification code
        from email_service import create_transaction_verification
        verification_code = create_transaction_verification(current_user.id, borrowing.id, 'renew')
        
        # Send email notification
        try:
            subject = f"Book Renewed: {borrowing.book.title}"
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <h2 style="color: #667eea;">Book Renewed Successfully!</h2>
                <p>Dear {current_user.full_name},</p>
                <p>Your borrowing has been renewed:</p>
                <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                    <h3 style="color: #333; margin-top: 0;">{borrowing.book.title}</h3>
                    <p style="margin: 5px 0;"><strong>Author:</strong> {borrowing.book.author}</p>
                    <p style="margin: 5px 0;"><strong>New Due Date:</strong> <span style="color: #28a745; font-weight: bold;">{borrowing.due_date.strftime('%B %d, %Y')}</span></p>
                    <p style="margin: 5px 0;"><strong>Renewals Used:</strong> {borrowing.renewed_count} of 2</p>
                </div>
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; border-radius: 10px; margin: 20px 0; text-align: center;">
                    <p style="color: white; margin: 5px 0; font-size: 14px;">Transaction Verification Code</p>
                    <h1 style="color: white; margin: 10px 0; letter-spacing: 5px; font-size: 32px;">{verification_code}</h1>
                    <p style="color: white; margin: 5px 0; font-size: 12px;">Valid for 24 hours</p>
                </div>
                <p><strong>Important:</strong></p>
                <ul>
                    <li>Please return the book by the new due date</li>
                    <li>Maximum 2 renewals allowed per book</li>
                    <li>Late fee: ₹5 per day after due date</li>
                    <li>Keep this verification code for your records</li>
                </ul>
                <p>Thank you for using Digital Learning Library!</p>
                <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
                <p style="color: #999; font-size: 12px;">Digital Learning Library<br>3-4, Police Station Road<br>+91 9392513416</p>
            </body>
            </html>
            """
            text_body = f"Book Renewed: {borrowing.book.title}\n\nNew Due Date: {borrowing.due_date.strftime('%B %d, %Y')}\n\nVerification Code: {verification_code}"
            send_email(subject, current_user.email, text_body, html_body)
        except Exception as e:
            print(f"Error sending email: {e}")
        
        flash(f'Book renewed! New due date: {borrowing.due_date.strftime("%B %d, %Y")}', 'success')
    else:
        if borrowing.is_overdue():
            flash('Cannot renew overdue books. Please return the book first.', 'danger')
        elif borrowing.renewed_count >= 2:
            flash('Maximum renewal limit reached.', 'warning')
        else:
            flash('Unable to renew this book.', 'danger')
    
    return redirect(url_for('user.dashboard'))


@user_bp.route('/reservations')
@login_required
def reservations():
    """User's reservations"""
    page = request.args.get('page', 1, type=int)
    
    reservations = Reservation.query.filter_by(user_id=current_user.id)\
        .order_by(Reservation.created_at.desc())\
        .paginate(page=page, per_page=10)
    
    return render_template('user/reservations.html', reservations=reservations)


@user_bp.route('/notifications')
@login_required
def notifications():
    """User's notifications"""
    page = request.args.get('page', 1, type=int)
    
    notifications = Notification.query.filter_by(user_id=current_user.id)\
        .order_by(Notification.created_at.desc())\
        .paginate(page=page, per_page=20)
    
    # Mark as read
    Notification.query.filter_by(user_id=current_user.id, is_read=False)\
        .update({'is_read': True})
    db.session.commit()
    
    return render_template('user/notifications.html', notifications=notifications)


# NOTE: `/transactions/verify` POST handler removed to avoid duplicate endpoints.
# Verification and finalization logic is implemented in `verify_transaction_code` below.


@user_bp.route('/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    """Mark a notification as read"""
    notification = Notification.query.filter_by(
        id=notification_id,
        user_id=current_user.id
    ).first_or_404()
    
    notification.is_read = True
    db.session.commit()
    
    flash('Notification marked as read.', 'success')
    return redirect(url_for('user.notifications'))


@user_bp.route('/notifications/mark-all-read', methods=['POST'])
@login_required
def mark_all_notifications_read():
    """Mark all notifications as read"""
    Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).update({'is_read': True})
    
    db.session.commit()
    
    flash('All notifications marked as read.', 'success')
    return redirect(url_for('user.notifications'))


@user_bp.route('/notifications/<int:notification_id>/delete', methods=['POST'])
@login_required
def delete_notification(notification_id):
    """Delete a notification"""
    notification = Notification.query.filter_by(
        id=notification_id,
        user_id=current_user.id
    ).first_or_404()
    
    db.session.delete(notification)
    db.session.commit()
    
    flash('Notification deleted.', 'info')
    return redirect(url_for('user.notifications'))


@user_bp.route('/reviews')
@login_required
def reviews():
    """User's reviews"""
    reviews = Review.query.filter_by(user_id=current_user.id)\
        .order_by(Review.created_at.desc())\
        .all()
    
    return render_template('user/reviews.html', reviews=reviews)


@user_bp.route('/reviews/<int:review_id>/edit', methods=['POST'])
@login_required
def edit_review(review_id):
    """Edit a review"""
    review = Review.query.filter_by(
        id=review_id,
        user_id=current_user.id
    ).first_or_404()
    
    rating = request.form.get('rating', type=int)
    review_text = request.form.get('review_text')
    
    if rating and review_text:
        review.rating = rating
        review.review_text = review_text
        db.session.commit()
        flash('Review updated successfully.', 'success')
    else:
        flash('Please provide both rating and review text.', 'error')
    
    return redirect(url_for('user.reviews'))


@user_bp.route('/reviews/<int:review_id>/delete', methods=['POST'])
@login_required
def delete_review(review_id):
    """Delete a review"""
    review = Review.query.filter_by(
        id=review_id,
        user_id=current_user.id
    ).first_or_404()
    
    db.session.delete(review)
    db.session.commit()
    
    flash('Review deleted.', 'info')
    return redirect(url_for('user.reviews'))


@user_bp.route('/fines')
@login_required
def fines():
    """User's fines history"""
    # Get outstanding fines (not paid)
    outstanding_borrowings = Borrowing.query.filter(
        Borrowing.user_id == current_user.id,
        Borrowing.return_date == None,
        Borrowing.due_date < datetime.utcnow()
    ).all()
    
    # Calculate outstanding fines
    outstanding_fines = []
    total_fines = 0
    for borrowing in outstanding_borrowings:
        days_overdue = (datetime.utcnow().date() - borrowing.due_date.date()).days
        fine_amount = days_overdue * 5  # ₹5 per day
        outstanding_fines.append({
            'borrowing': borrowing,
            'days_overdue': days_overdue,
            'amount': fine_amount,
            'id': borrowing.id
        })
        total_fines += fine_amount
    
    # Get paid fines history
    paid_fines_history = Borrowing.query.filter(
        Borrowing.user_id == current_user.id,
        Borrowing.fine_amount > 0,
        Borrowing.fine_paid == True
    ).order_by(Borrowing.return_date.desc()).all()
    
    paid_fines = sum([b.fine_amount for b in paid_fines_history])
    all_time_fines = total_fines + paid_fines
    
    return render_template('user/fines.html',
                          outstanding_fines=outstanding_fines,
                          paid_fines_history=paid_fines_history,
                          total_fines=total_fines,
                          paid_fines=paid_fines,
                          all_time_fines=all_time_fines)


@user_bp.route('/fines/<int:fine_id>/pay', methods=['POST'])
@login_required
def pay_fine(fine_id):
    """Pay a single fine"""
    borrowing = Borrowing.query.filter_by(
        id=fine_id,
        user_id=current_user.id
    ).first_or_404()
    
    payment_method = request.form.get('payment_method', 'cash')
    
    # Calculate fine
    if borrowing.return_date is None and borrowing.due_date < datetime.utcnow():
        days_overdue = (datetime.utcnow().date() - borrowing.due_date.date()).days
        fine_amount = days_overdue * 5
        
        borrowing.fine_amount = fine_amount
        borrowing.fine_paid = True
        
        # In a real application, integrate with payment gateway here
        # For now, we'll mark it as paid
        
        db.session.commit()
        
        flash(f'Fine of ₹{fine_amount} paid successfully via {payment_method.upper()}.', 'success')
        db.session.commit()
        
        flash(f'Fine of ₹{fine_amount} paid successfully.', 'success')
    else:
        flash('No fine to pay for this borrowing.', 'info')
    
    return redirect(url_for('user.fines'))


@user_bp.route('/fines/pay-all', methods=['POST'])
@login_required
def pay_all_fines():
    """Pay all outstanding fines"""
    payment_method = request.form.get('payment_method', 'cash')
    
    outstanding_borrowings = Borrowing.query.filter(
        Borrowing.user_id == current_user.id,
        Borrowing.return_date == None,
        Borrowing.due_date < datetime.utcnow()
    ).all()
    
    total_paid = 0
    for borrowing in outstanding_borrowings:
        days_overdue = (datetime.utcnow().date() - borrowing.due_date.date()).days
        fine_amount = days_overdue * 5
        
        borrowing.fine_amount = fine_amount
        borrowing.fine_paid = True
        total_paid += fine_amount
    
    db.session.commit()
    
    if total_paid > 0:
        flash(f'All fines paid successfully via {payment_method.upper()}. Total: ₹{total_paid}', 'success')
    else:
        flash('No outstanding fines to pay.', 'info')
    
    return redirect(url_for('user.fines'))


@user_bp.route('/pricing')
def pricing():
    """Pricing and membership plans"""
    return render_template('pricing.html')


@user_bp.route('/upgrade-plan/<plan>')
@login_required
def upgrade_plan(plan):
    """Handle plan upgrade"""
    plan_details = {
        'standard': {'name': 'Standard', 'price': 299, 'duration': 'month'},
        'premium': {'name': 'Premium', 'price': 599, 'duration': 'month'},
        'standard_annual': {'name': 'Standard Annual', 'price': 2990, 'duration': 'year'},
        'premium_annual': {'name': 'Premium Annual', 'price': 5990, 'duration': 'year'},
    }
    
    if plan not in plan_details:
        flash('Invalid plan selected.', 'error')
        return redirect(url_for('user.pricing'))
    
    selected_plan = plan_details[plan]
    
    # In a real application, you would integrate with a payment gateway here
    # For now, we'll just show a success message
    flash(f'Please complete payment of ₹{selected_plan["price"]} for {selected_plan["name"]} plan.', 'info')
    flash('Payment integration will be added soon. Contact admin for manual upgrade.', 'warning')
    
    return redirect(url_for('user.dashboard'))


@user_bp.route('/verify-transaction', methods=['GET'])
@login_required
def verify_transaction():
    """Display transaction verification page"""
    from models import TransactionVerification
    
    # Get user's recent verified transactions
    recent_verifications = TransactionVerification.query.filter_by(
        user_id=current_user.id,
        is_verified=True
    ).order_by(TransactionVerification.verified_at.desc()).limit(5).all()
    
    return render_template('user/verify_transaction.html',
                          recent_verifications=recent_verifications)


@user_bp.route('/verify-transaction', methods=['POST'])
@login_required
def verify_transaction_code():
    """Verify a transaction code"""
    from models import TransactionVerification
    
    code = request.form.get('verification_code', '').strip().upper()
    
    if not code:
        flash('Please enter a verification code.', 'warning')
        return redirect(url_for('user.verify_transaction'))
    
    if len(code) != 6:
        flash('Verification code must be 6 characters.', 'warning')
        return redirect(url_for('user.verify_transaction'))
    
    # Find the verification record
    verification = TransactionVerification.query.filter_by(
        user_id=current_user.id,
        verification_code=code
    ).first()
    
    if not verification:
        flash('Invalid verification code. Please check and try again.', 'danger')
        return redirect(url_for('user.verify_transaction'))
    
    # Check if already verified
    if verification.is_verified:
        flash('This code has already been verified.', 'info')
        return redirect(url_for('user.verify_transaction'))
    
    # Check if expired
    if verification.is_expired():
        flash('This verification code has expired (valid for 24 hours only).', 'danger')
        return redirect(url_for('user.verify_transaction'))
    
    # Mark as verified
    verification.is_verified = True
    verification.verified_at = datetime.utcnow()
    db.session.add(verification)

    # Finalize the transaction depending on its type
    try:
        borrowing = verification.borrowing
        ttype = verification.transaction_type

        if ttype == 'borrow':
            # finalize borrow: ensure book available then decrement
            if borrowing.status in ['pending', 'pending_verification'] or borrowing.status == 'pending':
                book = borrowing.book
                if book.available_copies <= 0:
                    flash('Book is no longer available. Please contact admin.', 'danger')
                    db.session.commit()
                    return redirect(url_for('user.verify_transaction'))
                book.available_copies -= 1
                borrowing.status = 'borrowed'
                borrowing.borrow_date = datetime.utcnow()
                db.session.add(book)
                db.session.add(borrowing)
                notification = Notification(
                    user_id=current_user.id,
                    title=f'Book Borrowed: {book.title}',
                    message=f'You have successfully borrowed "{book.title}". Due date: {borrowing.due_date.strftime("%B %d, %Y")}',
                    notification_type='borrow',
                    related_id=borrowing.id,
                    action_url=url_for('user.dashboard')
                )
                db.session.add(notification)

        elif ttype == 'return':
            # finalize return
            book = borrowing.book
            borrowing.return_date = datetime.utcnow()
            fine = borrowing.calculate_fine()
            borrowing.fine_amount = fine
            borrowing.status = 'returned'
            book.available_copies += 1
            db.session.add(book)
            db.session.add(borrowing)

            # notify next reservation
            next_reservation = Reservation.query.filter_by(
                book_id=book.id,
                status='pending'
            ).order_by(Reservation.created_at).first()
            if next_reservation:
                notification = Notification(
                    user_id=next_reservation.user_id,
                    title='Book Available!',
                    message=f'The book "{book.title}" is now available for pickup.',
                    notification_type='reservation'
                )
                next_reservation.expiry_date = datetime.utcnow() + timedelta(days=3)
                next_reservation.notified = True
                db.session.add(next_reservation)
                db.session.add(notification)

        elif ttype == 'renew':
            # attempt to apply renewal if possible
            if borrowing.can_renew():
                borrowing.renew()
                db.session.add(borrowing)

        db.session.commit()
        flash(f'✓ Verification successful and {ttype} completed for "{borrowing.book.title}".', 'success')
    except Exception as e:
        db.session.rollback()
        print(f"Error finalizing verification action: {e}")
        flash('An error occurred while finalizing the transaction. Please contact admin.', 'danger')

    return redirect(url_for('user.verify_transaction'))

