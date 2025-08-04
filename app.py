import os
import sqlite3
import threading
from flask import Flask, render_template, request, jsonify, send_file
from flask_socketio import SocketIO, emit
import pandas as pd
from werkzeug.utils import secure_filename

# Opcional PDF
try:
    from matplotlib.backends.backend_pdf import PdfPages
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXT = {'xls','xlsx'}
DB_PATH = 'db.sqlite'

db_lock = threading.Lock()

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
socketio = SocketIO(app)

# Apoyo SQLite con WAL y mayor timeout
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    return conn

# --- Rutas ---
@app.route('/')
def index():
    return render_template('index.html')

# Subida de Excel
@app.route('/upload', methods=['POST'])
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
    # Leer Excel y sanitizar datos
    try:
        df = pd.read_excel(path)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    # Normalizar estados y evitar constraint error
    df['ASISTENCIA'] = df.get('ASISTENCIA', '').astype(str).str.strip().str.upper()
    df['ASISTENCIA'] = df['ASISTENCIA'].where(df['ASISTENCIA'].isin(['PRESENCIAL','VIRTUAL','AUSENTE']), 'AUSENTE')
    # Volcar a SQLite con lock y garantizando cierre de conexión
    with db_lock:
        conn = get_conn()
        try:
            conn.execute('DELETE FROM asistencia')
            for _, r in df.iterrows():
                accionista = r.get('ACCIONISTA')
                representante = r.get('REPRESENTANTE LEGAL')
                apoderado = r.get('APODERADO')
                acciones = int(r.get('No. ACCIONES', 0) or 0)
                estado = r['ASISTENCIA']
                conn.execute(
                    'INSERT INTO asistencia (accionista,representante,apoderado,acciones,estado) VALUES (?,?,?,?,?)',
                    (accionista, representante, apoderado, acciones, estado)
                )
            conn.commit()
        finally:
            conn.close()
    return jsonify({'ok': True})
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
    # Leer Excel
    try:
        df = pd.read_excel(path)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    # Volcar a SQLite, protegido por lock
    with db_lock:
        conn = get_conn()
        conn.execute('DELETE FROM asistencia')
        for _, r in df.iterrows():
            conn.execute(
                'INSERT INTO asistencia (accionista,representante,apoderado,acciones,estado) VALUES (?,?,?,?,?)',
                (
                    r.get('ACCIONISTA'),
                    r.get('REPRESENTANTE LEGAL'),
                    r.get('APODERADO'),
                    int(r.get('No. ACCIONES', 0)),
                    str(r.get('ASISTENCIA', 'AUSENTE'))
                )
            )
        conn.commit()
        conn.close()
    return jsonify({'ok': True})

# Leer tabla en JSON
@app.route('/api/asistencia')
def get_asistencia():
    conn = get_conn()
    rows = conn.execute('SELECT * FROM asistencia').fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

# Actualizar estado
@app.route('/api/asistencia/<int:id>', methods=['POST'])
def update_asistencia(id):
    new_estado = request.json.get('estado')
    with db_lock:
        conn = get_conn()
        conn.execute('UPDATE asistencia SET estado = ? WHERE id = ?', (new_estado, id))
        conn.commit()
        conn.close()
    socketio.emit('estado_changed', {'id': id, 'estado': new_estado})
    return ('', 204)

# Exportaciones
@app.route('/export/<fmt>')
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