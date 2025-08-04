// Personalización de interfaz: logo y modo oscuro

document.addEventListener('DOMContentLoaded', () => {
  const logoDisplay = document.getElementById('logoDisplay');
  const logoInput = document.getElementById('logoInput');
  const themeToggle = document.getElementById('themeToggle');
  const body = document.body;

  // Cargar logo guardado
  const savedLogo = localStorage.getItem('customLogo');
  if (savedLogo && logoDisplay) {
    logoDisplay.src = savedLogo;
  }

  if (logoInput) {
    logoInput.addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        logoDisplay.src = reader.result;
        localStorage.setItem('customLogo', reader.result);
      };
      reader.readAsDataURL(file);
    });
  }

  // Modo oscuro
  const savedDark = localStorage.getItem('darkMode');
  if (savedDark === 'true') {
    body.classList.add('dark');
  }
  if (themeToggle) {
    const updateText = () => {
      themeToggle.textContent = body.classList.contains('dark') ? 'Modo claro' : 'Modo oscuro';
    };
    updateText();
    themeToggle.addEventListener('click', () => {
      body.classList.toggle('dark');
      localStorage.setItem('darkMode', body.classList.contains('dark'));
      updateText();
    });
  }
});
