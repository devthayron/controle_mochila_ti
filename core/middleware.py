"""
middleware.py — Intercepta todas as requisições e redireciona o usuário
para a tela de troca de senha obrigatória enquanto must_change_password=True.

Registro em settings.py:
    MIDDLEWARE = [
        ...
        'core.middleware.ForcePasswordChangeMiddleware',
    ]
"""

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse

# URLs liberadas mesmo com must_change_password=True
_ALLOWED_URLS = frozenset([
    "/login/",
    "/logout/",
    "/trocar-senha/",
])

# Prefixos sempre liberados (static, admin login)
_ALLOWED_PREFIXES = ("/static/", "/favicon")


class ForcePasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._deve_bloquear(request):
            return redirect(reverse("trocar_senha"))
        return self.get_response(request)

    def _deve_bloquear(self, request) -> bool:
        user = request.user

        # Não autenticado → deixa passar (LoginRequiredMixin cuida)
        if not user.is_authenticated:
            return False

        # URL já é a de troca de senha ou logout
        path = request.path
        if path in _ALLOWED_URLS:
            return False

        # Prefixos liberados (static files, etc.)
        if any(path.startswith(p) for p in _ALLOWED_PREFIXES):
            return False

        # Verifica flag
        try:
            return user.password_policy.must_change_password
        except Exception:
            # Se não há policy, não bloqueia (usuários legados)
            return False
