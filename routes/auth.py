"""
Authentication Routes - Login, Register, Password Reset
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta
import secrets

from models import db, User, Notification, ActivityLog
from email_service import send_welcome_email, send_login_alert

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        user_id = request.form.get('user_id', '').upper().strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember', False)
        
        user = User.query.filter(
            (User.user_id == user_id) | (User.email == user_id.lower())
        ).first()
        
        if user and user.check_password(password):
            if not user.is_active:
                flash('Your account has been deactivated. Please contact administrator.', 'danger')
                return render_template('auth/login.html')
            
            login_user(user, remember=remember)
            user.last_login = datetime.utcnow()
            
            # Log activity
            log = ActivityLog(
                user_id=user.id,
                action='login',
                details=f'User logged in from IP: {request.remote_addr}',
                ip_address=request.remote_addr
            )
            db.session.add(log)
            db.session.commit()
            
            # Send login notification email
            try:
                send_login_alert(user, request.remote_addr, device_info=request.user_agent.string)
            except Exception as e:
                print(f"Email sending failed: {str(e)}")
            
            flash(f'Welcome back, {user.full_name}!', 'success')
            
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            
            if user.role == 'admin':
                return redirect(url_for('admin.dashboard'))
            return redirect(url_for('user.dashboard'))
        
        flash('Invalid credentials. Please try again.', 'danger')
    
    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """User registration"""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        user_id = request.form.get('user_id', '').upper().strip()
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').lower().strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        phone = request.form.get('phone', '').strip()
        department = request.form.get('department', '')
        role = request.form.get('role', 'student')
        
        # Validation
        errors = []
        
        if len(user_id) < 4:
            errors.append('User ID must be at least 4 characters.')
        
        if len(password) < 6:
            errors.append('Password must be at least 6 characters.')
        
        if password != confirm_password:
            errors.append('Passwords do not match.')
        
        if User.query.filter_by(user_id=user_id).first():
            errors.append('User ID already exists.')
        
        if User.query.filter_by(email=email).first():
            errors.append('Email already registered.')
        
        if errors:
            for error in errors:
                flash(error, 'danger')
            return render_template('auth/register.html')
        
        # Create user
        verification_token = secrets.token_urlsafe(32)
        user = User(
            user_id=user_id,
            full_name=full_name,
            email=email,
            phone=phone,
            department=department,
            role=role if role in ['student', 'faculty'] else 'student',
            verification_token=verification_token
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()  # Commit user first to get user.id
        
        # Create welcome notification
        notification = Notification(
            user_id=user.id,
            title='Welcome to Digital Learning Library!',
            message='Thank you for registering. Start exploring our vast collection of books.',
            notification_type='general'
        )
        db.session.add(notification)
        
        # Log activity
        log = ActivityLog(
            action='registration',
            details=f'New user registered: {user_id}',
            ip_address=request.remote_addr
        )
        db.session.add(log)
        
        db.session.commit()
        
        # Send welcome email
        try:
            send_welcome_email(user)
        except Exception as e:
            print(f"Email sending failed: {str(e)}")
        
        flash('Registration successful! Please login to continue.', 'success')
        return redirect(url_for('auth.login'))
    
    from models import Department
    departments = Department.query.filter_by(is_active=True).all()
    return render_template('auth/register.html', departments=departments)


@auth_bp.route('/logout')
@login_required
def logout():
    """User logout"""
    # Log activity
    log = ActivityLog(
        user_id=current_user.id,
        action='logout',
        details='User logged out',
        ip_address=request.remote_addr
    )
    db.session.add(log)
    db.session.commit()
    
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('main.index'))


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Password reset request"""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').lower().strip()
        user = User.query.filter_by(email=email).first()
        
        if user:
            # Generate reset token
            reset_token = secrets.token_urlsafe(32)
            user.reset_token = reset_token
            user.reset_token_expiry = datetime.utcnow() + timedelta(hours=1)
            db.session.commit()
            
            # Here you would send an email with the reset link
            # For now, we'll just show a message
            flash(f'Password reset instructions have been sent to {email}', 'info')
        else:
            # Don't reveal whether email exists
            flash('If the email exists, password reset instructions will be sent.', 'info')
        
        return redirect(url_for('auth.login'))
    
    return render_template('auth/forgot_password.html')


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Password reset with token"""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    user = User.query.filter_by(reset_token=token).first()
    
    if not user or not user.reset_token_expiry or user.reset_token_expiry < datetime.utcnow():
        flash('Invalid or expired reset link.', 'danger')
        return redirect(url_for('auth.forgot_password'))
    
    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return render_template('auth/reset_password.html', token=token)
        
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/reset_password.html', token=token)
        
        user.set_password(password)
        user.reset_token = None
        user.reset_token_expiry = None
        db.session.commit()
        
        flash('Password has been reset successfully. Please login.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/reset_password.html', token=token)


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change password for logged in user"""
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not current_user.check_password(current_password):
            flash('Current password is incorrect.', 'danger')
            return render_template('auth/change_password.html')
        
        if len(new_password) < 6:
            flash('New password must be at least 6 characters.', 'danger')
            return render_template('auth/change_password.html')
        
        if new_password != confirm_password:
            flash('New passwords do not match.', 'danger')
            return render_template('auth/change_password.html')
        
        current_user.set_password(new_password)
        db.session.commit()
        
        flash('Password changed successfully!', 'success')
        return redirect(url_for('user.dashboard'))
    
    return render_template('auth/change_password.html')
