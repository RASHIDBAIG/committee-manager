from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3, os
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = 'committee-secret-2026-change-me'
DB_PATH = os.path.join(os.path.dirname(__file__), 'committee.db')
ADMIN_PASSWORD = "admin123"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS members (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, phone TEXT UNIQUE, cnic TEXT, address TEXT, address_type TEXT, guarantor_name TEXT, guarantor_phone TEXT, verified INTEGER DEFAULT 0, trust_score INTEGER DEFAULT 50, created_at TEXT);
        CREATE TABLE IF NOT EXISTS committees (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, monthly_amount INTEGER, total_months INTEGER, start_date TEXT, status TEXT DEFAULT 'active', created_at TEXT);
        CREATE TABLE IF NOT EXISTS committee_members (id INTEGER PRIMARY KEY AUTOINCREMENT, committee_id INTEGER, member_id INTEGER, payout_month INTEGER);
        CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY AUTOINCREMENT, committee_id INTEGER, member_id INTEGER, month_number INTEGER, amount INTEGER, status TEXT DEFAULT 'pending', transaction_id TEXT, paid_at TEXT);
    """)
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
        if request.form['password'] == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect(url_for('index'))
        flash('Ghalat password!', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    conn = get_db()
    members = conn.execute('SELECT COUNT(*) c FROM members').fetchone()['c']
    committees = conn.execute("SELECT COUNT(*) c FROM committees WHERE status='active'").fetchone()['c']
    pending = conn.execute("SELECT COUNT(*) c FROM payments WHERE status='pending'").fetchone()['c']
    conn.close()
    return render_template('index.html', members=members, committees=committees, pending=pending)

@app.route('/members')
@login_required
def members():
    conn = get_db()
    rows = conn.execute('SELECT * FROM members ORDER BY id DESC').fetchall()
    conn.close()
    return render_template('members.html', members=rows)

@app.route('/members/add', methods=['GET', 'POST'])
@login_required
def add_member():
    if request.method == 'POST':
        d = request.form
        conn = get_db()
        try:
            conn.execute("INSERT INTO members (name, phone, cnic, address, address_type, guarantor_name, guarantor_phone, verified, created_at) VALUES (?,?,?,?,?,?,?,?,?)", (d['name'], d['phone'], d['cnic'], d['address'], d['address_type'], d['guarantor_name'], d['guarantor_phone'], int(d.get('verified', 0)), datetime.now().isoformat()))
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
    all_members = conn.execute('SELECT * FROM members').fetchall()
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

# ==========================================
# MEMBER ROUTES (MOBILE APP)
# ==========================================
@app.route('/member_login', methods=['GET', 'POST'])
def member_login():
    if request.method == 'POST':
        phone = request.form['phone']
        conn = get_db()
        member = conn.execute('SELECT * FROM members WHERE phone = ?', (phone,)).fetchone()
        conn.close()
        if member:
            session['member_id'] = member['id']
            session['member_name'] = member['name']
            return redirect(url_for('member_dashboard'))
        flash('Phone number record mein nahi hai.', 'error')
    return render_template('member_login.html')

@app.route('/member_logout')
def member_logout():
    session.pop('member_id', None); session.pop('member_name', None)
    return redirect(url_for('member_login'))

@app.route('/member_dashboard')
def member_dashboard():
    if 'member_id' not in session: return redirect(url_for('member_login'))
    conn = get_db(); mid = session['member_id']
    committees = conn.execute("SELECT c.name, c.monthly_amount, c.total_months, c.start_date, cm.payout_month FROM committees c JOIN committee_members cm ON c.id = cm.committee_id WHERE cm.member_id = ?", (mid,)).fetchall()
    payments = conn.execute("SELECT p.month_number, p.amount, p.status, c.name as committee_name FROM payments p JOIN committees c ON p.committee_id = c.id WHERE p.member_id = ? ORDER BY p.id DESC", (mid,)).fetchall()
    conn.close()
    return render_template('member_dashboard.html', name=session['member_name'], committees=committees, payments=payments)

if __name__ == '__main__':
    init_db()
    print("\n=====================================")
    print("  App Mobile aur Laptop dono par chal rahi hai!")
    print("  Laptop: http://127.0.0.1:5000")
    print("  Mobile: Laptop ka IP daalein (e.g. 192.168.1.5:5000)")
    print("  Admin Password: admin123")
    print("=====================================\n")
    app.run(debug=True, host='0.0.0.0', port=5000)