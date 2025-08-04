// Dynamic creation of votaciones

document.addEventListener('DOMContentLoaded', () => {
  const preguntasContainer = document.getElementById('preguntas-container');
  const addPreguntaBtn = document.getElementById('add-pregunta');
  const form = document.getElementById('votacion-form');

  if (!form) return; // safeguard if not on page

  function addOpcion(container) {
    const opcionDiv = document.createElement('div');
    opcionDiv.className = 'opcion';

    const input = document.createElement('input');
    input.type = 'text';
    input.placeholder = 'Opción';
    opcionDiv.appendChild(input);

    const removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.textContent = '🗑️';
    removeBtn.className = 'remove-opcion';
    removeBtn.addEventListener('click', () => opcionDiv.remove());
    opcionDiv.appendChild(removeBtn);

    container.appendChild(opcionDiv);
  }

  function updatePreguntaLabels() {
    Array.from(preguntasContainer.children).forEach((p, idx) => {
      const label = p.querySelector('.pregunta-header span');
      if (label) label.textContent = `Pregunta ${idx + 1}:`;
    });
  }

  function createPregunta() {
    const preguntaDiv = document.createElement('div');
    preguntaDiv.className = 'pregunta';

    const header = document.createElement('div');
    header.className = 'pregunta-header';

    const title = document.createElement('span');
    header.appendChild(title);

    const removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.textContent = '🗑️';
    removeBtn.className = 'remove-pregunta';
    removeBtn.addEventListener('click', () => {
      preguntaDiv.remove();
      updatePreguntaLabels();
    });
    header.appendChild(removeBtn);

    preguntaDiv.appendChild(header);

    const inputPregunta = document.createElement('input');
    inputPregunta.type = 'text';
    inputPregunta.placeholder = 'Texto de la pregunta';
    inputPregunta.className = 'pregunta-texto';
    preguntaDiv.appendChild(inputPregunta);

    const opcionesDiv = document.createElement('div');
    opcionesDiv.className = 'opciones';
    preguntaDiv.appendChild(opcionesDiv);

    const addOpcionBtn = document.createElement('button');
    addOpcionBtn.type = 'button';
    addOpcionBtn.textContent = '+ Añadir opción';
    addOpcionBtn.className = 'add-opcion';
    addOpcionBtn.addEventListener('click', () => addOpcion(opcionesDiv));
    preguntaDiv.appendChild(addOpcionBtn);

    // add two default options
    addOpcion(opcionesDiv);
    addOpcion(opcionesDiv);

    preguntasContainer.appendChild(preguntaDiv);
    updatePreguntaLabels();
  }

  addPreguntaBtn.addEventListener('click', createPregunta);

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const nombre = document.getElementById('nombre_votacion').value;
    const fecha = document.getElementById('fecha').value;
    const preguntas = Array.from(preguntasContainer.children).map(p => {
      const texto = p.querySelector('.pregunta-texto').value;
      const opciones = Array.from(p.querySelectorAll('.opcion input')).map(i => i.value).filter(v => v);
      return { texto, opciones };
    }).filter(p => p.texto);

    const data = { nombre_votacion: nombre, fecha, preguntas };

    const resp = await fetch(form.action, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });

    if (resp.ok) {
      window.location.reload();
    } else {
      alert('Error al guardar');
    }
  });

  // start with one question
  createPregunta();
});
