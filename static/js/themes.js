document.addEventListener("DOMContentLoaded", function () {
    const themeToggle = document.querySelector('.theme-toggle');
    const currentTheme = localStorage.getItem('theme') || 'dark'; // Prendi il tema dal localStorage o usa il default 'dark'
    document.documentElement.setAttribute('data-bs-theme', currentTheme);
    if (currentTheme === 'light') {
        themeToggle.checked = false; // Se il tema corrente è "light", deseleziona il toggle
    }

    themeToggle.addEventListener('change', function () {
        let selectedTheme = this.checked ? 'dark' : 'light';
        document.documentElement.setAttribute('data-bs-theme', selectedTheme);
        localStorage.setItem('theme', selectedTheme); // Salva la selezione nel localStorage
    });
});
