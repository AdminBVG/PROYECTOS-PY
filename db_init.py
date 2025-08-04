import sqlite3

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
conn.commit()
conn.close()
print('✅ DB inicializada en db.sqlite')