from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
import sqlite3, os, uuid
from datetime import datetime
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'committee-secret-2026-change-me'
DB_PATH = os.path.join(os.path.dirname(__file__), 'committee.db')
SECURE_UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'secure_uploads')
if not os.path.exists(SECURE_UPLOAD_FOLDER): os.makedirs(SECURE_UPLOAD_FOLDER)

ADMIN_USERNAME = "admin"     
ADMIN_PASSWORD = "admin123"  

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS members (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, phone TEXT UNIQUE, password TEXT, plain_password TEXT, cnic TEXT, address TEXT, address_type TEXT, guarantor_name TEXT, guarantor_phone TEXT, verified INTEGER DEFAULT 0, trust_score INTEGER DEFAULT 50, status TEXT DEFAULT 'approved', preferred_amount INTEGER, created_at TEXT, cnic_front TEXT, cnic_back TEXT, selfie TEXT, profession TEXT, monthly_income TEXT, referred_by TEXT);
        CREATE TABLE IF NOT EXISTS committees (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, monthly_amount INTEGER, total_months INTEGER, start_date TEXT, status TEXT DEFAULT 'active', created_at TEXT);
        CREATE TABLE IF NOT EXISTS committee_members (id INTEGER PRIMARY KEY AUTOINCREMENT, committee_id INTEGER, member_id INTEGER, payout_month INTEGER);
        CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY AUTOINCREMENT, committee_id INTEGER, member_id INTEGER, month_number INTEGER, amount INTEGER, status TEXT DEFAULT 'pending', transaction_id TEXT, paid_at TEXT);
        CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, member_id INTEGER, message TEXT, created_at TEXT, is_read INTEGER DEFAULT 0);
    """)
    for col, dtype in [("status", "TEXT DEFAULT 'approved'"), ("preferred_amount", "INTEGER"), ("cnic_front", "TEXT"), ("cnic_back", "TEXT"), ("selfie", "TEXT"), ("profession", "TEXT"), ("monthly_income", "TEXT"), ("referred_by", "TEXT"), ("password", "TEXT"), ("plain_password", "TEXT")]:
        try: conn.execute(f"ALTER TABLE members ADD COLUMN {col} {dtype}")
        except sqlite3.OperationalError: pass
    conn.commit(); conn.close()

def login_required(f):
    @wraps(f)
    def deco(*a, **kw):
        if not session.get('admin'): return redirect(url_for('login'))
        return f(*a, **kw)
    return deco

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect(url_for('index'))
        flash('Ghalat Username ya Password!', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect(url_for('login'))

@app.route('/admin/view_image/<filename>')
@login_required
def view_image(filename):
    return send_from_directory(SECURE_UPLOAD_FOLDER, filename)

@app.route('/')
@login_required
def index():
    conn = get_db()
    members = conn.execute("SELECT COUNT(*) c FROM members WHERE status='approved'").fetchone()['c']
    pending_req = conn.execute("SELECT COUNT(*) c FROM members WHERE status='pending'").fetchone()['c']
    committees = conn.execute("SELECT COUNT(*) c FROM committees WHERE status='active'").fetchone()['c']
    pending_pay = conn.execute("SELECT COUNT(*) c FROM payments WHERE status='pending'").fetchone()['c']
    conn.close()
    return render_template('index.html', members=members, committees=committees, pending=pending_pay, pending_req=pending_req)

@app.route('/members')
@login_required
def members():
    conn = get_db()
    approved_members = conn.execute("SELECT * FROM members WHERE status='approved' ORDER BY id DESC").fetchall()
    pending_members = conn.execute("SELECT * FROM members WHERE status='pending' ORDER BY id DESC").fetchall()
    conn.close()
    return render_template('members.html', members=approved_members, pending_members=pending_members)

@app.route('/deleted_members')
@login_required
def deleted_members():
    conn = get_db()
    deleted = conn.execute("SELECT * FROM members WHERE status='deleted' ORDER BY id DESC").fetchall()
    conn.close()
    return render_template('deleted_members.html', deleted_members=deleted)

@app.route('/members/delete/<int:mid>')
@login_required
def delete_member_soft(mid):
    conn = get_db()
    conn.execute("UPDATE members SET status='deleted' WHERE id=?", (mid,))
    conn.commit(); conn.close()
    flash('Member Deleted List mein chala gaya hai.', 'success')
    return redirect(url_for('members'))

@app.route('/members/restore/<int:mid>')
@login_required
def restore_member(mid):
    conn = get_db()
    conn.execute("UPDATE members SET status='approved' WHERE id=?", (mid,))
    conn.commit(); conn.close()
    flash('Member wapas restore ho gaya!', 'success')
    return redirect(url_for('deleted_members'))

@app.route('/members/hard_delete/<int:mid>')
@login_required
def hard_delete_member(mid):
    conn = get_db()
    member = conn.execute("SELECT * FROM members WHERE id=?", (mid,)).fetchone()
    if member:
        for img in [member['cnic_front'], member['cnic_back'], member['selfie']]:
            if img:
                filepath = os.path.join(SECURE_UPLOAD_FOLDER, img)
                if os.path.exists(filepath): os.remove(filepath)
        conn.execute("DELETE FROM members WHERE id=?", (mid,))
        conn.commit()
        flash('Member aur uski tasveerein hamesha ke liye delete ho gayin.', 'success')
    conn.close()
    return redirect(url_for('deleted_members'))

@app.route('/members/approve/<int:mid>')
@login_required
def approve_member(mid):
    conn = get_db()
    conn.execute("UPDATE members SET status='approved' WHERE id=?", (mid,))
    conn.commit(); conn.close()
    flash('Member kamyabi se approve ho gaya!', 'success')
    return redirect(url_for('members'))

@app.route('/members/reject/<int:mid>')
@login_required
def reject_member(mid):
    return hard_delete_member(mid)

@app.route('/members/reset_password/<int:mid>', methods=['POST'])
@login_required
def admin_reset_password(mid):
    new_pw = request.form['new_password']
    conn = get_db()
    hashed_pw = generate_password_hash(new_pw)
    conn.execute("UPDATE members SET password=?, plain_password=? WHERE id=?", (hashed_pw, new_pw, mid))
    conn.commit(); conn.close()
    flash('Member ka password kamyabi se reset ho gaya!', 'success')
    return redirect(url_for('members'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        d = request.form
        conn = get_db()
        try:
            cnic_front = request.files.get('cnic_front')
            cnic_back = request.files.get('cnic_back')
            selfie = request.files.get('selfie')
            front_name, back_name, selfie_name = None, None, None

            if cnic_front and cnic_front.filename != '':
                ext = os.path.splitext(cnic_front.filename)[1]
                front_name = f"cnic_front_{uuid.uuid4().hex}{ext}"
                cnic_front.save(os.path.join(SECURE_UPLOAD_FOLDER, front_name))

            if cnic_back and cnic_back.filename != '':
                ext = os.path.splitext(cnic_back.filename)[1]
                back_name = f"cnic_back_{uuid.uuid4().hex}{ext}"
                cnic_back.save(os.path.join(SECURE_UPLOAD_FOLDER, back_name))
            
            if selfie and selfie.filename != '':
                ext = os.path.splitext(selfie.filename)[1]
                selfie_name = f"selfie_{uuid.uuid4().hex}{ext}"
                selfie.save(os.path.join(SECURE_UPLOAD_FOLDER, selfie_name))

            hashed_pw = generate_password_hash(d['password'])
            
            conn.execute("INSERT INTO members (name, phone, password, plain_password, cnic, address, preferred_amount, status, created_at, cnic_front, cnic_back, selfie, profession, monthly_income, referred_by) VALUES (?,?,?,?,?,?,?,'pending',?,?,?,?,?,?,?)", 
                (d['name'], d['phone'], hashed_pw, d['password'], d['cnic'], d['address'], d['preferred_amount'], datetime.now().isoformat(), front_name, back_name, selfie_name, d.get('profession'), d.get('monthly_income'), d.get('referred_by')))
            conn.commit()
            flash('Aap ki request bhej di gayi hai! Admin verify karne ke baad aap login kar sakenge.', 'success')
            return redirect(url_for('member_login'))
        except sqlite3.IntegrityError:
            flash('Yeh phone number pehle se registered hai.', 'error')
        conn.close()
    return render_template('register.html')

@app.route('/members/add', methods=['GET', 'POST'])
@login_required
def add_member():
    if request.method == 'POST':
        d = request.form
        conn = get_db()
        try:
            hashed_pw = generate_password_hash(d['password'])
            conn.execute("INSERT INTO members (name, phone, password, plain_password, cnic, address, address_type, guarantor_name, guarantor_phone, verified, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,'approved',?)", (d['name'], d['phone'], hashed_pw, d['password'], d['cnic'], d['address'], d['address_type'], d['guarantor_name'], d['guarantor_phone'], int(d.get('verified', 0)), datetime.now().isoformat()))
            conn.commit(); flash('Member add ho gaya!', 'success')
        except sqlite3.IntegrityError: flash('Yeh phone number pehle se maujood hai.', 'error')
        conn.close()
        return redirect(url_for('members'))
    return render_template('add_member.html')

@app.route('/members/<int:mid>/verify')
@login_required
def verify_member(mid):
    conn = get_db()
    conn.execute('UPDATE members SET verified=1, trust_score=trust_score+20 WHERE id=?', (mid,))
    conn.commit(); conn.close()
    return redirect(url_for('members'))

@app.route('/send_message', methods=['POST'])
@login_required
def send_message():
    member_id = request.form.get('member_id')
    msg_text = request.form['message']
    conn = get_db()
    conn.execute("INSERT INTO messages (member_id, message, created_at) VALUES (?,?,?)", (member_id, msg_text, datetime.now().isoformat()))
    conn.commit(); conn.close()
    flash('Message kamyabi se bhej diya gaya!', 'success')
    return redirect(request.referrer)

@app.route('/committees')
@login_required
def committees():
    conn = get_db()
    rows = conn.execute('SELECT * FROM committees ORDER BY id DESC').fetchall()
    conn.close()
    return render_template('committees.html', committees=rows)

@app.route('/committees/create', methods=['GET', 'POST'])
@login_required
def create_committee():
    if request.method == 'POST':
        d = request.form
        conn = get_db()
        cur = conn.execute("INSERT INTO committees (name, monthly_amount, total_months, start_date, created_at) VALUES (?,?,?,?,?)", (d['name'], int(d['monthly_amount']), int(d['total_months']), d['start_date'], datetime.now().isoformat()))
        conn.commit(); conn.close()
        return redirect(url_for('committee_detail', cid=cur.lastrowid))
    return render_template('create_committee.html')

@app.route('/committees/<int:cid>')
@login_required
def committee_detail(cid):
    conn = get_db()
    committee = conn.execute('SELECT * FROM committees WHERE id=?', (cid,)).fetchone()
    members_in = conn.execute("SELECT cm.*, m.name, m.phone, m.verified, m.trust_score FROM committee_members cm JOIN members m ON cm.member_id=m.id WHERE cm.committee_id=? ORDER BY cm.payout_month", (cid,)).fetchall()
    all_members = conn.execute("SELECT * FROM members WHERE status='approved'").fetchall()
    payments = conn.execute("SELECT p.*, m.name FROM payments p JOIN members m ON p.member_id=m.id WHERE p.committee_id=? ORDER BY p.month_number, p.id", (cid,)).fetchall()
    conn.close()
    return render_template('committee_detail.html', committee=committee, members_in=members_in, all_members=all_members, payments=payments)

@app.route('/committees/<int:cid>/add-member', methods=['POST'])
@login_required
def add_to_committee(cid):
    mid = int(request.form['member_id']); pm = int(request.form['payout_month'])
    conn = get_db()
    if not conn.execute('SELECT id FROM committee_members WHERE committee_id=? AND payout_month=?', (cid, pm)).fetchone():
        conn.execute('INSERT INTO committee_members (committee_id, member_id, payout_month) VALUES (?,?,?)', (cid, mid, pm))
        conn.commit()
    conn.close()
    return redirect(url_for('committee_detail', cid=cid))

@app.route('/committees/<int:cid>/remove-member/<int:cmid>')
@login_required
def remove_from_committee(cid, cmid):
    conn = get_db(); conn.execute('DELETE FROM committee_members WHERE id=?', (cmid,)); conn.commit(); conn.close()
    return redirect(url_for('committee_detail', cid=cid))

@app.route('/committees/<int:cid>/add-payment', methods=['POST'])
@login_required
def add_payment(cid):
    d = request.form
    conn = get_db()
    conn.execute("INSERT INTO payments (committee_id, member_id, month_number, amount, status, transaction_id, paid_at) VALUES (?,?,?,?,?,?,?)", (cid, int(d['member_id']), int(d['month_number']), int(d['amount']), d['status'], d.get('transaction_id', ''), datetime.now().isoformat() if d['status']=='paid' else None))
    conn.commit(); conn.close()
    return redirect(url_for('committee_detail', cid=cid))

@app.route('/payments/<int:pid>/mark-paid')
@login_required
def mark_paid(pid):
    conn = get_db(); conn.execute("UPDATE payments SET status='paid', paid_at=? WHERE id=?", (datetime.now().isoformat(), pid)); conn.commit(); conn.close()
    return redirect(request.referrer or url_for('index'))

@app.route('/committees/<int:cid>/delete')
@login_required
def delete_committee(cid):
    conn = get_db(); conn.execute('DELETE FROM payments WHERE committee_id=?', (cid,)); conn.execute('DELETE FROM committee_members WHERE committee_id=?', (cid,)); conn.execute('DELETE FROM committees WHERE id=?', (cid,)); conn.commit(); conn.close()
    return redirect(url_for('committees'))

@app.route('/member_login', methods=['GET', 'POST'])
def member_login():
    if request.method == 'POST':
        phone = request.form['phone']
        password = request.form['password']
        conn = get_db()
        member = conn.execute('SELECT * FROM members WHERE phone = ?', (phone,)).fetchone()
        conn.close()
        if member:
            if member['status'] == 'pending':
                flash('Aap ki request abhi pending hai. Admin approve karega phir aap login kar sakenge.', 'error')
                return render_template('member_login.html')
            if member['status'] == 'deleted':
                flash('Aap ka account delete kar diya gaya hai. Admin se rabta karein.', 'error')
                return render_template('member_login.html')
            
            stored_pw = member['password']
            if not stored_pw:
                stored_pw = generate_password_hash(member['phone'])
                
            if check_password_hash(stored_pw, password):
                session['member_id'] = member['id']
                session['member_name'] = member['name']
                return redirect(url_for('member_dashboard'))
            else:
                flash('Ghalat Password! Dobara koshish karein.', 'error')
        else:
            flash('Phone number record mein nahi hai.', 'error')
    return render_template('member_login.html')

@app.route('/member_logout')
def member_logout():
    session.pop('member_id', None); session.pop('member_name', None)
    return redirect(url_for('member_login'))

@app.route('/change_member_password', methods=['GET', 'POST'])
def change_member_password():
    if 'member_id' not in session:
        return redirect(url_for('member_login'))
    
    if request.method == 'POST':
        old_pw = request.form['old_password']
        new_pw = request.form['new_password']
        
        conn = get_db()
        member = conn.execute('SELECT * FROM members WHERE id = ?', (session['member_id'],)).fetchone()
        
        stored_pw = member['password']
        if not stored_pw:
            stored_pw = generate_password_hash(member['phone'])
            
        if check_password_hash(stored_pw, old_pw):
            new_hashed = generate_password_hash(new_pw)
            conn.execute('UPDATE members SET password=?, plain_password=? WHERE id=?', (new_hashed, new_pw, member['id']))
            conn.commit()
            conn.close()
            flash('Password kamyabi se change ho gaya!', 'success')
            return redirect(url_for('member_dashboard'))
        else:
            flash('Purana password ghalat hai.', 'error')
            conn.close()
            
    return render_template('change_password.html')

@app.route('/member_dashboard')
def member_dashboard():
    if 'member_id' not in session: return redirect(url_for('member_login'))
    conn = get_db(); mid = session['member_id']
    messages = conn.execute("SELECT * FROM messages WHERE member_id = ? OR member_id = 0 ORDER BY id DESC LIMIT 3", (mid,)).fetchall()
    committees = conn.execute("SELECT c.name, c.monthly_amount, c.total_months, c.start_date, cm.payout_month FROM committees c JOIN committee_members cm ON c.id = cm.committee_id WHERE cm.member_id = ?", (mid,)).fetchall()
    payments = conn.execute("SELECT p.month_number, p.amount, p.status, c.name as committee_name FROM payments p JOIN committees c ON p.committee_id = c.id WHERE p.member_id = ? ORDER BY p.id DESC", (mid,)).fetchall()
    conn.close()
    return render_template('member_dashboard.html', name=session['member_name'], messages=messages, committees=committees, payments=payments)

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)