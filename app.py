import sqlite3
import datetime
from flask import Flask, request, render_template_string, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash


app = Flask(__name__)
app.secret_key = 'hospital-super-secret-key'
DATABASE = 'hospital.db'


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT DEFAULT 'Patient',
                specialization TEXT DEFAULT 'N/A'
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                doctor_id INTEGER NOT NULL,
                appointment_date TEXT NOT NULL,
                status TEXT DEFAULT 'Pending',
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (doctor_id) REFERENCES users (id)
            )
        ''')
       
        default_users = [
            ('Dev', generate_password_hash('dev@123'), 'Admin', 'System Administrator'),
            ('dr_smith', generate_password_hash('smith@123'), 'Doctor', 'General Physician'),
            ('dr_adams', generate_password_hash('adams@123'), 'Doctor', 'Cardiologist'),
            ('ravi', generate_password_hash('ravi@123'), 'Patient', 'N/A'),
            ('raju', generate_password_hash('raju@123'), 'Patient', 'N/A'),
            ('ramu', generate_password_hash('ramu@123'), 'Patient', 'N/A'),
            ('yash', generate_password_hash('yash@123'), 'Patient', 'N/A')
        ]
       
        for username, password, role, specialization in default_users:
            existing = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO users (username, password, role, specialization) VALUES (?, ?, ?, ?)",
                    (username, password, role, specialization)
                )
        conn.commit()
        init_db()


@app.route('/')
def index():
    return render_template_string(INDEX_HTML)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])
        try:
            with get_db() as conn:
                conn.execute("INSERT INTO users (username, password, role, specialization) VALUES (?, ?, ?, ?)", (username, password, 'Patient', 'N/A'))
                conn.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username already exists.', 'danger')
    return render_template_string(REGISTER_HTML)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        with get_db() as conn:
            user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            if user and check_password_hash(user['password'], password):
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['role'] = user['role']
                flash('Logged in successfully!', 'success')
                return redirect(url_for('index'))
            else:
                flash('Invalid credentials.', 'danger')
    return render_template_string(LOGIN_HTML)


@app.route('/appointments', methods=['GET', 'POST'])
def appointments():
    if 'user_id' not in session:
        flash('Please login first.', 'warning')
        return redirect(url_for('login'))
   
    today_str = datetime.date.today().isoformat()
    max_date_str = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()


    if request.method == 'POST' and session.get('role') == 'Patient':
        doctor_id = request.form['doctor_id']
        appointment_date = request.form['appointment_date']
       
        if appointment_date < today_str:
            flash('Cannot book appointments for past dates.', 'danger')
            return redirect(url_for('appointments'))


        with get_db() as conn:
            existing_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM appointments WHERE doctor_id = ? AND appointment_date = ? AND status != 'Rejected'",
                (doctor_id, appointment_date)
            ).fetchone()['cnt']


            if existing_count >= 3:
                flash('Selected doctor is fully booked on this date (max 3 slots). Please choose another date.', 'danger')
            else:
                conn.execute(
                    "INSERT INTO appointments (user_id, doctor_id, appointment_date, status) VALUES (?, ?, ?, 'Pending')",
                    (session['user_id'], doctor_id, appointment_date)
                )
                conn.commit()
                flash('Appointment requested successfully! Status is Pending approval.', 'success')
        return redirect(url_for('appointments'))


    with get_db() as conn:
        doctors = conn.execute("SELECT * FROM users WHERE role = 'Doctor'").fetchall()
       
        if session.get('role') == 'Admin':
            user_appointments = conn.execute("""
                SELECT appointments.*, p.username as patient_name, d.username as doctor_name, d.specialization
                FROM appointments
                JOIN users p ON appointments.user_id = p.id
                JOIN users d ON appointments.doctor_id = d.id
            """).fetchall()
        elif session.get('role') == 'Doctor':
            user_appointments = conn.execute("""
                SELECT appointments.*, p.username as patient_name, d.username as doctor_name, d.specialization
                FROM appointments
                JOIN users p ON appointments.user_id = p.id
                JOIN users d ON appointments.doctor_id = d.id
                WHERE appointments.doctor_id = ?
            """, (session['user_id'],)).fetchall()
        else:
            user_appointments = conn.execute("""
                SELECT appointments.*, d.username as doctor_name, d.specialization
                FROM appointments
                JOIN users d ON appointments.doctor_id = d.id
                WHERE appointments.user_id = ?
            """, (session['user_id'],)).fetchall()
       
    return render_template_string(APPOINTMENTS_HTML, appointments=user_appointments, doctors=doctors, min_date=today_str, max_date=max_date_str)


@app.route('/appointment/<int:appt_id>/approve')
def approve_appointment(appt_id):
    if session.get('role') not in ['Admin', 'Doctor']:
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))
    with get_db() as conn:
        conn.execute("UPDATE appointments SET status = 'Approved' WHERE id = ?", (appt_id,))
        conn.commit()
    flash('Appointment approved successfully.', 'success')
    return redirect(url_for('appointments'))


@app.route('/appointment/<int:appt_id>/reject')
def reject_appointment(appt_id):
    if session.get('role') not in ['Admin', 'Doctor']:
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))
    with get_db() as conn:
        conn.execute("UPDATE appointments SET status = 'Rejected' WHERE id = ?", (appt_id,))
        conn.commit()
    flash('Appointment rejected.', 'info')
    return redirect(url_for('appointments'))


@app.route('/admin/users')
def admin_users():
    if session.get('role') != 'Admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))
    with get_db() as conn:
        users = conn.execute("SELECT * FROM users").fetchall()
    return render_template_string(ADMIN_USERS_HTML, users=users)


@app.route('/admin/users/add', methods=['POST'])
def admin_add_user():
    if session.get('role') != 'Admin':
        return redirect(url_for('index'))
    username = request.form['username']
    password = generate_password_hash(request.form['password'])
    role = request.form['role']
    specialization = request.form['specialization'] if role == 'Doctor' else 'N/A'
    try:
        with get_db() as conn:
            conn.execute("INSERT INTO users (username, password, role, specialization) VALUES (?, ?, ?, ?)", (username, password, role, specialization))
            conn.commit()
        flash(f'User {username} created successfully.', 'success')
    except sqlite3.IntegrityError:
        flash('Username already exists.', 'danger')
    return redirect(url_for('admin_users'))


@app.route('/admin/users/update/<int:user_id>', methods=['POST'])
def admin_update_user(user_id):
    if session.get('role') != 'Admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))
    new_role = request.form['role']
    new_spec = request.form['specialization'] if new_role == 'Doctor' else 'N/A'
    with get_db() as conn:
        conn.execute("UPDATE users SET role = ?, specialization = ? WHERE id = ?", (new_role, new_spec, user_id))
        conn.commit()
    flash('User role and details updated successfully.', 'success')
    return redirect(url_for('admin_users'))


@app.route('/admin/users/delete/<int:user_id>')
def admin_delete_user(user_id):
    if session.get('role') != 'Admin':
        return redirect(url_for('index'))
    with get_db() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
    flash('User deleted successfully.', 'info')
    return redirect(url_for('admin_users'))


@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=True, port=3000)


