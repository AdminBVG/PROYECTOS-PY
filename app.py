import os
import sqlite3
import threading
from functools import wraps
from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for, g
from io import BytesIO
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

# Python 3.12 does not support eventlet; use threading for SocketIO
# Ensure python-socketio and flask-socketio are 5.x for compatibility
socketio = SocketIO(app, async_mode="threading")

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


def resumen_acciones(votacion_id=None):
    """Calcula totales de acciones por estado para una votación."""
    conn = get_conn()
    if votacion_id is None:
        rows = conn.execute(
            'SELECT estado, SUM(acciones) AS acciones FROM asistencia GROUP BY estado'
        ).fetchall()
    else:
        rows = conn.execute(
            'SELECT estado, SUM(acciones) AS acciones FROM asistencia WHERE votacion_id=? GROUP BY estado',
            (votacion_id,)
        ).fetchall()
    conn.close()
    data = {r['estado']: r['acciones'] or 0 for r in rows}
    total = sum(data.values())
    activos = sum(v for e, v in data.items() if e in ('PRESENCIAL', 'VIRTUAL'))
    return total, activos, data

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
        SELECT v.id, v.nombre, v.fecha, v.quorum_minimo,
               COUNT(DISTINCT p.id) AS num_preguntas,
               COUNT(DISTINCT CASE WHEN vu.rol = 'asistencia' THEN vu.user_id END) AS asistentes,
               COUNT(DISTINCT CASE WHEN vu.rol = 'votante' THEN vu.user_id END) AS votantes,
               GROUP_CONCAT(DISTINCT CASE WHEN vu.rol = 'asistencia' THEN u.username END) AS asistentes_nombres,
               GROUP_CONCAT(DISTINCT CASE WHEN vu.rol = 'votante' THEN u.username END) AS votantes_nombres
        FROM votaciones v
        LEFT JOIN preguntas p ON p.votacion_id = v.id
        LEFT JOIN votacion_usuarios vu ON vu.votacion_id = v.id
        LEFT JOIN users u ON vu.user_id = u.id
        GROUP BY v.id
    ''').fetchall()
    conn.close()
    return render_template('panel_admin.html', users=users, votaciones=votaciones)

@app.route('/panel_asistencia')
@login_required
@requires_role('asistencia', 'votante')
def panel_asistencia():
    conn = get_conn()
    rol = 'asistencia' if g.user['role'] == 'asistencia' else 'votante'
    votaciones = conn.execute('''SELECT v.* FROM votaciones v
                                 JOIN votacion_usuarios vu ON v.id = vu.votacion_id
                                 WHERE vu.user_id = ? AND vu.rol = ? ''',
                               (g.user['id'], rol)).fetchall()
    conn.close()
    readonly = g.user['role'] == 'votante'
    return render_template('asistencia_panel.html', votaciones=votaciones, readonly=readonly)

@app.route('/panel_votacion')
@login_required
@requires_role('votante')
def panel_votacion():
    conn = get_conn()
    rows = conn.execute('''SELECT v.* FROM votaciones v
                           JOIN votacion_usuarios vu ON v.id = vu.votacion_id
                           WHERE vu.user_id = ? AND vu.rol = 'votante' ''',
                         (g.user['id'],)).fetchall()
    votaciones = []
    for v in rows:
        total, activos, _ = resumen_acciones(v['id'])
        pct = (activos / total * 100) if total else 0
        votaciones.append({**dict(v), 'quorum_ok': pct >= (v['quorum_minimo'] or 0), 'porcentaje': pct})
    conn.close()
    return render_template('votante_panel.html', votaciones=votaciones)

@app.route('/votacion/<int:votacion_id>')
@login_required
@requires_role('votante')
def iniciar_votacion(votacion_id):
    conn = get_conn()
    row = conn.execute('''SELECT v.* FROM votaciones v
                           JOIN votacion_usuarios vu ON v.id=vu.votacion_id
                           WHERE v.id=? AND vu.user_id=? AND vu.rol='votante' ''',
                         (votacion_id, g.user['id'])).fetchone()
    if not row:
        conn.close()
        return redirect(url_for('panel_votacion'))
    total, activos, _ = resumen_acciones(votacion_id)
    pct = (activos / total * 100) if total else 0
    if pct < (row['quorum_minimo'] or 0):
        conn.close()
        return redirect(url_for('panel_votacion'))
    conn.close()
    return render_template('votacion_registro.html', votacion=row)

@app.route('/api/votacion/<int:votacion_id>/preguntas')
@login_required
@requires_role('votante')
def preguntas_votacion(votacion_id):
    conn = get_conn()
    perm = conn.execute('SELECT 1 FROM votacion_usuarios WHERE votacion_id=? AND user_id=? AND rol="votante"', (votacion_id, g.user['id'])).fetchone()
    if not perm:
        conn.close()
        return jsonify([]), 403
    rows = conn.execute('SELECT id, texto FROM preguntas WHERE votacion_id=?', (votacion_id,)).fetchall()
    data = []
    for p in rows:
        opts = conn.execute('SELECT id, texto FROM opciones WHERE pregunta_id=?', (p['id'],)).fetchall()
        data.append({'id': p['id'], 'texto': p['texto'], 'opciones': [dict(o) for o in opts]})
    conn.close()
    return jsonify(data)

@app.route('/api/votacion/<int:votacion_id>/asistentes')
@login_required
@requires_role('votante')
def asistentes_votacion(votacion_id):
    conn = get_conn()
    perm = conn.execute('SELECT 1 FROM votacion_usuarios WHERE votacion_id=? AND user_id=? AND rol="votante"', (votacion_id, g.user['id'])).fetchone()
    if not perm:
        conn.close()
        return jsonify([]), 403
    rows = conn.execute(
        'SELECT id, accionista, representante, apoderado, acciones FROM asistencia WHERE votacion_id=? AND estado IN ("PRESENCIAL","VIRTUAL")',
        (votacion_id,)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

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
    """Crea una votación recibiendo datos estructurados."""
    data = request.get_json(silent=True)
    if data:
        nombre = data.get('nombre_votacion')
        fecha = data.get('fecha') or None
        quorum = float(data.get('quorum_minimo') or 0)
        preguntas = data.get('preguntas', [])
        votantes = [int(u) for u in data.get('votantes', [])]
        asistentes = [int(u) for u in data.get('asistentes', [])]
        conn = get_conn()
        cur = conn.cursor()
        cur.execute('INSERT INTO votaciones (nombre, fecha, quorum_minimo) VALUES (?,?,?)', (nombre, fecha, quorum))
        votacion_id = cur.lastrowid
        for p in preguntas:
            texto = p.get('texto', '').strip()
            if not texto:
                continue
            cur.execute('INSERT INTO preguntas (votacion_id, texto) VALUES (?, ?)', (votacion_id, texto))
            pregunta_id = cur.lastrowid
            for opt in p.get('opciones', []):
                opt = opt.strip()
                if opt:
                    cur.execute('INSERT INTO opciones (pregunta_id, texto) VALUES (?, ?)', (pregunta_id, opt))
        for uid in votantes:
            try:
                cur.execute('INSERT INTO votacion_usuarios (votacion_id, user_id, rol) VALUES (?,?,?)', (votacion_id, uid, 'votante'))
            except sqlite3.IntegrityError:
                pass
        for uid in asistentes:
            try:
                cur.execute('INSERT INTO votacion_usuarios (votacion_id, user_id, rol) VALUES (?,?,?)', (votacion_id, uid, 'asistencia'))
            except sqlite3.IntegrityError:
                pass
        conn.commit()
        conn.close()
        return jsonify({'status': 'ok'})
    # Fallback para formularios antiguos
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

@app.route('/admin/votacion/<int:votacion_id>/delete', methods=['POST'])
@requires_role('admin')
def admin_delete_votacion(votacion_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('DELETE FROM votacion_usuarios WHERE votacion_id=?', (votacion_id,))
    cur.execute('DELETE FROM opciones WHERE pregunta_id IN (SELECT id FROM preguntas WHERE votacion_id=?)', (votacion_id,))
    cur.execute('DELETE FROM preguntas WHERE votacion_id=?', (votacion_id,))
    cur.execute('DELETE FROM votaciones WHERE id=?', (votacion_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('panel_admin'))

@app.route('/admin/votacion/<int:votacion_id>/edit')
@requires_role('admin')
def admin_edit_votacion(votacion_id):
    conn = get_conn()
    votacion = conn.execute('SELECT * FROM votaciones WHERE id=?', (votacion_id,)).fetchone()
    if not votacion:
        conn.close()
        return redirect(url_for('panel_admin'))
    preguntas = []
    for p in conn.execute('SELECT * FROM preguntas WHERE votacion_id=?', (votacion_id,)).fetchall():
        opts = conn.execute('SELECT texto FROM opciones WHERE pregunta_id=?', (p['id'],)).fetchall()
        preguntas.append({'texto': p['texto'], 'opciones': [o['texto'] for o in opts]})
    asignados = conn.execute('SELECT user_id, rol FROM votacion_usuarios WHERE votacion_id=?', (votacion_id,)).fetchall()
    votantes = [r['user_id'] for r in asignados if r['rol'] == 'votante']
    asistentes = [r['user_id'] for r in asignados if r['rol'] == 'asistencia']
    users = conn.execute('SELECT id, username, role FROM users').fetchall()
    conn.close()
    data = {
        'id': votacion['id'],
        'nombre': votacion['nombre'],
        'fecha': votacion['fecha'],
        'quorum_minimo': votacion['quorum_minimo'],
        'preguntas': preguntas,
        'votantes': votantes,
        'asistentes': asistentes,
    }
    return render_template('edit_votacion.html', data=data, users=users)

@app.route('/admin/votacion/<int:votacion_id>/update', methods=['POST'])
@requires_role('admin')
def admin_update_votacion(votacion_id):
    data = request.get_json(silent=True) or {}
    nombre = data.get('nombre_votacion')
    fecha = data.get('fecha') or None
    quorum = float(data.get('quorum_minimo') or 0)
    preguntas = data.get('preguntas', [])
    votantes = [int(u) for u in data.get('votantes', [])]
    asistentes = [int(u) for u in data.get('asistentes', [])]
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('UPDATE votaciones SET nombre=?, fecha=?, quorum_minimo=? WHERE id=?', (nombre, fecha, quorum, votacion_id))
    cur.execute('DELETE FROM opciones WHERE pregunta_id IN (SELECT id FROM preguntas WHERE votacion_id=?)', (votacion_id,))
    cur.execute('DELETE FROM preguntas WHERE votacion_id=?', (votacion_id,))
    for p in preguntas:
        texto = p.get('texto', '').strip()
        if not texto:
            continue
        cur.execute('INSERT INTO preguntas (votacion_id, texto) VALUES (?, ?)', (votacion_id, texto))
        pregunta_id = cur.lastrowid
        for opt in p.get('opciones', []):
            opt = opt.strip()
            if opt:
                cur.execute('INSERT INTO opciones (pregunta_id, texto) VALUES (?, ?)', (pregunta_id, opt))
    cur.execute('DELETE FROM votacion_usuarios WHERE votacion_id=?', (votacion_id,))
    for uid in votantes:
        try:
            cur.execute('INSERT INTO votacion_usuarios (votacion_id, user_id, rol) VALUES (?,?,?)', (votacion_id, uid, 'votante'))
        except sqlite3.IntegrityError:
            pass
    for uid in asistentes:
        try:
            cur.execute('INSERT INTO votacion_usuarios (votacion_id, user_id, rol) VALUES (?,?,?)', (votacion_id, uid, 'asistencia'))
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok'})
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
    votacion_id = request.form.get('votacion_id', type=int)
    if not f or not votacion_id:
        return jsonify({'error': 'Datos incompletos'}), 400
    name = secure_filename(f.filename)
    ext = name.rsplit('.', 1)[-1].lower()
    if ext not in ALLOWED_EXT:
        return jsonify({'error': 'Formato no permitido'}), 400
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    path = os.path.join(app.config['UPLOAD_FOLDER'], name)
    f.save(path)
    try:
        df = pd.read_excel(path, engine='openpyxl')
        required = ['ACCIONISTA', 'REPRESENTANTE LEGAL', 'APODERADO', 'No. ACCIONES']
        missing = [c for c in required if c not in df.columns]
        if missing:
            return jsonify({'error': f"Columnas faltantes: {', '.join(missing)}"}), 400

        if 'ASISTENCIA' not in df.columns:
            df['ASISTENCIA'] = 'AUSENTE'
        else:
            df['ASISTENCIA'] = df['ASISTENCIA'].astype(str).str.strip().str.upper()
        df['ASISTENCIA'] = df['ASISTENCIA'].where(df['ASISTENCIA'].isin(ALLOWED_ESTADOS), 'AUSENTE')

        df['No. ACCIONES'] = pd.to_numeric(df.get('No. ACCIONES', 0), errors='coerce').fillna(0).astype(int)
        with db_lock:
            conn = get_conn()
            try:
                conn.execute('DELETE FROM asistencia WHERE votacion_id=?', (votacion_id,))
                for _, r in df.iterrows():
                    conn.execute(
                        'INSERT INTO asistencia (votacion_id, accionista,representante,apoderado,acciones,estado) VALUES (?,?,?,?,?,?)',
                        (
                            votacion_id,
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
@requires_role('asistencia', 'admin', 'votante')
def get_asistencia():
    votacion_id = request.args.get('votacion_id', type=int)
    if not votacion_id:
        return jsonify([])
    conn = get_conn()
    rows = conn.execute('SELECT * FROM asistencia WHERE votacion_id=?', (votacion_id,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/asistencia/resumen')
@requires_role('asistencia', 'admin', 'votante')
def asistencia_resumen():
    votacion_id = request.args.get('votacion_id', type=int)
    if not votacion_id:
        return jsonify({'error': 'votacion_id requerido'}), 400
    total, activos, data = resumen_acciones(votacion_id)
    conn = get_conn()
    row = conn.execute('SELECT quorum_minimo FROM votaciones WHERE id=?', (votacion_id,)).fetchone()
    conn.close()
    quorum_minimo = row['quorum_minimo'] if row else 0
    quorum_porcentaje = (activos / total * 100) if total else 0
    result = {
        'acciones_totales': total,
        'acciones_activas': activos,
        'quorum_minimo': quorum_minimo,
        'porcentaje': quorum_porcentaje,
        'quorum_cumplido': quorum_porcentaje >= quorum_minimo,
        'por_estado': {
            e: {
                'acciones': data.get(e, 0),
                'porcentaje_total': (data.get(e, 0) / total * 100) if total else 0,
                'porcentaje_activo': (data.get(e, 0) / activos * 100) if activos else 0,
            }
            for e in ALLOWED_ESTADOS
        },
    }
    return jsonify(result)

@app.route('/api/asistencia/<int:id>', methods=['POST'])
@requires_role('asistencia', 'admin')
def update_asistencia(id):
    if not request.is_json:
        return jsonify({'error': 'JSON requerido'}), 400
    data = request.get_json(silent=True) or {}
    new_estado = str(data.get('estado', '')).upper()
    if new_estado not in ALLOWED_ESTADOS:
        return jsonify({'error': 'Estado inválido'}), 400
    votacion_id = request.args.get('votacion_id', type=int)
    if not votacion_id:
        return jsonify({'error': 'votacion_id requerido'}), 400
    with db_lock:
        conn = get_conn()
        cur = conn.execute('UPDATE asistencia SET estado = ? WHERE id = ? AND votacion_id = ?', (new_estado, id, votacion_id))
        conn.commit()
        updated = cur.rowcount
        conn.close()
    if updated:
        socketio.emit('estado_changed', {'id': id, 'estado': new_estado})
        return ('', 204)
    return jsonify({'error': 'Registro no encontrado'}), 404

@app.route('/template/asistencia')
@requires_role('asistencia', 'admin')
def plantilla_asistencia():
    """Genera una plantilla vacía de asistencia en formato Excel."""
    df = pd.DataFrame(columns=['ACCIONISTA', 'REPRESENTANTE LEGAL', 'APODERADO', 'No. ACCIONES', 'ASISTENCIA'])
    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    return send_file(output, as_attachment=True, download_name='plantilla_asistencia.xlsx')

@app.route('/export/<fmt>')
@requires_role('asistencia', 'admin')
def export(fmt):
    votacion_id = request.args.get('votacion_id', type=int)
    conn = get_conn()
    if votacion_id:
        df = pd.read_sql('SELECT * FROM asistencia WHERE votacion_id=?', conn, params=(votacion_id,))
    else:
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
            fig, ax = plt.subplots(figsize=(4, 4))
            df['estado'].value_counts().plot.pie(ax=ax, autopct='%1.1f%%')
            ax.set_ylabel('')
            pdf.savefig(fig)
            plt.close(fig)

            fig2, ax2 = plt.subplots(figsize=(5, 3))
            df.groupby('estado')['acciones'].sum().plot.bar(ax=ax2)
            ax2.set_ylabel('Total Acciones')
            pdf.savefig(fig2)
            plt.close(fig2)
    else:
        return 'Formato no soportado', 400
    return send_file(fname, as_attachment=True)


@app.route('/api/votar', methods=['POST'])
@requires_role('votante')
def registrar_voto():
    """Registra un voto asociando número de acciones a una opción."""
    if not request.is_json:
        return jsonify({'error': 'JSON requerido'}), 400
    data = request.get_json(silent=True) or {}
    try:
        votacion_id = int(data.get('votacion_id'))
        pregunta_id = int(data.get('pregunta_id'))
        opcion_id = int(data.get('opcion_id'))
        acciones = int(data.get('acciones'))
    except (TypeError, ValueError):
        return jsonify({'error': 'Datos inválidos'}), 400
    # Verifica quórum antes de permitir votar
    total, activos, _ = resumen_acciones(votacion_id)
    conn = get_conn()
    q_row = conn.execute('SELECT quorum_minimo FROM votaciones WHERE id=?', (votacion_id,)).fetchone()
    conn.close()
    quorum_minimo = q_row['quorum_minimo'] if q_row else 0
    if total == 0 or (activos / total * 100) < quorum_minimo:
        return jsonify({'error': 'Quórum no alcanzado'}), 403
    with db_lock:
        conn = get_conn()
        conn.execute(
            'INSERT INTO votos (votacion_id, pregunta_id, opcion_id, acciones, user_id) VALUES (?,?,?,?,?)',
            (votacion_id, pregunta_id, opcion_id, acciones, g.user['id'])
        )
        conn.commit()
        conn.close()
    socketio.emit('voto_registrado', {
        'votacion_id': votacion_id,
        'pregunta_id': pregunta_id,
        'opcion_id': opcion_id,
        'acciones': acciones,
    })
    return jsonify({'status': 'ok'})


@app.route('/api/resultados/<int:votacion_id>')
@requires_role('votante', 'admin')
def resultados_votacion(votacion_id):
    """Resumen de resultados por pregunta basados en acciones activas."""
    total, activos, _ = resumen_acciones(votacion_id)
    conn = get_conn()
    rows = conn.execute(
        '''SELECT p.id AS pregunta_id, p.texto AS pregunta,
                  o.id AS opcion_id, o.texto AS opcion,
                  COALESCE(SUM(v.acciones),0) AS acciones
           FROM preguntas p
           JOIN opciones o ON o.pregunta_id = p.id
           LEFT JOIN votos v ON v.opcion_id = o.id
           WHERE p.votacion_id = ?
           GROUP BY o.id
           ORDER BY p.id, o.id''',
        (votacion_id,)
    ).fetchall()
    conn.close()
    preguntas = []
    current = None
    for r in rows:
        if not current or current['id'] != r['pregunta_id']:
            current = {'id': r['pregunta_id'], 'texto': r['pregunta'], 'opciones': []}
            preguntas.append(current)
        acc = r['acciones'] or 0
        pct = (acc / activos * 100) if activos else 0
        current['opciones'].append({'id': r['opcion_id'], 'texto': r['opcion'], 'acciones': acc, 'porcentaje': pct})
    return jsonify({'acciones_activas': activos, 'preguntas': preguntas})

if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG') == '1'
    socketio.run(app, host='0.0.0.0', port=5000, debug=debug_mode)
