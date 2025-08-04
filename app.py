import os
import sqlite3
import threading
from functools import wraps
from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for, g
from flask_socketio import SocketIO
import pandas as pd
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash

# Opcional PDF
try:
    from matplotlib.backends.backend_pdf import PdfPages
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXT = {'xls', 'xlsx'}
DB_PATH = 'db.sqlite'

db_lock = threading.Lock()

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = 'dev-secret'
socketio = SocketIO(app)

# --- Helpers ---

def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    return conn

@app.before_request
def load_user():
    g.user = None
    uid = session.get('user_id')
    if uid:
        conn = get_conn()
        g.user = conn.execute('SELECT * FROM users WHERE id = ?', (uid,)).fetchone()
        conn.close()

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not g.user:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper

def requires_role(*roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not g.user or g.user['role'] not in roles:
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return wrapper
    return decorator

# --- Autenticación ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        conn = get_conn()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            return redirect(url_for(f"panel_{user['role']}"))
        return render_template('login.html', error='Credenciales inválidas')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
def index():
    if g.user:
        return redirect(url_for(f"panel_{g.user['role']}"))
    return redirect(url_for('login'))

@app.route('/panel')
@login_required
def panel_redirect():
    """Deprecated helper that redirects to the panel según rol."""
    return redirect(url_for(f"panel_{g.user['role']}"))

@app.route('/panel_admin')
@login_required
@requires_role('admin')
def panel_admin():
    conn = get_conn()
    users = conn.execute('SELECT id, username, role FROM users').fetchall()
    votaciones = conn.execute('SELECT * FROM votaciones').fetchall()
    conn.close()
    return render_template('admin_panel.html', users=users, votaciones=votaciones)

@app.route('/panel_asistencia')
@login_required
@requires_role('asistencia')
def panel_asistencia():
    conn = get_conn()
    votaciones = conn.execute('''SELECT v.* FROM votaciones v
                                 JOIN votacion_usuarios vu ON v.id = vu.votacion_id
                                 WHERE vu.user_id = ? AND vu.rol = 'asistencia' ''',
                               (g.user['id'],)).fetchall()
    conn.close()
    return render_template('asistencia_panel.html', votaciones=votaciones)

@app.route('/panel_votacion')
@login_required
@requires_role('votante')
def panel_votacion():
    conn = get_conn()
    votaciones = conn.execute('''SELECT v.* FROM votaciones v
                                 JOIN votacion_usuarios vu ON v.id = vu.votacion_id
                                 WHERE vu.user_id = ? AND vu.rol = 'votante' ''',
                               (g.user['id'],)).fetchall()
    conn.close()
    return render_template('votante_panel.html', votaciones=votaciones)

# --- Admin ---

@app.route('/admin/create_user', methods=['POST'])
@requires_role('admin')
def admin_create_user():
    username = request.form.get('username')
    password = request.form.get('password')
    role = request.form.get('role')
    conn = get_conn()
    conn.execute('INSERT INTO users (username, password, role) VALUES (?,?,?)',
                 (username, generate_password_hash(password), role))
    conn.commit()
    conn.close()
    return redirect(url_for('panel_admin'))

@app.route('/admin/create_votacion', methods=['POST'])
@requires_role('admin')
def admin_create_votacion():
    nombre = request.form.get('nombre')
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('INSERT INTO votaciones (nombre) VALUES (?)', (nombre,))
    votacion_id = cur.lastrowid
    cur.execute('INSERT INTO preguntas (votacion_id, texto) VALUES (?, ?)', (votacion_id, 'Pregunta 1'))
    conn.commit()
    conn.close()
    return redirect(url_for('panel_admin'))

@app.route('/admin/asignar', methods=['POST'])
@requires_role('admin')
def admin_asignar():
    user_id = request.form.get('user_id')
    votacion_id = request.form.get('votacion_id')
    rol = request.form.get('rol')
    conn = get_conn()
    conn.execute('INSERT INTO votacion_usuarios (votacion_id, user_id, rol) VALUES (?,?,?)',
                 (votacion_id, user_id, rol))
    conn.commit()
    conn.close()
    return redirect(url_for('panel_admin'))

# --- Asistencia existente ---

@app.route('/upload', methods=['POST'])
@requires_role('asistencia', 'admin')
def upload():
    f = request.files.get('file')
    if not f:
        return jsonify({'error': 'No file provided'}), 400
    name = secure_filename(f.filename)
    ext = name.rsplit('.', 1)[-1].lower()
    if ext not in ALLOWED_EXT:
        return jsonify({'error': 'Formato no permitido'}), 400
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    path = os.path.join(app.config['UPLOAD_FOLDER'], name)
    f.save(path)
    try:
        df = pd.read_excel(path)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    df['ASISTENCIA'] = df.get('ASISTENCIA', '').astype(str).str.strip().str.upper()
    df['ASISTENCIA'] = df['ASISTENCIA'].where(df['ASISTENCIA'].isin(['PRESENCIAL','VIRTUAL','AUSENTE']), 'AUSENTE')
    with db_lock:
        conn = get_conn()
        try:
            conn.execute('DELETE FROM asistencia')
            for _, r in df.iterrows():
                conn.execute(
                    'INSERT INTO asistencia (accionista,representante,apoderado,acciones,estado) VALUES (?,?,?,?,?)',
                    (
                        r.get('ACCIONISTA'),
                        r.get('REPRESENTANTE LEGAL'),
                        r.get('APODERADO'),
                        int(r.get('No. ACCIONES', 0) or 0),
                        r['ASISTENCIA']
                    )
                )
            conn.commit()
        finally:
            conn.close()
    return jsonify({'ok': True})

@app.route('/api/asistencia')
@requires_role('asistencia', 'admin')
def get_asistencia():
    conn = get_conn()
    rows = conn.execute('SELECT * FROM asistencia').fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/asistencia/<int:id>', methods=['POST'])
@requires_role('asistencia', 'admin')
def update_asistencia(id):
    new_estado = request.json.get('estado')
    with db_lock:
        conn = get_conn()
        conn.execute('UPDATE asistencia SET estado = ? WHERE id = ?', (new_estado, id))
        conn.commit()
        conn.close()
    socketio.emit('estado_changed', {'id': id, 'estado': new_estado})
    return ('', 204)

@app.route('/export/<fmt>')
@requires_role('asistencia', 'admin')
def export(fmt):
    conn = get_conn()
    df = pd.read_sql('SELECT * FROM asistencia', conn)
    conn.close()
    base = 'asistencia_export'
    if fmt == 'excel':
        fname = f"{base}.xlsx"
        df.to_excel(fname, index=False)
    elif fmt == 'csv':
        fname = f"{base}.csv"
        df.to_csv(fname, index=False)
    elif fmt == 'pdf' and HAS_MPL:
        fname = f"{base}.pdf"
        with PdfPages(fname) as pdf:
            fig, ax = plt.subplots()
            df['estado'].value_counts().plot.pie(ax=ax, autopct='%1.1f%%')
            ax.set_ylabel('')
            pdf.savefig(fig)
            plt.close(fig)

            fig2, ax2 = plt.subplots()
            df.groupby('estado')['acciones'].sum().plot.bar(ax=ax2)
            ax2.set_ylabel('Total Acciones')
            pdf.savefig(fig2)
            plt.close(fig2)
    else:
        return 'Formato no soportado', 400
    return send_file(fname, as_attachment=True)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
