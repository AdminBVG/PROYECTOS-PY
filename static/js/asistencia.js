// Control avanzado de asistencia
// Carga datos, permite modificar estados y guardar cambios

document.addEventListener('DOMContentLoaded', () => {
  const tbody = document.querySelector('#tablaAsistencia tbody');
  const summary = document.getElementById('summary');
  const search = document.getElementById('search');
  const filter = document.getElementById('filterEstado');

  let rows = [];

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
      tr.innerHTML = `
        <td>${r.accionista || ''}</td>
        <td>${r.representante || ''}</td>
        <td>${r.apoderado || ''}</td>
        <td>
          <select class="estado">
            <option value="PRESENCIAL" ${r.estado === 'PRESENCIAL' ? 'selected' : ''}>Presente</option>
            <option value="AUSENTE" ${r.estado === 'AUSENTE' ? 'selected' : ''}>Ausente</option>
            <option value="VIRTUAL" ${r.estado === 'VIRTUAL' ? 'selected' : ''}>Virtual</option>
          </select>
        </td>`;
      tbody.appendChild(tr);
      counts[r.estado] = (counts[r.estado] || 0) + 1;
    });
    summary.textContent = `${counts.PRESENCIAL || 0} presentes / ${counts.AUSENTE || 0} ausentes / ${counts.VIRTUAL || 0} virtual`;
  }

  function guardar() {
    const peticiones = [...tbody.querySelectorAll('tr')].map(tr => {
      const id = tr.dataset.id;
      const estado = tr.querySelector('select').value;
      return fetch(`/api/asistencia/${id}`, {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({estado})
      });
    });
    Promise.all(peticiones);
  }

  document.getElementById('markAll').addEventListener('click', () => {
    tbody.querySelectorAll('select.estado').forEach(s => s.value = 'PRESENCIAL');
  });
  document.getElementById('clearAll').addEventListener('click', () => {
    tbody.querySelectorAll('select.estado').forEach(s => s.value = 'AUSENTE');
  });
  document.getElementById('save').addEventListener('click', guardar);
  search.addEventListener('input', render);
  filter.addEventListener('change', render);

  // Reloj y auto guardado
  setInterval(() => {
    document.getElementById('clock').textContent = new Date().toLocaleTimeString();
  }, 1000);
  setInterval(guardar, 30000);

  load();
});
