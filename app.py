from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import sqlite3
import os
from datetime import datetime, timedelta
from calendar import monthrange
from openpyxl import Workbook
import base64
from io import BytesIO
from PIL import Image
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Tạo thư mục nếu chưa tồn tại
for folder in ['static/photos', 'static/reports', 'static/leave_attachments']:
    if not os.path.exists(folder):
        os.makedirs(folder)

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
    c.execute('''CREATE TABLE IF NOT EXISTS leave_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        request_date TEXT,
        leave_date TEXT,
        leave_type TEXT,
        reason TEXT,
        attachment_path TEXT DEFAULT '',  -- Thêm cột đính kèm
        status TEXT DEFAULT 'Chờ duyệt',
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS work_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        report_date TEXT,
        content TEXT,
        attachment_path TEXT,
        status TEXT DEFAULT 'Chưa xem',  -- Thêm trạng thái báo cáo
        feedback TEXT DEFAULT '',  -- Thêm phản hồi từ admin
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        message TEXT,
        created_at TEXT,
        is_read INTEGER DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    c.execute("INSERT OR IGNORE INTO users (username, password, role, email) VALUES (?, ?, ?, ?)", 
              ('admin', 'admin123', 'admin', 'admin@example.com'))
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

def send_email(to_email, subject, body):
    from_email = "2002.tihy@gmail.com"
    password = "hcts yipw kngs ptgj"
    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(from_email, password)
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print(f"Error sending email: {e}")

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
        return render_template('login.html', error="Sai tài khoản hoặc mật khẩu!")
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
    
    # Xử lý lọc
    filter_type = request.form.get('filter_type', 'week')
    selected_month = request.form.get('selected_month', datetime.now().strftime('%Y-%m'))
    
    if filter_type == 'week':
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        query = "SELECT timestamp, type, photo_path, reason FROM time_records WHERE user_id = ? AND timestamp >= ? ORDER BY timestamp DESC"
        c.execute(query, (current_user.id, f'{start_date} 00:00:00'))
    else:
        query = "SELECT timestamp, type, photo_path, reason FROM time_records WHERE user_id = ? AND timestamp LIKE ? ORDER BY timestamp DESC"
        c.execute(query, (current_user.id, f'{selected_month}%'))
    records = c.fetchall()
    
    # Lấy thông báo
    c.execute("SELECT message, created_at, is_read FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 5", 
              (current_user.id,))
    notifications = c.fetchall()
    
    # Tổng hợp ngày công/ngày nghỉ
    c.execute("SELECT COUNT(DISTINCT SUBSTR(timestamp, 1, 10)) FROM time_records WHERE user_id = ? AND timestamp LIKE ?", 
              (current_user.id, f'{selected_month}%'))
    total_work_days = c.fetchone()[0] * 0.5  # Giả định mỗi lần chấm công = 0.5 ngày
    c.execute("SELECT COUNT(*) FROM leave_requests WHERE user_id = ? AND status = 'Đã duyệt' AND leave_date LIKE ?", 
              (current_user.id, f'{selected_month}%'))
    total_leave_days = c.fetchone()[0]
    
    # Lấy danh sách ngày nghỉ đã duyệt
    if filter_type == 'week':
        c.execute("SELECT leave_date, leave_type FROM leave_requests WHERE user_id = ? AND status = 'Đã duyệt' AND request_date >= ?", 
                  (current_user.id, f'{start_date} 00:00:00'))
    else:
        c.execute("SELECT leave_date, leave_type FROM leave_requests WHERE user_id = ? AND status = 'Đã duyệt' AND request_date LIKE ?", 
                  (current_user.id, f'{selected_month}%'))
    leave_records = c.fetchall()
    
    # Lấy danh sách báo cáo công việc
    if filter_type == 'week':
        c.execute("SELECT report_date, content, attachment_path, status FROM work_reports WHERE user_id = ? AND report_date >= ? ORDER BY report_date DESC LIMIT 7", 
                  (current_user.id, f'{start_date} 00:00:00'))
    else:
        c.execute("SELECT report_date, content, attachment_path, status FROM work_reports WHERE user_id = ? AND report_date LIKE ? ORDER BY report_date DESC LIMIT 7", 
                  (current_user.id, f'{selected_month}%'))
    reports = c.fetchall()
    
    # Lấy danh sách đơn xin nghỉ
    if filter_type == 'week':
        c.execute("SELECT request_date, leave_date, leave_type, reason, status, attachment_path FROM leave_requests WHERE user_id = ? AND request_date >= ? ORDER BY request_date DESC LIMIT 7", 
                  (current_user.id, f'{start_date} 00:00:00'))
    else:
        c.execute("SELECT request_date, leave_date, leave_type, reason, status, attachment_path FROM leave_requests WHERE user_id = ? AND request_date LIKE ? ORDER BY request_date DESC LIMIT 7", 
                  (current_user.id, f'{selected_month}%'))
    leave_requests = c.fetchall()
    
    conn.close()

    # Xử lý dữ liệu chấm công
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
                'in_morning': {'time': '', 'photo': ''},
                'out_morning': {'time': '', 'photo': ''},
                'in_afternoon': {'time': '', 'photo': ''},
                'out_afternoon': {'time': '', 'photo': ''},
                'reason': reason,
                'work_days': 0.0
            }
        daily_records[date][record_type] = {'time': time_str, 'photo': photo_path}
    
    # Tính công và thêm ngày nghỉ
    for date, data in daily_records.items():
        morning_complete = data['in_morning']['time'] and data['out_morning']['time']
        afternoon_complete = data['in_afternoon']['time'] and data['out_afternoon']['time']
        if morning_complete and afternoon_complete:
            data['work_days'] = 1.0
        elif morning_complete or afternoon_complete:
            data['work_days'] = 0.5
    
    for leave_date, leave_type in leave_records:
        if leave_date not in daily_records:
            daily_records[leave_date] = {
                'in_morning': {'time': '', 'photo': ''},
                'out_morning': {'time': '', 'photo': ''},
                'in_afternoon': {'time': '', 'photo': ''},
                'out_afternoon': {'time': '', 'photo': ''},
                'reason': 'Nghỉ',
                'work_days': 0.0
            }
        if leave_type == 'Cả ngày':
            daily_records[leave_date]['reason'] = 'Nghỉ cả ngày'
        elif leave_type == 'Sáng':
            daily_records[leave_date]['reason'] = 'Nghỉ sáng'
        elif leave_type == 'Chiều':
            daily_records[leave_date]['reason'] = 'Nghỉ chiều'

    return render_template('employee_dashboard.html', 
                           daily_records=daily_records, 
                           filter_type=filter_type, 
                           selected_month=selected_month,
                           reports=reports,
                           leave_requests=leave_requests,
                           notifications=notifications,
                           total_work_days=total_work_days,
                           total_leave_days=total_leave_days)

@app.route('/checkin', methods=['GET', 'POST'])
@login_required
def checkin():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    
    c.execute("SELECT type FROM time_records WHERE user_id = ? AND timestamp LIKE ?", 
              (current_user.id, f'{today}%'))
    records = [r[0] for r in c.fetchall()]
    
    current_hour = datetime.now().hour
    is_morning = current_hour < 12
    check_type = None
    status_message = ""
    
    if is_morning:
        if 'in_morning' not in records:
            check_type = 'in_morning'
            status_message = "Bạn đang chấm công vào sáng."
        elif 'out_morning' not in records:
            check_type = 'out_morning'
            status_message = "Bạn đang chấm công ra sáng."
        else:
            status_message = "Bạn đã chấm công đầy đủ buổi sáng."
    else:
        if 'in_afternoon' not in records:
            check_type = 'in_afternoon'
            status_message = "Bạn đang chấm công vào chiều."
        elif 'out_afternoon' not in records:
            check_type = 'out_afternoon'
            status_message = "Bạn đang chấm công ra chiều."
        else:
            status_message = "Bạn đã chấm công đầy đủ buổi chiều."

    if 'in_morning' in records and 'out_morning' in records and 'in_afternoon' in records and 'out_afternoon' in records:
        status_message = "Bạn đã chấm công đầy đủ hôm nay."

    if request.method == 'POST' and check_type:
        photo_data = request.form['photo']
        reason = request.form.get('reason', '')
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        photo_path = None
        
        if photo_data:
            try:
                img_data = base64.b64decode(photo_data.split(',')[1])
                photo_path = f'static/photos/{current_user.id}_{timestamp.replace(":", "-")}.jpg'
                with open(photo_path, 'wb') as f:
                    f.write(img_data)
            except Exception as e:
                print(f"Error saving photo: {e}")
                photo_path = None

        c.execute("INSERT INTO time_records (user_id, timestamp, type, photo_path, reason) VALUES (?, ?, ?, ?, ?)",
                  (current_user.id, timestamp, check_type, photo_path, reason))
        conn.commit()
        conn.close()
        return redirect(url_for('employee_dashboard'))
    
    conn.close()
    return render_template('checkin.html', check_type=check_type, status_message=status_message)

@app.route('/leave_request', methods=['GET', 'POST'])
@login_required
def leave_request():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    if request.method == 'POST':
        leave_date = request.form['leave_date']
        leave_type = request.form['leave_type']
        reason = request.form['reason']
        attachment = request.files.get('attachment')
        request_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        attachment_path = ''
        
        if attachment:
            attachment_path = f'static/leave_attachments/{current_user.id}_{request_date.replace(":", "-")}_{attachment.filename}'
            attachment.save(attachment_path)
        
        c.execute("INSERT INTO leave_requests (user_id, request_date, leave_date, leave_type, reason, attachment_path) VALUES (?, ?, ?, ?, ?, ?)",
                  (current_user.id, request_date, leave_date, leave_type, reason, attachment_path))
        conn.commit()
        
        c.execute("SELECT full_name, email FROM users WHERE id = ?", (current_user.id,))
        full_name, emp_email = c.fetchone()
        
        c.execute("SELECT email FROM users WHERE role = 'admin'")
        admin_email = c.fetchone()[0]
        send_email(admin_email, "Thông báo: Đơn xin nghỉ mới", 
                   f"{full_name} đã gửi đơn xin nghỉ ngày {leave_date} ({leave_type}). Lý do: {reason}")
        
        c.execute("INSERT INTO notifications (user_id, message, created_at) VALUES (?, ?, ?)",
                  (current_user.id, f"Đã gửi đơn xin nghỉ ngày {leave_date}", request_date))
        conn.commit()
        conn.close()
        return redirect(url_for('employee_dashboard'))
    
    c.execute("SELECT request_date, leave_date, leave_type, reason, status, attachment_path FROM leave_requests WHERE user_id = ?", 
              (current_user.id,))
    requests = c.fetchall()
    conn.close()
    return render_template('leave_request.html', requests=requests)

@app.route('/work_report', methods=['GET', 'POST'])
@login_required
def work_report():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    if request.method == 'POST':
        content = request.form['content']
        attachment = request.files.get('attachment')
        report_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        attachment_path = ''
        
        if attachment:
            attachment_path = f'static/reports/{current_user.id}_{report_date.replace(":", "-")}_{attachment.filename}'
            attachment.save(attachment_path)
        
        c.execute("INSERT INTO work_reports (user_id, report_date, content, attachment_path) VALUES (?, ?, ?, ?)",
                  (current_user.id, report_date, content, attachment_path))
        conn.commit()
        
        c.execute("SELECT full_name FROM users WHERE id = ?", (current_user.id,))
        full_name = c.fetchone()[0]
        
        c.execute("SELECT email FROM users WHERE role = 'admin'")
        admin_email = c.fetchone()[0]
        send_email(admin_email, "Thông báo: Báo cáo công việc mới", 
                   f"{full_name} đã gửi báo cáo ngày {report_date}. Nội dung: {content}")
        
        conn.close()
        return redirect(url_for('employee_dashboard'))
    
    c.execute("SELECT report_date, content, attachment_path, status, feedback FROM work_reports WHERE user_id = ?", 
              (current_user.id,))
    reports = c.fetchall()
    conn.close()
    return render_template('work_report.html', reports=reports)

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
                'in_morning': '', 'out_morning': '', 'in_afternoon': '', 'out_afternoon': '', 'photo': '', 'reason': ''
            }
        
        daily_records[username]['days'][date][record_type] = time_str
        daily_records[username]['days'][date]['photo'] = photo_path
        daily_records[username]['days'][date]['reason'] = reason
    
    conn.close()
    return render_template('admin_dashboard.html', daily_records=daily_records)

@app.route('/admin/employees', methods=['GET', 'POST'])
@login_required
def admin_employees():
    if current_user.id != 1:
        return "Access denied"
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # Đổi mật khẩu
    if request.method == 'POST' and 'change_password' in request.form:
        user_id = request.form['user_id']
        new_password = request.form['new_password']
        c.execute("UPDATE users SET password = ? WHERE id = ?", (new_password, user_id))
        conn.commit()
        flash(f"Đã đổi mật khẩu cho nhân viên ID {user_id}.", "success")
    
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
    c.execute("SELECT u.id, u.full_name, t.timestamp, t.type, t.photo_path, t.reason FROM users u LEFT JOIN time_records t ON u.id = t.user_id WHERE t.timestamp LIKE ? AND u.role = 'employee'",
              (f'{selected_month}%',))
    records = c.fetchall()
    
    c.execute("SELECT id, full_name FROM users WHERE role = 'employee'")
    employees = c.fetchall()
    employee_dict = {emp[0]: emp[1] for emp in employees}
    
    year, month = map(int, selected_month.split('-'))
    _, days_in_month = monthrange(year, month)
    days_in_month = [datetime(year, month, day).strftime('%Y-%m-%d') for day in range(1, days_in_month + 1)]
    
    c.execute("SELECT user_id, leave_date, leave_type FROM leave_requests WHERE status = 'Đã duyệt' AND leave_date LIKE ?",
              (f'{selected_month}%',))
    leave_records = c.fetchall()
    
    attendance_data = {emp_id: {'days': {}, 'total': 0.0} for emp_id in employee_dict}
    for record in records:
        emp_id = record[0]
        timestamp = record[2]
        if not timestamp:
            continue
        date = timestamp.split(' ')[0]
        time_str = timestamp.split(' ')[1]
        record_type = record[3]
        photo_path = record[4]
        reason = record[5] or ''
        
        if date not in attendance_data[emp_id]['days']:
            attendance_data[emp_id]['days'][date] = {
                'in_morning': '', 'out_morning': '', 'in_afternoon': '', 'out_afternoon': '', 'photo': '', 'reason': ''
            }
        attendance_data[emp_id]['days'][date][record_type] = time_str
        attendance_data[emp_id]['days'][date]['photo'] = photo_path
        attendance_data[emp_id]['days'][date]['reason'] = reason
    
    for emp_id, data in attendance_data.items():
        for date, day_data in data['days'].items():
            morning_complete = day_data['in_morning'] and day_data['out_morning']
            afternoon_complete = day_data['in_afternoon'] and day_data['out_afternoon']
            if morning_complete and afternoon_complete:
                attendance_data[emp_id]['total'] += 1.0
            elif morning_complete or afternoon_complete:
                attendance_data[emp_id]['total'] += 0.5
    
    for emp_id, leave_date, leave_type in leave_records:
        if emp_id not in attendance_data:
            attendance_data[emp_id] = {'days': {}, 'total': 0.0}
        if leave_date not in attendance_data[emp_id]['days']:
            attendance_data[emp_id]['days'][leave_date] = {
                'in_morning': '', 'out_morning': '', 'in_afternoon': '', 'out_afternoon': '', 'photo': '', 'reason': ''
            }
        if leave_type == 'Cả ngày':
            attendance_data[emp_id]['days'][leave_date]['reason'] = 'Nghỉ cả ngày'
        elif leave_type == 'Sáng':
            attendance_data[emp_id]['days'][leave_date]['reason'] = 'Nghỉ sáng'
        elif leave_type == 'Chiều':
            attendance_data[emp_id]['days'][leave_date]['reason'] = 'Nghỉ chiều'
    
    conn.close()
    return render_template('admin_attendance.html', attendance_data=attendance_data, employee_dict=employee_dict, days_in_month=days_in_month, selected_month=selected_month)

@app.route('/admin/reports', methods=['GET', 'POST'])
@login_required
def admin_reports():
    if current_user.id != 1:
        return "Access denied"
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    if request.method == 'POST':
        report_id = request.form['report_id']
        feedback = request.form['feedback']
        c.execute("UPDATE work_reports SET status = 'Đã xem', feedback = ? WHERE id = ?", (feedback, report_id))
        conn.commit()
        
        c.execute("SELECT u.email, w.report_date, w.content FROM work_reports w JOIN users u ON w.user_id = u.id WHERE w.id = ?", 
                  (report_id,))
        emp_email, report_date, content = c.fetchone()
        send_email(emp_email, f"Phản hồi báo cáo ngày {report_date}", 
                   f"Báo cáo của bạn ngày {report_date} đã được xem. Phản hồi: {feedback}")
        
        c.execute("INSERT INTO notifications (user_id, message, created_at) VALUES ((SELECT user_id FROM work_reports WHERE id = ?), ?, ?)",
                  (report_id, f"Báo cáo ngày {report_date} đã được xem: {feedback}", datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
    
    c.execute("SELECT w.id, u.full_name, w.report_date, w.content, w.attachment_path, w.status, w.feedback FROM work_reports w JOIN users u ON w.user_id = u.id")
    reports = c.fetchall()
    conn.close()
    return render_template('admin_reports.html', reports=reports)

@app.route('/admin/leave_requests', methods=['GET', 'POST'])
@login_required
def admin_leave_requests():
    if current_user.id != 1:
        return "Access denied"
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    if request.method == 'POST':
        request_id = request.form['request_id']
        action = request.form['action']
        status = 'Đã duyệt' if action == 'approve' else 'Bị từ chối'
        
        c.execute("UPDATE leave_requests SET status = ? WHERE id = ?", (status, request_id))
        conn.commit()
        
        c.execute("SELECT u.email, l.leave_date, l.leave_type, l.reason FROM leave_requests l JOIN users u ON l.user_id = u.id WHERE l.id = ?", 
                  (request_id,))
        emp_email, leave_date, leave_type, reason = c.fetchone()
        send_email(emp_email, f"Thông báo: Đơn xin nghỉ ngày {leave_date}", 
                   f"Đơn xin nghỉ của bạn ngày {leave_date} ({leave_type}) đã {status.lower()}. Lý do: {reason}")
        
        c.execute("INSERT INTO notifications (user_id, message, created_at) VALUES ((SELECT user_id FROM leave_requests WHERE id = ?), ?, ?)",
                  (request_id, f"Đơn xin nghỉ ngày {leave_date} đã {status.lower()}", datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
    
    c.execute("SELECT l.id, u.full_name, l.request_date, l.leave_date, l.leave_type, l.reason, l.status, l.attachment_path FROM leave_requests l JOIN users u ON l.user_id = u.id")
    requests = c.fetchall()
    conn.close()
    return render_template('admin_leave_requests.html', requests=requests)

@app.route('/admin/edit_attendance', methods=['GET', 'POST'])
@login_required
def admin_edit_attendance():
    if current_user.id != 1:
        return "Access denied"
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    c.execute("SELECT id, full_name FROM users WHERE role = 'employee'")
    employees = c.fetchall()
    
    if request.method == 'POST':
        user_id = request.form['user_id']
        date = request.form['date']
        check_type = request.form['check_type']
        time = request.form['time']
        photo = request.files.get('photo')
        reason = request.form.get('reason', '')
        
        timestamp = f"{date} {time}"
        photo_path = ''
        if photo:
            photo_path = f'static/photos/{user_id}_{timestamp.replace(":", "-")}_{photo.filename}'
            photo.save(photo_path)
        
        c.execute("INSERT OR REPLACE INTO time_records (user_id, timestamp, type, photo_path, reason) VALUES (?, ?, ?, ?, ?)",
                  (user_id, timestamp, check_type, photo_path, reason))
        conn.commit()
        conn.close()
        return redirect(url_for('admin_attendance'))
    
    c.execute("SELECT u.full_name, t.timestamp, t.type, t.photo_path, t.reason FROM users u JOIN time_records t ON u.id = t.user_id")
    records = c.fetchall()
    conn.close()
    return render_template('admin_edit_attendance.html', employees=employees, records=records)

@app.route('/admin/data_management', methods=['GET', 'POST'])
@login_required
def data_management():
    if current_user.id != 1:
        return "Access denied"
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # Kiểm tra dung lượng dữ liệu
    c.execute("SELECT COUNT(*) FROM time_records")
    total_records = c.fetchone()[0]
    max_records = 100000  # Giới hạn tối đa (có thể cấu hình)
    storage_status = f"{total_records}/{max_records} bản ghi ({(total_records/max_records)*100:.1f}%)"
    
    # Xóa dữ liệu cũ tự động nếu đầy
    if total_records >= max_records * 0.9:
        c.execute("DELETE FROM time_records WHERE timestamp < ?", 
                  (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d %H:%M:%S'),)
        conn.commit()
        flash("Đã xóa dữ liệu cũ hơn 1 năm để giải phóng dung lượng.", "success")
    
    # Xóa nhiều bản ghi bằng tích chọn
    if request.method == 'POST':
        selected_ids = request.form.getlist('selected_records')
        if selected_ids:
            c.execute("DELETE FROM time_records WHERE id IN ({})".format(','.join('?' * len(selected_ids))), 
                      selected_ids)
            conn.commit()
            flash(f"Đã xóa {len(selected_ids)} bản ghi.", "success")
        return redirect(url_for('data_management'))
    
    c.execute("SELECT id, user_id, timestamp, type, photo_path FROM time_records ORDER BY timestamp DESC")
    records = c.fetchall()
    conn.close()
    return render_template('admin_data_management.html', records=records, storage_status=storage_status)

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
    c.execute("DELETE FROM leave_requests WHERE user_id = ?", (user_id,))
    c.execute("DELETE FROM work_reports WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_employees'))

if __name__ == '__main__':
    app.run(debug=True)