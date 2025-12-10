"""
Book Routes - Browse, Search, Details, Borrow, Reserve
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file, make_response
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from sqlalchemy import or_, func
import os

from models import db, Book, Borrowing, Reservation, Review, Category, Department, Notification
from email_service import send_email

books_bp = Blueprint('books', __name__)


@books_bp.route('/')
def index():
    """Browse all books with filters"""
    # Get filter parameters
    search = request.args.get('search', '').strip()
    department = request.args.get('department', '').strip()
    category = request.args.get('category', '').strip()
    availability = request.args.get('availability', '').strip()
    
    # Build query
    query = Book.query.filter_by(is_active=True)
    
    # Apply search filter
    if search:
        search_filter = or_(
            Book.title.ilike(f'%{search}%'),
            Book.author.ilike(f'%{search}%'),
            Book.isbn.ilike(f'%{search}%'),
            Book.description.ilike(f'%{search}%')
        )
        query = query.filter(search_filter)
    
    # Apply department filter
    if department:
        query = query.filter_by(department=department)
    
    # Apply category filter
    if category:
        query = query.filter_by(category=category)
    
    # Apply availability filter
    if availability == 'available':
        query = query.filter(Book.available_copies > 0)
    elif availability == 'unavailable':
        query = query.filter(Book.available_copies == 0)
    
    # Get all filtered books
    all_books = query.order_by(Book.title).all()
    
    # Calculate available count
    available_count = sum(1 for book in all_books if book.is_available())
    
    # Get filter options - get unique values from database
    all_departments = db.session.query(Book.department)\
        .filter(Book.is_active == True, Book.department != None, Book.department != '')\
        .distinct()\
        .order_by(Book.department)\
        .all()
    departments = [dept[0] for dept in all_departments]
    
    all_categories = db.session.query(Book.category)\
        .filter(Book.is_active == True, Book.category != None, Book.category != '')\
        .distinct()\
        .order_by(Book.category)\
        .all()
    categories = [cat[0] for cat in all_categories]
    
    # Create a simple object to mimic pagination for template compatibility
    class BooksList:
        def __init__(self, items):
            self.items = items
            self.total = len(items)
    
    books = BooksList(all_books)
    
    return render_template('books/index.html',
                          books=books,
                          categories=categories,
                          departments=departments,
                          available_count=available_count)


@books_bp.route('/<int:book_id>')
def detail(book_id):
    """Book detail page"""
    book = Book.query.get_or_404(book_id)
    
    # Get reviews
    reviews = Review.query.filter_by(book_id=book_id, is_approved=True)\
        .order_by(Review.created_at.desc()).limit(10).all()
    
    # Get similar books
    similar_books = Book.query.filter(
        Book.id != book_id,
        Book.is_active == True,
        or_(
            Book.category == book.category,
            Book.author == book.author
        )
    ).limit(4).all()
    
    # Check if user has borrowed this book
    user_borrowed = False
    user_reserved = False
    user_reviewed = False
    
    if current_user.is_authenticated:
        user_borrowed = Borrowing.query.filter_by(
            user_id=current_user.id,
            book_id=book_id,
            status='borrowed'
        ).first() is not None
        
        user_reserved = Reservation.query.filter_by(
            user_id=current_user.id,
            book_id=book_id,
            status='pending'
        ).first() is not None
        
        user_reviewed = Review.query.filter_by(
            user_id=current_user.id,
            book_id=book_id
        ).first() is not None
    
    return render_template('books/detail.html',
                          book=book,
                          reviews=reviews,
                          similar_books=similar_books,
                          user_borrowed=user_borrowed,
                          user_reserved=user_reserved,
                          user_reviewed=user_reviewed)


@books_bp.route('/<int:book_id>/borrow', methods=['POST'])
@login_required
def borrow(book_id):
    """Borrow a book"""
    book = Book.query.get_or_404(book_id)
    
    # Check if book is available
    if not book.is_available():
        flash('This book is currently not available.', 'danger')
        return redirect(url_for('books.detail', book_id=book_id))
    
    # Check if user can borrow
    if not current_user.can_borrow():
        if current_user.get_total_fine() > 0:
            flash('Please clear your pending fines before borrowing.', 'warning')
        else:
            flash('You have reached the maximum borrowing limit (5 books).', 'warning')
        return redirect(url_for('books.detail', book_id=book_id))
    
    # Check if user already has this book
    existing = Borrowing.query.filter_by(
        user_id=current_user.id,
        book_id=book_id,
        status='borrowed'
    ).first()
    
    if existing:
        flash('You already have this book borrowed.', 'warning')
        return redirect(url_for('books.detail', book_id=book_id))
    
    # Create borrowing record
    due_date = datetime.utcnow() + timedelta(days=14)
    borrowing = Borrowing(
        user_id=current_user.id,
        book_id=book_id,
        due_date=due_date,
        status='pending'
    )
    
    # Don't update book availability until user confirms with verification code
    
    # Cancel any pending reservation by this user
    reservation = Reservation.query.filter_by(
        user_id=current_user.id,
        book_id=book_id,
        status='pending'
    ).first()
    
    if reservation:
        reservation.status = 'fulfilled'
    
    db.session.add(borrowing)
    db.session.commit()
    
    # Create notification with action URL
    notification = Notification(
        user_id=current_user.id,
        title=f'Book Borrow Request: {book.title}',
        message=f'We have received your borrow request for "{book.title}". Please confirm using the verification code sent to your email. Due date on confirmation will be: {due_date.strftime("%B %d, %Y")}',
        notification_type='borrow',
        related_id=borrowing.id,
        action_url=url_for('user.dashboard')
    )
    db.session.add(notification)
    db.session.commit()
    
    # Generate verification code
    from email_service import create_transaction_verification
    verification_code = create_transaction_verification(current_user.id, borrowing.id, 'borrow')
    print(f"[books.borrow] Generated verification code for borrowing {borrowing.id}: {verification_code} -> {current_user.email}")
    
    # Send email notification with verification code (user must confirm)
    try:
        print(f"[books.borrow] Sending verification email to {current_user.email} for borrowing {borrowing.id}")
        subject = f"Book Borrowed: {book.title}"
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2 style="color: #667eea;">Book Borrowed Successfully!</h2>
            <p>Dear {current_user.full_name},</p>
            <p>You have successfully borrowed the following book:</p>
            <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                <h3 style="color: #333; margin-top: 0;">{book.title}</h3>
                <p style="margin: 5px 0;"><strong>Author:</strong> {book.author}</p>
                <p style="margin: 5px 0;"><strong>ISBN:</strong> {book.isbn}</p>
                <p style="margin: 5px 0;"><strong>Borrowed Date:</strong> {borrowing.borrow_date.strftime('%B %d, %Y')}</p>
                <p style="margin: 5px 0;"><strong>Due Date:</strong> <span style="color: #dc3545; font-weight: bold;">{due_date.strftime('%B %d, %Y')}</span></p>
            </div>
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; border-radius: 10px; margin: 20px 0; text-align: center;">
                <p style="color: white; margin: 5px 0; font-size: 14px;">Transaction Verification Code</p>
                <h1 style="color: white; margin: 10px 0; letter-spacing: 5px; font-size: 32px;">{verification_code}</h1>
                <p style="color: white; margin: 5px 0; font-size: 12px;">Valid for 24 hours</p>
            </div>
            <p><strong>Important Reminders:</strong></p>
            <ul>
                <li>Please return the book by the due date to avoid fines</li>
                <li>Late fee: ₹5 per day after the due date</li>
                <li>You can renew the book up to 2 times if needed</li>
                <li>Keep this verification code for your records</li>
            </ul>
            <p>Thank you for using Digital Learning Library!</p>
            <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
            <p style="color: #999; font-size: 12px;">Digital Learning Library<br>3-4, Police Station Road<br>+91 9392513416</p>
        </body>
        </html>
        """
        text_body = f"Book Borrowed: {book.title}\n\nDue Date: {due_date.strftime('%B %d, %Y')}\n\nVerification Code: {verification_code}\n\nPlease return on time to avoid late fees."
        send_email(subject, current_user.email, text_body, html_body)
    except Exception as e:
        print(f"Error sending email: {e}")
    
    flash('Borrow request submitted. Check your email for the verification code to complete borrowing.', 'info')
    return redirect(url_for('user.dashboard'))


@books_bp.route('/<int:book_id>/reserve', methods=['POST'])
@login_required
def reserve(book_id):
    """Reserve a book"""
    book = Book.query.get_or_404(book_id)
    
    # Check if book is already available
    if book.is_available():
        flash('This book is available. You can borrow it directly.', 'info')
        return redirect(url_for('books.detail', book_id=book_id))
    
    # Check if user already has a reservation
    existing = Reservation.query.filter_by(
        user_id=current_user.id,
        book_id=book_id,
        status='pending'
    ).first()
    
    if existing:
        flash('You already have a reservation for this book.', 'warning')
        return redirect(url_for('books.detail', book_id=book_id))
    
    # Create reservation
    reservation = Reservation(
        user_id=current_user.id,
        book_id=book_id
    )
    
    db.session.add(reservation)
    db.session.commit()
    
    # Send email notification
    try:
        subject = f"Book Reserved: {book.title}"
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2 style="color: #667eea;">Book Reserved Successfully!</h2>
            <p>Dear {current_user.full_name},</p>
            <p>You have successfully reserved the following book:</p>
            <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                <h3 style="color: #333; margin-top: 0;">{book.title}</h3>
                <p style="margin: 5px 0;"><strong>Author:</strong> {book.author}</p>
                <p style="margin: 5px 0;"><strong>ISBN:</strong> {book.isbn}</p>
                <p style="margin: 5px 0;"><strong>Reserved Date:</strong> {reservation.created_at.strftime('%B %d, %Y')}</p>
            </div>
            <p><strong>What happens next?</strong></p>
            <ul>
                <li>We will notify you when the book becomes available</li>
                <li>You will have 3 days to collect the book after notification</li>
                <li>Your reservation will expire if not collected within 3 days</li>
            </ul>
            <p>Thank you for using Digital Learning Library!</p>
            <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
            <p style="color: #999; font-size: 12px;">Digital Learning Library<br>3-4, Police Station Road<br>+91 9392513416</p>
        </body>
        </html>
        """
        text_body = f"Book Reserved: {book.title}\n\nWe will notify you when the book becomes available."
        send_email(subject, current_user.email, text_body, html_body)
    except Exception as e:
        print(f"Error sending email: {e}")
    
    flash('Book reserved successfully! We will notify you when it becomes available.', 'success')
    return redirect(url_for('user.dashboard'))


@books_bp.route('/<int:book_id>/cancel-reservation', methods=['POST'])
@login_required
def cancel_reservation(book_id):
    """Cancel a reservation"""
    reservation = Reservation.query.filter_by(
        user_id=current_user.id,
        book_id=book_id,
        status='pending'
    ).first_or_404()
    
    reservation.status = 'cancelled'
    db.session.commit()
    
    flash('Reservation cancelled successfully.', 'info')
    return redirect(url_for('user.dashboard'))


@books_bp.route('/<int:book_id>/review', methods=['POST'])
@login_required
def add_review(book_id):
    """Add a book review"""
    book = Book.query.get_or_404(book_id)
    
    # Check if user already reviewed
    existing = Review.query.filter_by(
        user_id=current_user.id,
        book_id=book_id
    ).first()
    
    if existing:
        flash('You have already reviewed this book.', 'warning')
        return redirect(url_for('books.detail', book_id=book_id))
    
    rating = request.form.get('rating', type=int)
    review_text = request.form.get('review_text', '').strip()
    
    if not rating or rating < 1 or rating > 5:
        flash('Please provide a valid rating (1-5).', 'danger')
        return redirect(url_for('books.detail', book_id=book_id))
    
    review = Review(
        user_id=current_user.id,
        book_id=book_id,
        rating=rating,
        review_text=review_text
    )
    
    db.session.add(review)
    db.session.commit()
    
    flash('Thank you for your review!', 'success')
    return redirect(url_for('books.detail', book_id=book_id))


@books_bp.route('/category/<category_name>')
def by_category(category_name):
    """Books by category"""
    page = request.args.get('page', 1, type=int)
    
    books = Book.query.filter_by(category=category_name, is_active=True)\
        .order_by(Book.title).paginate(page=page, per_page=12)
    
    category = Category.query.filter_by(name=category_name).first_or_404()
    
    return render_template('books/category.html',
                          books=books,
                          category=category)


@books_bp.route('/department/<dept_code>')
def by_department(dept_code):
    """Books by department"""
    page = request.args.get('page', 1, type=int)
    
    books = Book.query.filter_by(department=dept_code, is_active=True)\
        .order_by(Book.title).paginate(page=page, per_page=12)
    
    department = Department.query.filter_by(code=dept_code).first_or_404()
    
    return render_template('books/department.html',
                          books=books,
                          department=department)


@books_bp.route('/<int:book_id>/view-pdf')
def view_pdf(book_id):
    """View book PDF online"""
    book = Book.query.get_or_404(book_id)
    
    # In a real application, serve actual PDF from storage
    # For demo, we'll create a simple PDF or redirect to a reader
    from flask import send_file, make_response
    import io
    
    # Check if PDF file exists
    pdf_path = os.path.join('static', 'books', 'pdfs', f'{book.id}.pdf')
    
    if os.path.exists(pdf_path):
        return send_file(pdf_path, mimetype='application/pdf')
    else:
        # Return a placeholder message
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>{book.title}</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                }}
                .container {{
                    text-align: center;
                    padding: 40px;
                    background: rgba(255,255,255,0.1);
                    border-radius: 10px;
                }}
                h1 {{ font-size: 2em; margin-bottom: 20px; }}
                p {{ font-size: 1.2em; line-height: 1.6; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>📚 {book.title}</h1>
                <p><strong>Author:</strong> {book.author}</p>
                <p><strong>ISBN:</strong> {book.isbn}</p>
                <p style="margin-top: 30px;">
                    PDF content will be available soon.<br>
                    Please borrow the physical book or check back later.
                </p>
            </div>
        </body>
        </html>
        """
        return make_response(html_content)


@books_bp.route('/<int:book_id>/download-pdf')
def download_pdf(book_id):
    """Download book PDF"""
    book = Book.query.get_or_404(book_id)
    
    # Try ISBN filename first, then ID filename
    isbn_filename = f"{book.isbn.replace('/', '-').replace(' ', '_')}.pdf"
    pdf_path_isbn = os.path.join('static', 'books', 'pdfs', isbn_filename)
    pdf_path_id = os.path.join('static', 'books', 'pdfs', f'{book.id}.pdf')
    
    if os.path.exists(pdf_path_isbn):
        return send_file(
            pdf_path_isbn,
            as_attachment=True,
            download_name=f'{book.title}.pdf',
            mimetype='application/pdf'
        )
    elif os.path.exists(pdf_path_id):
        return send_file(
            pdf_path_id,
            as_attachment=True,
            download_name=f'{book.title}.pdf',
            mimetype='application/pdf'
        )
    else:
        flash('PDF not available for download yet. Please borrow the physical book.', 'warning')
        return redirect(url_for('books.detail', book_id=book_id))


@books_bp.route('/<int:book_id>/read-online')
def read_online(book_id):
    """Read book PDF online"""
    book = Book.query.get_or_404(book_id)
    
    # Try ISBN filename first, then ID filename
    isbn_filename = f"{book.isbn.replace('/', '-').replace(' ', '_')}.pdf"
    pdf_path_isbn = os.path.join('static', 'books', 'pdfs', isbn_filename)
    pdf_path_id = os.path.join('static', 'books', 'pdfs', f'{book.id}.pdf')
    
    if os.path.exists(pdf_path_isbn):
        # Serve PDF for inline viewing
        return send_file(
            pdf_path_isbn,
            mimetype='application/pdf',
            as_attachment=False,
            download_name=f'{book.title}.pdf'
        )
    elif os.path.exists(pdf_path_id):
        return send_file(
            pdf_path_id,
            mimetype='application/pdf',
            as_attachment=False,
            download_name=f'{book.title}.pdf'
        )
    else:
        flash('PDF not available for online reading yet. Please borrow the physical book.', 'warning')
        return redirect(url_for('books.detail', book_id=book_id))


