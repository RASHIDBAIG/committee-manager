from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, Response
import sqlite3, os, uuid, csv, random
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
        CREATE TABLE IF NOT EXISTS members (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, phone TEXT UNIQUE, password TEXT, plain_password TEXT, cnic TEXT, address TEXT, address_type TEXT, guarantor_name TEXT, guarantor_phone TEXT, guarantor_cnic TEXT, verified INTEGER DEFAULT 0, trust_score INTEGER DEFAULT 50, status TEXT DEFAULT 'approved', preferred_amount INTEGER, created_at TEXT, cnic_front TEXT, cnic_back TEXT, selfie TEXT, profession TEXT, monthly_income TEXT, referred_by TEXT, rejection_reason TEXT, is_defaulter INTEGER DEFAULT 0, guarantor_member_id INTEGER, security_deposit INTEGER DEFAULT 0, is_blacklisted INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS committees (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, monthly_amount INTEGER, total_months INTEGER, start_date TEXT, status TEXT DEFAULT 'active', commission_pct INTEGER DEFAULT 2, created_at TEXT);
        CREATE TABLE IF NOT EXISTS committee_members (id INTEGER PRIMARY KEY AUTOINCREMENT, committee_id INTEGER, member_id INTEGER, payout_month INTEGER, payout_released INTEGER DEFAULT 0, payout_locked INTEGER DEFAULT 0, lock_reason TEXT);
        CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY AUTOINCREMENT, committee_id INTEGER, member_id INTEGER, month_number INTEGER, amount INTEGER, status TEXT DEFAULT 'pending', transaction_id TEXT, screenshot TEXT, paid_at TEXT, verified_by TEXT, verified_at TEXT);
        CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, member_id INTEGER, message TEXT, created_at TEXT, is_read INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id TEXT, action TEXT, target_type TEXT, target_id INTEGER, details TEXT, ip TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS blacklist (id INTEGER PRIMARY KEY AUTOINCREMENT, phone TEXT, cnic TEXT, reason TEXT, added_by TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS security_deposits (id INTEGER PRIMARY KEY AUTOINCREMENT, member_id INTEGER, committee_id INTEGER, amount INTEGER, status TEXT DEFAULT 'held', created_at TEXT);
        CREATE TABLE IF NOT EXISTS agreements (id INTEGER PRIMARY KEY AUTOINCREMENT, member_id INTEGER, committee_id INTEGER, signed_name TEXT, signed_at TEXT, ip TEXT);
    """)
    for col, dtype in [("status", "TEXT DEFAULT 'approved'"), ("preferred_amount", "INTEGER"), ("cnic_front", "TEXT"), ("cnic_back", "TEXT"), ("selfie", "TEXT"), ("profession", "TEXT"), ("monthly_income", "TEXT"), ("referred_by", "TEXT"), ("password", "TEXT"), ("plain_password", "TEXT"), ("rejection_reason", "TEXT"), ("is_defaulter", "INTEGER DEFAULT 0"), ("guarantor_cnic", "TEXT"), ("guarantor_member_id", "INTEGER"), ("security_deposit", "INTEGER DEFAULT 0"), ("is_blacklisted", "INTEGER DEFAULT 0")]:
        try: conn.execute(f"ALTER TABLE members ADD COLUMN {col} {dtype}")
        except sqlite3.OperationalError: pass
    try: conn.execute("ALTER TABLE committees ADD COLUMN commission_pct INTEGER DEFAULT 2")
    except sqlite3.OperationalError: pass
    for col, dtype in [("screenshot", "TEXT"), ("verified_by", "TEXT"), ("verified_at", "TEXT")]:
        try: conn.execute(f"ALTER TABLE payments ADD COLUMN {col} {dtype}")
        except sqlite3.OperationalError: pass
    for col, dtype in [("payout_released", "INTEGER DEFAULT 0"), ("payout_locked", "INTEGER DEFAULT 0"), ("lock_reason", "TEXT")]:
        try: conn.execute(f"ALTER TABLE committee_members ADD COLUMN {col} {dtype}")
        except sqlite3.OperationalError: pass
    conn.commit(); conn.close()


def log_action(action, target_type, target_id, details):
    try:
        conn = get_db()
        conn.execute("INSERT INTO audit_log (admin_id, action, target_type, target_id, details, ip, created_at) VALUES (?,?,?,?,?,?,?)",
                     ('admin', action, target_type, target_id, details, request.remote_addr, datetime.now().isoformat()))
        conn.commit(); conn.close()
    except Exception as e:
        print("Audit log error:", e)
def login_required(f):
    @wraps(f)
    def deco(*a, **kw):
        if not session.get('admin'): return redirect(url_for('login'))
        return f(*a, **kw)
    return deco

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['username'] == ADMIN_USERNAME and request.form['password'] == ADMIN_PASSWORD:
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
    pending_pay = conn.execute("SELECT COUNT(*) c FROM payments WHERE status='pending' OR status='submitted'").fetchone()['c']
    
    total_comm = 0
    comm_data = conn.execute("SELECT SUM(p.amount), c.commission_pct FROM payments p JOIN committees c ON p.committee_id=c.id WHERE p.status='paid' GROUP BY c.id").fetchall()
    for row in comm_data:
        if row[0] and row[1]: total_comm += (row[0] * row[1] / 100)
    
    conn.close()
    return render_template('index.html', members=members, committees=committees, pending=pending_pay, pending_req=pending_req, total_comm=int(total_comm))

@app.route('/members')
@login_required
def members():
    conn = get_db()
    approved_members = conn.execute("SELECT * FROM members WHERE status='approved' ORDER BY id DESC").fetchall()
    pending_members = conn.execute("SELECT * FROM members WHERE status='pending' ORDER BY id DESC").fetchall()
    conn.close()
    return render_template('members.html', members=approved_members, pending_members=pending_members)

@app.route('/members/mark_defaulter/<int:mid>', methods=['POST'])
@login_required
def mark_defaulter(mid):
    reason = request.form.get('reason', 'Payment default')
    conn = get_db()
    member = conn.execute("SELECT * FROM members WHERE id=?", (mid,)).fetchone()
    if not member:
        flash('Member nahi mila.', 'error'); conn.close(); return redirect(url_for('members'))
    conn.execute("UPDATE members SET is_defaulter=1, is_blacklisted=1, trust_score=0 WHERE id=?", (mid,))
    conn.execute("INSERT INTO blacklist (phone, cnic, reason, added_by, created_at) VALUES (?,?,?,?,?)",
                 (member['phone'], member['cnic'] or '', reason, 'admin', datetime.now().isoformat()))
    committees = conn.execute("SELECT committee_id FROM committee_members WHERE member_id=?", (mid,)).fetchall()
    for c in committees:
        guarantors = conn.execute("SELECT cm.id FROM committee_members cm JOIN members m ON cm.member_id=m.id WHERE cm.committee_id=? AND m.guarantor_member_id=?", (c['committee_id'], mid)).fetchall()
        for g in guarantors:
            conn.execute("UPDATE committee_members SET payout_locked=1, lock_reason=? WHERE id=?", (f"Guarantor of defaulter: {member['name']}", g['id']))
    conn.commit(); conn.close()
    log_action('MARK_DEFAULTER', 'member', mid, f"Reason: {reason}")
    flash(f"{member['name']} DEFAULTER mark ho gaya. Guarantor payout LOCK ho gaya.", 'success')
    return redirect(url_for('members'))

@app.route('/members/unmark_defaulter/<int:mid>', methods=['POST'])
@login_required
def unmark_defaulter(mid):
    reason = request.form.get('reason', 'Cleared after recovery')
    conn = get_db()
    member = conn.execute("SELECT * FROM members WHERE id=?", (mid,)).fetchone()
    conn.execute("UPDATE members SET is_defaulter=0, is_blacklisted=0, trust_score=50 WHERE id=?", (mid,))
    conn.execute("DELETE FROM blacklist WHERE phone=?", (member['phone'],))
    committees = conn.execute("SELECT committee_id FROM committee_members WHERE member_id=?", (mid,)).fetchall()
    for c in committees:
        conn.execute("UPDATE committee_members SET payout_locked=0, lock_reason=NULL WHERE committee_id=?", (c['committee_id'],))
    conn.commit(); conn.close()
    log_action('UNMARK_DEFAULTER', 'member', mid, f"Reason: {reason}")
    flash(f"{member['name']} ka defaulter status clear ho gaya.", 'success')
    return redirect(url_for('members'))

@app.route('/members/approve/<int:mid>')
@login_required
def approve_member(mid):
    conn = get_db()
    m = conn.execute("SELECT * FROM members WHERE id=?", (mid,)).fetchone()
    bl = conn.execute("SELECT * FROM blacklist WHERE phone=? OR cnic=?", (m['phone'], m['cnic'] or '')).fetchone()
    if bl:
        flash('Yeh banda BLACKLIST mein hai. Approve nahi ho sakta.', 'error')
        conn.close(); return redirect(url_for('members'))
    conn.execute("UPDATE members SET status='approved', rejection_reason=NULL WHERE id=?", (mid,))
    conn.commit(); conn.close()
    log_action('APPROVE_MEMBER', 'member', mid, f"Name: {m['name']}")
    flash('Member approve ho gaya!', 'success')
    return redirect(url_for('members'))

@app.route('/members/reject/<int:mid>', methods=['POST'])
@login_required
def reject_member(mid):
    reason = request.form.get('reason', 'Aap ki details sahi nahi thin.')
    conn = get_db()
    conn.execute("UPDATE members SET status='rejected', rejection_reason=? WHERE id=?", (reason, mid))
    conn.commit(); conn.close()
    return redirect(url_for('members'))

@app.route('/committees/create', methods=['GET', 'POST'])
@login_required
def create_committee():
    if request.method == 'POST':
        d = request.form
        conn = get_db()
        cur = conn.execute("INSERT INTO committees (name, monthly_amount, total_months, start_date, commission_pct, created_at) VALUES (?,?,?,?,?,?)", (d['name'], int(d['monthly_amount']), int(d['total_months']), d['start_date'], int(d['commission_pct']), datetime.now().isoformat()))
        conn.commit(); conn.close()
        return redirect(url_for('committee_detail', cid=cur.lastrowid))
    return render_template('create_committee.html')

@app.route('/committees/<int:cid>/draw_bari')
@login_required
def draw_bari(cid):
    conn = get_db()
    members = conn.execute("SELECT id FROM committee_members WHERE committee_id=?", (cid,)).fetchall()
    ids = [m['id'] for m in members]
    random.shuffle(ids)
    for index, cmid in enumerate(ids):
        conn.execute("UPDATE committee_members SET payout_month=? WHERE id=?", (index+1, cmid))
    conn.commit(); conn.close()
    flash('Bariyan kamyabi se draw ho gayin!', 'success')
    return redirect(url_for('committee_detail', cid=cid))

@app.route('/committees/<int:cid>/export_csv')
@login_required
def export_csv(cid):
    conn = get_db()
    committee = conn.execute("SELECT * FROM committees WHERE id=?", (cid,)).fetchone()
    payments = conn.execute("SELECT p.*, m.name, m.phone FROM payments p JOIN members m ON p.member_id=m.id WHERE p.committee_id=? ORDER BY p.month_number, p.id", (cid,)).fetchall()
    
    def generate():
        yield 'Naam,Phone,Month,Amount,Status,TID\n'
        for p in payments:
            yield f"{p['name']},{p['phone']},#{p['month_number']},{p['amount']},{p['status']},{p['transaction_id'] or ''}\n"
    conn.close()
    return Response(generate(), mimetype='text/csv', headers={"Content-Disposition": f"attachment;filename={committee['name']}_report.csv"})

@app.route('/payments/<int:pid>/approve_payment')
@login_required
def approve_payment(pid):
    conn = get_db()
    conn.execute("UPDATE payments SET status='paid', paid_at=? WHERE id=?", (datetime.now().isoformat(), pid))
    conn.commit(); conn.close()
    flash('Payment approve ho gayi!', 'success')
    return redirect(request.referrer)

@app.route('/member/upload_payment/<int:pid>', methods=['POST'])
def upload_payment(pid):
    if 'member_id' not in session: return redirect(url_for('member_login'))
    file = request.files.get('screenshot')
    tid = request.form.get('transaction_id')
    
    conn = get_db()
    img_name = None
    if file and file.filename != '':
        ext = os.path.splitext(file.filename)[1]
        img_name = f"pay_proof_{uuid.uuid4().hex}{ext}"
        file.save(os.path.join(SECURE_UPLOAD_FOLDER, img_name))
        
    conn.execute("UPDATE payments SET status='submitted', transaction_id=?, screenshot=? WHERE id=? AND member_id=?", (tid, img_name, pid, session['member_id']))
    conn.commit(); conn.close()
    flash('Payment proof bhej diya gaya. Admin verify karega.', 'success')
    return redirect(url_for('member_dashboard'))

@app.route('/member_dashboard')
def member_dashboard():
    if 'member_id' not in session: return redirect(url_for('member_login'))
    conn = get_db(); mid = session['member_id']
    messages = conn.execute("SELECT * FROM messages WHERE member_id = ? OR member_id = 0 ORDER BY id DESC LIMIT 3", (mid,)).fetchall()
    committees = conn.execute("SELECT c.name, c.monthly_amount, c.total_months, c.start_date, cm.payout_month, cm.id as cm_id FROM committees c JOIN committee_members cm ON c.id = cm.committee_id WHERE cm.member_id = ?", (mid,)).fetchall()
    payments = conn.execute("SELECT p.*, c.name as committee_name FROM payments p JOIN committees c ON p.committee_id = c.id WHERE p.member_id = ? ORDER BY p.id DESC", (mid,)).fetchall()
    conn.close()
    return render_template('member_dashboard.html', name=session['member_name'], messages=messages, committees=committees, payments=payments)

@app.route('/member_login', methods=['GET', 'POST'])
def member_login():
    if request.method == 'POST':
        phone = request.form['phone']; password = request.form['password']
        conn = get_db(); member = conn.execute('SELECT * FROM members WHERE phone = ?', (phone,)).fetchone(); conn.close()
        if member:
            if member['status'] != 'approved':
                flash(f"Aap ka account {member['status']} hai. Admin se rabta karein.", 'error')
                return render_template('member_login.html')
            stored_pw = member['password'] or generate_password_hash(member['phone'])
            if check_password_hash(stored_pw, password):
                session['member_id'] = member['id']; session['member_name'] = member['name']
                return redirect(url_for('member_dashboard'))
            flash('Ghalat Password!', 'error')
        else: flash('Phone number record mein nahi hai.', 'error')
    return render_template('member_login.html')

@app.route('/member_logout')
def member_logout():
    session.pop('member_id', None); session.pop('member_name', None)
    return redirect(url_for('member_login'))

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

@app.route('/send_message', methods=['POST'])
@login_required
def send_message():
    member_id = request.form.get('member_id'); msg_text = request.form['message']
    conn = get_db(); conn.execute("INSERT INTO messages (member_id, message, created_at) VALUES (?,?,?)", (member_id, msg_text, datetime.now().isoformat())); conn.commit(); conn.close()
    return redirect(request.referrer)

@app.route('/committees')
@login_required
def committees():
    conn = get_db(); rows = conn.execute('SELECT * FROM committees ORDER BY id DESC').fetchall(); conn.close()
    return render_template('committees.html', committees=rows)

@app.route('/committees/<int:cid>/delete')
@login_required
def delete_committee(cid):
    conn = get_db(); conn.execute('DELETE FROM payments WHERE committee_id=?', (cid,)); conn.execute('DELETE FROM committee_members WHERE committee_id=?', (cid,)); conn.execute('DELETE FROM committees WHERE id=?', (cid,)); conn.commit(); conn.close()
    return redirect(url_for('committees'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        d = request.form
        conn = get_db()
        try:
            hashed_pw = generate_password_hash(d['password'])
            conn.execute("INSERT INTO members (name, phone, password, plain_password, cnic, address, preferred_amount, status, created_at, profession, monthly_income, referred_by, guarantor_name, guarantor_phone, guarantor_cnic, guarantor_cnic_front, guarantor_cnic_back) VALUES (?,?,?,?,?,?,?,'pending',?,?,?,?,?,?,?)", 
                (d['name'], d['phone'], hashed_pw, d['password'], d['cnic'], d['address'], d['preferred_amount'], datetime.now().isoformat(), d.get('profession'), d.get('monthly_income'), d.get('referred_by'), d.get('guarantor_name', ''), d.get('guarantor_phone', ''), d.get('guarantor_cnic', ''), guar_front_name, guar_back_name))
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
            conn.execute("INSERT INTO members (name, phone, password, plain_password, cnic, address, address_type, guarantor_name, guarantor_phone, guarantor_cnic, verified, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,'approved',?)", (d['name'], d['phone'], hashed_pw, d['password'], d['cnic'], d['address'], d['address_type'], d['guarantor_name'], d['guarantor_phone'], d.get('guarantor_cnic', ''), int(d.get('verified', 0)), datetime.now().isoformat()))
            conn.commit(); flash('Member add ho gaya!', 'success')
        except sqlite3.IntegrityError: flash('Yeh phone number pehle se maujood hai.', 'error')
        conn.close()
        return redirect(url_for('members'))
    return render_template('add_member.html')

@app.route('/members/<int:mid>/verify')
@login_required
def verify_member(mid):
    conn = get_db(); conn.execute('UPDATE members SET verified=1, trust_score=trust_score+20 WHERE id=?', (mid,)); conn.commit(); conn.close()
    return redirect(url_for('members'))


# ================= FRAUD PREVENTION ROUTES =================

@app.route('/committees/<int:cid>/lock_payout/<int:cmid>', methods=['POST'])
@login_required
def lock_payout(cid, cmid):
    reason = request.form.get('reason', 'Manual lock')
    conn = get_db()
    conn.execute("UPDATE committee_members SET payout_locked=1, lock_reason=? WHERE id=? AND committee_id=?", (reason, cmid, cid))
    conn.commit(); conn.close()
    log_action('LOCK_PAYOUT', 'committee_member', cmid, f"Committee {cid}, Reason: {reason}")
    flash('Payout LOCK ho gaya. Ab release nahi hoga.', 'success')
    return redirect(url_for('committee_detail', cid=cid))

@app.route('/committees/<int:cid>/release_payout/<int:cmid>', methods=['POST'])
@login_required
def release_payout(cid, cmid):
    conn = get_db()
    cm = conn.execute("SELECT cm.*, m.name, m.security_deposit FROM committee_members cm JOIN members m ON cm.member_id=m.id WHERE cm.id=?", (cmid,)).fetchone()
    if not cm:
        flash('Member nahi mila.', 'error'); conn.close(); return redirect(url_for('committee_detail', cid=cid))
    if cm['payout_locked']:
        flash(f"Payout LOCK hai. Wajah: {cm['lock_reason'] or 'Guarantor default'}", 'error')
        conn.close(); return redirect(url_for('committee_detail', cid=cid))
    unpaid = conn.execute("SELECT COUNT(*) c FROM payments WHERE committee_id=? AND member_id=? AND month_number<? AND status!='paid'", (cid, cm['member_id'], cm['payout_month'])).fetchone()['c']
    if unpaid > 0:
        flash(f"{unpaid} payments abhi baqi hain. Payout release nahi ho sakta.", 'error')
        conn.close(); return redirect(url_for('committee_detail', cid=cid))
    conn.execute("UPDATE committee_members SET payout_released=1 WHERE id=?", (cmid,))
    conn.commit(); conn.close()
    log_action('RELEASE_PAYOUT', 'committee_member', cmid, f"Committee {cid}, Member: {cm['name']}")
    flash(f"{cm['name']} ka payout release ho gaya.", 'success')
    return redirect(url_for('committee_detail', cid=cid))

@app.route('/security-deposit/<int:mid>', methods=['POST'])
@login_required
def add_security_deposit(mid):
    amount = int(request.form.get('amount', 0))
    cid = int(request.form.get('committee_id', 0))
    conn = get_db()
    conn.execute("INSERT INTO security_deposits (member_id, committee_id, amount, status, created_at) VALUES (?,?,?,'held',?)", (mid, cid, amount, datetime.now().isoformat()))
    conn.execute("UPDATE members SET security_deposit=security_deposit+? WHERE id=?", (amount, mid))
    conn.commit(); conn.close()
    log_action('ADD_SECURITY_DEPOSIT', 'member', mid, f"Amount: {amount}, Committee: {cid}")
    flash(f"Rs. {amount} security deposit record ho gayi.", 'success')
    return redirect(url_for('members'))

@app.route('/agreement/<int:mid>')
@login_required
def view_agreement(mid):
    conn = get_db()
    m = conn.execute("SELECT * FROM members WHERE id=?", (mid,)).fetchone()
    ag = conn.execute("SELECT * FROM agreements WHERE member_id=? ORDER BY id DESC LIMIT 1", (mid,)).fetchone()
    conn.close()
    return render_template('agreement.html', member=m, agreement=ag)

@app.route('/agreement/<int:mid>/sign', methods=['POST'])
@login_required
def sign_agreement(mid):
    signed_name = request.form.get('signed_name', '').strip()
    if not signed_name:
        flash('Naam likhna zaroori hai.', 'error'); return redirect(url_for('view_agreement', mid=mid))
    conn = get_db()
    conn.execute("INSERT INTO agreements (member_id, committee_id, signed_name, signed_at, ip) VALUES (?,?,?,?,?)",
                 (mid, 0, signed_name, datetime.now().isoformat(), request.remote_addr))
    conn.commit(); conn.close()
    log_action('SIGN_AGREEMENT', 'member', mid, f"Signed by: {signed_name}")
    flash('Agreement sign ho gaya. Yeh legal record hai.', 'success')
    return redirect(url_for('view_agreement', mid=mid))

@app.route('/audit-log')
@login_required
def audit_log_view():
    conn = get_db()
    logs = conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 300").fetchall()
    conn.close()
    return render_template('audit_log.html', logs=logs)

@app.route('/blacklist')
@login_required
def blacklist_view():
    conn = get_db()
    bl = conn.execute("SELECT * FROM blacklist ORDER BY id DESC").fetchall()
    conn.close()
    return render_template('blacklist.html', blacklist=bl)

@app.route('/blacklist/remove/<int:bid>', methods=['POST'])
@login_required
def blacklist_remove(bid):
    reason = request.form.get('reason', '')
    conn = get_db()
    item = conn.execute("SELECT * FROM blacklist WHERE id=?", (bid,)).fetchone()
    conn.execute("DELETE FROM blacklist WHERE id=?", (bid,))
    conn.execute("UPDATE members SET is_blacklisted=0 WHERE phone=?", (item['phone'],))
    conn.commit(); conn.close()
    log_action('BLACKLIST_REMOVE', 'blacklist', bid, f"Reason: {reason}, Phone: {item['phone']}")
    flash('Blacklist se remove ho gaya.', 'success')
    return redirect(url_for('blacklist_view'))

# ================= END FRAUD PREVENTION =================

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)