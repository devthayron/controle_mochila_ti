/* base.js — Controle de Mochila TI */

// ── SIDEBAR TOGGLE ──────────────────────────────────────
function toggleSidebar() {
    document.getElementById('sidebar').classList.toggle('open');
}

// Close sidebar when clicking outside on mobile
document.addEventListener('click', function(e) {
    const sidebar = document.getElementById('sidebar');
    if (window.innerWidth <= 768 &&
        sidebar.classList.contains('open') &&
        !sidebar.contains(e.target) &&
        !e.target.closest('.hamburger')) {
        sidebar.classList.remove('open');
    }
});

// ── LOGOUT ──────────────────────────────────────────────
document.querySelectorAll('.js-logout').forEach(el => {
    el.addEventListener('click', function(e) {
        e.preventDefault();
        document.getElementById('logout-form').submit();
    });
});

// ── AUTO-DISMISS ALERTS ─────────────────────────────────
document.querySelectorAll('.alert').forEach(alert => {
    // Auto-dismiss success alerts after 5s
    if (alert.classList.contains('alert-success')) {
        setTimeout(() => {
            alert.style.transition = 'opacity .4s';
            alert.style.opacity    = '0';
            setTimeout(() => alert.remove(), 400);
        }, 5000);
    }
});

// ── ACTIVE NAV HIGHLIGHT (fallback) ─────────────────────
(function() {
    const path  = window.location.pathname;
    document.querySelectorAll('.nav-item').forEach(link => {
        if (link.getAttribute('href') === path) {
            link.classList.add('active');
        }
    });
})();
