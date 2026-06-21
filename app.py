import os
import secrets
import logging
from datetime import datetime, timedelta
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
from matcher import analyze_resume

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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

# Production settings
if os.getenv('FLASK_ENV') == 'production':
    app.debug = False
    app.config['DEBUG'] = False

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize extensions
csrf = CSRFProtect(app)
mail = Mail(app)

# ==================== MongoDB Connection ====================

try:
    mongo_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
    client = MongoClient(mongo_uri, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    logger.info("MongoDB Connected Successfully!")
    
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
    logger.error(f"MongoDB Connection Error: {str(e)}")
    exit(1)

# ==================== Helper Functions ====================

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
            logger.error(f"Error in admin_required: {str(e)}")
            flash('Error verifying admin privileges', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def send_email(recipient, subject, template, **kwargs):
    try:
        msg = Message(subject=subject, recipients=[recipient])
        msg.html = render_template(f'emails/{template}', **kwargs)
        mail.send(msg)
        return True
    except Exception as e:
        logger.error(f"Email error: {str(e)}")
        return False

def extract_text_from_file(filepath):
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
        logger.error(f"Extraction error: {str(e)}")
        return ""

def create_notification(user_id, title, message, type='info', link=None):
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
        logger.error(f"Notification error: {str(e)}")

def get_unread_count(user_id):
    try:
        return notifications_collection.count_documents({
            'user_id': user_id,
            'is_read': False
        })
    except:
        return 0

# ==================== Auth Routes ====================

@app.route('/')
def index():
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
            
            if not all([full_name, email, password, confirm]):
                flash('All fields required', 'error')
                return redirect(url_for('register'))
            
            if password != confirm:
                flash('Passwords do not match', 'error')
                return redirect(url_for('register'))
            
            if len(password) < 8:
                flash('Password must be at least 8 characters', 'error')
                return redirect(url_for('register'))
            
            if users_collection.find_one({'email': email}):
                flash('Email already registered', 'error')
                return redirect(url_for('register'))
            
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
            
            session['user_id'] = str(result.inserted_id)
            session['user_email'] = email
            session['user_name'] = full_name
            session['user_role'] = role
            
            flash('Registration successful!', 'success')
            
            if role == 'recruiter':
                return redirect(url_for('recruiter_dashboard'))
            elif role == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('jobseeker_dashboard'))
                
        except Exception as e:
            logger.error(f"Registration error: {str(e)}")
            flash('Registration failed', 'error')
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            email = request.form.get('email')
            password = request.form.get('password')
            
            user = users_collection.find_one({'email': email})
            
            if user and check_password_hash(user['password'], password):
                if not user.get('is_active', True):
                    flash('Your account has been deactivated. Please contact admin.', 'error')
                    return redirect(url_for('login'))
                
                session['user_id'] = str(user['_id'])
                session['user_email'] = user['email']
                session['user_name'] = user.get('name') or user.get('full_name', 'User')
                session['user_role'] = user['role']
                
                if user.get('profile_picture'):
                    session['profile_picture'] = user['profile_picture']
                elif user.get('company_logo'):
                    session['profile_picture'] = user['company_logo']
                
                flash(f'Welcome back, {session["user_name"]}!', 'success')
                
                if user['role'] == 'recruiter':
                    return redirect(url_for('recruiter_dashboard'))
                elif user['role'] == 'admin':
                    return redirect(url_for('admin_dashboard'))
                else:
                    return redirect(url_for('jobseeker_dashboard'))
            else:
                flash('Invalid email or password', 'error')
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
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
    try:
        notifs = list(notifications_collection.find(
            {'user_id': session['user_id']}
        ).sort('created_at', -1))
        
        for n in notifs:
            n['_id'] = str(n['_id'])
            if 'created_at' in n:
                n['created_at_str'] = n['created_at'].strftime('%B %d, %Y at %H:%M')
        
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
        logger.error(f"Notifications error: {str(e)}")
        flash('Error loading notifications', 'error')
        return redirect(url_for('index'))

@app.route('/notifications/count')
@login_required
def notification_count():
    try:
        count = get_unread_count(session['user_id'])
        return jsonify({'count': count})
    except:
        return jsonify({'count': 0})

# ==================== Admin Routes (NO COMPLAINTS) ====================

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    try:
        total_users = users_collection.count_documents({})
        total_jobseekers = users_collection.count_documents({'role': 'jobseeker'})
        total_recruiters = users_collection.count_documents({'role': 'recruiter'})
        total_jobs = jobs_collection.count_documents({})
        active_jobs = jobs_collection.count_documents({'is_active': True})
        total_applications = applications_collection.count_documents({})
        
        recent_users = list(users_collection.find().sort('created_at', -1).limit(10))
        for user in recent_users:
            user['_id'] = str(user['_id'])
            if 'created_at' in user:
                user['created_at_str'] = user['created_at'].strftime('%Y-%m-%d %H:%M')
        
        recent_jobs = list(jobs_collection.find().sort('posted_date', -1).limit(10))
        for job in recent_jobs:
            job['_id'] = str(job['_id'])
            if 'posted_date' in job:
                job['posted_date_str'] = job['posted_date'].strftime('%Y-%m-%d')
        
        recent_apps = list(applications_collection.find().sort('applied_date', -1).limit(10))
        for app in recent_apps:
            app['_id'] = str(app['_id'])
            if 'applied_date' in app:
                app['applied_date_str'] = app['applied_date'].strftime('%Y-%m-%d')
        
        return render_template('admin/dashboard.html',
                             total_users=total_users,
                             total_jobseekers=total_jobseekers,
                             total_recruiters=total_recruiters,
                             total_jobs=total_jobs,
                             active_jobs=active_jobs,
                             total_applications=total_applications,
                             recent_users=recent_users,
                             recent_jobs=recent_jobs,
                             recent_apps=recent_apps,
                             user_name=session.get('user_name'))
        
    except Exception as e:
        logger.error(f"Admin dashboard error: {str(e)}")
        flash('Error loading admin dashboard', 'error')
        return redirect(url_for('index'))

@app.route('/admin/users')
@admin_required
def admin_users():
    try:
        role = request.args.get('role', '')
        search = request.args.get('search', '')
        
        query = {}
        if role:
            query['role'] = role
        if search:
            query['$or'] = [
                {'email': {'$regex': search, '$options': 'i'}},
                {'name': {'$regex': search, '$options': 'i'}},
                {'full_name': {'$regex': search, '$options': 'i'}}
            ]
        
        users = list(users_collection.find(query).sort('created_at', -1))
        
        user_list = []
        for user in users:
            user_id = str(user['_id'])
            
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
                'applications_count': applications_count,
                'shortlisted_count': shortlisted_count,
                'hired_count': hired_count,
                'jobs_count': jobs_count
            })
        
        total_users = len(user_list)
        total_jobseekers = len([u for u in user_list if u['role'] == 'jobseeker'])
        total_recruiters = len([u for u in user_list if u['role'] == 'recruiter'])
        total_admins = len([u for u in user_list if u['role'] == 'admin'])
        
        return render_template('admin/users.html',
                             users=user_list,
                             total_users=total_users,
                             total_jobseekers=total_jobseekers,
                             total_recruiters=total_recruiters,
                             total_admins=total_admins,
                             selected_role=role,
                             search_query=search,
                             user_name=session.get('user_name'))
    
    except Exception as e:
        logger.error(f"Admin users error: {str(e)}")
        flash('Error loading users', 'error')
        return redirect(url_for('admin_dashboard'))
        
@app.route('/admin/user/<user_id>/toggle-status', methods=['POST'])
@admin_required
def admin_toggle_user_status(user_id):
    try:
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        
        if not user:
            flash('User not found', 'error')
            return redirect(url_for('admin_users'))
        
        new_status = not user.get('is_active', True)
        
        users_collection.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': {'is_active': new_status}}
        )
        
        status_text = 'activated' if new_status else 'deactivated'
        flash(f'User {status_text} successfully', 'success')
        
        return redirect(url_for('admin_users'))
    
    except Exception as e:
        logger.error(f"Toggle user status error: {str(e)}")
        flash('Error updating user status', 'error')
        return redirect(url_for('admin_users'))

@app.route('/admin/user/<user_id>/delete', methods=['POST'])
@admin_required
def admin_delete_user(user_id):
    try:
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        
        if not user:
            flash('User not found', 'error')
            return redirect(url_for('admin_users'))
        
        user_email = user.get('email')
        user_role = user.get('role')
        
        if user_role == 'jobseeker':
            apps_deleted = applications_collection.delete_many({'user_id': user_id})
            logger.info(f"Deleted {apps_deleted.deleted_count} applications for user {user_email}")
        
        if user_role == 'recruiter':
            recruiter_jobs = jobs_collection.find({'recruiter_id': user_id})
            job_ids = [str(job['_id']) for job in recruiter_jobs]
            
            if job_ids:
                apps_deleted = applications_collection.delete_many({'job_id': {'$in': job_ids}})
                logger.info(f"Deleted {apps_deleted.deleted_count} applications for recruiter's jobs")
            
            jobs_deleted = jobs_collection.delete_many({'recruiter_id': user_id})
            logger.info(f"Deleted {jobs_deleted.deleted_count} jobs posted by recruiter")
        
        users_collection.delete_one({'_id': ObjectId(user_id)})
        
        flash(f'User {user_email} and all associated data deleted successfully', 'success')
        return redirect(url_for('admin_users'))
    
    except Exception as e:
        logger.error(f"Delete user error: {str(e)}")
        flash('Error deleting user', 'error')
        return redirect(url_for('admin_users'))

@app.route('/admin/jobs')
@admin_required
def admin_jobs():
    try:
        status = request.args.get('status', '')
        search = request.args.get('search', '')
        
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
        
        jobs = list(jobs_collection.find(query).sort('posted_date', -1))
        
        job_list = []
        for job in jobs:
            job_id = str(job['_id'])
            
            recruiter = None
            if 'recruiter_id' in job:
                recruiter = users_collection.find_one({'_id': ObjectId(job['recruiter_id'])})
            
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
        
        total_jobs = len(job_list)
        active_jobs = len([j for j in job_list if j['is_active']])
        filled_jobs = len([j for j in job_list if j['seats_filled'] >= j['total_seats']])
        
        return render_template('admin/jobs.html',
                             jobs=job_list,
                             total_jobs=total_jobs,
                             active_jobs=active_jobs,
                             filled_jobs=filled_jobs,
                             selected_status=status,
                             search_query=search,
                             user_name=session.get('user_name'))
    
    except Exception as e:
        logger.error(f"Admin jobs error: {str(e)}")
        flash('Error loading jobs', 'error')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/user/<user_id>')
@admin_required
def admin_user_detail(user_id):
    try:
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        
        if not user:
            flash('User not found', 'error')
            return redirect(url_for('admin_users'))
        
        user['_id'] = str(user['_id'])
        
        # Get user stats
        if user.get('role') == 'jobseeker':
            applications = list(applications_collection.find({'user_id': user_id}).sort('applied_date', -1))
            for app in applications:
                app['_id'] = str(app['_id'])
                if 'applied_date' in app:
                    app['applied_date_str'] = app['applied_date'].strftime('%Y-%m-%d')
            
            applications_count = len(applications)
            shortlisted_count = len([a for a in applications if a.get('status') == 'shortlisted'])
            hired_count = len([a for a in applications if a.get('status') == 'hired'])
            saved_jobs_list = []
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
                
                job_apps = list(applications_collection.find({'job_id': job['_id']}))
                job['applications_count'] = len(job_apps)
                job['shortlisted_count'] = len([a for a in job_apps if a.get('status') == 'shortlisted'])
                job['hired_count'] = len([a for a in job_apps if a.get('status') == 'hired'])
                job['pending_count'] = len([a for a in job_apps if a.get('status') == 'pending'])
                
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
                             user_name=session.get('user_name'))
        
    except Exception as e:
        logger.error(f"Admin user detail error: {str(e)}")
        flash('Error loading user details', 'error')
        return redirect(url_for('admin_users'))
        
@app.route('/admin/job/<job_id>/toggle-status', methods=['POST'])
@admin_required
def admin_toggle_job_status(job_id):
    try:
        job = jobs_collection.find_one({'_id': ObjectId(job_id)})
        
        if not job:
            flash('Job not found', 'error')
            return redirect(url_for('admin_jobs'))
        
        new_status = not job.get('is_active', True)
        
        jobs_collection.update_one(
            {'_id': ObjectId(job_id)},
            {'$set': {'is_active': new_status}}
        )
        
        status_text = 'activated' if new_status else 'deactivated'
        flash(f'Job {status_text} successfully', 'success')
        
        return redirect(url_for('admin_jobs'))
    
    except Exception as e:
        logger.error(f"Toggle job status error: {str(e)}")
        flash('Error updating job status', 'error')
        return redirect(url_for('admin_jobs'))

@app.route('/admin/job/<job_id>/delete', methods=['POST'])
@admin_required
def admin_delete_job(job_id):
    try:
        job = jobs_collection.find_one({'_id': ObjectId(job_id)})
        
        if not job:
            flash('Job not found', 'error')
            return redirect(url_for('admin_jobs'))
        
        apps_deleted = applications_collection.delete_many({'job_id': job_id})
        jobs_collection.delete_one({'_id': ObjectId(job_id)})
        
        flash(f'Job "{job.get("title")}" and {apps_deleted.deleted_count} applications deleted successfully', 'success')
        return redirect(url_for('admin_jobs'))
    
    except Exception as e:
        logger.error(f"Delete job error: {str(e)}")
        flash('Error deleting job', 'error')
        return redirect(url_for('admin_jobs'))

@app.route('/admin/stats')
@admin_required
def admin_stats():
    try:
        period = request.args.get('period', '30')
        try:
            days = int(period)
        except:
            days = 30
        
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
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
        
        total_users = users_collection.count_documents({})
        new_users = users_collection.count_documents({'created_at': {'$gte': cutoff_date}})
        
        users_by_role = {
            'jobseeker': users_collection.count_documents({'role': 'jobseeker'}),
            'recruiter': users_collection.count_documents({'role': 'recruiter'}),
            'admin': users_collection.count_documents({'role': 'admin'})
        }
        
        total_jobs = jobs_collection.count_documents({})
        new_jobs = jobs_collection.count_documents({'posted_date': {'$gte': cutoff_date}})
        active_jobs = jobs_collection.count_documents({'is_active': True})
        
        jobs_by_type = {}
        for job in jobs_collection.find():
            job_type = job.get('job_type', 'unknown')
            jobs_by_type[job_type] = jobs_by_type.get(job_type, 0) + 1
        
        total_apps = applications_collection.count_documents({})
        new_apps = applications_collection.count_documents({'applied_date': {'$gte': cutoff_date}})
        
        apps_by_status = {
            'pending': applications_collection.count_documents({'status': 'pending'}),
            'shortlisted': applications_collection.count_documents({'status': 'shortlisted'}),
            'hired': applications_collection.count_documents({'status': 'hired'}),
            'rejected': applications_collection.count_documents({'status': 'rejected'})
        }
        
        recent_activities = []
        
        recent_users = list(users_collection.find().sort('created_at', -1).limit(5))
        for user in recent_users:
            recent_activities.append({
                'type': 'user_register',
                'user_name': user.get('full_name') or user.get('name', 'Unknown'),
                'role': user.get('role'),
                'time_str': user.get('created_at').strftime('%Y-%m-%d %H:%M') if user.get('created_at') else 'N/A'
            })
        
        recent_jobs = list(jobs_collection.find().sort('posted_date', -1).limit(5))
        for job in recent_jobs:
            recent_activities.append({
                'type': 'job_post',
                'job_title': job.get('title'),
                'company': job.get('company'),
                'time_str': job.get('posted_date').strftime('%Y-%m-%d %H:%M') if job.get('posted_date') else 'N/A'
            })
        
        recent_apps = list(applications_collection.find().sort('applied_date', -1).limit(5))
        for app in recent_apps:
            recent_activities.append({
                'type': 'application',
                'job_title': app.get('job_title'),
                'company': app.get('company'),
                'time_str': app.get('applied_date').strftime('%Y-%m-%d %H:%M') if app.get('applied_date') else 'N/A'
            })
        
        recent_activities.sort(key=lambda x: x.get('time_str', ''), reverse=True)
        recent_activities = recent_activities[:20]
        
        return render_template('admin/stats.html',
                             period=days,
                             user_growth=user_growth,
                             monthly_growth=monthly_growth,
                             total_users=total_users,
                             new_users=new_users,
                             users_by_role=users_by_role,
                             total_jobs=total_jobs,
                             new_jobs=new_jobs,
                             active_jobs=active_jobs,
                             jobs_by_type=jobs_by_type,
                             total_apps=total_apps,
                             new_apps=new_apps,
                             apps_by_status=apps_by_status,
                             recent_activities=recent_activities,
                             user_name=session.get('user_name'))
    
    except Exception as e:
        logger.error(f"Admin stats error: {str(e)}")
        flash('Error loading statistics', 'error')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/create-user', methods=['GET', 'POST'])
@admin_required
def admin_create_user():
    try:
        if request.method == 'POST':
            full_name = request.form.get('full_name')
            email = request.form.get('email')
            password = request.form.get('password')
            role = request.form.get('role')
            
            if not all([full_name, email, password, role]):
                flash('All fields are required', 'error')
                return redirect(url_for('admin_create_user'))
            
            if len(password) < 8:
                flash('Password must be at least 8 characters', 'error')
                return redirect(url_for('admin_create_user'))
            
            if users_collection.find_one({'email': email}):
                flash('Email already registered', 'error')
                return redirect(url_for('admin_create_user'))
            
            user = {
                'name': full_name,
                'full_name': full_name,
                'email': email,
                'password': generate_password_hash(password),
                'role': role,
                'created_at': datetime.utcnow(),
                'is_active': True
            }
            
            users_collection.insert_one(user)
            flash(f'User {email} created successfully!', 'success')
            return redirect(url_for('admin_users'))
        
        return render_template('admin/create_user.html', 
                             unread_notifications=0,
                             user_name=session.get('user_name'))
    
    except Exception as e:
        logger.error(f"Create user error: {str(e)}")
        flash('Error creating user', 'error')
        return redirect(url_for('admin_users'))

# ==================== Recruiter Routes ====================

@app.route('/recruiter/dashboard')
@recruiter_required
def recruiter_dashboard():
    try:
        jobs = list(jobs_collection.find({'recruiter_id': session['user_id']}).sort('posted_date', -1))
        
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
        
        job_ids = [str(job['_id']) for job in jobs]
        total_applications = applications_collection.count_documents({'job_id': {'$in': job_ids}})
        total_shortlisted = applications_collection.count_documents(
            {'job_id': {'$in': job_ids}, 'status': 'shortlisted'}
        )
        total_hired = applications_collection.count_documents(
            {'job_id': {'$in': job_ids}, 'status': 'hired'}
        )
        
        unread_count = get_unread_count(session['user_id'])
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
        logger.error(f"Recruiter dashboard error: {str(e)}")
        flash('Error loading dashboard', 'error')
        return redirect(url_for('index'))

@app.route('/recruiter/profile', methods=['GET', 'POST'])
@recruiter_required
def recruiter_profile():
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
            
            if 'company_logo' in request.files:
                file = request.files['company_logo']
                if file and file.filename and allowed_file(file.filename):
                    ext = file.filename.rsplit('.', 1)[1].lower()
                    filename = secure_filename(f"company_{session['user_id']}_{datetime.utcnow().timestamp()}.{ext}")
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)
                    update_data['company_logo'] = filename
                    session['profile_picture'] = filename
            
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
        
        if user and user.get('company_logo'):
            session['profile_picture'] = user['company_logo']
        
        return render_template('recruiter/profile.html',
                             user=user,
                             unread_notifications=unread_count,
                             user_name=session.get('user_name'))
        
    except Exception as e:
        logger.error(f"Recruiter profile error: {str(e)}")
        flash('Error loading profile', 'error')
        return redirect(url_for('recruiter_dashboard'))

@app.route('/recruiter/jobs')
@recruiter_required
def recruiter_jobs():
    try:
        jobs = list(jobs_collection.find({'recruiter_id': session['user_id']}).sort('posted_date', -1))
        
        jobs_with_stats = []
        for job in jobs:
            job_id = str(job['_id'])
            
            total_apps = applications_collection.count_documents({'job_id': job_id})
            shortlisted = applications_collection.count_documents({'job_id': job_id, 'status': 'shortlisted'})
            hired = applications_collection.count_documents({'job_id': job_id, 'status': 'hired'})
            pending = applications_collection.count_documents({'job_id': job_id, 'status': 'pending'})
            
            applications_list = list(applications_collection.find({'job_id': job_id}).sort('analysis.overall', -1).limit(3))
            
            candidates = []
            for app in applications_list:
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
                'job_type': job.get('job_type', 'full-time'),
                'experience_level': job.get('experience_level', 'entry'),
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
        logger.error(f"Recruiter jobs error: {str(e)}")
        flash('Error loading jobs', 'error')
        return redirect(url_for('recruiter_dashboard'))

@app.route('/recruiter/post-job', methods=['GET', 'POST'])
@recruiter_required
def post_job():
    if request.method == 'POST':
        try:
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
                'min_age': int(min_age) if min_age else None,
                'max_age': int(max_age) if max_age else None,
                'required_languages': required_languages if required_languages else None,
                'posted_date': datetime.utcnow(),
                'is_active': True,
                'seats_filled': 0,
                'total_seats': int(request.form.get('total_seats', 1))
            }
            
            jobs_collection.insert_one(job)
            flash('Job posted successfully!', 'success')
            return redirect(url_for('recruiter_jobs'))
            
        except Exception as e:
            logger.error(f"Post job error: {str(e)}")
            flash('Error posting job. Please check all fields.', 'error')
    
    unread_count = get_unread_count(session['user_id'])
    return render_template('recruiter/post_job.html', unread_notifications=unread_count)

@app.route('/recruiter/job/<job_id>')
@recruiter_required
def recruiter_job_detail(job_id):
    try:
        job = jobs_collection.find_one({'_id': ObjectId(job_id)})
        
        if not job or job['recruiter_id'] != session['user_id']:
            flash('Job not found', 'error')
            return redirect(url_for('recruiter_jobs'))
        
        applications = list(applications_collection.find({'job_id': job_id}).sort('analysis.overall', -1))
        
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
        logger.error(f"Recruiter job detail error: {str(e)}")
        flash('Error loading job details', 'error')
        return redirect(url_for('recruiter_jobs'))

@app.route('/recruiter/candidates/<job_id>')
@recruiter_required
def view_candidates(job_id):
    try:
        job = jobs_collection.find_one({'_id': ObjectId(job_id)})
        
        if not job or job['recruiter_id'] != session['user_id']:
            flash('Job not found', 'error')
            return redirect(url_for('recruiter_jobs'))
        
        applications = list(applications_collection.find({'job_id': job_id}).sort('analysis.overall', -1))
        
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
                    'age': user.get('age', 'Not provided'),
                    'languages': user.get('languages', 'Not provided'),
                    'profile_picture': user.get('profile_picture'),
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
        logger.error(f"View candidates error: {str(e)}")
        flash('Error loading candidates', 'error')
        return redirect(url_for('recruiter_jobs'))

@app.route('/recruiter/candidates-table/<job_id>')
@recruiter_required
def view_candidates_table(job_id):
    try:
        job = jobs_collection.find_one({'_id': ObjectId(job_id)})
        
        if not job or job['recruiter_id'] != session['user_id']:
            flash('Job not found', 'error')
            return redirect(url_for('recruiter_dashboard'))
        
        applications = list(applications_collection.find({'job_id': job_id}).sort('analysis.overall', -1))
        
        candidates = []
        for app in applications:
            user = users_collection.find_one({'_id': ObjectId(app['user_id'])})
            if user:
                candidates.append({
                    'id': str(app['_id']),
                    'user_id': str(user['_id']),
                    'name': user.get('full_name', 'Unknown'),
                    'age': user.get('age', 'N/A'),
                    'languages': user.get('languages', 'N/A'),
                    'profile_picture': user.get('profile_picture'),
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
        logger.error(f"Candidates table error: {str(e)}")
        flash('Error loading candidates', 'error')
        return redirect(url_for('recruiter_dashboard'))

@app.route('/recruiter/update-status/<application_id>', methods=['POST'])
@recruiter_required
def update_application_status(application_id):
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
        
        job = jobs_collection.find_one({'_id': ObjectId(job_id)})
        
        if status == 'hired':
            jobs_collection.update_one(
                {'_id': ObjectId(job_id)},
                {'$inc': {'seats_filled': 1}}
            )
            create_notification(
                app['user_id'],
                '🎉 Congratulations! You are hired!',
                f'You have been selected for the {job.get("title")} position at {job.get("company")}.',
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
        logger.error(f"Update status error: {str(e)}")
        flash('Error updating status', 'error')
    
    return redirect(request.referrer)

@app.route('/recruiter/delete-job/<job_id>', methods=['POST'])
@recruiter_required
def delete_job(job_id):
    try:
        job = jobs_collection.find_one({'_id': ObjectId(job_id)})
        if not job or job['recruiter_id'] != session['user_id']:
            flash('Job not found', 'error')
            return redirect(url_for('recruiter_jobs'))
        
        jobs_collection.update_one(
            {'_id': ObjectId(job_id)},
            {'$set': {'is_active': False}}
        )
        
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
        logger.error(f"Delete job error: {str(e)}")
        flash('Error closing job', 'error')
    
    return redirect(url_for('recruiter_jobs'))

@app.route('/candidate/profile/<user_id>')
@login_required
def candidate_profile(user_id):
    try:
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
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
        logger.error(f"Profile fetch error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ==================== Job Seeker Routes ====================

@app.route('/jobseeker/search-jobs')
@jobseeker_required
def search_jobs():
    try:
        query = request.args.get('q', '').strip()
        location = request.args.get('location', '').strip()
        job_type = request.args.get('job_type', '')
        experience = request.args.get('experience', '')
        sort_by = request.args.get('sort_by', 'recent')
        
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
        
        # Sort order
        sort_order = [('posted_date', -1)]
        if sort_by == 'oldest':
            sort_order = [('posted_date', 1)]
        elif sort_by == 'company_asc':
            sort_order = [('company', 1)]
        elif sort_by == 'company_desc':
            sort_order = [('company', -1)]
        
        jobs = list(jobs_collection.find(search_filter).sort(sort_order))
        
        user = users_collection.find_one({'_id': ObjectId(session['user_id'])})
        applications = list(applications_collection.find({'user_id': session['user_id']}))
        applied_ids = [a['job_id'] for a in applications]
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
                'experience_level': job.get('experience_level'),
                'posted_date': job.get('posted_date'),
                'has_applied': job_id in applied_ids,
                'is_saved': job_id in saved_ids
            })
        
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
        logger.error(f"Search error: {str(e)}")
        flash('Error performing search', 'error')
        return redirect(url_for('jobseeker_dashboard'))

@app.route('/jobseeker/dashboard')
@jobseeker_required
def jobseeker_dashboard():
    try:
        user = users_collection.find_one({'_id': ObjectId(session['user_id'])})
        has_resume = user and 'resume_text' in user and user['resume_text']
        
        jobs = list(jobs_collection.find({
            'is_active': True,
            '$expr': {'$lt': ['$seats_filled', '$total_seats']}
        }).sort('posted_date', -1))
        
        applications = list(applications_collection.find({'user_id': session['user_id']}))
        applied_ids = [a['job_id'] for a in applications]
        
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
        logger.error(f"Jobseeker dashboard error: {str(e)}")
        flash('Error loading dashboard', 'error')
        return redirect(url_for('index'))

@app.route('/jobseeker/profile', methods=['GET', 'POST'])
@jobseeker_required
def jobseeker_profile():
    try:
        if request.method == 'POST':
            full_name = request.form.get('full_name')
            update_data = {
                'name': full_name,
                'full_name': full_name,
                'phone': request.form.get('phone'),
                'location': request.form.get('location'),
                'age': request.form.get('age'),
                'languages': request.form.get('languages'),
                'skills': request.form.get('skills'),
                'experience': request.form.get('experience'),
                'education': request.form.get('education'),
                'linkedin': request.form.get('linkedin'),
                'github': request.form.get('github'),
                'portfolio': request.form.get('portfolio'),
                'updated_at': datetime.utcnow()
            }
            
            if 'profile_picture' in request.files:
                file = request.files['profile_picture']
                if file and file.filename and allowed_file(file.filename):
                    ext = file.filename.rsplit('.', 1)[1].lower()
                    filename = secure_filename(f"profile_{session['user_id']}_{datetime.utcnow().timestamp()}.{ext}")
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)
                    update_data['profile_picture'] = filename
                    session['profile_picture'] = filename
            
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
        
        total_apps = applications_collection.count_documents({'user_id': session['user_id']})
        shortlisted = applications_collection.count_documents({'user_id': session['user_id'], 'status': 'shortlisted'})
        hired = applications_collection.count_documents({'user_id': session['user_id'], 'status': 'hired'})
        
        unread_count = get_unread_count(session['user_id'])
        
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
        logger.error(f"Jobseeker profile error: {str(e)}")
        flash('Error loading profile', 'error')
        return redirect(url_for('jobseeker_dashboard'))

@app.route('/jobseeker/upload-resume', methods=['POST'])
@jobseeker_required
def upload_resume():
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
        logger.error(f"Upload resume error: {str(e)}")
        flash('Error uploading file', 'error')
    
    return redirect(url_for('jobseeker_dashboard'))

@app.route('/jobseeker/job/<job_id>')
@jobseeker_required
def jobseeker_job_detail(job_id):
    try:
        job = jobs_collection.find_one({'_id': ObjectId(job_id)})
        
        if not job or not job.get('is_active'):
            flash('Job not found', 'error')
            return redirect(url_for('jobseeker_dashboard'))
        
        has_applied = applications_collection.find_one({
            'user_id': session['user_id'],
            'job_id': job_id
        }) is not None
        
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
                total_jobs_posted = jobs_collection.count_documents({'recruiter_id': job['recruiter_id']})
                active_jobs_count = jobs_collection.count_documents({'recruiter_id': job['recruiter_id'], 'is_active': True})
                recruiter_jobs = list(jobs_collection.find({'recruiter_id': job['recruiter_id']}, {'_id': 1}))
                recruiter_job_ids = [str(j['_id']) for j in recruiter_jobs]
                total_hires = applications_collection.count_documents({'job_id': {'$in': recruiter_job_ids}, 'status': 'hired'})
        
        analysis = None
        if user and 'resume_text' in user and user['resume_text'] and not has_applied:
            analysis = analyze_resume(
                user['resume_text'],
                job.get('description', '') + ' ' + job.get('requirements', ''),
                job.get('title', '')
            )
            # Fix: Convert overall_score to overall if needed
            if analysis and 'overall_score' in analysis:
                analysis['overall'] = analysis['overall_score']
        
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
        logger.error(f"Job detail error: {str(e)}")
        flash('Error loading job details', 'error')
        return redirect(url_for('jobseeker_dashboard'))
@app.route('/jobseeker/apply/<job_id>', methods=['POST'])
@jobseeker_required
def apply_job(job_id):
    try:
        user_id = session['user_id']
        
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            flash('User not found. Please login again.', 'error')
            return redirect(url_for('login'))
        
        if 'resume_text' not in user or not user['resume_text']:
            flash('Please upload your resume first', 'error')
            return redirect(url_for('jobseeker_dashboard'))
        
        try:
            job = jobs_collection.find_one({'_id': ObjectId(job_id)})
        except:
            flash('Invalid job ID', 'error')
            return redirect(url_for('jobseeker_dashboard'))
        
        if not job:
            flash('Job not found', 'error')
            return redirect(url_for('jobseeker_dashboard'))
        
        if job.get('seats_filled', 0) >= job.get('total_seats', 1):
            flash('This position has been filled', 'error')
            return redirect(url_for('jobseeker_dashboard'))
        
        existing = applications_collection.find_one({
            'user_id': user_id,
            'job_id': job_id
        })
        
        if existing:
            flash('You have already applied for this job', 'warning')
            return redirect(url_for('jobseeker_dashboard'))
        
        analysis = analyze_resume(
            user['resume_text'],
            job.get('description', '') + ' ' + job.get('requirements', ''),
            job.get('title', '')
        )
        
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
        
        try:
            result = applications_collection.insert_one(application)
            logger.info(f"Application saved with ID: {result.inserted_id}")
            
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
                flash('You have already applied for this job', 'warning')
            else:
                logger.error(f"Insert error: {str(e)}")
                flash(f'Error submitting application: {str(e)}', 'error')
        
        return redirect(url_for('jobseeker_dashboard'))
        
    except Exception as e:
        logger.error(f"Application error: {str(e)}")
        flash(f'Error submitting application: {str(e)}', 'error')
        return redirect(url_for('jobseeker_dashboard'))

@app.route('/jobseeker/save-job/<job_id>', methods=['POST'])
@jobseeker_required
def save_job(job_id):
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
    try:
        apps = list(applications_collection.find({'user_id': session['user_id']}).sort('applied_date', -1))
        
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
        logger.error(f"My applications error: {str(e)}")
        flash('Error loading applications', 'error')
        return redirect(url_for('jobseeker_dashboard'))

@app.route('/jobseeker/application/<application_id>')
@jobseeker_required
def jobseeker_application_detail(application_id):
    try:
        app = applications_collection.find_one({'_id': ObjectId(application_id)})
        
        if not app or app['user_id'] != session['user_id']:
            flash('Application not found', 'error')
            return redirect(url_for('my_applications'))
        
        job = jobs_collection.find_one({'_id': ObjectId(app['job_id'])})
        
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
        logger.error(f"Application detail error: {str(e)}")
        flash('Error loading application details', 'error')
        return redirect(url_for('my_applications'))

@app.route('/jobseeker/saved-jobs')
@jobseeker_required
def saved_jobs():
    try:
        user = users_collection.find_one({'_id': ObjectId(session['user_id'])})
        saved_ids = user.get('saved_jobs', []) if user else []
        
        jobs = []
        for job_id in saved_ids:
            job = jobs_collection.find_one({'_id': ObjectId(job_id), 'is_active': True})
            if job:
                job['_id'] = str(job['_id'])
                jobs.append(job)
        
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
        logger.error(f"Saved jobs error: {str(e)}")
        flash('Error loading saved jobs', 'error')
        return redirect(url_for('jobseeker_dashboard'))

# ==================== File Download & Image Serving ====================

@app.route('/download/<filename>')
@login_required
def download_file(filename):
    try:
        return send_file(
            os.path.join(app.config['UPLOAD_FOLDER'], filename),
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        flash('Error downloading file', 'error')
        return redirect(request.referrer or url_for('index'))

@app.route('/image/<filename>')
def get_image(filename):
    try:
        return send_file(
            os.path.join(app.config['UPLOAD_FOLDER'], filename),
            mimetype='image/jpeg'
        )
    except:
        return send_file('static/default-avatar.png', mimetype='image/png')

# ==================== Health Check ====================

@app.route('/health')
def health_check():
    return "OK", 200

# ==================== Static Pages ====================

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/faq')
def faq():
    return render_template('faq.html')

@app.route('/privacy-policy')
def privacy_policy():
    return render_template('privacy_policy.html')

@app.route('/terms-of-service')
def terms_of_service():
    return render_template('terms_of_service.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/favicon.ico')
def favicon():
    return send_file('static/favicon.ico')

# ==================== Google OAuth ====================

from authlib.integrations.flask_client import OAuth

oauth = OAuth(app)

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
    try:
        redirect_uri = os.getenv('GOOGLE_REDIRECT_URI', 'https://resumeradar.onrender.com/google/callback')
        return google.authorize_redirect(redirect_uri)
    except Exception as e:
        logger.error(f"Google login error: {str(e)}")
        flash('Unable to login with Google. Please try again.', 'error')
        return redirect(url_for('login'))

@app.route('/google/callback')
def google_callback():
    try:
        token = google.authorize_access_token()
        resp = google.get('userinfo')
        userinfo = resp.json()
        
        email = userinfo.get('email')
        name = userinfo.get('name', email.split('@')[0])
        
        if not email:
            flash('Could not retrieve email from Google', 'error')
            return redirect(url_for('login'))
        
        user = users_collection.find_one({'email': email})
        
        if user:
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
        logger.error(f"Google OAuth error: {str(e)}")
        flash('Google login failed. Please try again.', 'error')
        return redirect(url_for('login'))

# ==================== Forgot Password ====================

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
                
                reset_url = url_for('reset_password', token=token, _external=True)
                
                msg = Message(
                    subject='Password Reset Request - ResumeRadar',
                    recipients=[email],
                    html=f"""
                    <h2>Reset Your Password</h2>
                    <p>Click the link below to reset your password:</p>
                    <a href="{reset_url}">{reset_url}</a>
                    <p>This link expires in 1 hour.</p>
                    """
                )
                mail.send(msg)
                flash('Password reset link sent to your email!', 'success')
            else:
                flash('If your email is registered, you will receive a reset link', 'success')
            
            return redirect(url_for('login'))
            
        except Exception as e:
            logger.error(f"Forgot password error: {str(e)}")
            flash('Error processing request', 'error')
    
    return render_template('forgot_password.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    reset_record = password_resets_collection.find_one({
        'token': token,
        'expires_at': {'$gt': datetime.utcnow()}
    })
    
    if not reset_record:
        flash('Invalid or expired reset link', 'error')
        return redirect(url_for('forgot_password'))
    
    if request.method == 'POST':
        try:
            password = request.form.get('password')
            confirm = request.form.get('confirm_password')
            
            if password != confirm:
                flash('Passwords do not match', 'error')
                return redirect(url_for('reset_password', token=token))
            
            if len(password) < 8:
                flash('Password must be at least 8 characters', 'error')
                return redirect(url_for('reset_password', token=token))
            
            users_collection.update_one(
                {'email': reset_record['email']},
                {'$set': {'password': generate_password_hash(password)}}
            )
            
            password_resets_collection.delete_one({'token': token})
            
            flash('Password reset successful! Please login.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            logger.error(f"Reset error: {str(e)}")
            flash('Error resetting password', 'error')
    
    return render_template('reset_password.html', token=token)

# ==================== Delete Account ====================

@app.route('/delete-account', methods=['POST'])
@login_required
def delete_account():
    try:
        user_id = session['user_id']
        user_role = session.get('user_role')
        
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        user_email = user.get('email') if user else 'Unknown'
        
        if user_role == 'jobseeker':
            apps_deleted = applications_collection.delete_many({'user_id': user_id})
            logger.info(f"Deleted {apps_deleted.deleted_count} applications for user {user_email}")
        
        if user_role == 'recruiter':
            recruiter_jobs = jobs_collection.find({'recruiter_id': user_id})
            job_ids = [str(job['_id']) for job in recruiter_jobs]
            
            if job_ids:
                apps_deleted = applications_collection.delete_many({'job_id': {'$in': job_ids}})
                logger.info(f"Deleted {apps_deleted.deleted_count} applications for recruiter's jobs")
            
            jobs_deleted = jobs_collection.delete_many({'recruiter_id': user_id})
            logger.info(f"Deleted {jobs_deleted.deleted_count} jobs posted by recruiter")
        
        users_collection.delete_one({'_id': ObjectId(user_id)})
        session.clear()
        
        flash("Your account has been permanently deleted. We're sorry to see you go!", 'info')
        return redirect(url_for('index'))
        
    except Exception as e:
        logger.error(f"Delete account error: {str(e)}")
        flash(f'Error deleting account: {str(e)}', 'error')
        return redirect(request.referrer or url_for('index'))

# ==================== Error Handlers ====================

@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500

# ==================== Run Application ====================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)