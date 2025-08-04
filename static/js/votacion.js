document.addEventListener('DOMContentLoaded', () => {
  const app = document.getElementById('votacionApp');
  const votacionId = app.dataset.votacion;
  let asistentes = [];
  let preguntas = [];

  async function load() {
    const [a, p] = await Promise.all([
      fetch(`/api/votacion/${votacionId}/asistentes`).then(r => r.json()),
      fetch(`/api/votacion/${votacionId}/preguntas`).then(r => r.json())
    ]);
    asistentes = a;
    preguntas = p;
    render();
  }

  function render() {
    app.innerHTML = '';
    preguntas.forEach(p => {
      const div = document.createElement('div');
      div.className = 'pregunta';
      div.innerHTML = `<h3>${p.texto}</h3>`;
      const setAll = document.createElement('select');
      setAll.innerHTML = `<option value="">Asignar a todos...</option>` +
        p.opciones.map(o => `<option value="${o.id}">${o.texto}</option>`).join('');
      setAll.addEventListener('change', () => {
        div.querySelectorAll('select.voto').forEach(s => { s.value = setAll.value; });
        updateResumen(div, p);
      });
      div.appendChild(setAll);

      const table = document.createElement('table');
      const thead = `<tr><th>Nombre</th><th>Voto</th></tr>`;
      table.innerHTML = `<thead>${thead}</thead>`;
      const tbody = document.createElement('tbody');
      asistentes.forEach(a => {
        const tr = document.createElement('tr');
        tr.dataset.acciones = a.acciones;
        const nombre = a.accionista || a.representante || a.apoderado || '';
        tr.innerHTML = `<td>${nombre}</td>`;
        const sel = document.createElement('select');
        sel.className = 'voto';
        sel.innerHTML = `<option value="">--</option>` +
          p.opciones.map(o => `<option value="${o.id}">${o.texto}</option>`).join('');
        sel.addEventListener('change', () => updateResumen(div, p));
        tr.appendChild(sel);
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      div.appendChild(table);

      const resumen = document.createElement('div');
      resumen.className = 'resumen';
      div.appendChild(resumen);

      const btn = document.createElement('button');
      btn.textContent = 'Guardar votos';
      btn.addEventListener('click', () => guardar(p, div));
      div.appendChild(btn);

      const key = `votacion_${votacionId}_p${p.id}`;
      if (localStorage.getItem(key)) {
        div.classList.add('votada');
        btn.disabled = true;
      }

      app.appendChild(div);
      updateResumen(div, p);
    });
  }

  function updateResumen(div, p) {
    const counts = {};
    div.querySelectorAll('select.voto').forEach(s => {
      counts[s.value] = (counts[s.value] || 0) + 1;
    });
    const res = div.querySelector('.resumen');
    res.textContent = p.opciones.map(o => `${o.texto}: ${counts[o.id] || 0}`).join(' | ');
  }

  async function guardar(p, div) {
    const key = `votacion_${votacionId}_p${p.id}`;
    const peticiones = [];
    div.querySelectorAll('tbody tr').forEach(tr => {
      const opcion = tr.querySelector('select.voto').value;
      if (!opcion) return;
      const acciones = parseInt(tr.dataset.acciones || '0', 10);
      peticiones.push(fetch('/api/votar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          votacion_id: votacionId,
          pregunta_id: p.id,
          opcion_id: parseInt(opcion,10),
          acciones
        })
      }));
    });
    try {
      await Promise.all(peticiones);
      localStorage.setItem(key, '1');
      div.classList.add('votada');
      div.querySelector('button').disabled = true;
      alert('Votos registrados');
    } catch (e) {
      alert('Error al registrar votos');
    }
  }

  load();
});
