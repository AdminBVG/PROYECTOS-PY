import sqlite3
from werkzeug.security import generate_password_hash

# Crea o abre la base
conn = sqlite3.connect('db.sqlite')
c = conn.cursor()

# Tabla de asistencia
c.execute('''
CREATE TABLE IF NOT EXISTS asistencia (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    accionista TEXT,
    representante TEXT,
    apoderado TEXT,
    acciones INTEGER,
    estado TEXT CHECK(estado IN ('PRESENCIAL','VIRTUAL','AUSENTE')) NOT NULL DEFAULT 'AUSENTE'
)
''')

# Usuarios
c.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    role TEXT CHECK(role IN ('admin','asistencia','votante')) NOT NULL
)
''')

# Votaciones
c.execute('''
CREATE TABLE IF NOT EXISTS votaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL
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

# Asignaciones de usuarios a votaciones
c.execute('''
CREATE TABLE IF NOT EXISTS votacion_usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    votacion_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    rol TEXT CHECK(rol IN ('asistencia','votante')) NOT NULL,
    FOREIGN KEY(votacion_id) REFERENCES votaciones(id),
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
