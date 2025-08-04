// Control avanzado de asistencia
// Carga datos, permite modificar estados y guardar cambios

document.addEventListener('DOMContentLoaded', () => {
  const socket = io();
  const tbody = document.querySelector('#tablaAsistencia tbody');
  const summary = document.getElementById('summary');
  const search = document.getElementById('search');
  const filter = document.getElementById('filterEstado');

  let rows = [];
  const changed = new Map();

  function load() {
    fetch('/api/asistencia')
      .then(r => r.json())
      .then(data => {
        rows = data;
        render();
      });
  }

  function render() {
    tbody.innerHTML = '';
    const counts = {PRESENCIAL:0, AUSENTE:0, VIRTUAL:0};
    rows.forEach(r => {
      if (filter.value && r.estado !== filter.value) return;
      const cadena = `${r.accionista || ''} ${r.representante || ''} ${r.apoderado || ''}`.toLowerCase();
      if (search.value && !cadena.includes(search.value.toLowerCase())) return;
      const tr = document.createElement('tr');
      tr.dataset.id = r.id;
      const currentEstado = changed.get(r.id) || r.estado;
      tr.innerHTML = `
        <td>${r.accionista || ''}</td>
        <td>${r.representante || ''}</td>
        <td>${r.apoderado || ''}</td>
        <td>
          <select class="estado">
            <option value="PRESENCIAL" ${currentEstado === 'PRESENCIAL' ? 'selected' : ''}>Presente</option>
            <option value="AUSENTE" ${currentEstado === 'AUSENTE' ? 'selected' : ''}>Ausente</option>
            <option value="VIRTUAL" ${currentEstado === 'VIRTUAL' ? 'selected' : ''}>Virtual</option>
          </select>
        </td>`;
      const select = tr.querySelector('select');
      select.addEventListener('change', () => {
        changed.set(r.id, select.value);
      });
      tbody.appendChild(tr);
      counts[currentEstado] = (counts[currentEstado] || 0) + 1;
    });
    summary.textContent = `${counts.PRESENCIAL || 0} presentes / ${counts.AUSENTE || 0} ausentes / ${counts.VIRTUAL || 0} virtual`;
  }

  socket.on('estado_changed', ({id, estado}) => {
    const row = tbody.querySelector(`tr[data-id="${id}"]`);
    const record = rows.find(r => r.id === id);
    if (record) record.estado = estado;
    if (row) {
      const select = row.querySelector('select.estado');
      if (select) select.value = estado;
    }
    render();
  });

  async function guardar() {
    if (!changed.size) return;
    const peticiones = Array.from(changed.entries()).map(([id, estado]) =>
      fetch(`/api/asistencia/${id}`, {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({estado})
      })
    );
    try {
      await Promise.all(peticiones);
      changed.clear();
    } catch (err) {
      console.error(err);
      alert('Error al guardar cambios');
    }
  }

  document.getElementById('markAll').addEventListener('click', () => {
    tbody.querySelectorAll('select.estado').forEach(s => {
      s.value = 'PRESENCIAL';
      changed.set(s.closest('tr').dataset.id, s.value);
    });
  });
  document.getElementById('clearAll').addEventListener('click', () => {
    tbody.querySelectorAll('select.estado').forEach(s => {
      s.value = 'AUSENTE';
      changed.set(s.closest('tr').dataset.id, s.value);
    });
  });
  document.getElementById('save').addEventListener('click', guardar);
  search.addEventListener('input', render);
  filter.addEventListener('change', render);

  // Reloj y auto guardado
  setInterval(() => {
    document.getElementById('clock').textContent = new Date().toLocaleTimeString();
  }, 1000);
  setInterval(() => {
    if (changed.size) guardar();
  }, 30000);

  load();
});
