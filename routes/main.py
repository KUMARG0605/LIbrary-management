"""
Main Routes - Home, About, Contact pages
"""

from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from email_service import send_email
from models import Setting
from models import db, Book, Category, Department, Borrowing

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    """Homepage with featured books and statistics"""
    # Get featured/latest books
    featured_books = Book.query.filter_by(is_active=True)\
        .order_by(Book.added_date.desc()).limit(8).all()
    
    # Get popular books (most borrowed)
    popular_books = db.session.query(Book, db.func.count(Borrowing.id).label('borrow_count'))\
        .join(Borrowing).group_by(Book.id)\
        .order_by(db.desc('borrow_count')).limit(4).all()
    
    # Get statistics
    stats = {
        'total_books': Book.query.count(),
        'available_books': Book.query.filter(Book.available_copies > 0).count(),
        'categories': Category.query.filter_by(is_active=True).count(),
        'departments': Department.query.filter_by(is_active=True).count(),
    }
    
    # Get categories with book count
    categories_with_count = db.session.query(
        Category, db.func.count(Book.id).label('book_count')
    ).outerjoin(Book, Book.category == Category.name)\
        .filter(Category.is_active == True)\
        .group_by(Category.id).all()
    
    return render_template('main/index.html',
                          featured_books=featured_books,
                          popular_books=popular_books,
                          stats=stats,
                          categories_with_count=categories_with_count)


@main_bp.route('/about')
def about():
    """About page"""
    return render_template('main/about.html')


@main_bp.route('/contact', methods=['GET', 'POST'])
def contact():
    """Contact page with form"""
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        subject = request.form.get('subject')
        message = request.form.get('message')
        # Save to DB or send notification to admin + confirmation to user
        admin_email = Setting.get('admin_email', None) or current_app.config.get('MAIL_DEFAULT_SENDER') or 'admin@library.com'

        # Build admin email
        try:
            subject_admin = f"Contact Form: {subject}"
            html_body_admin = render_template('emails/announcement.html', user=None, title=subject_admin, content=f"From: {name} &lt;{email}&gt;<br><br>{message}")
            text_body_admin = f"Contact Form Submission\nFrom: {name} <{email}>\n\nMessage:\n{message}"
            send_email(subject_admin, admin_email, text_body_admin, html_body_admin)

            # Confirmation to user
            subject_user = "We received your message"
            html_body_user = f"<html><body><p>Hello {name},</p><p>Thank you for contacting Digital Learning Library. We received your message and will get back to you soon.</p><p><strong>Your message:</strong><br>{message}</p><p>Regards,<br>Digital Learning Library</p></body></html>"
            text_body_user = f"Hello {name},\n\nThank you for contacting Digital Learning Library. We received your message and will get back to you soon.\n\nYour message:\n{message}\n\nRegards,\nDigital Learning Library"
            send_email(subject_user, email, text_body_user, html_body_user)
        except Exception as e:
            print(f"Error sending contact emails: {e}")

        flash('Thank you for your message! We will get back to you soon.', 'success')
        return redirect(url_for('main.contact'))
    
    return render_template('main/contact.html')


@main_bp.route('/search')
def search():
    """Global search functionality"""
    query = request.args.get('q', '')
    page = request.args.get('page', 1, type=int)
    
    if query:
        books = Book.query.filter(
            db.or_(
                Book.title.ilike(f'%{query}%'),
                Book.author.ilike(f'%{query}%'),
                Book.isbn.ilike(f'%{query}%'),
                Book.description.ilike(f'%{query}%')
            )
        ).filter_by(is_active=True).paginate(page=page, per_page=12)
    else:
        books = None
    
    return render_template('main/search.html', books=books, query=query)


@main_bp.route('/faq')
def faq():
    """FAQ page"""
    faqs = [
        {
            'question': 'How many books can I borrow at once?',
            'answer': 'You can borrow up to 5 books at a time. This limit helps ensure that all library members have access to the materials they need.'
        },
        {
            'question': 'What is the borrowing period?',
            'answer': 'The standard borrowing period is 14 days. You can renew books up to 2 times if no one else has reserved them.'
        },
        {
            'question': 'What are the late fees?',
            'answer': 'Late fees are ₹5 per day per book. We recommend returning or renewing books on time to avoid accumulating fines.'
        },
        {
            'question': 'How do I reserve a book?',
            'answer': 'If a book is currently unavailable, you can reserve it through the book details page. You will be notified when the book becomes available.'
        },
        {
            'question': 'Can I renew my books online?',
            'answer': 'Yes! You can renew your borrowed books through your dashboard, provided the book hasn\'t been reserved by another user and you haven\'t exceeded the renewal limit.'
        },
        {
            'question': 'What if I lose a book?',
            'answer': 'If you lose a book, please report it immediately to the library. You will be required to pay the replacement cost of the book plus a processing fee.'
        },
    ]
    return render_template('main/faq.html', faqs=faqs)


@main_bp.route('/privacy')
def privacy():
    """Privacy policy page"""
    return render_template('main/privacy.html')


@main_bp.route('/terms')
def terms():
    """Terms of service page"""
    return render_template('main/terms.html')
