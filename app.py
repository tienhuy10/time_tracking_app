from flask import Flask, render_template, request, redirect, url_for, session, send_file
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import sqlite3
import os
from datetime import datetime, timedelta
from calendar import monthrange  # Thêm import này
from openpyxl import Workbook
import base64
from io import BytesIO
from PIL import Image

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

if not os.path.exists('static/photos'):
    os.makedirs('static/photos')

def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        full_name TEXT DEFAULT '',
        phone TEXT DEFAULT '',
        email TEXT DEFAULT '',
        role TEXT DEFAULT 'employee'
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS time_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        timestamp TEXT,
        type TEXT,
        photo_path TEXT,
        reason TEXT DEFAULT '',
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    c.execute("INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, ?)", 
              ('admin', 'admin123', 'admin'))
    conn.commit()
    conn.close()

init_db()

class User(UserMixin):
    def __init__(self, id):
        self.id = id

@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    conn.close()
    if user:
        return User(user[0])
    return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
        user = c.fetchone()
        conn.close()
        if user:
            login_user(User(user[0]))
            if user[6] == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('employee_dashboard'))
        return "Sai tài khoản hoặc mật khẩu!"
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def employee_dashboard():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    search_type = request.form.get('search_type', '')
    query = "SELECT timestamp, type, photo_path, reason FROM time_records WHERE user_id = ?"
    params = [current_user.id]
    
    if search_type:
        query += " AND type = ?"
        params.append(search_type)
    
    c.execute(query, params)
    records = c.fetchall()
    conn.close()

    daily_records = {}
    for record in records:
        timestamp = record[0]
        date = timestamp.split(' ')[0]
        time_str = timestamp.split(' ')[1]
        record_type = record[1]
        photo_path = record[2]
        reason = record[3]
        
        if date not in daily_records:
            daily_records[date] = {
                'in_morning': {'time': '', 'photo': '', 'reason': ''},
                'out_morning': {'time': '', 'photo': '', 'reason': ''},
                'in_afternoon': {'time': '', 'photo': '', 'reason': ''},
                'out_afternoon': {'time': '', 'photo': '', 'reason': ''},
                'total_time': {'hours': 0, 'minutes': 0, 'seconds': 0}
            }
        
        daily_records[date][record_type] = {'time': time_str, 'photo': photo_path, 'reason': reason}

    for date, records in daily_records.items():
        total_seconds = 0
        if records['in_morning']['time'] and records['out_morning']['time']:
            in_morning = datetime.strptime(records['in_morning']['time'], '%H:%M:%S')
            out_morning = datetime.strptime(records['out_morning']['time'], '%H:%M:%S')
            total_seconds += (out_morning - in_morning).seconds
        if records['in_afternoon']['time'] and records['out_afternoon']['time']:
            in_afternoon = datetime.strptime(records['in_afternoon']['time'], '%H:%M:%S')
            out_afternoon = datetime.strptime(records['out_afternoon']['time'], '%H:%M:%S')
            total_seconds += (out_afternoon - in_afternoon).seconds
        
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        daily_records[date]['total_time'] = {'hours': hours, 'minutes': minutes, 'seconds': seconds}

    return render_template('employee_dashboard.html', daily_records=daily_records)

@app.route('/checkin', methods=['GET', 'POST'])
@login_required
def checkin():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    
    c.execute("SELECT type FROM time_records WHERE user_id = ? AND timestamp LIKE ?", 
              (current_user.id, f'{today}%'))
    records = c.fetchall()
    checkin_types = [r[0] for r in records]
    
    current_hour = datetime.now().hour
    is_morning = current_hour < 12
    
    next_checkin_type = None
    if is_morning:
        if 'in_morning' not in checkin_types:
            next_checkin_type = 'in_morning'
        elif 'out_morning' not in checkin_types:
            next_checkin_type = 'out_morning'
    else:
        if 'in_afternoon' not in checkin_types:
            next_checkin_type = 'in_afternoon'
        elif 'out_afternoon' not in checkin_types:
            next_checkin_type = 'out_afternoon'

    if request.method == 'POST' and next_checkin_type:
        photo_data = request.form['photo']
        reason = request.form.get('reason', '')
        
        img_data = base64.b64decode(photo_data.split(',')[1])
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        photo_path = f'static/photos/{current_user.id}_{timestamp.replace(":", "-")}.jpg'
        
        with open(photo_path, 'wb') as f:
            f.write(img_data)

        c.execute("INSERT INTO time_records (user_id, timestamp, type, photo_path, reason) VALUES (?, ?, ?, ?, ?)",
                  (current_user.id, timestamp, next_checkin_type, photo_path, reason))
        conn.commit()
        conn.close()
        return redirect(url_for('employee_dashboard'))
    
    conn.close()
    return render_template('checkin.html', next_checkin_type=next_checkin_type)

@app.route('/admin')
@login_required
def admin_dashboard():
    if current_user.id != 1:
        return "Access denied"
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    c.execute("SELECT u.username, u.full_name, t.timestamp, t.type, t.photo_path, t.reason FROM users u LEFT JOIN time_records t ON u.id = t.user_id WHERE t.timestamp >= ?",
              (f'{start_date} 00:00:00',))
    records = c.fetchall()
    
    daily_records = {}
    for record in records:
        username = record[0]
        full_name = record[1]
        timestamp = record[2]
        if not timestamp:
            continue
        date = timestamp.split(' ')[0]
        time_str = timestamp.split(' ')[1]
        record_type = record[3]
        photo_path = record[4]
        reason = record[5]
        
        if username not in daily_records:
            daily_records[username] = {'full_name': full_name, 'days': {}}
        if date not in daily_records[username]['days']:
            daily_records[username]['days'][date] = {
                'in_morning': {'time': '', 'photo': '', 'reason': ''},
                'out_morning': {'time': '', 'photo': '', 'reason': ''},
                'in_afternoon': {'time': '', 'photo': '', 'reason': ''},
                'out_afternoon': {'time': '', 'photo': '', 'reason': ''},
                'total_time': {'hours': 0, 'minutes': 0, 'seconds': 0}
            }
        
        daily_records[username]['days'][date][record_type] = {'time': time_str, 'photo': photo_path, 'reason': reason}

    for username, data in daily_records.items():
        for date, records in data['days'].items():
            total_seconds = 0
            if records['in_morning']['time'] and records['out_morning']['time']:
                in_morning = datetime.strptime(records['in_morning']['time'], '%H:%M:%S')
                out_morning = datetime.strptime(records['out_morning']['time'], '%H:%M:%S')
                total_seconds += (out_morning - in_morning).seconds
            if records['in_afternoon']['time'] and records['out_afternoon']['time']:
                in_afternoon = datetime.strptime(records['in_afternoon']['time'], '%H:%M:%S')
                out_afternoon = datetime.strptime(records['out_afternoon']['time'], '%H:%M:%S')
                total_seconds += (out_afternoon - in_afternoon).seconds
            
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            daily_records[username]['days'][date]['total_time'] = {'hours': hours, 'minutes': minutes, 'seconds': seconds}

    conn.close()
    return render_template('admin_dashboard.html', daily_records=daily_records)

@app.route('/admin/employees', methods=['GET', 'POST'])
@login_required
def admin_employees():
    if current_user.id != 1:
        return "Access denied"
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT id, username, full_name, phone, email, role FROM users")
    users = c.fetchall()
    conn.close()
    return render_template('admin_employees.html', users=users)

@app.route('/admin/attendance', methods=['GET', 'POST'])
@login_required
def admin_attendance():
    if current_user.id != 1:
        return "Access denied"
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    selected_month = request.form.get('month', datetime.now().strftime('%Y-%m'))
    c.execute("SELECT u.id, u.full_name, t.timestamp, t.type, t.reason FROM users u LEFT JOIN time_records t ON u.id = t.user_id WHERE t.timestamp LIKE ? AND u.role = 'employee'",
              (f'{selected_month}%',))
    records = c.fetchall()
    
    # Lấy danh sách nhân viên
    c.execute("SELECT id, full_name FROM users WHERE role = 'employee'")
    employees = c.fetchall()
    employee_dict = {emp[0]: emp[1] for emp in employees}
    
    # Tạo danh sách ngày trong tháng
    days_in_month = []
    year, month = map(int, selected_month.split('-'))
    for day in range(1, 32):
        try:
            date = datetime(year, month, day).strftime('%Y-%m-%d')
            days_in_month.append(date)
        except ValueError:
            break
    
    # Xử lý dữ liệu chấm công
    attendance_data = {emp_id: {'days': {}, 'total': 0} for emp_id in employee_dict}
    for record in records:
        emp_id = record[0]
        timestamp = record[2]
        if not timestamp:
            continue
        date = timestamp.split(' ')[0]
        time_str = timestamp.split(' ')[1]
        record_type = record[3]
        reason = record[4] or ''
        
        if emp_id not in attendance_data:
            attendance_data[emp_id] = {'days': {}, 'total': 0}
        if date not in attendance_data[emp_id]['days']:
            attendance_data[emp_id]['days'][date] = {
                'in_morning': '', 'out_morning': '', 'in_afternoon': '', 'out_afternoon': '', 'reason': ''
            }
        attendance_data[emp_id]['days'][date][record_type] = time_str
        if record_type == 'in_morning' and time_str:  # Chỉ cần có vào sáng là tính ngày công
            attendance_data[emp_id]['total'] += 1
        if reason:
            attendance_data[emp_id]['days'][date]['reason'] = reason
    
    conn.close()
    return render_template('admin_attendance.html', attendance_data=attendance_data, employee_dict=employee_dict, days_in_month=days_in_month, selected_month=selected_month)

@app.route('/admin/filter_month', methods=['GET', 'POST'])
@login_required
def admin_filter_month():
    if current_user.id != 1:
        return "Access denied"
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    c.execute("SELECT id, username, full_name FROM users WHERE role = 'employee'")
    users = c.fetchall()
    
    default_month = datetime.now().strftime('%Y-%m')
    
    if request.method == 'POST':
        user_id = request.form['user_id']
        selected_month = request.form['month']
        
        c.execute("SELECT u.full_name, t.timestamp, t.type, t.reason FROM users u JOIN time_records t ON u.id = t.user_id WHERE u.id = ? AND t.timestamp LIKE ?",
                  (user_id, f'{selected_month}%'))
        records = c.fetchall()
        
        daily_records = {}
        stats = {'on_time': 0, 'late': 0, 'absent': 0, 'reasons': []}
        
        # Tính số ngày trong tháng
        year, month = map(int, selected_month.split('-'))
        _, days_in_month = monthrange(year, month)
        all_dates = set([datetime(year, month, day).strftime('%Y-%m-%d') for day in range(1, days_in_month + 1)])
        
        for record in records:
            full_name = record[0]
            timestamp = record[1]
            date = timestamp.split(' ')[0]
            time_str = timestamp.split(' ')[1]
            record_type = record[2]
            reason = record[3]
            
            if date not in daily_records:
                daily_records[date] = {
                    'full_name': full_name,
                    'in_morning': {'time': '', 'reason': ''},
                    'out_morning': {'time': ''},
                    'in_afternoon': {'time': '', 'reason': ''},
                    'out_afternoon': {'time': ''}
                }
            
            daily_records[date][record_type] = {'time': time_str, 'reason': reason or ''}

        for date in all_dates:
            if date in daily_records:
                in_morning_time = daily_records[date]['in_morning']['time']
                if in_morning_time:
                    in_morning = datetime.strptime(in_morning_time, '%H:%M:%S')
                    if in_morning.hour < 8 or (in_morning.hour == 8 and in_morning.minute == 0):
                        stats['on_time'] += 1
                    else:
                        stats['late'] += 1
                    if daily_records[date]['in_morning']['reason']:
                        stats['reasons'].append(f"{date}: {daily_records[date]['in_morning']['reason']}")
            else:
                stats['absent'] += 1
        
        conn.close()
        return render_template('admin_filter_month.html', daily_records=daily_records, stats=stats, users=users, selected_month=selected_month)
    
    conn.close()
    return render_template('admin_filter_month.html', users=users, selected_month=default_month)  # Truyền default_month

@app.route('/admin/export', methods=['POST'])
@login_required
def admin_export():
    if current_user.id != 1:
        return "Access denied"
    selected_month = request.form['month']
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    c.execute("SELECT u.full_name, t.timestamp, t.type, t.reason FROM users u LEFT JOIN time_records t ON u.id = t.user_id WHERE t.timestamp LIKE ? AND u.role = 'employee'",
              (f'{selected_month}%',))
    records = c.fetchall()
    
    wb = Workbook()
    ws = wb.active
    ws.append(["Họ tên", "Ngày tháng năm", "Loại chấm công", "Thời gian", "Lý do"])
    for record in records:
        full_name = record[0]
        timestamp = record[1]
        if not timestamp:
            continue
        date = timestamp.split(' ')[0]
        time = timestamp.split(' ')[1]
        check_type = record[2]
        reason = record[3] or ''
        ws.append([full_name, date, check_type, time, reason])
    
    conn.close()
    file_path = f"attendance_{selected_month}.xlsx"
    wb.save(file_path)
    return send_file(file_path, as_attachment=True)

@app.route('/add_employee', methods=['GET', 'POST'])
@login_required
def add_employee():
    if current_user.id != 1:
        return "Access denied"
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        full_name = request.form['full_name']
        phone = request.form['phone']
        email = request.form['email']
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (username, password, full_name, phone, email, role) VALUES (?, ?, ?, ?, ?, 'employee')",
                      (username, password, full_name, phone, email))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return "Tên đăng nhập đã tồn tại!"
        conn.close()
        return redirect(url_for('admin_employees'))
    return render_template('add_employee.html')

@app.route('/edit_employee/<int:user_id>', methods=['GET', 'POST'])
@login_required
def edit_employee(user_id):
    if current_user.id != 1:
        return "Access denied"
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    if request.method == 'POST':
        username = request.form['username']
        full_name = request.form['full_name']
        phone = request.form['phone']
        email = request.form['email']
        c.execute("UPDATE users SET username = ?, full_name = ?, phone = ?, email = ? WHERE id = ?",
                  (username, full_name, phone, email, user_id))
        conn.commit()
        conn.close()
        return redirect(url_for('admin_employees'))
    
    c.execute("SELECT username, full_name, phone, email FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    conn.close()
    return render_template('edit_employee.html', user=user, user_id=user_id)

@app.route('/delete_employee/<int:user_id>')
@login_required
def delete_employee(user_id):
    if current_user.id != 1:
        return "Access denied"
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id = ?", (user_id,))
    c.execute("DELETE FROM time_records WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_employees'))

if __name__ == '__main__':
    app.run(debug=True)