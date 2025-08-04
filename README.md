# PROYECTOS-PY

Sistema de asistencia y votaciones construido con Flask y Socket.IO.

## Requisitos

- Python 3.12
- Flask 2.x
- flask-socketio 5.x
- python-socketio 5.x
- pandas
- (Opcional) matplotlib para exportar a PDF

## Instalación

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt  # si existe
```

Si no hay un `requirements.txt`, instala manualmente:

```bash
pip install flask flask-socketio==5.* python-socketio==5.* pandas
```

## Inicializar base de datos

```bash
python db_init.py
```

## Ejecución

```bash
python app.py
```

La aplicación se sirve en `http://localhost:5000`.

## Roles

- **admin**: gestiona usuarios y votaciones.
- **asistencia**: importa y controla estados de asistentes.
- **votante**: Secretaría General que registra votos.

## Flujo de uso

1. El administrador crea usuarios y votaciones desde su panel.
2. El rol de asistencia importa el Excel de participantes y marca estados
   (PRESENCIAL, VIRTUAL o AUSENTE) individualmente o en bloque.
3. Los cambios de asistencia se reflejan en tiempo real con Socket.IO y se
   pueden exportar a Excel, CSV o PDF.
4. El rol votante registra los votos sobre las preguntas de cada votación.
   Los votos se contabilizan respecto a las acciones representadas por
   asistentes activos (PRESENCIAL + VIRTUAL). El quórum y los porcentajes se
   calculan usando únicamente estas acciones activas.

## Importar asistentes

Desde el panel de asistencia se carga un archivo Excel con las columnas
`ACCIONISTA`, `REPRESENTANTE LEGAL`, `APODERADO`, `No. ACCIONES` y
`ASISTENCIA`. Los estados se normalizan a PRESENCIAL, VIRTUAL o AUSENTE.

## Crear votaciones

El administrador dispone de un editor visual tipo formulario para agregar
preguntas y opciones dinámicamente. La estructura completa se guarda en
JSON y se asignan usuarios participantes.

## Registrar asistencia y votos

- El rol de asistencia cambia estados en la tabla interactiva.
- El rol votante ingresa al panel de votaciones y registra los votos.

### Endpoints relevantes

- `GET /api/asistencia/resumen`: devuelve acciones por estado y quórum.
- `POST /api/votar`: registra votos indicando votación, pregunta, opción y
  número de acciones.
- `GET /api/resultados/<votacion_id>`: resume resultados por pregunta y
  porcentaje sobre acciones activas.

## Créditos y dependencias

Proyecto base desarrollado para demostración educativa. Usa Flask,
flask-socketio, pandas y (opcionalmente) matplotlib.

