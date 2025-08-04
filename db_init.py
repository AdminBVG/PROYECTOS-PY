import sqlite3
from werkzeug.security import generate_password_hash

# Crea o abre la base
conn = sqlite3.connect('db.sqlite')
c = conn.cursor()
# Usuarios
c.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    cedula TEXT UNIQUE,
    role TEXT CHECK(role IN ('admin','asistencia','votante')) NOT NULL
)
''')

# Asegura columnas opcionales en instalaciones existentes
# Verifica si la columna 'cedula' existe y la agrega si falta
existing_cols = [row[1] for row in c.execute("PRAGMA table_info(users)").fetchall()]
if 'cedula' not in existing_cols:
    try:
        c.execute("ALTER TABLE users ADD COLUMN cedula TEXT UNIQUE")
        print("✅ Columna 'cedula' añadida a la tabla users")
    except sqlite3.OperationalError as exc:
        print(f"❌ No se pudo crear la columna 'cedula': {exc}")
        print("Ejecute manualmente: ALTER TABLE users ADD COLUMN cedula TEXT UNIQUE")
        conn.close()
        raise SystemExit(1)

# Votaciones
c.execute('''
CREATE TABLE IF NOT EXISTS votaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    fecha TEXT,
    quorum_minimo REAL DEFAULT 0
)
''')

# Asegura columnas opcionales
for col, definition in (
    ('fecha', "ALTER TABLE votaciones ADD COLUMN fecha TEXT"),
    ('quorum_minimo', "ALTER TABLE votaciones ADD COLUMN quorum_minimo REAL DEFAULT 0"),
):
    try:
        c.execute(definition)
    except sqlite3.OperationalError:
        pass

# Tabla de asistencia (por votación)
c.execute('''
CREATE TABLE IF NOT EXISTS asistencia (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    votacion_id INTEGER NOT NULL,
    accionista TEXT,
    representante TEXT,
    apoderado TEXT,
    acciones INTEGER,
    estado TEXT CHECK(estado IN ('PRESENCIAL','VIRTUAL','AUSENTE')) NOT NULL DEFAULT 'AUSENTE',
    FOREIGN KEY(votacion_id) REFERENCES votaciones(id)
)
''')

# Preguntas
c.execute('''
CREATE TABLE IF NOT EXISTS preguntas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    votacion_id INTEGER NOT NULL,
    texto TEXT NOT NULL,
    FOREIGN KEY(votacion_id) REFERENCES votaciones(id)
)
''')

# Opciones por pregunta
c.execute('''
CREATE TABLE IF NOT EXISTS opciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pregunta_id INTEGER NOT NULL,
    texto TEXT NOT NULL,
    FOREIGN KEY(pregunta_id) REFERENCES preguntas(id)
)
''')

# Asignaciones de usuarios a votaciones
c.execute('''
CREATE TABLE IF NOT EXISTS usuarios_votacion (
    votacion_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    rol TEXT CHECK(rol IN ('asistencia','votante')) NOT NULL,
    PRIMARY KEY (votacion_id, user_id, rol),
    FOREIGN KEY(votacion_id) REFERENCES votaciones(id),
    FOREIGN KEY(user_id) REFERENCES users(id)
)
''')

# Registro de votos por pregunta/opción
c.execute('''
CREATE TABLE IF NOT EXISTS votos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    votacion_id INTEGER NOT NULL,
    pregunta_id INTEGER NOT NULL,
    opcion_id INTEGER NOT NULL,
    acciones INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(votacion_id) REFERENCES votaciones(id),
    FOREIGN KEY(pregunta_id) REFERENCES preguntas(id),
    FOREIGN KEY(opcion_id) REFERENCES opciones(id),
    FOREIGN KEY(user_id) REFERENCES users(id)
)
''')

# Usuario administrador por defecto
c.execute("SELECT id FROM users WHERE username='admin'")
if not c.fetchone():
    c.execute(
        "INSERT INTO users (username, password, role) VALUES (?,?,?)",
        ('admin', generate_password_hash('admin'), 'admin')
    )

conn.commit()
conn.close()
print('✅ DB inicializada en db.sqlite')
