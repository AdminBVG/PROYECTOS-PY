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
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret')
socketio = SocketIO(app)

PANEL_ROUTES = {
    'admin': 'panel_admin',
    'asistencia': 'panel_asistencia',
    'votante': 'panel_votacion',
}

ALLOWED_ESTADOS = ('PRESENCIAL', 'VIRTUAL', 'AUSENTE')

# --- Helpers ---

def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys = ON')
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
            route = PANEL_ROUTES.get(user['role'])
            return redirect(url_for(route)) if route else redirect(url_for('login'))
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
        route = PANEL_ROUTES.get(g.user['role'])
        if route:
            return redirect(url_for(route))
    return redirect(url_for('login'))

@app.route('/panel')
@login_required
def panel_redirect():
    """Deprecated helper that redirects to the panel según rol."""
    route = PANEL_ROUTES.get(g.user['role'])
    return redirect(url_for(route)) if route else redirect(url_for('login'))

@app.route('/panel_admin')
@login_required
@requires_role('admin')
def panel_admin():
    """Panel principal del administrador con secciones de usuarios y votaciones."""
    conn = get_conn()
    users = conn.execute('''
        SELECT u.id, u.username, u.cedula, u.role,
               COALESCE(GROUP_CONCAT(v.nombre, ', '), '') AS votaciones
        FROM users u
        LEFT JOIN votacion_usuarios vu ON vu.user_id = u.id
        LEFT JOIN votaciones v ON v.id = vu.votacion_id
        GROUP BY u.id
    ''').fetchall()
    votaciones = conn.execute('''
        SELECT v.id, v.nombre, v.fecha,
               COUNT(DISTINCT p.id) AS num_preguntas,
               COUNT(DISTINCT CASE WHEN vu.rol = 'asistencia' THEN vu.user_id END) AS asistentes
        FROM votaciones v
        LEFT JOIN preguntas p ON p.votacion_id = v.id
        LEFT JOIN votacion_usuarios vu ON vu.votacion_id = v.id
        GROUP BY v.id
    ''').fetchall()
    conn.close()
    return render_template('panel_admin.html', users=users, votaciones=votaciones)

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
    """Crea un nuevo usuario con rol y cédula."""
    username = request.form.get('username')
    password = request.form.get('password')
    role = request.form.get('role')
    cedula = request.form.get('cedula')
    conn = get_conn()
    try:
        conn.execute(
            'INSERT INTO users (username, password, role, cedula) VALUES (?,?,?,?)',
            (username, generate_password_hash(password), role, cedula)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        users = conn.execute('''
            SELECT u.id, u.username, u.cedula, u.role,
                   COALESCE(GROUP_CONCAT(v.nombre, ', '), '') AS votaciones
            FROM users u
            LEFT JOIN votacion_usuarios vu ON vu.user_id = u.id
            LEFT JOIN votaciones v ON v.id = vu.votacion_id
            GROUP BY u.id
        ''').fetchall()
        votaciones = conn.execute('''
            SELECT v.id, v.nombre, v.fecha,
                   COUNT(DISTINCT p.id) AS num_preguntas,
                   COUNT(DISTINCT CASE WHEN vu.rol = 'asistencia' THEN vu.user_id END) AS asistentes
            FROM votaciones v
            LEFT JOIN preguntas p ON p.votacion_id = v.id
            LEFT JOIN votacion_usuarios vu ON vu.votacion_id = v.id
            GROUP BY v.id
        ''').fetchall()
        conn.close()
        return render_template('panel_admin.html', users=users, votaciones=votaciones,
                               error='Usuario o cédula ya existe')
    conn.close()
    return redirect(url_for('panel_admin'))

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@requires_role('admin')
def admin_delete_user(user_id):
    """Elimina un usuario por ID."""
    conn = get_conn()
    conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.execute('DELETE FROM votacion_usuarios WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('panel_admin'))

@app.route('/admin/create_votacion', methods=['POST'])
@requires_role('admin')
def admin_create_votacion():
    """Crea una votación con fecha opcional y preguntas."""
    nombre = request.form.get('nombre')
    fecha = request.form.get('fecha') or None
    preguntas_raw = request.form.get('preguntas', '')
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('INSERT INTO votaciones (nombre, fecha) VALUES (?, ?)', (nombre, fecha))
    votacion_id = cur.lastrowid

    for line in preguntas_raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if '|' in line:
            q_text, opciones = line.split('|', 1)
        else:
            q_text, opciones = line, ''
        cur.execute('INSERT INTO preguntas (votacion_id, texto) VALUES (?, ?)', (votacion_id, q_text.strip()))
        pregunta_id = cur.lastrowid
        for opt in [o.strip() for o in opciones.split(',') if o.strip()]:
            cur.execute('INSERT INTO opciones (pregunta_id, texto) VALUES (?, ?)', (pregunta_id, opt))

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

        if 'ASISTENCIA' not in df.columns:
            df['ASISTENCIA'] = 'AUSENTE'
        else:
            df['ASISTENCIA'] = df['ASISTENCIA'].astype(str).str.strip().str.upper()
        df['ASISTENCIA'] = df['ASISTENCIA'].where(df['ASISTENCIA'].isin(ALLOWED_ESTADOS), 'AUSENTE')

        df['No. ACCIONES'] = pd.to_numeric(df.get('No. ACCIONES', 0), errors='coerce').fillna(0).astype(int)
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
                            int(r['No. ACCIONES']),
                            r['ASISTENCIA']
                        )
                    )
                conn.commit()
            finally:
                conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

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
    if not request.is_json:
        return jsonify({'error': 'JSON requerido'}), 400
    data = request.get_json(silent=True) or {}
    new_estado = str(data.get('estado', '')).upper()
    if new_estado not in ALLOWED_ESTADOS:
        return jsonify({'error': 'Estado inválido'}), 400
    with db_lock:
        conn = get_conn()
        cur = conn.execute('UPDATE asistencia SET estado = ? WHERE id = ?', (new_estado, id))
        conn.commit()
        updated = cur.rowcount
        conn.close()
    if updated:
        socketio.emit('estado_changed', {'id': id, 'estado': new_estado})
        return ('', 204)
    return jsonify({'error': 'Registro no encontrado'}), 404

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
    debug_mode = os.environ.get('FLASK_DEBUG') == '1'
    socketio.run(app, host='0.0.0.0', port=5000, debug=debug_mode)
