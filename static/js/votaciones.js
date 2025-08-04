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

  function createPregunta(data = null) {
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
    if (data && data.texto) inputPregunta.value = data.texto;
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

    if (data && Array.isArray(data.opciones) && data.opciones.length) {
      data.opciones.forEach(opt => {
        const opcionDiv = document.createElement('div');
        opcionDiv.className = 'opcion';
        const input = document.createElement('input');
        input.type = 'text';
        input.placeholder = 'Opción';
        input.value = opt;
        opcionDiv.appendChild(input);
        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.textContent = '🗑️';
        removeBtn.className = 'remove-opcion';
        removeBtn.addEventListener('click', () => opcionDiv.remove());
        opcionDiv.appendChild(removeBtn);
        opcionesDiv.appendChild(opcionDiv);
      });
    } else {
      addOpcion(opcionesDiv);
      addOpcion(opcionesDiv);
    }

    preguntasContainer.appendChild(preguntaDiv);
    updatePreguntaLabels();
  }

  addPreguntaBtn.addEventListener('click', createPregunta);

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const nombre = document.getElementById('nombre_votacion').value;
    const fecha = document.getElementById('fecha').value;
    const quorum = parseFloat(document.getElementById('quorum_minimo').value || '0');
    const preguntas = Array.from(preguntasContainer.children).map(p => {
      const texto = p.querySelector('.pregunta-texto').value;
      const opciones = Array.from(p.querySelectorAll('.opcion input')).map(i => i.value).filter(v => v);
      return { texto, opciones };
    }).filter(p => p.texto);

    const votantes = Array.from(document.querySelectorAll('.rol-votante:checked')).map(cb => cb.value);
    const asistentes = Array.from(document.querySelectorAll('.rol-asistencia:checked')).map(cb => cb.value);
    const data = { nombre_votacion: nombre, fecha, quorum_minimo: quorum, preguntas, votantes, asistentes };

    const resp = await fetch(form.action, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });

    if (resp.ok) {
      window.location.href = '/panel_admin';
    } else {
      alert('Error al guardar');
    }
  });

  function loadInitial() {
    if (!window.initialData) {
      createPregunta();
      updateResumenRoles();
      return;
    }
    document.getElementById('nombre_votacion').value = window.initialData.nombre || '';
    if (window.initialData.fecha) document.getElementById('fecha').value = window.initialData.fecha;
    preguntasContainer.innerHTML = '';
    (window.initialData.preguntas || []).forEach(p => createPregunta(p));
    document.querySelectorAll('.rol-votante').forEach(cb => {
      if ((window.initialData.votantes || []).includes(parseInt(cb.value))) cb.checked = true;
    });
    document.querySelectorAll('.rol-asistencia').forEach(cb => {
      if ((window.initialData.asistentes || []).includes(parseInt(cb.value))) cb.checked = true;
    });
    document.getElementById('quorum_minimo').value = window.initialData.quorum_minimo || 0;
    updateResumenRoles();
  }

  document.addEventListener('change', (e) => {
    if (e.target.classList && (e.target.classList.contains('rol-asistencia') || e.target.classList.contains('rol-votante')))
      updateResumenRoles();
  });

  function updateResumenRoles() {
    const asistentes = document.querySelectorAll('.rol-asistencia:checked').length;
    const votantes = document.querySelectorAll('.rol-votante:checked').length;
    const resumen = document.getElementById('resumenRoles');
    if (resumen) resumen.textContent = `Asistencia: ${asistentes} | Votación: ${votantes}`;
  }

  loadInitial();
});
