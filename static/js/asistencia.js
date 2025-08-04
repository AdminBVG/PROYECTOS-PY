// Control avanzado de asistencia con importación y gráficos en tiempo real

document.addEventListener('DOMContentLoaded', () => {
  const socket = io();
  const tbody = document.querySelector('#tablaAsistencia tbody');
  const summary = document.getElementById('summary');
  const search = document.getElementById('search');
  const filter = document.getElementById('filterEstado');
  const quorumInput = document.getElementById('quorum');

  const uploadInput = document.getElementById('fileInput');
  const uploadBtn = document.getElementById('uploadBtn');
  const templateBtn = document.getElementById('templateBtn');

  const pieChart = new Chart(document.getElementById('pieChart').getContext('2d'), {
    type: 'pie',
    data: {
      labels: ['Presencial', 'Virtual', 'Ausente'],
      datasets: [{ data: [0, 0, 0], backgroundColor: ['#4CAF50', '#2196F3', '#f44336'] }]
    },
    options: { responsive: true, maintainAspectRatio: false }
  });

  const barChart = new Chart(document.getElementById('barChart').getContext('2d'), {
    type: 'bar',
    data: {
      labels: ['Presencial', 'Virtual', 'Ausente'],
      datasets: [{ label: 'Acciones', data: [0, 0, 0], backgroundColor: ['#4CAF50', '#2196F3', '#f44336'] }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: { y: { beginAtZero: true } }
    }
  });

  let rows = [];
  const changed = new Map();

  function load() {
    fetch('/api/asistencia')
      .then(r => r.json())
      .then(data => { rows = data; render(); });
  }

  function render() {
    tbody.innerHTML = '';
    const counts = { PRESENCIAL: 0, VIRTUAL: 0, AUSENTE: 0 };
    const acciones = { PRESENCIAL: 0, VIRTUAL: 0, AUSENTE: 0 };
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
        <td>${r.acciones || 0}</td>
        <td>
          <select class="estado">
            <option value="PRESENCIAL" ${currentEstado === 'PRESENCIAL' ? 'selected' : ''}>Presente</option>
            <option value="VIRTUAL" ${currentEstado === 'VIRTUAL' ? 'selected' : ''}>Virtual</option>
            <option value="AUSENTE" ${currentEstado === 'AUSENTE' ? 'selected' : ''}>Ausente</option>
          </select>
        </td>`;
      const select = tr.querySelector('select');
      select.addEventListener('change', () => {
        changed.set(r.id, select.value);
        render();
      });
      tbody.appendChild(tr);
      counts[currentEstado] = (counts[currentEstado] || 0) + 1;
      acciones[currentEstado] = (acciones[currentEstado] || 0) + (r.acciones || 0);
    });
    summary.textContent = `${counts.PRESENCIAL} presenciales / ${counts.VIRTUAL} virtuales / ${counts.AUSENTE} ausentes`;

    renderCharts(counts, acciones);

    const totalPresentes = counts.PRESENCIAL + counts.VIRTUAL;
    const quorum = parseInt(quorumInput.value || '0', 10);
    quorumInput.style.borderColor = totalPresentes >= quorum ? 'green' : 'red';
  }

  function renderCharts(counts, acciones) {
    pieChart.data.datasets[0].data = [counts.PRESENCIAL, counts.VIRTUAL, counts.AUSENTE];
    pieChart.update();
    barChart.data.datasets[0].data = [acciones.PRESENCIAL, acciones.VIRTUAL, acciones.AUSENTE];
    barChart.update();
  }

  socket.on('estado_changed', ({ id, estado }) => {
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
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ estado })
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
    render();
  });
  document.getElementById('markVirtual').addEventListener('click', () => {
    tbody.querySelectorAll('select.estado').forEach(s => {
      s.value = 'VIRTUAL';
      changed.set(s.closest('tr').dataset.id, s.value);
    });
    render();
  });
  document.getElementById('clearAll').addEventListener('click', () => {
    tbody.querySelectorAll('select.estado').forEach(s => {
      s.value = 'AUSENTE';
      changed.set(s.closest('tr').dataset.id, s.value);
    });
    render();
  });

  document.getElementById('exportExcel').addEventListener('click', () => window.location = '/export/excel');
  document.getElementById('exportCsv').addEventListener('click', () => window.location = '/export/csv');
  document.getElementById('exportPdf').addEventListener('click', () => window.location = '/export/pdf');
  if (templateBtn) templateBtn.addEventListener('click', () => window.location = '/template/asistencia');

  uploadBtn.addEventListener('click', () => {
    const file = uploadInput.files[0];
    if (!file) return alert('Seleccione un archivo');
    const fd = new FormData();
    fd.append('file', file);
    fetch('/upload', { method: 'POST', body: fd })
      .then(r => r.json())
      .then(res => {
        if (res.ok) {
          alert('Importación exitosa');
          load();
        } else {
          alert(res.error || 'Error al importar');
        }
      });
  });

  document.getElementById('save').addEventListener('click', guardar);
  search.addEventListener('input', render);
  filter.addEventListener('change', render);
  quorumInput.addEventListener('input', render);

  // Reloj y auto guardado
  setInterval(() => {
    document.getElementById('clock').textContent = new Date().toLocaleTimeString();
  }, 1000);
  setInterval(() => {
    if (changed.size) guardar();
  }, 30000);

  load();
});
