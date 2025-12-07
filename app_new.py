"""
Flask Application Factory
Library Management System - Main Application
"""

import os
from dotenv import load_dotenv
from flask import Flask, render_template
from flask_login import LoginManager
from flask_mail import Mail
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect

from config import config
from models import db, User

# Load environment variables from .env file
load_dotenv()

# Initialize extensions
login_manager = LoginManager()
mail = Mail()
migrate = Migrate()
csrf = CSRFProtect()


def create_app(config_name=None):
    """Application factory pattern"""
    if config_name is None:
        config_name = os.environ.get('FLASK_CONFIG', 'development')
    
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # Initialize extensions with app
    db.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    
    # Login manager configuration
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    # Register blueprints
    from routes.main import main_bp
    from routes.auth import auth_bp
    from routes.books import books_bp
    from routes.user import user_bp
    from routes.admin import admin_bp
    from routes.api import api_bp
    
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(books_bp, url_prefix='/books')
    app.register_blueprint(user_bp, url_prefix='/user')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(api_bp, url_prefix='/api')
    
    # Exempt API routes from CSRF protection
    csrf.exempt(api_bp)
    
    # Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('errors/500.html'), 500
    
    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template('errors/403.html'), 403
    
    # Context processors
    @app.context_processor
    def inject_globals():
        from models import Category, Department, Notification
        from flask_login import current_user
        
        categories = Category.query.filter_by(is_active=True).all()
        departments = Department.query.filter_by(is_active=True).all()
        
        unread_notifications = 0
        if current_user.is_authenticated:
            unread_notifications = Notification.query.filter_by(
                user_id=current_user.id, is_read=False
            ).count()
        
        return dict(
            categories=categories,
            departments=departments,
            unread_notifications=unread_notifications
        )
    
    # Create database tables
    with app.app_context():
        db.create_all()
        initialize_data()
    
    return app


def initialize_data():
    """Initialize default data"""
    from models import Category, Department, User, Setting
    
    # Create default categories if not exist
    default_categories = [
        ('Fiction', 'Novels, short stories, and imaginative literature', 'fa-book-open'),
        ('Non-Fiction', 'Factual books on various topics', 'fa-book'),
        ('Science', 'Scientific books and research', 'fa-flask'),
        ('Technology', 'Computer science and engineering', 'fa-laptop-code'),
        ('History', 'Historical books and biographies', 'fa-landmark'),
        ('Literature', 'Classic and contemporary literature', 'fa-feather'),
        ('Comics', 'Graphic novels and comics', 'fa-mask'),
        ('Horror', 'Horror and thriller novels', 'fa-ghost'),
        ('Reference', 'Encyclopedias and reference books', 'fa-search'),
        ('Academic', 'Textbooks and academic resources', 'fa-graduation-cap'),
    ]
    
    for name, desc, icon in default_categories:
        if not Category.query.filter_by(name=name).first():
            category = Category(name=name, description=desc, icon=icon)
            db.session.add(category)
    
    # Create default departments
    default_departments = [
        ('CSE', 'Computer Science and Engineering'),
        ('ECE', 'Electronics and Communication Engineering'),
        ('EEE', 'Electrical and Electronics Engineering'),
        ('MECH', 'Mechanical Engineering'),
        ('CIVIL', 'Civil Engineering'),
        ('CHEM', 'Chemical Engineering'),
        ('MME', 'Metallurgical and Materials Engineering'),
        ('BIO', 'Biotechnology'),
        ('MBA', 'Master of Business Administration'),
        ('MCA', 'Master of Computer Applications'),
    ]
    
    for code, name in default_departments:
        if not Department.query.filter_by(code=code).first():
            dept = Department(code=code, name=name)
            db.session.add(dept)
    
    # Create admin user if not exists
    if not User.query.filter_by(role='admin').first():
        admin = User(
            user_id='ADMIN001',
            email='admin@library.com',
            full_name='System Administrator',
            role='admin',
            is_verified=True,
            is_active=True
        )
        admin.set_password('admin123')
        db.session.add(admin)
    
    # Initialize default settings
    default_settings = [
        ('library_name', 'Digital Learning Library', 'Name of the library'),
        ('max_borrow_days', '14', 'Maximum days a book can be borrowed'),
        ('max_books_per_user', '5', 'Maximum books a user can borrow'),
        ('fine_per_day', '5', 'Fine amount per day for overdue books'),
        ('max_renewals', '2', 'Maximum number of renewals allowed'),
    ]
    
    for key, value, desc in default_settings:
        if not Setting.query.filter_by(key=key).first():
            setting = Setting(key=key, value=value, description=desc)
            db.session.add(setting)
    
    db.session.commit()


# Create app instance
app = create_app()


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5000, threaded=True)
