"""
mixins.py — Mixins de autenticação e autorização baseados em Groups + Permissions.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect

from . import permissions as perms


# ──────────────────────────────────────────────
# BASE MIXIN
# ──────────────────────────────────────────────

class PermContextMixin(LoginRequiredMixin):
    """
    Injeta `user_perms` e `user_profile` (shim) no contexto de templates.
    """

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        u = self.request.user
        context["user_perms"] = {
            "pode_editar":             perms._pode_editar(u),
            "is_admin":                perms._is_admin(u),
            "is_supervisor":           perms._is_supervisor(u),
            "pode_gerenciar_usuarios": perms.pode_gerenciar_usuarios(u),
        }
        context["user_profile"] = _LegacyProfileShim(u)
        return context


class _LegacyProfileShim:
    """Compatibilidade com templates que ainda usam user_profile.*"""

    def __init__(self, user):
        self._user = user

    @property
    def pode_editar(self):
        return perms._pode_editar(self._user)

    @property
    def is_admin(self):
        return perms._is_admin(self._user)

    @property
    def is_supervisor(self):
        return perms._is_supervisor(self._user)

    @property
    def is_usuario(self):
        return not perms._pode_editar(self._user)


# ──────────────────────────────────────────────
# SUPERVISOR MIXIN
# ──────────────────────────────────────────────

class SupervisorRequiredMixin(PermContextMixin):
    """Requer permissão de edição (Supervisor ou Admin)."""

    def dispatch(self, request, *args, **kwargs):
        result = super().dispatch(request, *args, **kwargs)
        if not request.user.is_authenticated:
            return result
        if not perms._pode_editar(request.user):
            messages.error(request, "Você não tem permissão para realizar essa ação.")
            return redirect("dashboard")
        return result


# ──────────────────────────────────────────────
# ADMIN MIXIN
# ──────────────────────────────────────────────

class AdminRequiredMixin(PermContextMixin):
    """Requer permissão de administrador."""

    def dispatch(self, request, *args, **kwargs):
        result = super().dispatch(request, *args, **kwargs)
        if not request.user.is_authenticated:
            return result
        if not perms._is_admin(request.user):
            messages.error(request, "Acesso restrito a administradores.")
            return redirect("dashboard")
        return result


# ──────────────────────────────────────────────
# ALIAS RETROCOMPATÍVEL
# ──────────────────────────────────────────────

NivelMixin = PermContextMixin