from authlib.integrations.flask_client import OAuth
from werkzeug.middleware.proxy_fix import ProxyFix
import secrets
from datetime import datetime, timedelta
from flask_mail import Mail, Message

from authlib.integrations.flask_client import OAuth

import os

# Production settings
if os.getenv('FLASK_ENV') == 'production':
    app.debug = False
    app.config['DEBUG'] = False


# Add these imports at the top
import secrets
import hashlib
import requests
from datetime import datetime, timedelta

from bson import json_util
import json

from datetime import datetime, timedelta

import os
import secrets
from datetime import datetime
from bson import ObjectId
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from flask_wtf.csrf import CSRFProtect
from flask_mail import Mail, Message
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
import certifi
import traceback
from dotenv import load_dotenv















import PyPDF2
import docx
from ai_matcher import analyze_resume_advanced

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-this')
app.config['WTF_CSRF_SECRET_KEY'] = os.getenv('WTF_CSRF_SECRET_KEY', 'csrf-secret-key-change-this')
app.config['WTF_CSRF_ENABLED'] = True

# Email configuration
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'true').lower() == 'true'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER')

# File upload configuration
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'txt', 'png', 'jpg', 'jpeg', 'gif'}

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize extensions
csrf = CSRFProtect(app)

mail = Mail(app)

# Initialize OAuth (add after app initialization)
oauth = OAuth(app)

# MongoDB Connection
try:
    mongo_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
    client = MongoClient(mongo_uri, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    print("✅ MongoDB Connected Successfully!")
    
    db = client[os.getenv('MONGODB_DB', 'resume_screener')]
    users_collection = db.users
    jobs_collection = db.jobs
    applications_collection = db.applications
    password_resets_collection = db.password_resets
    notifications_collection = db.notifications
    
    # Create indexes
    users_collection.create_index('email', unique=True)
    applications_collection.create_index([('user_id', 1), ('job_id', 1)], unique=True)
    
except Exception as e:
    print(f"❌ MongoDB Connection Error: {str(e)}")
    print("Please check your MongoDB connection and restart.")
    exit(1)


# MongoDB Connection
try:
    mongo_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
    client = MongoClient(mongo_uri, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    print("✅ MongoDB Connected Successfully!")
    
    db = client[os.getenv('MONGODB_DB', 'resume_screener')]
    users_collection = db.users
    jobs_collection = db.jobs
    applications_collection = db.applications
    password_resets_collection = db.password_resets
    notifications_collection = db.notifications
    complaints_collection = db.complaints  # ADD THIS LINE
    
    # Create indexes
    users_collection.create_index('email', unique=True)
    applications_collection.create_index([('user_id', 1), ('job_id', 1)], unique=True)
    
except Exception as e:
    print(f"❌ MongoDB Connection Error: {str(e)}")
    print("Please check your MongoDB connection and restart.")
    exit(1)
# ==================== Helper Functions ====================

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page', 'error')
            return redirect(url_for('login'))
        
        try:
            user = users_collection.find_one({'_id': ObjectId(session['user_id'])})
            if not user or user.get('role') != 'admin':
                flash('Access denied. Admin privileges required.', 'error')
                return redirect(url_for('index'))
        except Exception as e:
            print(f"Error in admin_required: {str(e)}")
            flash('Error verifying admin privileges', 'error')
            return redirect(url_for('index'))
        
        return f(*args, **kwargs)
    return decorated_function




def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def recruiter_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login', 'error')
            return redirect(url_for('login'))
        user = users_collection.find_one({'_id': ObjectId(session['user_id'])})
        if not user or user.get('role') != 'recruiter':
            flash('Access denied. Recruiter privileges required.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def jobseeker_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login', 'error')
            return redirect(url_for('login'))
        user = users_collection.find_one({'_id': ObjectId(session['user_id'])})
        if not user or user.get('role') != 'jobseeker':
            flash('Access denied. Job seeker privileges required.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def send_email(recipient, subject, template, **kwargs):
    """Send email"""
    try:
        msg = Message(subject=subject, recipients=[recipient])
        msg.html = render_template(f'emails/{template}', **kwargs)
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Email error: {str(e)}")
        return False

def extract_text_from_file(filepath):
    """Extract text from file"""
    try:
        ext = filepath.rsplit('.', 1)[1].lower()
        if ext == 'pdf':
            text = ""
            with open(filepath, 'rb') as f:
                pdf = PyPDF2.PdfReader(f)
                for page in pdf.pages:
                    text += page.extract_text()
            return text
        elif ext == 'docx':
            doc = docx.Document(filepath)
            return '\n'.join([para.text for para in doc.paragraphs])
        elif ext == 'txt':
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
    except Exception as e:
        print(f"Extraction error: {str(e)}")
        return ""

def create_notification(user_id, title, message, type='info', link=None):
    """Create notification"""
    try:
        notification = {
            'user_id': user_id,
            'title': title,
            'message': message,
            'type': type,
            'link': link,
            'is_read': False,
            'created_at': datetime.utcnow()
        }
        notifications_collection.insert_one(notification)
    except Exception as e:
        print(f"Notification error: {str(e)}")

def get_unread_count(user_id):
    """Get unread notifications count"""
    try:
        return notifications_collection.count_documents({
            'user_id': user_id,
            'is_read': False
        })
    except:
        return 0







# ==================== Complaint System ====================

@app.route('/admin/complaints')
@admin_required
def admin_complaints():
    """View all complaints raised against users"""
    try:
        complaints = list(complaints_collection.find().sort('created_at', -1))
        
        for complaint in complaints:
            complaint['_id'] = str(complaint['_id'])
            # Get reporter details
            reporter = users_collection.find_one({'_id': ObjectId(complaint['reporter_id'])})
            if reporter:
                complaint['reporter_name'] = reporter.get('full_name') or reporter.get('name', 'Unknown')
                complaint['reporter_email'] = reporter.get('email')
            
            # Get reported user details
            reported_user = users_collection.find_one({'_id': ObjectId(complaint['reported_user_id'])})
            if reported_user:
                complaint['reported_user_name'] = reported_user.get('full_name') or reported_user.get('name', 'Unknown')
                complaint['reported_user_email'] = reported_user.get('email')
                complaint['reported_user_role'] = reported_user.get('role', 'unknown')
                complaint['profile_picture'] = reported_user.get('profile_picture') or reported_user.get('company_logo')
        
        unread_count = get_unread_count(session['user_id'])
        
        return render_template('admin/complaints.html',
                             complaints=complaints,
                             unread_notifications=unread_count,
                             user_name=session.get('user_name'))
        
    except Exception as e:
        print(f"Admin complaints error: {str(e)}")
        flash('Error loading complaints', 'error')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/complaint/<complaint_id>/resolve', methods=['POST'])
@admin_required
def resolve_complaint(complaint_id):
    """Mark a complaint as resolved"""
    try:
        complaints_collection.update_one(
            {'_id': ObjectId(complaint_id)},
            {'$set': {'status': 'resolved', 'resolved_at': datetime.utcnow(), 'resolved_by': session['user_id']}}
        )
        flash('Complaint marked as resolved', 'success')
    except Exception as e:
        print(f"Resolve complaint error: {str(e)}")
        flash('Error resolving complaint', 'error')
    
    return redirect(url_for('admin_complaints'))

@app.route('/report-user/<user_id>', methods=['POST'])
@login_required
def report_user(user_id):
    """Report a user for inappropriate behavior"""
    try:
        reason = request.form.get('reason')
        description = request.form.get('description')
        
        if not reason:
            flash('Please provide a reason for reporting', 'error')
            return redirect(request.referrer)
        
        complaint = {
            'reporter_id': session['user_id'],
            'reported_user_id': user_id,
            'reason': reason,
            'description': description,
            'status': 'pending',
            'created_at': datetime.utcnow()
        }
        
        complaints_collection.insert_one(complaint)
        
        # Notify admin
        create_notification(
            'admin',
            'New Complaint Received',
            f'A new complaint has been filed against user',
            'warning',
            url_for('admin_complaints')
        )
        
        flash('Complaint submitted successfully. Admin will review it.', 'success')
        
    except Exception as e:
        print(f"Report user error: {str(e)}")
        flash('Error submitting complaint', 'error')
    
    return redirect(request.referrer)














# ==================== Auth Routes ====================

@app.route('/')
def index():
    """Home page"""
    unread_count = 0
    if 'user_id' in session:
        unread_count = get_unread_count(session['user_id'])
    return render_template('index.html', unread_notifications=unread_count)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            full_name = request.form.get('full_name')
            email = request.form.get('email')
            password = request.form.get('password')
            confirm = request.form.get('confirm_password')
            role = request.form.get('role')
            
            # Validation
            if not all([full_name, email, password, confirm]):
                flash('All fields are required', 'error')
                return redirect(url_for('register'))
            
            if password != confirm:
                flash('Passwords do not match', 'error')
                return redirect(url_for('register'))
            
            if len(password) < 8:
                flash('Password must be at least 8 characters', 'error')
                return redirect(url_for('register'))
            
            # Check if user exists
            if users_collection.find_one({'email': email}):
                flash('Email already registered', 'error')
                return redirect(url_for('register'))
            
            # Create user with both name fields
            user = {
                'name': full_name,
                'full_name': full_name,
                'email': email,
                'password': generate_password_hash(password),
                'role': role,
                'created_at': datetime.utcnow(),
                'is_active': True
            }
            
            result = users_collection.insert_one(user)
            
            # Store in session
            session['user_id'] = str(result.inserted_id)
            session['user_email'] = email
            session['user_name'] = full_name
            session['user_role'] = role
            
            flash('Registration successful!', 'success')
            
            # Redirect based on role
            if role == 'recruiter':
                return redirect(url_for('recruiter_dashboard'))
            elif role == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('jobseeker_dashboard'))
                
        except Exception as e:
            print(f"Registration error: {str(e)}")
            flash(f'Registration failed: {str(e)}', 'error')
            return redirect(url_for('register'))
    
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            email = request.form.get('email')
            password = request.form.get('password')
            
            user = users_collection.find_one({'email': email})
            
            if user and check_password_hash(user['password'], password):
                # Check if user is active
                if not user.get('is_active', True):
                    flash('Your account has been deactivated. Please contact admin.', 'error')
                    return redirect(url_for('login'))
                
                session['user_id'] = str(user['_id'])
                session['user_email'] = user['email']
                session['user_name'] = user.get('name') or user.get('full_name', 'User')
                session['user_role'] = user['role']
                
                # Store profile picture in session
                if user.get('profile_picture'):
                    session['profile_picture'] = user['profile_picture']
                elif user.get('company_logo'):
                    session['profile_picture'] = user['company_logo']
                
                flash(f'Welcome back, {session["user_name"]}!', 'success')
                
                # Redirect based on role
                if user['role'] == 'recruiter':
                    return redirect(url_for('recruiter_dashboard'))
                elif user['role'] == 'admin':
                    return redirect(url_for('admin_dashboard'))
                else:
                    return redirect(url_for('jobseeker_dashboard'))
            else:
                flash('Invalid email or password', 'error')
        except Exception as e:
            print(f"Login error: {str(e)}")
            flash('Login failed', 'error')
    
    return render_template('login.html')




@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully', 'info')
    return redirect(url_for('index'))

# ==================== Notification Routes ====================

@app.route('/notifications')
@login_required
def notifications():
    """View all notifications"""
    try:
        notifs = list(notifications_collection.find(
            {'user_id': session['user_id']}
        ).sort('created_at', -1))
        
        for n in notifs:
            n['_id'] = str(n['_id'])
            if 'created_at' in n:
                n['created_at_str'] = n['created_at'].strftime('%B %d, %Y at %H:%M')
        
        # Mark all as read
        notifications_collection.update_many(
            {'user_id': session['user_id'], 'is_read': False},
            {'$set': {'is_read': True}}
        )
        
        unread_count = get_unread_count(session['user_id'])
        
        return render_template('notifications.html',
                             notifications=notifs,
                             unread_notifications=unread_count,
                             user_name=session.get('user_name'))
        
    except Exception as e:
        print(f"Notifications error: {str(e)}")
        flash('Error loading notifications', 'error')
        return redirect(url_for('index'))

@app.route('/notifications/count')
@login_required
def notification_count():
    """Get unread notifications count"""
    try:
        count = get_unread_count(session['user_id'])
        return jsonify({'count': count})
    except:
        return jsonify({'count': 0})


# ==================== Admin Routes ====================

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page', 'error')
            return redirect(url_for('login'))
        
        user = users_collection.find_one({'_id': ObjectId(session['user_id'])})
        if not user or user.get('role') != 'admin':
            flash('Access denied. Admin privileges required.', 'error')
            return redirect(url_for('index'))
        
        return f(*args, **kwargs)
    return decorated_function


@app.route('/admin/profile')
@admin_required
def admin_profile():
    """Admin profile page"""
    try:
        user = users_collection.find_one({'_id': ObjectId(session['user_id'])})
        unread_count = get_unread_count(session['user_id'])
        
        return render_template('admin/profile.html',
                             user=user,
                             unread_notifications=unread_count,
                             user_name=session.get('user_name'))
    except Exception as e:
        print(f"Admin profile error: {str(e)}")
        flash('Error loading profile', 'error')
        return redirect(url_for('admin_dashboard'))


@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    """Admin dashboard with system overview"""
    try:
        # Get statistics
        total_users = users_collection.count_documents({})
        total_jobseekers = users_collection.count_documents({'role': 'jobseeker'})
        total_recruiters = users_collection.count_documents({'role': 'recruiter'})
        total_jobs = jobs_collection.count_documents({})
        active_jobs = jobs_collection.count_documents({'is_active': True})
        total_applications = applications_collection.count_documents({})
        
        # ADD COMPLAINTS STATS (make sure complaints_collection exists)
        try:
            pending_complaints = complaints_collection.count_documents({'status': 'pending'})
            total_complaints = complaints_collection.count_documents({})
        except:
            pending_complaints = 0
            total_complaints = 0
        
        # Get recent complaints for preview
        recent_complaints = []
        try:
            recent_complaints = list(complaints_collection.find({'status': 'pending'}).sort('created_at', -1).limit(5))
            for complaint in recent_complaints:
                complaint['_id'] = str(complaint['_id'])
                # Get reporter details
                reporter = users_collection.find_one({'_id': ObjectId(complaint['reporter_id'])})
                if reporter:
                    complaint['reporter_name'] = reporter.get('full_name') or reporter.get('name', 'Unknown')
                # Get reported user details
                reported_user = users_collection.find_one({'_id': ObjectId(complaint['reported_user_id'])})
                if reported_user:
                    complaint['reported_user_name'] = reported_user.get('full_name') or reported_user.get('name', 'Unknown')
        except Exception as e:
            print(f"Error getting complaints: {str(e)}")
        
        # Get recent users
        recent_users = list(users_collection.find().sort('created_at', -1).limit(10))
        for user in recent_users:
            user['_id'] = str(user['_id'])
            if 'created_at' in user:
                user['created_at_str'] = user['created_at'].strftime('%Y-%m-%d %H:%M')
        
        # Get recent jobs
        recent_jobs = list(jobs_collection.find().sort('posted_date', -1).limit(10))
        for job in recent_jobs:
            job['_id'] = str(job['_id'])
            if 'posted_date' in job:
                job['posted_date_str'] = job['posted_date'].strftime('%Y-%m-%d')
        
        # Get recent applications
        recent_apps = list(applications_collection.find().sort('applied_date', -1).limit(10))
        for app in recent_apps:
            app['_id'] = str(app['_id'])
            if 'applied_date' in app:
                app['applied_date_str'] = app['applied_date'].strftime('%Y-%m-%d')
        
        unread_count = get_unread_count(session['user_id'])
        
        return render_template('admin/dashboard.html',
                             total_users=total_users,
                             total_jobseekers=total_jobseekers,
                             total_recruiters=total_recruiters,
                             total_jobs=total_jobs,
                             active_jobs=active_jobs,
                             total_applications=total_applications,
                             pending_complaints=pending_complaints,  # MAKE SURE THIS IS PASSED
                             total_complaints=total_complaints,      # AND THIS
                             recent_complaints=recent_complaints,
                             recent_users=recent_users,
                             recent_jobs=recent_jobs,
                             recent_apps=recent_apps,
                             unread_notifications=unread_count,
                             user_name=session.get('user_name'))
        
    except Exception as e:
        print(f"Admin dashboard error: {str(e)}")
        import traceback
        traceback.print_exc()
        flash('Error loading admin dashboard', 'error')
        return redirect(url_for('index'))
@app.route('/admin/create-user', methods=['GET', 'POST'])
@admin_required
def admin_create_user():
    """Admin route to manually create a new user"""
    try:
        if request.method == 'POST':
            full_name = request.form.get('full_name')
            email = request.form.get('email')
            password = request.form.get('password')
            role = request.form.get('role')
            
            # Validation
            if not all([full_name, email, password, role]):
                flash('All fields are required', 'error')
                return redirect(url_for('admin_create_user'))
            
            if len(password) < 8:
                flash('Password must be at least 8 characters', 'error')
                return redirect(url_for('admin_create_user'))
            
            # Check if user exists
            if users_collection.find_one({'email': email}):
                flash('Email already registered', 'error')
                return redirect(url_for('admin_create_user'))
            
            # Create user
            user = {
                'name': full_name,
                'full_name': full_name,
                'email': email,
                'password': generate_password_hash(password),
                'role': role,
                'created_at': datetime.utcnow(),
                'is_active': True,
                'created_by': session.get('user_id')
            }
            
            users_collection.insert_one(user)
            flash(f'User {email} created successfully!', 'success')
            return redirect(url_for('admin_users'))
        
        unread_count = get_unread_count(session['user_id'])
        return render_template('admin/create_user.html', 
                             unread_notifications=unread_count,
                             user_name=session.get('user_name'))
    
    except Exception as e:
        print(f"Create user error: {str(e)}")
        flash('Error creating user', 'error')
        return redirect(url_for('admin_users'))


        

@app.route('/admin/users')
@admin_required
def admin_users():
    """Manage all users"""
    try:
        # Get filter parameters
        role = request.args.get('role', '')
        search = request.args.get('search', '')
        
        # Build query
        query = {}
        if role:
            query['role'] = role
        if search:
            query['$or'] = [
                {'email': {'$regex': search, '$options': 'i'}},
                {'name': {'$regex': search, '$options': 'i'}},
                {'full_name': {'$regex': search, '$options': 'i'}}
            ]
        
        # Get users
        users = list(users_collection.find(query).sort('created_at', -1))
        
        user_list = []
        for user in users:
            user_id = str(user['_id'])
            
            # Get user stats
            if user.get('role') == 'jobseeker':
                applications_count = applications_collection.count_documents({'user_id': user_id})
                shortlisted_count = applications_collection.count_documents({'user_id': user_id, 'status': 'shortlisted'})
                hired_count = applications_collection.count_documents({'user_id': user_id, 'status': 'hired'})
                jobs_count = 0
            elif user.get('role') == 'recruiter':
                jobs_count = jobs_collection.count_documents({'recruiter_id': user_id})
                applications_count = 0
                shortlisted_count = 0
                hired_count = 0
            else:
                applications_count = 0
                shortlisted_count = 0
                hired_count = 0
                jobs_count = 0
            
            user_list.append({
                '_id': user_id,
                'name': user.get('name') or user.get('full_name', 'Unknown'),
                'email': user.get('email'),
                'role': user.get('role', 'unknown'),
                'company': user.get('company', ''),
                'created_at': user.get('created_at'),
                'created_at_str': user.get('created_at').strftime('%Y-%m-%d') if user.get('created_at') else 'N/A',
                'is_active': user.get('is_active', True),
                'has_resume': 'resume_text' in user and user['resume_text'],
                'applications_count': applications_count,
                'shortlisted_count': shortlisted_count,
                'hired_count': hired_count,
                'jobs_count': jobs_count
            })
        
        # Get counts for stats
        total_users = len(user_list)
        total_jobseekers = len([u for u in user_list if u['role'] == 'jobseeker'])
        total_recruiters = len([u for u in user_list if u['role'] == 'recruiter'])
        total_admins = len([u for u in user_list if u['role'] == 'admin'])
        
        unread_count = get_unread_count(session['user_id'])
        
        return render_template('admin/users.html',
                             users=user_list,
                             total_users=total_users,
                             total_jobseekers=total_jobseekers,
                             total_recruiters=total_recruiters,
                             total_admins=total_admins,
                             selected_role=role,
                             search_query=search,
                             unread_notifications=unread_count,
                             user_name=session.get('user_name'))
    
    except Exception as e:
        print(f"Admin users error: {str(e)}")
        flash('Error loading users', 'error')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/user/<user_id>')
@admin_required
def admin_user_detail(user_id):
    """View detailed user information"""
    try:
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        
        if not user:
            flash('User not found', 'error')
            return redirect(url_for('admin_users'))
        
        user['_id'] = str(user['_id'])
        
        # Get user activity
        if user.get('role') == 'jobseeker':
            applications = list(applications_collection.find({'user_id': user_id}).sort('applied_date', -1))
            for app in applications:
                app['_id'] = str(app['_id'])
                if 'applied_date' in app:
                    app['applied_date_str'] = app['applied_date'].strftime('%Y-%m-%d')
            
            # Calculate stats
            applications_count = len(applications)
            shortlisted_count = len([a for a in applications if a.get('status') == 'shortlisted'])
            hired_count = len([a for a in applications if a.get('status') == 'hired'])
            
            saved_jobs = user.get('saved_jobs', [])
            saved_jobs_list = []
            for job_id in saved_jobs:
                job = jobs_collection.find_one({'_id': ObjectId(job_id)})
                if job:
                    job['_id'] = str(job['_id'])
                    saved_jobs_list.append(job)
            
            jobs_count = 0
            posted_jobs = []
            total_applications_received = 0
            total_shortlisted = 0
            total_hired = 0
            
        elif user.get('role') == 'recruiter':
            posted_jobs = list(jobs_collection.find({'recruiter_id': user_id}).sort('posted_date', -1))
            jobs_count = len(posted_jobs)
            total_applications_received = 0
            total_shortlisted = 0
            total_hired = 0
            
            for job in posted_jobs:
                job['_id'] = str(job['_id'])
                if 'posted_date' in job:
                    job['posted_date_str'] = job['posted_date'].strftime('%Y-%m-%d')
                
                # Get application stats for each job
                job_apps = list(applications_collection.find({'job_id': job['_id']}))
                job['applications_count'] = len(job_apps)
                job['shortlisted_count'] = len([a for a in job_apps if a.get('status') == 'shortlisted'])
                job['hired_count'] = len([a for a in job_apps if a.get('status') == 'hired'])
                job['pending_count'] = len([a for a in job_apps if a.get('status') == 'pending'])
                
                # Get recent applicants
                recent_apps = sorted(job_apps, key=lambda x: x.get('applied_date', datetime.min), reverse=True)[:5]
                job['applications'] = []
                for app in recent_apps:
                    applicant = users_collection.find_one({'_id': ObjectId(app['user_id'])})
                    if applicant:
                        job['applications'].append({
                            'name': applicant.get('full_name') or applicant.get('name', 'Unknown'),
                            'score': app.get('analysis', {}).get('overall', 0),
                            'status': app.get('status', 'pending')
                        })
                
                total_applications_received += job['applications_count']
                total_shortlisted += job['shortlisted_count']
                total_hired += job['hired_count']
            
            applications = []
            applications_count = 0
            shortlisted_count = 0
            hired_count = 0
            saved_jobs_list = []
        
        else:
            applications = []
            applications_count = 0
            shortlisted_count = 0
            hired_count = 0
            saved_jobs_list = []
            jobs_count = 0
            posted_jobs = []
            total_applications_received = 0
            total_shortlisted = 0
            total_hired = 0
        
        # Create recent activity (simplified for now)
        recent_activities = []
        
        unread_count = get_unread_count(session['user_id'])
        
        return render_template('admin/user_detail.html',
                             user=user,
                             applications=applications,
                             applications_count=applications_count,
                             shortlisted_count=shortlisted_count,
                             hired_count=hired_count,
                             saved_jobs=saved_jobs_list,
                             posted_jobs=posted_jobs,
                             jobs_count=jobs_count,
                             total_applications_received=total_applications_received,
                             total_shortlisted=total_shortlisted,
                             total_hired=total_hired,
                             recent_activities=recent_activities,
                             unread_notifications=unread_count,
                             user_name=session.get('user_name'))
        
    except Exception as e:
        print(f"Admin user detail error: {str(e)}")
        import traceback
        traceback.print_exc()
        flash('Error loading user details', 'error')
        return redirect(url_for('admin_users'))

@app.route('/admin/user/<user_id>/toggle-status', methods=['POST'])
@admin_required
def admin_toggle_user_status(user_id):
    """Activate or deactivate a user"""
    try:
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        
        if not user:
            flash('User not found', 'error')
            return redirect(url_for('admin_users'))
        
        # Toggle status
        new_status = not user.get('is_active', True)
        
        users_collection.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': {'is_active': new_status}}
        )
        
        status_text = 'activated' if new_status else 'deactivated'
        flash(f'User {status_text} successfully', 'success')
        
        # Notify user
        try:
            create_notification(
                user_id,
                'Account Status Changed',
                f'Your account has been {status_text} by an administrator.',
                'info'
            )
        except:
            pass
        
        return redirect(url_for('admin_users'))
    
    except Exception as e:
        print(f"Toggle user status error: {str(e)}")
        flash('Error updating user status', 'error')
        return redirect(url_for('admin_users'))

@app.route('/admin/user/<user_id>/delete', methods=['POST'])
@admin_required
def admin_delete_user(user_id):
    """Delete a user and all associated data"""
    try:
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        
        if not user:
            flash('User not found', 'error')
            return redirect(url_for('admin_users'))
        
        user_email = user.get('email')
        user_role = user.get('role')
        
        # Delete user's applications (if job seeker)
        if user_role == 'jobseeker':
            apps_deleted = applications_collection.delete_many({'user_id': user_id})
            print(f"Deleted {apps_deleted.deleted_count} applications for user {user_email}")
        
        # Delete user's notifications
        notifications_collection.delete_many({'user_id': user_id})
        
        # If recruiter, also handle their jobs
        if user_role == 'recruiter':
            # Get all jobs posted by this recruiter
            recruiter_jobs = jobs_collection.find({'recruiter_id': user_id})
            job_ids = [str(job['_id']) for job in recruiter_jobs]
            
            # Delete applications for these jobs
            if job_ids:
                apps_deleted = applications_collection.delete_many({'job_id': {'$in': job_ids}})
                print(f"Deleted {apps_deleted.deleted_count} applications for recruiter's jobs")
            
            # Delete the jobs
            jobs_deleted = jobs_collection.delete_many({'recruiter_id': user_id})
            print(f"Deleted {jobs_deleted.deleted_count} jobs posted by recruiter")
        
        # Finally, delete the user
        users_collection.delete_one({'_id': ObjectId(user_id)})
        
        flash(f'User {user_email} and all associated data deleted successfully', 'success')
        return redirect(url_for('admin_users'))
    
    except Exception as e:
        print(f"Delete user error: {str(e)}")
        flash('Error deleting user', 'error')
        return redirect(url_for('admin_users'))

@app.route('/admin/jobs')
@admin_required
def admin_jobs():
    """Manage all jobs"""
    try:
        # Get filter parameters
        status = request.args.get('status', '')
        search = request.args.get('search', '')
        
        # Build query
        query = {}
        if status == 'active':
            query['is_active'] = True
        elif status == 'inactive':
            query['is_active'] = False
        
        if search:
            query['$or'] = [
                {'title': {'$regex': search, '$options': 'i'}},
                {'company': {'$regex': search, '$options': 'i'}},
                {'location': {'$regex': search, '$options': 'i'}}
            ]
        
        # Get jobs
        jobs = list(jobs_collection.find(query).sort('posted_date', -1))
        
        job_list = []
        for job in jobs:
            job_id = str(job['_id'])
            
            # Get recruiter info
            recruiter = None
            if 'recruiter_id' in job:
                recruiter = users_collection.find_one({'_id': ObjectId(job['recruiter_id'])})
            
            # Get application stats
            applications_count = applications_collection.count_documents({'job_id': job_id})
            shortlisted_count = applications_collection.count_documents({'job_id': job_id, 'status': 'shortlisted'})
            hired_count = applications_collection.count_documents({'job_id': job_id, 'status': 'hired'})
            
            job_list.append({
                '_id': job_id,
                'title': job.get('title'),
                'company': job.get('company'),
                'location': job.get('location'),
                'recruiter_name': recruiter.get('name') or recruiter.get('full_name', 'Unknown') if recruiter else 'Unknown',
                'recruiter_email': recruiter.get('email') if recruiter else 'Unknown',
                'posted_date': job.get('posted_date'),
                'posted_date_str': job.get('posted_date').strftime('%Y-%m-%d') if job.get('posted_date') else 'N/A',
                'is_active': job.get('is_active', True),
                'applications_count': applications_count,
                'shortlisted_count': shortlisted_count,
                'hired_count': hired_count,
                'seats_filled': job.get('seats_filled', 0),
                'total_seats': job.get('total_seats', 1)
            })
        
        # Get counts
        total_jobs = len(job_list)
        active_jobs = len([j for j in job_list if j['is_active']])
        filled_jobs = len([j for j in job_list if j['seats_filled'] >= j['total_seats']])
        
        unread_count = get_unread_count(session['user_id'])
        
        return render_template('admin/jobs.html',
                             jobs=job_list,
                             total_jobs=total_jobs,
                             active_jobs=active_jobs,
                             filled_jobs=filled_jobs,
                             selected_status=status,
                             search_query=search,
                             unread_notifications=unread_count,
                             user_name=session.get('user_name'))
    
    except Exception as e:
        print(f"Admin jobs error: {str(e)}")
        flash('Error loading jobs', 'error')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/job/<job_id>/toggle-status', methods=['POST'])
@admin_required
def admin_toggle_job_status(job_id):
    """Activate or deactivate a job"""
    try:
        job = jobs_collection.find_one({'_id': ObjectId(job_id)})
        
        if not job:
            flash('Job not found', 'error')
            return redirect(url_for('admin_jobs'))
        
        # Toggle status
        new_status = not job.get('is_active', True)
        
        jobs_collection.update_one(
            {'_id': ObjectId(job_id)},
            {'$set': {'is_active': new_status}}
        )
        
        status_text = 'activated' if new_status else 'deactivated'
        flash(f'Job {status_text} successfully', 'success')
        
        # Notify recruiter
        if 'recruiter_id' in job:
            try:
                create_notification(
                    job['recruiter_id'],
                    'Job Status Changed',
                    f'Your job posting "{job.get("title")}" has been {status_text} by an administrator.',
                    'info',
                    url_for('recruiter_job_detail', job_id=job_id)
                )
            except:
                pass
        
        return redirect(url_for('admin_jobs'))
    
    except Exception as e:
        print(f"Toggle job status error: {str(e)}")
        flash('Error updating job status', 'error')
        return redirect(url_for('admin_jobs'))

@app.route('/admin/job/<job_id>/delete', methods=['POST'])
@admin_required
def admin_delete_job(job_id):
    """Delete a job and all associated applications"""
    try:
        job = jobs_collection.find_one({'_id': ObjectId(job_id)})
        
        if not job:
            flash('Job not found', 'error')
            return redirect(url_for('admin_jobs'))
        
        # Delete all applications for this job
        apps_deleted = applications_collection.delete_many({'job_id': job_id})
        
        # Delete the job
        jobs_collection.delete_one({'_id': ObjectId(job_id)})
        
        flash(f'Job "{job.get("title")}" and {apps_deleted.deleted_count} applications deleted successfully', 'success')
        return redirect(url_for('admin_jobs'))
    
    except Exception as e:
        print(f"Delete job error: {str(e)}")
        flash('Error deleting job', 'error')
        return redirect(url_for('admin_jobs'))


@app.route('/admin/stats')
@admin_required
def admin_stats():
    """Enhanced statistics with user growth and activity overview"""
    try:
        # Get period from request
        period = request.args.get('period', '30')
        try:
            days = int(period)
        except:
            days = 30
        
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # User growth by date (daily for last 30 days)
        user_growth = []
        for i in range(days, -1, -1):
            date = datetime.utcnow() - timedelta(days=i)
            start_of_day = datetime(date.year, date.month, date.day, 0, 0, 0)
            end_of_day = datetime(date.year, date.month, date.day, 23, 59, 59)
            
            count = users_collection.count_documents({
                'created_at': {'$gte': start_of_day, '$lte': end_of_day}
            })
            
            user_growth.append({
                'date': date.strftime('%Y-%m-%d'),
                'count': count
            })
        
        # Monthly user growth
        monthly_growth = []
        for i in range(6, -1, -1):
            month_date = datetime.utcnow() - timedelta(days=30 * i)
            start_of_month = datetime(month_date.year, month_date.month, 1, 0, 0, 0)
            if month_date.month == 12:
                end_of_month = datetime(month_date.year + 1, 1, 1, 0, 0, 0) - timedelta(days=1)
            else:
                end_of_month = datetime(month_date.year, month_date.month + 1, 1, 0, 0, 0) - timedelta(days=1)
            
            count = users_collection.count_documents({
                'created_at': {'$gte': start_of_month, '$lte': end_of_month}
            })
            
            monthly_growth.append({
                'month': start_of_month.strftime('%B %Y'),
                'count': count
            })
        
        # User statistics
        total_users = users_collection.count_documents({})
        new_users = users_collection.count_documents({'created_at': {'$gte': cutoff_date}})
        
        users_by_role = {
            'jobseeker': users_collection.count_documents({'role': 'jobseeker'}),
            'recruiter': users_collection.count_documents({'role': 'recruiter'}),
            'admin': users_collection.count_documents({'role': 'admin'})
        }
        
        # Active users (logged in last 7 days)
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        active_users = users_collection.count_documents({'last_login': {'$gte': seven_days_ago}})
        
        # Job statistics
        total_jobs = jobs_collection.count_documents({})
        new_jobs = jobs_collection.count_documents({'posted_date': {'$gte': cutoff_date}})
        active_jobs = jobs_collection.count_documents({'is_active': True})
        
        jobs_by_type = {}
        for job in jobs_collection.find():
            job_type = job.get('job_type', 'unknown')
            jobs_by_type[job_type] = jobs_by_type.get(job_type, 0) + 1
        
        # Application statistics
        total_apps = applications_collection.count_documents({})
        new_apps = applications_collection.count_documents({'applied_date': {'$gte': cutoff_date}})
        
        apps_by_status = {
            'pending': applications_collection.count_documents({'status': 'pending'}),
            'shortlisted': applications_collection.count_documents({'status': 'shortlisted'}),
            'hired': applications_collection.count_documents({'status': 'hired'}),
            'rejected': applications_collection.count_documents({'status': 'rejected'})
        }
        
        # Complaint statistics
        pending_complaints = complaints_collection.count_documents({'status': 'pending'})
        total_complaints = complaints_collection.count_documents({})
        
        # Activity overview - recent activities
        recent_activities = []
        
        # Recent user registrations
        recent_users = list(users_collection.find().sort('created_at', -1).limit(5))
        for user in recent_users:
            recent_activities.append({
                'type': 'user_register',
                'user_name': user.get('full_name') or user.get('name', 'Unknown'),
                'user_email': user.get('email'),
                'role': user.get('role'),
                'timestamp': user.get('created_at'),
                'time_str': user.get('created_at').strftime('%Y-%m-%d %H:%M') if user.get('created_at') else 'N/A'
            })
        
        # Recent job postings
        recent_jobs = list(jobs_collection.find().sort('posted_date', -1).limit(5))
        for job in recent_jobs:
            recruiter = users_collection.find_one({'_id': ObjectId(job.get('recruiter_id'))}) if job.get('recruiter_id') else None
            recent_activities.append({
                'type': 'job_post',
                'job_title': job.get('title'),
                'company': job.get('company'),
                'recruiter_name': recruiter.get('full_name') or recruiter.get('name', 'Unknown') if recruiter else 'Unknown',
                'timestamp': job.get('posted_date'),
                'time_str': job.get('posted_date').strftime('%Y-%m-%d %H:%M') if job.get('posted_date') else 'N/A'
            })
        
        # Recent applications
        recent_apps = list(applications_collection.find().sort('applied_date', -1).limit(5))
        for app in recent_apps:
            job_seeker = users_collection.find_one({'_id': ObjectId(app.get('user_id'))}) if app.get('user_id') else None
            recent_activities.append({
                'type': 'application',
                'job_title': app.get('job_title'),
                'company': app.get('company'),
                'job_seeker_name': job_seeker.get('full_name') or job_seeker.get('name', 'Unknown') if job_seeker else 'Unknown',
                'status': app.get('status'),
                'timestamp': app.get('applied_date'),
                'time_str': app.get('applied_date').strftime('%Y-%m-%d %H:%M') if app.get('applied_date') else 'N/A'
            })
        
        # Sort activities by timestamp
        recent_activities.sort(key=lambda x: x.get('timestamp') or datetime.min, reverse=True)
        recent_activities = recent_activities[:20]  # Keep only last 20
        
        unread_count = get_unread_count(session['user_id'])
        
        return render_template('admin/stats.html',
                             period=days,
                             user_growth=user_growth,
                             monthly_growth=monthly_growth,
                             total_users=total_users,
                             new_users=new_users,
                             users_by_role=users_by_role,
                             active_users=active_users,
                             total_jobs=total_jobs,
                             new_jobs=new_jobs,
                             active_jobs=active_jobs,
                             jobs_by_type=jobs_by_type,
                             total_apps=total_apps,
                             new_apps=new_apps,
                             apps_by_status=apps_by_status,
                             pending_complaints=pending_complaints,
                             total_complaints=total_complaints,
                             recent_activities=recent_activities,
                             unread_notifications=unread_count,
                             user_name=session.get('user_name'))
    
    except Exception as e:
        print(f"Admin stats error: {str(e)}")
        import traceback
        traceback.print_exc()
        flash('Error loading statistics', 'error')
        return redirect(url_for('admin_dashboard'))



          
@app.route('/admin/create-admin', methods=['GET', 'POST'])
def create_admin():
    """Create the first admin user (accessible only when no admins exist)"""
    # Check if any admin exists
    admin_exists = users_collection.count_documents({'role': 'admin'}) > 0
    
    # If admin exists and user is not logged in as admin, redirect to login
    if admin_exists and ('user_id' not in session or session.get('user_role') != 'admin'):
        flash('Admin already exists. Please login with admin credentials.', 'error')
        return redirect(url_for('login'))
    
    # If admin exists and user IS logged in as admin, allow access (for creating additional admins)
    # If no admin exists, allow access to create first admin
    
    if request.method == 'POST':
        try:
            full_name = request.form.get('full_name')
            email = request.form.get('email')
            password = request.form.get('password')
            confirm = request.form.get('confirm_password')
            admin_code = request.form.get('admin_code')
            
            # Validation
            if not all([full_name, email, password, confirm, admin_code]):
                flash('All fields are required', 'error')
                return redirect(url_for('create_admin'))
            
            if password != confirm:
                flash('Passwords do not match', 'error')
                return redirect(url_for('create_admin'))
            
            if len(password) < 8:
                flash('Password must be at least 8 characters', 'error')
                return redirect(url_for('create_admin'))
            
            # Verify admin code (you can change this)
            if admin_code != 'ADMIN123':
                flash('Invalid admin code', 'error')
                return redirect(url_for('create_admin'))
            
            # Check if email already exists
            if users_collection.find_one({'email': email}):
                flash('Email already registered', 'error')
                return redirect(url_for('create_admin'))
            
            # Create admin user
            user = {
                'name': full_name,
                'full_name': full_name,
                'email': email,
                'password': generate_password_hash(password),
                'role': 'admin',
                'created_at': datetime.utcnow(),
                'is_active': True
            }
            
            result = users_collection.insert_one(user)
            
            # Auto login the new admin
            session['user_id'] = str(result.inserted_id)
            session['user_email'] = email
            session['user_name'] = full_name
            session['user_role'] = 'admin'
            
            flash('Admin account created successfully!', 'success')
            return redirect(url_for('admin_dashboard'))
            
        except Exception as e:
            print(f"Create admin error: {str(e)}")
            flash(f'Error creating admin account: {str(e)}', 'error')
            return redirect(url_for('create_admin'))
    
    return render_template('admin/create_admin.html')

               
           
# ==================== Recruiter Routes ====================

@app.route('/recruiter/dashboard')
@recruiter_required
def recruiter_dashboard():
    """Recruiter dashboard"""
    try:
        # Get recruiter's jobs
        jobs = list(jobs_collection.find(
            {'recruiter_id': session['user_id']}
        ).sort('posted_date', -1))
        
        jobs_list = []
        for job in jobs:
            job['_id'] = str(job['_id'])
            job['applications'] = applications_collection.count_documents({'job_id': str(job['_id'])})
            job['shortlisted'] = applications_collection.count_documents(
                {'job_id': str(job['_id']), 'status': 'shortlisted'}
            )
            job['hired'] = applications_collection.count_documents(
                {'job_id': str(job['_id']), 'status': 'hired'}
            )
            jobs_list.append(job)
        
        # Calculate total stats across all jobs
        job_ids = [str(job['_id']) for job in jobs]
        total_applications = applications_collection.count_documents({'job_id': {'$in': job_ids}})
        total_shortlisted = applications_collection.count_documents(
            {'job_id': {'$in': job_ids}, 'status': 'shortlisted'}
        )
        total_hired = applications_collection.count_documents(
            {'job_id': {'$in': job_ids}, 'status': 'hired'}
        )
        
        # Get unread notifications
        unread_count = get_unread_count(session['user_id'])
        
        # Get user data
        user = users_collection.find_one({'_id': ObjectId(session['user_id'])})
        
        return render_template('recruiter/dashboard.html',
                             jobs=jobs_list,
                             total_applications=total_applications,
                             total_shortlisted=total_shortlisted,
                             total_hired=total_hired,
                             unread_notifications=unread_count,
                             user=user,
                             user_name=session.get('user_name'))
        
    except Exception as e:
        print(f"Dashboard error: {str(e)}")
        traceback.print_exc()
        flash('Error loading dashboard', 'error')
        return redirect(url_for('index'))
#========================================================================================
@app.route('/candidate/profile/<user_id>')
@login_required
def candidate_profile(user_id):
    """Get candidate profile data for modal"""
    try:
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get user's applications with analysis
        applications = list(applications_collection.find({'user_id': user_id}).sort('applied_date', -1).limit(5))
        
        profile_data = {
            'name': user.get('full_name') or user.get('name', 'Unknown'),
            'email': user.get('email'),
            'phone': user.get('phone', 'Not provided'),
            'location': user.get('location', 'Not provided'),
            'age': user.get('age', 'Not provided'),
            'languages': user.get('languages', 'Not provided'),
            'skills': user.get('skills', 'Not provided'),
            'experience': user.get('experience', 'Not provided'),
            'education': user.get('education', 'Not provided'),
            'linkedin': user.get('linkedin', ''),
            'github': user.get('github', ''),
            'portfolio': user.get('portfolio', ''),
            'profile_picture': user.get('profile_picture'),
            'resume_file': user.get('resume_file'),
            'created_at': user.get('created_at').strftime('%B %d, %Y') if user.get('created_at') else 'N/A',
            'applications': []
        }
        
        for app in applications:
            profile_data['applications'].append({
                'job_title': app.get('job_title'),
                'company': app.get('company'),
                'applied_date': app.get('applied_date').strftime('%B %d, %Y') if app.get('applied_date') else 'N/A',
                'status': app.get('status', 'pending'),
                'score': app.get('analysis', {}).get('overall', 0),
                'technical': app.get('analysis', {}).get('technical', 0),
                'soft_skills': app.get('analysis', {}).get('soft_skills', 0)
            })
        
        return jsonify(profile_data)
        
    except Exception as e:
        print(f"Profile fetch error: {str(e)}")
        return jsonify({'error': str(e)}), 500
#=========================
@app.route('/recruiter/candidates-table/<job_id>')
@recruiter_required
def view_candidates_table(job_id):
    """View candidates in tabular format with selection and print options"""
    try:
        job = jobs_collection.find_one({'_id': ObjectId(job_id)})
        
        if not job or job['recruiter_id'] != session['user_id']:
            flash('Job not found', 'error')
            return redirect(url_for('recruiter_dashboard'))
        
        # Get all applications for this job
        applications = list(applications_collection.find(
            {'job_id': job_id}
        ).sort('analysis.overall', -1))
        
        candidates = []
        for app in applications:
            user = users_collection.find_one({'_id': ObjectId(app['user_id'])})
            if user:
               candidates.append({
    'id': str(app['_id']),
    'user_id': str(user['_id']),
    'name': user.get('full_name', 'Unknown'),
    'age': user.get('age', 'N/A'),  # New field
    'languages': user.get('languages', 'N/A'),  # New field
    'profile_picture': user.get('profile_picture'),  # New field
    'email': user.get('email'),
    'phone': user.get('phone', 'Not provided'),
    'location': user.get('location', 'Not provided'),
    'applied_date': app.get('applied_date'),
    'status': app.get('status', 'pending'),
    'overall_score': app.get('analysis', {}).get('overall', 0),
    'technical_score': app.get('analysis', {}).get('technical', 0),
    'soft_score': app.get('analysis', {}).get('soft_skills', 0),
    'experience_score': app.get('analysis', {}).get('experience', 0),
    'education_score': app.get('analysis', {}).get('education', 0),
    'resume_file': user.get('resume_file'),
    'selected': False
})
        
        job['_id'] = str(job['_id'])
        unread_count = get_unread_count(session['user_id'])
        
        return render_template('recruiter/candidates_table.html',
                             job=job,
                             candidates=candidates,
                             unread_notifications=unread_count,
                             user_name=session.get('user_name'))
        
    except Exception as e:
        print(f"Candidates table error: {str(e)}")
        flash('Error loading candidates', 'error')
        return redirect(url_for('recruiter_dashboard'))









@app.route('/recruiter/profile', methods=['GET', 'POST'])
@recruiter_required
def recruiter_profile():
    """Recruiter profile with company info"""
    try:
        if request.method == 'POST':
            full_name = request.form.get('full_name')
            update_data = {
                'name': full_name,
                'full_name': full_name,
                'company': request.form.get('company'),
                'company_website': request.form.get('company_website'),
                'location': request.form.get('location'),
                'phone': request.form.get('phone'),
                'bio': request.form.get('bio'),
                'updated_at': datetime.utcnow()
            }
            
            # Handle company logo upload
            if 'company_logo' in request.files:
                file = request.files['company_logo']
                if file and file.filename and allowed_file(file.filename):
                    ext = file.filename.rsplit('.', 1)[1].lower()
                    filename = secure_filename(f"company_{session['user_id']}_{datetime.utcnow().timestamp()}.{ext}")
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)
                    update_data['company_logo'] = filename
                    
                    # Update session with profile picture for navbar
                    session['profile_picture'] = filename
            
            # Handle password change
            current_password = request.form.get('current_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')
            
            if current_password and new_password and confirm_password:
                user = users_collection.find_one({'_id': ObjectId(session['user_id'])})
                if check_password_hash(user['password'], current_password):
                    if new_password == confirm_password and len(new_password) >= 8:
                        update_data['password'] = generate_password_hash(new_password)
                        flash('Password updated successfully!', 'success')
                    else:
                        flash('New passwords do not match or are too short', 'error')
                else:
                    flash('Current password is incorrect', 'error')
            
            users_collection.update_one(
                {'_id': ObjectId(session['user_id'])},
                {'$set': update_data}
            )
            
            session['user_name'] = update_data['full_name']
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('recruiter_profile'))
        
        user = users_collection.find_one({'_id': ObjectId(session['user_id'])})
        unread_count = get_unread_count(session['user_id'])
        
        # Store profile picture in session for navbar
        if user and user.get('company_logo'):
            session['profile_picture'] = user['company_logo']
        
        return render_template('recruiter/profile.html',
                             user=user,
                             unread_notifications=unread_count,
                             user_name=session.get('user_name'))
        
    except Exception as e:
        print(f"Profile error: {str(e)}")
        flash('Error loading profile', 'error')
        return redirect(url_for('recruiter_dashboard'))

@app.route('/recruiter/jobs')
@recruiter_required
def recruiter_jobs():
    """View all jobs with stats"""
    try:
        jobs = list(jobs_collection.find(
            {'recruiter_id': session['user_id']}
        ).sort('posted_date', -1))
        
        jobs_with_stats = []
        for job in jobs:
            job_id = str(job['_id'])
            
            # Get application stats
            total_apps = applications_collection.count_documents({'job_id': job_id})
            shortlisted = applications_collection.count_documents({'job_id': job_id, 'status': 'shortlisted'})
            hired = applications_collection.count_documents({'job_id': job_id, 'status': 'hired'})
            pending = applications_collection.count_documents({'job_id': job_id, 'status': 'pending'})
            
            # Get top candidates
            applications = list(applications_collection.find(
                {'job_id': job_id}
            ).sort('analysis.overall', -1).limit(3))
            
            candidates = []
            for app in applications:
                user = users_collection.find_one({'_id': ObjectId(app['user_id'])})
                if user:
                    candidates.append({
                        'name': user.get('full_name', 'Unknown'),
                        'overall_score': app.get('analysis', {}).get('overall', 0),
                        'status': app.get('status', 'pending')
                    })
            
            jobs_with_stats.append({
                '_id': job_id,
                'title': job.get('title'),
                'company': job.get('company'),
                'location': job.get('location'),
                'job_type': job.get('job_type', 'full-time'),  # Make sure this is included
                'experience_level': job.get('experience_level', 'entry'),  # Make sure this is included
                'posted_date': job.get('posted_date'),
                'total_applications': total_apps,
                'shortlisted': shortlisted,
                'hired': hired,
                'pending': pending,
                'seats_filled': job.get('seats_filled', 0),
                'total_seats': job.get('total_seats', 1),
                'is_active': job.get('is_active', True),
                'top_candidates': candidates
            })
        
        unread_count = get_unread_count(session['user_id'])
        
        return render_template('recruiter/jobs.html',
                             jobs=jobs_with_stats,
                             unread_notifications=unread_count,
                             user_name=session.get('user_name'))
        
    except Exception as e:
        print(f"Jobs error: {str(e)}")
        flash('Error loading jobs', 'error')
        return redirect(url_for('recruiter_dashboard'))





@app.route('/recruiter/post-job', methods=['GET', 'POST'])
@recruiter_required
def post_job():
    """Post a new job"""
    if request.method == 'POST':
        try:
            # Handle age requirements (optional)
            min_age = request.form.get('min_age')
            max_age = request.form.get('max_age')
            required_languages = request.form.get('required_languages')
            
            job = {
                'recruiter_id': session['user_id'],
                'recruiter_name': session['user_name'],
                'title': request.form.get('title'),
                'company': request.form.get('company'),
                'location': request.form.get('location'),
                'description': request.form.get('description'),
                'requirements': request.form.get('requirements'),
                'salary_min': int(request.form.get('salary_min', 0)) if request.form.get('salary_min') else None,
                'salary_max': int(request.form.get('salary_max', 0)) if request.form.get('salary_max') else None,
                'job_type': request.form.get('job_type'),
                'experience_level': request.form.get('experience_level'),
                'min_age': int(min_age) if min_age else None,  # New field
                'max_age': int(max_age) if max_age else None,  # New field
                'required_languages': required_languages if required_languages else None,  # New field
                'posted_date': datetime.utcnow(),
                'is_active': True,
                'seats_filled': 0,
                'total_seats': int(request.form.get('total_seats', 1))
            }
            
            jobs_collection.insert_one(job)
            flash('Job posted successfully!', 'success')
            return redirect(url_for('recruiter_jobs'))
            
        except Exception as e:
            print(f"Post job error: {str(e)}")
            flash('Error posting job. Please check all fields.', 'error')
    
    unread_count = get_unread_count(session['user_id'])
    return render_template('recruiter/post_job.html', unread_notifications=unread_count)
@app.route('/recruiter/job/<job_id>')
@recruiter_required
def recruiter_job_detail(job_id):
    """View job details with all candidates"""
    try:
        job = jobs_collection.find_one({'_id': ObjectId(job_id)})
        
        if not job or job['recruiter_id'] != session['user_id']:
            flash('Job not found', 'error')
            return redirect(url_for('recruiter_jobs'))
        
        # Get all applications
        applications = list(applications_collection.find(
            {'job_id': job_id}
        ).sort('analysis.overall', -1))
        
        candidates = []
        for app in applications:
            user = users_collection.find_one({'_id': ObjectId(app['user_id'])})
            if user:
                candidates.append({
                    'id': str(app['_id']),
                    'name': user.get('full_name', 'Unknown'),
                    'email': user.get('email'),
                    'applied_date': app.get('applied_date'),
                    'status': app.get('status', 'pending'),
                    'analysis': app.get('analysis', {}),
                    'resume_file': user.get('resume_file')
                })
        
        # Calculate stats
        stats = {
            'total': len(candidates),
            'shortlisted': len([c for c in candidates if c['status'] == 'shortlisted']),
            'hired': len([c for c in candidates if c['status'] == 'hired']),
            'rejected': len([c for c in candidates if c['status'] == 'rejected']),
            'pending': len([c for c in candidates if c['status'] == 'pending'])
        }
        
        job['_id'] = str(job['_id'])
        unread_count = get_unread_count(session['user_id'])
        
        return render_template('recruiter/job_detail.html',
                             job=job,
                             candidates=candidates,
                             stats=stats,
                             unread_notifications=unread_count,
                             user_name=session.get('user_name'))
        
    except Exception as e:
        print(f"Job detail error: {str(e)}")
        flash('Error loading job details', 'error')
        return redirect(url_for('recruiter_jobs'))

@app.route('/recruiter/candidates/<job_id>')
@recruiter_required
def view_candidates(job_id):
    """View all candidates for a job"""
    try:
        job = jobs_collection.find_one({'_id': ObjectId(job_id)})
        
        if not job or job['recruiter_id'] != session['user_id']:
            flash('Job not found', 'error')
            return redirect(url_for('recruiter_jobs'))
        
        applications = list(applications_collection.find(
            {'job_id': job_id}
        ).sort('analysis.overall', -1))
        
        candidates = []
        for app in applications:
            user = users_collection.find_one({'_id': ObjectId(app['user_id'])})
            if user:
                candidates.append({
                    'id': str(app['_id']),
                    'user_id': str(user['_id']),
                    'name': user.get('full_name', 'Unknown'),
                    'email': user.get('email'),
                    'phone': user.get('phone', 'Not provided'),
                    'location': user.get('location', 'Not provided'),
                    'age': user.get('age', 'Not provided'),  # Add age
                    'languages': user.get('languages', 'Not provided'),  # Add languages
                    'profile_picture': user.get('profile_picture'),  # THIS IS THE KEY LINE
                    'applied_date': app.get('applied_date'),
                    'status': app.get('status', 'pending'),
                    'analysis': app.get('analysis', {}),
                    'resume_file': user.get('resume_file')
                })
        
        job['_id'] = str(job['_id'])
        unread_count = get_unread_count(session['user_id'])
        
        return render_template('recruiter/candidates.html',
                             job=job,
                             candidates=candidates,
                             unread_notifications=unread_count,
                             user_name=session.get('user_name'))
        
    except Exception as e:
        print(f"Candidates error: {str(e)}")
        flash('Error loading candidates', 'error')
        return redirect(url_for('recruiter_jobs'))
@app.route('/recruiter/update-status/<application_id>', methods=['POST'])
@recruiter_required
def update_application_status(application_id):
    """Update application status"""
    try:
        status = request.form.get('status')
        job_id = request.form.get('job_id')
        
        app = applications_collection.find_one({'_id': ObjectId(application_id)})
        if not app:
            flash('Application not found', 'error')
            return redirect(request.referrer)
        
        applications_collection.update_one(
            {'_id': ObjectId(application_id)},
            {'$set': {'status': status, 'updated_at': datetime.utcnow()}}
        )
        
        # Get job details for notification
        job = jobs_collection.find_one({'_id': ObjectId(job_id)})
        
        if status == 'hired':
            jobs_collection.update_one(
                {'_id': ObjectId(job_id)},
                {'$inc': {'seats_filled': 1}}
            )
            
            # Notify candidate
            create_notification(
                app['user_id'],
                '🎉 Congratulations! You are hired!',
                f'You have been selected for the {job.get("title")} position at {job.get("company")}. The recruiter will contact you soon.',
                'success',
                url_for('jobseeker_application_detail', application_id=application_id)
            )
            
        elif status == 'shortlisted':
            create_notification(
                app['user_id'],
                '✅ Application Shortlisted',
                f'Your application for {job.get("title")} at {job.get("company")} has been shortlisted!',
                'info',
                url_for('jobseeker_application_detail', application_id=application_id)
            )
            
        elif status == 'rejected':
            create_notification(
                app['user_id'],
                'Application Update',
                f'Thank you for applying to {job.get("title")} at {job.get("company")}. After careful review, we have decided to move forward with other candidates.',
                'info',
                url_for('jobseeker_application_detail', application_id=application_id)
            )
        
        flash('Application status updated', 'success')
        
    except Exception as e:
        print(f"Update status error: {str(e)}")
        flash('Error updating status', 'error')
    
    return redirect(request.referrer)

@app.route('/recruiter/delete-job/<job_id>', methods=['POST'])
@recruiter_required
def delete_job(job_id):
    """Delete/close a job"""
    try:
        job = jobs_collection.find_one({'_id': ObjectId(job_id)})
        if not job or job['recruiter_id'] != session['user_id']:
            flash('Job not found', 'error')
            return redirect(url_for('recruiter_jobs'))
        
        jobs_collection.update_one(
            {'_id': ObjectId(job_id)},
            {'$set': {'is_active': False}}
        )
        
        # Notify applicants
        applications = applications_collection.find({'job_id': job_id})
        for app in applications:
            create_notification(
                app['user_id'],
                'Job Position Closed',
                f'The position {job.get("title")} at {job.get("company")} has been filled/closed.',
                'warning'
            )
        
        flash('Job closed successfully', 'success')
        
    except Exception as e:
        print(f"Delete job error: {str(e)}")
        flash('Error closing job', 'error')
    
    return redirect(url_for('recruiter_jobs'))

# ==================== Recruiter Search Routes ====================

@app.route('/recruiter/search-candidates')
@recruiter_required
def search_candidates():
    """Search and filter candidates for recruiters"""
    try:
        # Get search parameters
        query = request.args.get('q', '').strip()
        job_id = request.args.get('job_id', '')
        status = request.args.get('status', '')
        min_score = request.args.get('min_score', 0, type=int)
        sort_by = request.args.get('sort_by', 'score')
        
        # Base query for applications
        search_filter = {}
        
        # Filter by specific job
        if job_id and job_id != 'all':
            # Verify job belongs to this recruiter
            job = jobs_collection.find_one({'_id': ObjectId(job_id), 'recruiter_id': session['user_id']})
            if job:
                search_filter['job_id'] = job_id
            else:
                job_id = 'all'
        
        # Filter by status
        if status:
            search_filter['status'] = status
        
        # Get applications
        applications = list(applications_collection.find(search_filter))
        
        # Get user details for each application
        candidates = []
        for app in applications:
            user = users_collection.find_one({'_id': ObjectId(app['user_id'])})
            if user:
                # Calculate match score if available
                score = app.get('analysis', {}).get('overall', 0)
                
                # Filter by minimum score
                if score >= min_score:
                    # Check if candidate matches search query
                    if query:
                        query_lower = query.lower()
                        name_match = query_lower in user.get('full_name', '').lower()
                        email_match = query_lower in user.get('email', '').lower()
                        skills_match = False
                        
                        # Check skills
                        user_skills = user.get('skills', '').lower()
                        if query_lower in user_skills:
                            skills_match = True
                        
                        if not (name_match or email_match or skills_match):
                            continue
                    
                    candidates.append({
                        'id': str(app['_id']),
                        'user_id': str(user['_id']),
                        'name': user.get('full_name', 'Unknown'),
                        'email': user.get('email'),
                        'phone': user.get('phone', ''),
                        'location': user.get('location', ''),
                        'skills': user.get('skills', ''),
                        'job_title': app.get('job_title'),
                        'company': app.get('company'),
                        'applied_date': app.get('applied_date'),
                        'status': app.get('status', 'pending'),
                        'score': score,
                        'technical_score': app.get('analysis', {}).get('technical', 0),
                        'soft_score': app.get('analysis', {}).get('soft_skills', 0),
                        'experience_score': app.get('analysis', {}).get('experience', 0),
                        'education_score': app.get('analysis', {}).get('education', 0),
                        'resume_file': user.get('resume_file')
                    })
        
        # Sort candidates
        if sort_by == 'score':
            candidates.sort(key=lambda x: x['score'], reverse=True)
        elif sort_by == 'date':
            candidates.sort(key=lambda x: x['applied_date'] if x['applied_date'] else datetime.min, reverse=True)
        elif sort_by == 'name':
            candidates.sort(key=lambda x: x['name'])
        
        # Get recruiter's jobs for filter dropdown
        recruiter_jobs = list(jobs_collection.find(
            {'recruiter_id': session['user_id']}
        ).sort('posted_date', -1))
        
        jobs_list = []
        for job in recruiter_jobs:
            jobs_list.append({
                '_id': str(job['_id']),
                'title': job.get('title'),
                'company': job.get('company')
            })
        
        unread_count = get_unread_count(session['user_id'])
        
        return render_template('recruiter/search_candidates.html',
                             candidates=candidates,
                             jobs=jobs_list,
                             selected_job=job_id,
                             selected_status=status,
                             selected_min_score=min_score,
                             selected_sort=sort_by,
                             search_query=query,
                             unread_notifications=unread_count,
                             user_name=session.get('user_name'))
        
    except Exception as e:
        print(f"Search candidates error: {str(e)}")
        flash('Error searching candidates', 'error')
        return redirect(url_for('recruiter_dashboard'))

# ==================== Job Seeker Routes ====================

@app.route('/jobseeker/dashboard')
@jobseeker_required
def jobseeker_dashboard():
    """Job seeker dashboard"""
    try:
        user = users_collection.find_one({'_id': ObjectId(session['user_id'])})
        has_resume = user and 'resume_text' in user and user['resume_text']
        
        # Get active jobs
        jobs = list(jobs_collection.find({
            'is_active': True,
            '$expr': {'$lt': ['$seats_filled', '$total_seats']}
        }).sort('posted_date', -1))
        
        # Get user's applications
        applications = list(applications_collection.find(
            {'user_id': session['user_id']}
        ))
        applied_ids = [a['job_id'] for a in applications]
        
        # Get saved jobs
        saved_ids = user.get('saved_jobs', []) if user else []
        
        jobs_list = []
        for job in jobs:
            job_id = str(job['_id'])
            jobs_list.append({
                '_id': job_id,
                'title': job.get('title'),
                'company': job.get('company'),
                'location': job.get('location'),
                'description': job.get('description'),
                'requirements': job.get('requirements'),
                'salary_min': job.get('salary_min'),
                'salary_max': job.get('salary_max'),
                'job_type': job.get('job_type'),
                'posted_date': job.get('posted_date'),
                'has_applied': job_id in applied_ids,
                'is_saved': job_id in saved_ids
            })
        
        unread_count = get_unread_count(session['user_id'])
        
        return render_template('jobseeker/dashboard.html',
                             jobs=jobs_list,
                             has_resume=has_resume,
                             unread_notifications=unread_count,
                             user=user,
                             user_name=session.get('user_name'))
        
    except Exception as e:
        print(f"Dashboard error: {str(e)}")
        traceback.print_exc()
        flash('Error loading dashboard', 'error')
        return redirect(url_for('index'))

@app.route('/jobseeker/profile', methods=['GET', 'POST'])
@jobseeker_required
def jobseeker_profile():
    """Job seeker profile"""
    try:
        if request.method == 'POST':
            full_name = request.form.get('full_name')
            update_data = {
                'name': full_name,
                'full_name': full_name,
                'phone': request.form.get('phone'),
                'location': request.form.get('location'),
                'age': request.form.get('age'),  # New field
                'languages': request.form.get('languages'),  # New field
                'skills': request.form.get('skills'),
                'experience': request.form.get('experience'),
                'education': request.form.get('education'),
                'linkedin': request.form.get('linkedin'),
                'github': request.form.get('github'),
                'portfolio': request.form.get('portfolio'),
                'updated_at': datetime.utcnow()
            }
            
            # Handle profile picture upload
            if 'profile_picture' in request.files:
                file = request.files['profile_picture']
                if file and file.filename and allowed_file(file.filename):
                    # Generate unique filename
                    ext = file.filename.rsplit('.', 1)[1].lower()
                    filename = secure_filename(f"profile_{session['user_id']}_{datetime.utcnow().timestamp()}.{ext}")
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)
                    update_data['profile_picture'] = filename
                    
                    # Update session with profile picture for navbar
                    session['profile_picture'] = filename
            
            # Handle password change
            current_password = request.form.get('current_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')
            
            if current_password and new_password and confirm_password:
                user = users_collection.find_one({'_id': ObjectId(session['user_id'])})
                if check_password_hash(user['password'], current_password):
                    if new_password == confirm_password and len(new_password) >= 8:
                        update_data['password'] = generate_password_hash(new_password)
                        flash('Password updated successfully!', 'success')
                    else:
                        flash('New passwords do not match or are too short', 'error')
                else:
                    flash('Current password is incorrect', 'error')
            
            users_collection.update_one(
                {'_id': ObjectId(session['user_id'])},
                {'$set': update_data}
            )
            
            session['user_name'] = update_data['full_name']
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('jobseeker_profile'))
        
        user = users_collection.find_one({'_id': ObjectId(session['user_id'])})
        
        # Get application stats
        total_apps = applications_collection.count_documents({'user_id': session['user_id']})
        shortlisted = applications_collection.count_documents({'user_id': session['user_id'], 'status': 'shortlisted'})
        hired = applications_collection.count_documents({'user_id': session['user_id'], 'status': 'hired'})
        
        unread_count = get_unread_count(session['user_id'])
        
        # Store profile picture in session for navbar
        if user and user.get('profile_picture'):
            session['profile_picture'] = user['profile_picture']
        
        return render_template('jobseeker/profile.html',
                             user=user,
                             total_applications=total_apps,
                             shortlisted=shortlisted,
                             hired=hired,
                             unread_notifications=unread_count,
                             user_name=session.get('user_name'))
        
    except Exception as e:
        print(f"Profile error: {str(e)}")
        flash('Error loading profile', 'error')
        return redirect(url_for('jobseeker_dashboard'))
@app.route('/jobseeker/upload-resume', methods=['POST'])
@jobseeker_required
def upload_resume():
    """Upload resume"""
    try:
        if 'resume' not in request.files:
            flash('No file selected', 'error')
            return redirect(url_for('jobseeker_dashboard'))
        
        file = request.files['resume']
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(url_for('jobseeker_dashboard'))
        
        if file and allowed_file(file.filename):
            filename = secure_filename(f"resume_{session['user_id']}_{datetime.utcnow().timestamp()}.{file.filename.rsplit('.', 1)[1]}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            text = extract_text_from_file(filepath)
            
            users_collection.update_one(
                {'_id': ObjectId(session['user_id'])},
                {'$set': {
                    'resume_file': filename,
                    'resume_text': text,
                    'resume_uploaded_at': datetime.utcnow()
                }}
            )
            
            flash('Resume uploaded and analyzed!', 'success')
        else:
            flash('Invalid file type. Allowed: PDF, DOCX, TXT', 'error')
            
    except Exception as e:
        print(f"Upload error: {str(e)}")
        flash('Error uploading file', 'error')
    
    return redirect(url_for('jobseeker_dashboard'))

@app.route('/jobseeker/job/<job_id>')
@jobseeker_required
def jobseeker_job_detail(job_id):
    """View job details with AI analysis and recruiter info"""
    try:
        job = jobs_collection.find_one({'_id': ObjectId(job_id)})
        
        if not job or not job.get('is_active'):
            flash('Job not found', 'error')
            return redirect(url_for('jobseeker_dashboard'))
        
        # Check if user has applied
        has_applied = applications_collection.find_one({
            'user_id': session['user_id'],
            'job_id': job_id
        }) is not None
        
        # Check if job is saved
        user = users_collection.find_one({'_id': ObjectId(session['user_id'])})
        saved_ids = user.get('saved_jobs', []) if user else []
        is_saved = job_id in saved_ids
        
        # Get recruiter/company details
        recruiter = None
        total_jobs_posted = 0
        active_jobs_count = 0
        total_hires = 0
        
        if 'recruiter_id' in job:
            recruiter = users_collection.find_one({'_id': ObjectId(job['recruiter_id'])})
            if recruiter:
                # Get company stats
                total_jobs_posted = jobs_collection.count_documents({'recruiter_id': job['recruiter_id']})
                active_jobs_count = jobs_collection.count_documents({'recruiter_id': job['recruiter_id'], 'is_active': True})
                
                # Get total hires from applications where status is 'hired' for jobs by this recruiter
                recruiter_jobs = list(jobs_collection.find({'recruiter_id': job['recruiter_id']}, {'_id': 1}))
                recruiter_job_ids = [str(j['_id']) for j in recruiter_jobs]
                total_hires = applications_collection.count_documents({'job_id': {'$in': recruiter_job_ids}, 'status': 'hired'})
        
        # Get AI analysis if user has resume and hasn't applied
        analysis = None
        if user and 'resume_text' in user and user['resume_text'] and not has_applied:
            analysis = analyze_resume_advanced(user['resume_text'], job)
        
        job['_id'] = str(job['_id'])
        unread_count = get_unread_count(session['user_id'])
        
        return render_template('jobseeker/job_detail.html',
                             job=job,
                             has_applied=has_applied,
                             is_saved=is_saved,
                             analysis=analysis,
                             recruiter=recruiter,
                             total_jobs_posted=total_jobs_posted,
                             active_jobs_count=active_jobs_count,
                             total_hires=total_hires,
                             unread_notifications=unread_count,
                             user=user,
                             user_name=session.get('user_name'))
        
    except Exception as e:
        print(f"Job detail error: {str(e)}")
        flash('Error loading job details', 'error')
        return redirect(url_for('jobseeker_dashboard'))


   
@app.route('/jobseeker/apply/<job_id>', methods=['POST'])
@jobseeker_required
def apply_job(job_id):
    """Apply for a job"""
    try:
        print("\n" + "="*60)
        print("📝 JOB APPLICATION ATTEMPT")
        print("="*60)
        
        user_id = session['user_id']
        print(f"User ID: {user_id}")
        print(f"Job ID: {job_id}")
        
        # Get user
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            flash('User not found. Please login again.', 'error')
            return redirect(url_for('login'))
        
        # Check resume
        if 'resume_text' not in user or not user['resume_text']:
            flash('Please upload your resume first', 'error')
            return redirect(url_for('jobseeker_dashboard'))
        
        # Get job
        try:
            job = jobs_collection.find_one({'_id': ObjectId(job_id)})
        except:
            flash('Invalid job ID', 'error')
            return redirect(url_for('jobseeker_dashboard'))
        
        if not job:
            flash('Job not found', 'error')
            return redirect(url_for('jobseeker_dashboard'))
        
        # Check if job is available
        if job.get('seats_filled', 0) >= job.get('total_seats', 1):
            flash('This position has been filled', 'error')
            return redirect(url_for('jobseeker_dashboard'))
        
        # Check if THIS SPECIFIC USER already applied
        existing = applications_collection.find_one({
            'user_id': user_id,
            'job_id': job_id
        })
        
        if existing:
            print(f"❌ User {user_id} already applied to job {job_id}")
            flash('You have already applied for this job', 'warning')
            return redirect(url_for('jobseeker_dashboard'))
        
        print(f"✅ No existing application found for this user")
        
        # Analyze resume
        try:
            analysis = analyze_resume_advanced(user['resume_text'], job)
        except Exception as e:
            print(f"Analysis error: {str(e)}")
            analysis = {
                'overall': 65,
                'technical': 70,
                'soft_skills': 65,
                'experience': 60,
                'education': 70,
                'matched_technical': [],
                'missing_technical': [],
                'soft_skills_found': [],
                'experience_years': 3,
                'feedback': 'Application submitted successfully.'
            }
        
        # Create application
        application = {
            'user_id': user_id,
            'user_email': session['user_email'],
            'user_name': session['user_name'],
            'job_id': job_id,
            'job_title': job.get('title'),
            'company': job.get('company'),
            'applied_date': datetime.utcnow(),
            'analysis': analysis,
            'status': 'pending'
        }
        
        # Insert with error handling for duplicate key
        try:
            result = applications_collection.insert_one(application)
            print(f"✅ Application saved with ID: {result.inserted_id}")
            
            # Notify recruiter
            try:
                create_notification(
                    job['recruiter_id'],
                    '📨 New Application Received',
                    f'{session["user_name"]} applied for {job.get("title")}',
                    'info',
                    url_for('recruiter_job_detail', job_id=job_id)
                )
            except:
                pass
            
            flash('Application submitted successfully!', 'success')
            
        except Exception as e:
            if 'duplicate key' in str(e):
                print(f"❌ Duplicate key error - user already applied")
                flash('You have already applied for this job', 'warning')
            else:
                print(f"❌ Insert error: {str(e)}")
                flash(f'Error submitting application: {str(e)}', 'error')
        
        print("="*60)
        return redirect(url_for('jobseeker_dashboard'))
        
    except Exception as e:
        print(f"❌ Application error: {str(e)}")
        import traceback
        traceback.print_exc()
        flash(f'Error submitting application: {str(e)}', 'error')
        return redirect(url_for('jobseeker_dashboard'))



        
      
            
         
           

        
        
      
@app.route('/jobseeker/save-job/<job_id>', methods=['POST'])
@jobseeker_required
def save_job(job_id):
    """Save a job"""
    try:
        users_collection.update_one(
            {'_id': ObjectId(session['user_id'])},
            {'$addToSet': {'saved_jobs': job_id}}
        )
        return jsonify({'success': True, 'message': 'Job saved'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/jobseeker/unsave-job/<job_id>', methods=['POST'])
@jobseeker_required
def unsave_job(job_id):
    """Remove saved job"""
    try:
        users_collection.update_one(
            {'_id': ObjectId(session['user_id'])},
            {'$pull': {'saved_jobs': job_id}}
        )
        return jsonify({'success': True, 'message': 'Job removed'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/jobseeker/applications')
@jobseeker_required
def my_applications():
    """View all applications"""
    try:
        apps = list(applications_collection.find(
            {'user_id': session['user_id']}
        ).sort('applied_date', -1))
        
        applications_list = []
        for app in apps:
            app['_id'] = str(app['_id'])
            applications_list.append(app)
        
        unread_count = get_unread_count(session['user_id'])
        
        return render_template('jobseeker/applications.html',
                             applications=applications_list,
                             unread_notifications=unread_count,
                             user_name=session.get('user_name'))
        
    except Exception as e:
        print(f"Applications error: {str(e)}")
        flash('Error loading applications', 'error')
        return redirect(url_for('jobseeker_dashboard'))

@app.route('/jobseeker/application/<application_id>')
@jobseeker_required
def jobseeker_application_detail(application_id):
    """View application details"""
    try:
        app = applications_collection.find_one({'_id': ObjectId(application_id)})
        
        if not app or app['user_id'] != session['user_id']:
            flash('Application not found', 'error')
            return redirect(url_for('my_applications'))
        
        # Get job details
        job = jobs_collection.find_one({'_id': ObjectId(app['job_id'])})
        
        # Get recruiter details
        recruiter = None
        if job and 'recruiter_id' in job:
            recruiter = users_collection.find_one({'_id': ObjectId(job['recruiter_id'])})
        
        app['_id'] = str(app['_id'])
        if job:
            job['_id'] = str(job['_id'])
        
        unread_count = get_unread_count(session['user_id'])
        
        return render_template('jobseeker/application_detail.html',
                             application=app,
                             job=job,
                             recruiter=recruiter,
                             unread_notifications=unread_count,
                             user_name=session.get('user_name'))
        
    except Exception as e:
        print(f"Application detail error: {str(e)}")
        flash('Error loading application details', 'error')
        return redirect(url_for('my_applications'))

@app.route('/jobseeker/saved-jobs')
@jobseeker_required
def saved_jobs():
    """View saved jobs"""
    try:
        user = users_collection.find_one({'_id': ObjectId(session['user_id'])})
        saved_ids = user.get('saved_jobs', []) if user else []
        
        jobs = []
        for job_id in saved_ids:
            job = jobs_collection.find_one({'_id': ObjectId(job_id), 'is_active': True})
            if job:
                job['_id'] = str(job['_id'])
                jobs.append(job)
        
        # Check which jobs user has applied to
        applications = list(applications_collection.find({'user_id': session['user_id']}))
        applied_ids = [a['job_id'] for a in applications]
        
        for job in jobs:
            job['has_applied'] = job['_id'] in applied_ids
        
        unread_count = get_unread_count(session['user_id'])
        
        return render_template('jobseeker/saved_jobs.html',
                             jobs=jobs,
                             unread_notifications=unread_count,
                             user_name=session.get('user_name'))
        
    except Exception as e:
        print(f"Saved jobs error: {str(e)}")
        flash('Error loading saved jobs', 'error')
        return redirect(url_for('jobseeker_dashboard'))



# ==================== Job Seeker Search Routes ====================

@app.route('/jobseeker/search-jobs')
@jobseeker_required
def search_jobs():
    """Search and filter jobs for jobseekers"""
    try:
        # Get search parameters
        query = request.args.get('q', '').strip()
        location = request.args.get('location', '').strip()
        job_type = request.args.get('job_type', '')
        experience = request.args.get('experience', '')
        sort_by = request.args.get('sort_by', 'recent')
        
        # Build search query
        search_filter = {'is_active': True, '$expr': {'$lt': ['$seats_filled', '$total_seats']}}
        
        if query:
            search_filter['$or'] = [
                {'title': {'$regex': query, '$options': 'i'}},
                {'company': {'$regex': query, '$options': 'i'}},
                {'description': {'$regex': query, '$options': 'i'}},
                {'requirements': {'$regex': query, '$options': 'i'}}
            ]
        
        if location:
            search_filter['location'] = {'$regex': location, '$options': 'i'}
        
        if job_type:
            search_filter['job_type'] = job_type
        
        if experience:
            search_filter['experience_level'] = experience
        
        # Determine sort order
        sort_order = [('posted_date', -1)]  # default: newest first
        if sort_by == 'oldest':
            sort_order = [('posted_date', 1)]
        elif sort_by == 'company_asc':
            sort_order = [('company', 1)]
        elif sort_by == 'company_desc':
            sort_order = [('company', -1)]
        
        # Execute search
        jobs = list(jobs_collection.find(search_filter).sort(sort_order))
        
        # Get user's applications and saved jobs
        user = users_collection.find_one({'_id': ObjectId(session['user_id'])})
        applications = list(applications_collection.find({'user_id': session['user_id']}))
        applied_ids = [a['job_id'] for a in applications]
        saved_ids = user.get('saved_jobs', []) if user else []
        
        # Format jobs for display
        jobs_list = []
        for job in jobs:
            job_id = str(job['_id'])
            jobs_list.append({
                '_id': job_id,
                'title': job.get('title'),
                'company': job.get('company'),
                'location': job.get('location'),
                'description': job.get('description'),
                'requirements': job.get('requirements'),
                'salary_min': job.get('salary_min'),
                'salary_max': job.get('salary_max'),
                'job_type': job.get('job_type'),
                'experience_level': job.get('experience_level'),
                'posted_date': job.get('posted_date'),
                'has_applied': job_id in applied_ids,
                'is_saved': job_id in saved_ids
            })
        
        # Get filter options for dropdowns
        filter_options = {
            'job_types': jobs_collection.distinct('job_type', {'is_active': True}),
            'experience_levels': jobs_collection.distinct('experience_level', {'is_active': True}),
            'locations': jobs_collection.distinct('location', {'is_active': True})
        }
        
        unread_count = get_unread_count(session['user_id'])
        
        return render_template('jobseeker/search_results.html',
                             jobs=jobs_list,
                             filters=filter_options,
                             search_query=query,
                             selected_location=location,
                             selected_job_type=job_type,
                             selected_experience=experience,
                             selected_sort=sort_by,
                             unread_notifications=unread_count,
                             user_name=session.get('user_name'))
        
    except Exception as e:
        print(f"Search error: {str(e)}")
        flash('Error performing search', 'error')
        return redirect(url_for('jobseeker_dashboard'))






# ==================== File Download ====================

@app.route('/download/<filename>')
@login_required
def download_file(filename):
    """Download file"""
    try:
        return send_file(
            os.path.join(app.config['UPLOAD_FOLDER'], filename),
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        print(f"Download error: {str(e)}")
        flash('Error downloading file', 'error')
        return redirect(request.referrer or url_for('index'))

# ==================== Error Handlers ====================

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500


#=====================user delete==========================

@app.route('/delete-account', methods=['POST'])
@login_required
def delete_account():
    """Delete user account and all related data - Works for both Job Seekers and Recruiters"""
    try:
        user_id = session['user_id']
        user_role = session.get('user_role')
        
        # Get user details for confirmation message
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        user_email = user.get('email') if user else 'Unknown'
        
        # Delete user's applications (if job seeker)
        if user_role == 'jobseeker':
            apps_deleted = applications_collection.delete_many({'user_id': user_id})
            print(f"Deleted {apps_deleted.deleted_count} applications for user {user_email}")
        
        # Delete user's notifications
        notifs_deleted = notifications_collection.delete_many({'user_id': user_id})
        print(f"Deleted {notifs_deleted.deleted_count} notifications for user {user_email}")
        
        # Delete user's password resets
        password_resets_collection.delete_many({'email': user_email})
        
        # If recruiter, also handle their jobs
        if user_role == 'recruiter':
            # Get all jobs posted by this recruiter
            recruiter_jobs = jobs_collection.find({'recruiter_id': user_id})
            job_ids = [str(job['_id']) for job in recruiter_jobs]
            
            # Delete applications for these jobs
            if job_ids:
                apps_deleted = applications_collection.delete_many({'job_id': {'$in': job_ids}})
                print(f"Deleted {apps_deleted.deleted_count} applications for recruiter's jobs")
            
            # Delete the jobs
            jobs_deleted = jobs_collection.delete_many({'recruiter_id': user_id})
            print(f"Deleted {jobs_deleted.deleted_count} jobs posted by recruiter")
        
        # Finally, delete the user
        users_collection.delete_one({'_id': ObjectId(user_id)})
        
        # Clear session
        session.clear()
        
        flash("Your account has been permanently deleted. We're sorry to see you go!", 'info')
        return redirect(url_for('index'))
        
    except Exception as e:
        print(f"Delete account error: {str(e)}")
        flash(f'Error deleting account: {str(e)}', 'error')
        return redirect(request.referrer or url_for('index'))


@app.route('/image/<filename>')
def get_image(filename):
    """Serve profile images"""
    try:
        return send_file(
            os.path.join(app.config['UPLOAD_FOLDER'], filename),
            mimetype='image/jpeg'
        )
    except:
        # Return default avatar if image not found
        return redirect(url_for('static', filename='default-avatar.png'))

#=======================Fixes================


@app.route('/debug/fix-indexes')
def fix_indexes():
    """Fix the indexes to allow multiple users per job"""
    try:
        results = []
        
        # List all indexes before
        results.append("<h3>Before:</h3>")
        indexes = list(applications_collection.list_indexes())
        for idx in indexes:
            results.append(f"<p>{idx['name']}: {idx['key']}</p>")
        
        # Drop all custom indexes (keep _id)
        for idx in indexes:
            if idx['name'] != '_id_':
                applications_collection.drop_index(idx['name'])
                results.append(f"<p>Dropped index: {idx['name']}</p>")
        
        # Create the correct compound unique index
        applications_collection.create_index(
            [('user_id', 1), ('job_id', 1)], 
            unique=True,
            name='user_job_unique'
        )
        results.append("<p>✅ Created correct index: user_job_unique on (user_id, job_id)</p>")
        
        # List indexes after
        results.append("<h3>After:</h3>")
        indexes = list(applications_collection.list_indexes())
        for idx in indexes:
            results.append(f"<p>{idx['name']}: {idx['key']}</p>")
        
        return "<br>".join(results)
        
    except Exception as e:
        return f"Error: {str(e)}"

@app.route('/debug/nuclear-reset')
def nuclear_reset():
    """COMPLETE RESET - DELETE ALL APPLICATIONS"""
    try:
        # Delete all applications
        apps_deleted = applications_collection.delete_many({})
        
        # Drop and recreate index
        try:
            applications_collection.drop_index('job_id_1_jobseeker_id_1')
        except:
            pass
        
        try:
            applications_collection.drop_index('user_id_1_job_id_1')
        except:
            pass
        
        # Create correct index
        applications_collection.create_index([('user_id', 1), ('job_id', 1)], unique=True)
        
        return f"""
        <html>
        <body style="background: #1a1e24; color: #e4e6eb; font-family: Arial; padding: 40px;">
            <h2 style="color: #6d5dfc;">💥 Nuclear Reset Complete</h2>
            <p>Deleted {apps_deleted.deleted_count} applications</p>
            <p>Recreated indexes correctly</p>
            <p>You can now start fresh!</p>
            <br>
            <a href="/" style="color: #6d5dfc;">Go to Homepage</a>
        </body>
        </html>
        """
    except Exception as e:
        return f"Error: {str(e)}"
# ============= STATIC PAGES =============

@app.route('/about')
def about():
    """About Us page"""
    return render_template('about.html')

@app.route('/faq')
def faq():
    """FAQ page"""
    return render_template('faq.html')



@app.route('/privacy-policy')
def privacy_policy():
    """Privacy Policy page"""
    return render_template('privacy_policy.html')

@app.route('/terms-of-service')
def terms_of_service():
    """Terms of Service page"""
    return render_template('terms_of_service.html')



@app.errorhandler(500)
def internal_error(error):
    """Handle 500 - Server Error"""
    return render_template('500.html'), 500

@app.errorhandler(403)
def forbidden_error(error):
    """Handle 403 - Access Denied"""
    return render_template('403.html'), 403

@app.errorhandler(405)
def method_not_allowed(error):
    """Handle 405 - Method Not Allowed"""
    flash('Method not allowed for this request.', 'error')
    return redirect(url_for('index'))


@app.route('/favicon.ico')
def favicon():
    from flask import send_from_directory
    return send_from_directory('static', 'favicon.ico')





# ==================== Social Login ====================



@app.route('/login/facebook')
def login_facebook():
    """Redirect to Facebook OAuth"""
    flash('Facebook login is being implemented. Please use email/password for now.', 'info')
    return redirect(url_for('login'))

# ==================== Enhanced Forgot Password ====================

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        try:
            email = request.form.get('email')
            
            if not email:
                flash('Email is required', 'error')
                return redirect(url_for('forgot_password'))
            
            user = users_collection.find_one({'email': email})
            
            if user:
                token = secrets.token_urlsafe(32)
                
                password_resets_collection.update_one(
                    {'email': email},
                    {'$set': {
                        'token': token,
                        'created_at': datetime.utcnow(),
                        'expires_at': datetime.utcnow() + timedelta(hours=1)
                    }},
                    upsert=True
                )
                
                # IMPORTANT: Use url_for to generate the correct URL
                reset_url = url_for('reset_password', token=token, _external=True)
                
                # Send email with proper HTML
                msg = Message(
                    subject='Password Reset Request - AI Resume Screener',
                    recipients=[email],
                    html=f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <meta charset="UTF-8">
                        <title>Password Reset</title>
                    </head>
                    <body style="font-family: Arial, sans-serif;">
                        <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 10px;">
                            <h2 style="color: #6d5dfc;">Reset Your Password</h2>
                            <p>Hello <strong>{user.get('full_name') or user.get('name', 'User')}</strong>,</p>
                            <p>We received a request to reset your password for your AI Resume Screener account.</p>
                            <p style="text-align: center; margin: 30px 0;">
                                <a href="{reset_url}" style="display: inline-block; padding: 12px 24px; background: #6d5dfc; color: white; text-decoration: none; border-radius: 5px;">
                                    Reset Password
                                </a>
                            </p>
                            <p>Or copy and paste this link into your browser:</p>
                            <p style="background: #f5f5f5; padding: 10px; word-break: break-all;">{reset_url}</p>
                            <p>This link will expire in <strong>1 hour</strong>.</p>
                            <hr>
                            <p style="font-size: 12px; color: #666;">If you didn't request this, please ignore this email.</p>
                            <p style="font-size: 12px; color: #666;">AI Resume Screener</p>
                        </div>
                    </body>
                    </html>
                    """
                )
                mail.send(msg)
                flash('Password reset link sent to your email!', 'success')
            else:
                flash('If your email is registered, you will receive a reset link', 'success')
            
            return redirect(url_for('login'))
            
        except Exception as e:
            print(f"Forgot password error: {str(e)}")
            flash('Error processing request', 'error')
            return redirect(url_for('forgot_password'))
    
    return render_template('forgot_password.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Reset password with token"""
    
    # First, validate the token exists and is not expired
    reset_record = password_resets_collection.find_one({
        'token': token,
        'expires_at': {'$gt': datetime.utcnow()}
    })
    
    if not reset_record:
        flash('Invalid or expired reset link. Please request a new one.', 'error')
        return redirect(url_for('forgot_password'))
    
    # GET request - show the reset password form
    if request.method == 'GET':
        return render_template('reset_password.html', token=token)
    
    # POST request - process the password reset
    if request.method == 'POST':
        try:
            password = request.form.get('password')
            confirm_password = request.form.get('confirm_password')
            
            # Validation
            if not password or not confirm_password:
                flash('Both password fields are required', 'error')
                return render_template('reset_password.html', token=token)
            
            if password != confirm_password:
                flash('Passwords do not match', 'error')
                return render_template('reset_password.html', token=token)
            
            if len(password) < 8:
                flash('Password must be at least 8 characters long', 'error')
                return render_template('reset_password.html', token=token)
            
            # Update user password
            user = users_collection.find_one({'email': reset_record['email']})
            
            if not user:
                flash('User not found. Please register first.', 'error')
                return redirect(url_for('register'))
            
            # Hash and update password
            hashed_password = generate_password_hash(password)
            users_collection.update_one(
                {'email': reset_record['email']},
                {'$set': {'password': hashed_password}}
            )
            
            # Delete the used token
            password_resets_collection.delete_one({'token': token})
            
            flash('Password reset successful! Please login with your new password.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            print(f"Reset password error: {str(e)}")
            flash('An error occurred. Please try again.', 'error')
            return render_template('reset_password.html', token=token)

@app.route('/my-complaints')
@login_required
def my_complaints():
    """View complaints submitted by the current user"""
    try:
        complaints = list(complaints_collection.find(
            {'reporter_id': session['user_id']}
        ).sort('created_at', -1))
        
        for complaint in complaints:
            complaint['_id'] = str(complaint['_id'])
            # Get reported user details
            reported_user = users_collection.find_one({'_id': ObjectId(complaint['reported_user_id'])})
            if reported_user:
                complaint['reported_user_name'] = reported_user.get('full_name') or reported_user.get('name', 'Unknown')
                complaint['reported_user_email'] = reported_user.get('email')
                complaint['reported_user_role'] = reported_user.get('role', 'unknown')
        
        unread_count = get_unread_count(session['user_id'])
        
        return render_template('my_complaints.html',
                             complaints=complaints,
                             unread_notifications=unread_count,
                             user_name=session.get('user_name'))
        
    except Exception as e:
        print(f"My complaints error: {str(e)}")
        flash('Error loading complaints', 'error')
        return redirect(url_for('index'))
#============================google=====================



# Google OAuth Configuration - Simplified
google = oauth.register(
    name='google',
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    access_token_url='https://oauth2.googleapis.com/token',
    authorize_url='https://accounts.google.com/o/oauth2/auth',
    api_base_url='https://www.googleapis.com/oauth2/v3/',
    client_kwargs={
        'scope': 'email profile',
        'prompt': 'select_account'
    }
)
@app.route('/login/google')
def google_login():
    """Redirect to Google OAuth"""
    try:
        redirect_uri = 'http://localhost:5000/google/callback'
        return google.authorize_redirect(redirect_uri)
    except Exception as e:
        print(f"Google login error: {str(e)}")
        flash('Unable to login with Google. Please try again.', 'error')
        return redirect(url_for('login'))

@app.route('/google/callback')
def google_callback():
    """Handle Google OAuth callback"""
    try:
        print("="*50)
        print("GOOGLE CALLBACK RECEIVED")
        
        # Get token
        token = google.authorize_access_token()
        print(f"Token received")
        
        # Get user info using the token
        resp = google.get('userinfo', token=token)
        userinfo = resp.json()
        print(f"User info: {userinfo}")
        
        email = userinfo.get('email')
        name = userinfo.get('name', email.split('@')[0])
        
        if not email:
            flash('Could not retrieve email from Google', 'error')
            return redirect(url_for('login'))
        
        # Check if user exists
        user = users_collection.find_one({'email': email})
        
        if user:
            # Existing user - login
            session['user_id'] = str(user['_id'])
            session['user_email'] = user['email']
            session['user_name'] = user.get('full_name') or user.get('name', name)
            session['user_role'] = user.get('role', 'jobseeker')
            
            flash(f'Welcome back, {session["user_name"]}!', 'success')
            
            if user.get('role') == 'recruiter':
                return redirect(url_for('recruiter_dashboard'))
            elif user.get('role') == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('jobseeker_dashboard'))
        else:
            # New user - create account
            new_user = {
                'name': name,
                'full_name': name,
                'email': email,
                'password': generate_password_hash(secrets.token_urlsafe(16)),
                'role': 'jobseeker',
                'created_at': datetime.utcnow(),
                'is_active': True,
                'auth_provider': 'google'
            }
            
            result = users_collection.insert_one(new_user)
            
            session['user_id'] = str(result.inserted_id)
            session['user_email'] = email
            session['user_name'] = name
            session['user_role'] = 'jobseeker'
            
            flash('Account created successfully with Google!', 'success')
            return redirect(url_for('jobseeker_dashboard'))
            
    except Exception as e:
        print(f"Google OAuth error: {str(e)}")
        import traceback
        traceback.print_exc()
        flash('Google login failed. Please try again.', 'error')
        return redirect(url_for('login'))
@app.route('/debug/urls')
def debug_urls():
    return f"""
    <h2>Debug Info</h2>
    <p>Google Callback URL should be: <strong>http://localhost:5000/google/callback</strong></p>
    <p>Reset URL example: <strong>http://localhost:5000/reset-password/test-token</strong></p>
    <p>Make sure you're accessing the app at: <a href="http://localhost:5000">http://localhost:5000</a></p>
    """
@app.route('/debug/check-token/<email>')
def check_token(email):
    """Check if reset token exists for this email"""
    token_record = password_resets_collection.find_one({'email': email})
    if token_record:
        return f"""
        <h3>Token Found for {email}</h3>
        <p>Token: {token_record.get('token')}</p>
        <p>Expires: {token_record.get('expires_at')}</p>
        <p>Reset Link: <a href="http://localhost:5000/reset-password/{token_record.get('token')}">
        http://localhost:5000/reset-password/{token_record.get('token')}</a></p>
        """
    else:
        return f"No reset token found for {email}. Please request a new one."
@app.route('/debug/google-config')
def google_config():
    """Check Google OAuth configuration"""
    return f"""
    <h3>Google OAuth Configuration</h3>
    <p>Client ID: {os.getenv('GOOGLE_CLIENT_ID', 'NOT SET')[:20]}...</p>
    <p>Redirect URI: {os.getenv('GOOGLE_REDIRECT_URI', 'NOT SET')}</p>
    <p>Authlib Status: {'✅ Configured' if google else '❌ Not Configured'}</p>
    <p><a href="/login/google">Try Google Login</a></p>
    """
def get_reset_url(token):
    """Get the correct reset URL based on where the app is running"""
    # Try to get from environment first
    app_url = os.getenv('APP_URL')
    if app_url:
        return f"{app_url}/reset-password/{token}"
    
    # Fallback to localhost
    return f"http://localhost:5000/reset-password/{token}"
@app.route('/direct-reset/<email>')
def direct_reset(email):
    """Direct reset link - bypass email completely"""
    user = users_collection.find_one({'email': email})
    
    if not user:
        return f"User {email} not found"
    
    token = secrets.token_urlsafe(32)
    
    password_resets_collection.update_one(
        {'email': email},
        {'$set': {
            'token': token,
            'created_at': datetime.utcnow(),
            'expires_at': datetime.utcnow() + timedelta(hours=1)
        }},
        upsert=True
    )
    
    reset_url = url_for('reset_password', token=token, _external=True)
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Password Reset Link</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                max-width: 600px;
                margin: 50px auto;
                padding: 20px;
                background: #f5f5f5;
            }}
            .card {{
                background: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }}
            .link {{
                background: #f0f0f0;
                padding: 15px;
                border-radius: 5px;
                word-break: break-all;
                margin: 20px 0;
            }}
            .button {{
                display: inline-block;
                padding: 12px 24px;
                background: #6d5dfc;
                color: white;
                text-decoration: none;
                border-radius: 5px;
                margin: 10px 0;
            }}
        </style>
    </head>
    <body>
        <div class="card">
            <h2>Password Reset for {email}</h2>
            <p>Click the button below to reset your password:</p>
            
            <div style="text-align: center;">
                <a href="{reset_url}" class="button">Reset Password</a>
            </div>
            
            <div class="link">
                <strong>Or copy this link:</strong><br>
                {reset_url}
            </div>
            
            <p>This link expires in 1 hour.</p>
            <hr>
            <p><a href="/login">Back to Login</a></p>
        </div>
    </body>
    </html>
    """
# ==================== Simple Password Reset Routes (No CSRF) ====================

@app.route('/reset-password-simple/<email>')
def reset_password_simple(email):
    """Simple reset without CSRF - Direct password reset"""
    user = users_collection.find_one({'email': email})
    
    if not user:
        return f"""
        <!DOCTYPE html>
        <html>
        <head><title>User Not Found</title></head>
        <body style="font-family: Arial; text-align: center; padding: 50px;">
            <h2>❌ User Not Found</h2>
            <p>Email <strong>{email}</strong> is not registered.</p>
            <p><a href="/register">Register Now</a> | <a href="/login">Back to Login</a></p>
        </body>
        </html>
        """
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Reset Password</title>
        <style>
            body {{ font-family: Arial; background: #f5f5f5; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }}
            .card {{ background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); width: 400px; }}
            input {{ width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ddd; border-radius: 5px; box-sizing: border-box; }}
            button {{ background: #6d5dfc; color: white; padding: 12px; border: none; border-radius: 5px; cursor: pointer; width: 100%; }}
            button:hover {{ background: #5a4bda; }}
            h2 {{ color: #333; margin-bottom: 20px; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h2>Reset Password</h2>
            <p>Resetting password for: <strong>{email}</strong></p>
            <form method="POST" action="/update-password-simple/{email}">
                <input type="password" name="password" placeholder="New Password (min 8 chars)" required>
                <input type="password" name="confirm" placeholder="Confirm Password" required>
                <button type="submit">Update Password</button>
            </form>
            <p style="text-align: center; margin-top: 20px;"><a href="/login">Back to Login</a></p>
        </div>
    </body>
    </html>
    """

@app.route('/update-password-simple/<email>', methods=['POST'])
def update_password_simple(email):
    """Update password directly without CSRF"""
    password = request.form.get('password')
    confirm = request.form.get('confirm')
    
    if not password or not confirm:
        return "<h2>Error</h2><p>Both fields required.</p><a href='javascript:history.back()'>Go Back</a>"
    
    if password != confirm:
        return "<h2>Error</h2><p>Passwords do not match.</p><a href='javascript:history.back()'>Go Back</a>"
    
    if len(password) < 8:
        return "<h2>Error</h2><p>Password must be at least 8 characters.</p><a href='javascript:history.back()'>Go Back</a>"
    
    # Update password
    users_collection.update_one(
        {'email': email},
        {'$set': {'password': generate_password_hash(password)}}
    )
    
    # Delete any reset tokens
    password_resets_collection.delete_many({'email': email})
    
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Password Updated</title></head>
    <body style="font-family: Arial; text-align: center; padding: 50px;">
        <h2 style="color: green;">✅ Password Updated Successfully!</h2>
        <p>You can now login with your new password.</p>
        <a href="/login" style="background: #6d5dfc; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Login Now</a>
    </body>
    </html>
    """

# Add CSRF exemptions AFTER defining the routes
csrf.exempt(reset_password_simple)
csrf.exempt(update_password_simple)

@app.route('/debug/google-debug')
def google_debug():
    """Debug Google OAuth"""
    return f"""
    <h3>Google OAuth Configuration</h3>
    <p>Client ID: {os.getenv('GOOGLE_CLIENT_ID', 'NOT SET')[:30]}...</p>
    <p>Redirect URI: {os.getenv('GOOGLE_REDIRECT_URI', 'NOT SET')}</p>
    <p>Authlib Status: {'✅ Configured' if google else '❌ Not Configured'}</p>
    <p><a href="/login/google">Try Google Login</a></p>
    <p><a href="/debug/check-user/your-email">Check if user exists</a></p>
    """
@app.route('/debug/notifications')
@login_required
def debug_notifications():
    """Debug notifications"""
    try:
        count = notifications_collection.count_documents({'user_id': session['user_id']})
        unread = get_unread_count(session['user_id'])
        return f"""
        <h3>Notifications Debug</h3>
        <p>Total notifications: {count}</p>
        <p>Unread: {unread}</p>
        <p><a href="/notifications">View Notifications</a></p>
        """
    except Exception as e:
        return f"Error: {str(e)}"
@app.route('/contact')
def contact():
    return render_template('contact.html')
@app.route('/debug/scopes')
def debug_scopes():
    """Check if scopes are configured"""
    return """
    <h2>Required Scopes for Google Login:</h2>
    <ul>
        <li>✅ openid - Required for user identification</li>
        <li>✅ email - Required to get user's email</li>
        <li>✅ profile - Required to get user's name</li>
    </ul>
    <p>These should be configured in your Google Cloud Console under OAuth consent screen > Scopes.</p>
    <p><a href="/login/google">Test Google Login</a></p>
    """
# ==================== Run ====================

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🌑 AI RESUME SCREENER - PROFESSIONAL EDITION")
    print("="*60)
    print(f"✅ MongoDB Connected")
    print(f"✅ AI Matcher Initialized")
    print(f"📧 Email: {'✅ Configured' if app.config['MAIL_USERNAME'] else '⚠️ Not Configured'}")
    print(f"🌐 Server: http://localhost:5000")
    print("="*60)
    print("\nFeatures:")
    print("  • Advanced AI Matching")
    print("  • Real Email Notifications")
    print("  • Secure Authentication")
    print("  • Password Change")
    print("  • Profile Management")
    print("  • Resume Upload")
    print("  • Job Applications")
    print("  • Saved Jobs")
    print("="*60)
    
  
    app.run(debug=True, host='0.0.0.0', port=5000)
if __name__ == '__main__':
    # For local development
    app.run(debug=True, host='127.0.0.1', port=5000)