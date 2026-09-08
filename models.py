import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash

DB_NAME = "medicoapp.db"

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row  # Access columns by name
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create Users table (Roles: 'admin', 'doctor', 'patient')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'patient',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create OP Appointments table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_name TEXT NOT NULL,
            patient_phone TEXT NOT NULL,
            doctor_name TEXT NOT NULL,
            department TEXT NOT NULL,
            appointment_date TEXT NOT NULL,
            time_slot TEXT NOT NULL,
            status TEXT DEFAULT 'Pending',
            created_by_user_id INTEGER,
            FOREIGN KEY (created_by_user_id) REFERENCES users (id)
        )
    ''')

    # Create Default Admin User if none exists
    cursor.execute('SELECT * FROM users WHERE role = ?', ('admin',))
    if not cursor.fetchone():
        admin_pass = generate_password_hash("AdminPass123")
        cursor.execute('''
            INSERT INTO users (username, email, password_hash, role)
            VALUES (?, ?, ?, ?)
        ''', ('admin', 'admin@medicoapp.com', admin_pass, 'admin'))

    conn.commit()
    conn.close()

# --- User Database Operations using SQL Cursors ---

def create_user(username, email, password, role='patient'):
    conn = get_db_connection()
    cursor = conn.cursor()
    hashed = generate_password_hash(password)
    try:
        cursor.execute('''
            INSERT INTO users (username, email, password_hash, role)
            VALUES (?, ?, ?, ?)
        ''', (username, email, hashed, role))
        conn.commit()
        return True, "User registered successfully!"
    except sqlite3.IntegrityError:
        return False, "Username or Email already exists."
    finally:
        conn.close()

def authenticate_user(username_or_email, password):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM users WHERE username = ? OR email = ?
    ''', (username_or_email, username_or_email))
    user = cursor.fetchone()
    conn.close()

    if user and check_password_hash(user['password_hash'], password):
        return dict(user)
    return None

def get_all_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, email, role, created_at FROM users')
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return users

def update_user(user_id, email, role):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE users SET email = ?, role = ? WHERE id = ?
    ''', (email, role, user_id))
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0

def delete_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0

# --- Appointment Database Operations ---

def create_appointment(patient_name, phone, doctor_name, dept, app_date, time_slot, user_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO appointments (patient_name, patient_phone, doctor_name, department, appointment_date, time_slot, created_by_user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (patient_name, phone, doctor_name, dept, app_date, time_slot, user_id))
    conn.commit()
    app_id = cursor.lastrowid
    conn.close()
    return app_id

def get_all_appointments():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM appointments ORDER BY id DESC')
    appointments = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return appointments

def update_appointment_status(app_id, status):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE appointments SET status = ? WHERE id = ?', (status, app_id))
    conn.commit()
    conn.close()

def get_dashboard_stats():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) as total FROM users')
    total_users = cursor.fetchone()['total']
    
    cursor.execute('SELECT COUNT(*) as total FROM appointments')
    total_apps = cursor.fetchone()['total']
    
    cursor.execute('SELECT COUNT(*) as total FROM appointments WHERE status = "Confirmed"')
    confirmed_apps = cursor.fetchone()['total']
    
    cursor.execute('SELECT COUNT(*) as total FROM appointments WHERE status = "Pending"')
    pending_apps = cursor.fetchone()['total']
    
    conn.close()
    return {
        "users": total_users,
        "total_appointments": total_apps,
        "confirmed_appointments": confirmed_apps,
        "pending_appointments": pending_apps
    }