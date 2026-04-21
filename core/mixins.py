from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect

from . import permissions as perms


# ──────────────────────────────────────────────
# SUPERVISOR MIXIN
# ──────────────────────────────────────────────

class SupervisorRequiredMixin(LoginRequiredMixin):
    """Requer permissão de Supervisor ou Admin."""

    def dispatch(self, request, *args, **kwargs):
        if not perms.pode_editar(request.user):
            messages.error(request, "Você não tem permissão para realizar essa ação.")
            return redirect("dashboard")

        return super().dispatch(request, *args, **kwargs)


# ──────────────────────────────────────────────
# USUARIO AREA MIXIN
# ──────────────────────────────────────────────

class UsuarioAreaMixin(LoginRequiredMixin):
    """Acesso à área de usuários (Admin e Supervisor)."""

    def dispatch(self, request, *args, **kwargs):
        if not perms.pode_acessar_area_usuarios(request.user):
            messages.error(request, "Você não tem permissão para acessar esta área.")
            return redirect("dashboard")

        return super().dispatch(request, *args, **kwargs)


# ──────────────────────────────────────────────
# ADMIN MIXIN
# ──────────────────────────────────────────────

class AdminRequiredMixin(LoginRequiredMixin):
    """Somente Admin."""

    def dispatch(self, request, *args, **kwargs):
        if not perms.is_admin(request.user):
            messages.error(request, "Acesso restrito a administradores.")
            return redirect("dashboard")

        return super().dispatch(request, *args, **kwargs)