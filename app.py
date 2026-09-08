import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from functools import wraps
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_cors import CORS
import jwt

import models

app = Flask(__name__)
app.config['SECRET_KEY'] = 'medicoapp-super-secret-key-2026'

# Configure CORS
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Email Settings (Standard SMTP)
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587
SENDER_EMAIL = 'your-email@gmail.com'      # Replace with actual email
SENDER_PASSWORD = 'your-app-password'      # Replace with App Password

# Initialize DB on Startup
models.init_db()

# --- Helper Utilities & Decorators ---

def send_email_notification(subject, recipient, body_text):
    """Sends background email notifications using Python's built-in smtplib"""
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = recipient
        msg['Subject'] = subject
        msg.attach(MIMEText(body_text, 'plain'))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"[Email Error] Failed to send email to {recipient}: {e}")
        return False

def jwt_token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
        
        if not token:
            token = session.get('jwt_token')

        if not token:
            return jsonify({'message': 'Token is missing!'}), 401

        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = data
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token has expired!'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'message': 'Invalid token!'}), 401

        return f(current_user, *args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    @jwt_token_required
    def decorated(current_user, *args, **kwargs):
        if current_user.get('role') != 'admin':
            return jsonify({'message': 'Admin privileges required!'}), 403
        return f(current_user, *args, **kwargs)
    return decorated


# --- Web Page Views ---

@app.route('/')
def index():
    stats = models.get_dashboard_stats()
    appointments = models.get_all_appointments()
    users = models.get_all_users() if session.get('user_role') == 'admin' else []
    return render_template('index.html', stats=stats, appointments=appointments, users=users)


# --- Authentication & JWT Routes ---

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json() or request.form
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    role = data.get('role', 'patient')

    if not username or not email or not password:
        return jsonify({'message': 'All fields are required'}), 400

    success, msg = models.create_user(username, email, password, role)
    if success:
        send_email_notification("Welcome to MedicoApp", email, f"Hello {username},\n\nYour registration was successful!")
        return jsonify({'message': msg}), 201
    return jsonify({'message': msg}), 400

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json() or request.form
    username = data.get('username')
    password = data.get('password')

    user = models.authenticate_user(username, password)
    if not user:
        return jsonify({'message': 'Invalid credentials'}), 401

    token = jwt.encode({
        'user_id': user['id'],
        'username': user['username'],
        'role': user['role'],
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=12)
    }, app.config['SECRET_KEY'], algorithm="HS256")

    session['jwt_token'] = token
    session['user_id'] = user['id']
    session['username'] = user['username']
    session['user_role'] = user['role']

    return jsonify({
        'message': 'Login successful',
        'token': token,
        'user': {'id': user['id'], 'username': user['username'], 'role': user['role']}
    }), 200

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


# --- OP Appointments Routes ---

@app.route('/api/appointments', methods=['POST'])
def book_appointment():
    data = request.get_json() or request.form
    patient_name = data.get('patient_name')
    phone = data.get('patient_phone')
    doctor_name = data.get('doctor_name')
    dept = data.get('department')
    app_date = data.get('appointment_date')
    time_slot = data.get('time_slot')
    user_id = session.get('user_id')

    if not all([patient_name, phone, doctor_name, dept, app_date, time_slot]):
        return jsonify({'message': 'Missing appointment details'}), 400

    app_id = models.create_appointment(patient_name, phone, doctor_name, dept, app_date, time_slot, user_id)
    return jsonify({'message': 'OP Appointment booked successfully!', 'appointment_id': app_id}), 201


# --- Role-Based Admin Panel Management ---

@app.route('/api/admin/dashboard', methods=['GET'])
@admin_required
def admin_dashboard(current_user):
    stats = models.get_dashboard_stats()
    return jsonify({'stats': stats}), 200

@app.route('/api/admin/users/<int:user_id>', methods=['PUT'])
@admin_required
def admin_update_user(current_user, user_id):
    data = request.get_json()
    email = data.get('email')
    role = data.get('role')

    if not email or not role:
        return jsonify({'message': 'Email and Role are required'}), 400

    updated = models.update_user(user_id, email, role)
    if updated:
        return jsonify({'message': f'User ID {user_id} updated successfully'}), 200
    return jsonify({'message': 'User not found or no changes made'}), 404

@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@admin_required
def admin_delete_user(current_user, user_id):
    if user_id == current_user['user_id']:
        return jsonify({'message': 'Admin cannot delete their own account'}), 400

    deleted = models.delete_user(user_id)
    if deleted:
        return jsonify({'message': f'User ID {user_id} deleted successfully'}), 200
    return jsonify({'message': 'User not found'}), 404

@app.route('/api/admin/appointments/<int:app_id>/status', methods=['PUT'])
@admin_required
def admin_update_appointment_status(current_user, app_id):
    data = request.get_json()
    status = data.get('status')
    
    if status not in ['Pending', 'Confirmed', 'Cancelled']:
        return jsonify({'message': 'Invalid status'}), 400

    models.update_appointment_status(app_id, status)
    return jsonify({'message': f'Appointment status updated to {status}'}), 200


if __name__ == '__main__':
    app.run(debug=True, port=5000)