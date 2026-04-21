"""
mixins.py — Mixins de autenticação e autorização baseados em Groups + Permissions.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect

from . import permissions as perms


# ──────────────────────────────────────────────
# BASE MIXIN — injeta contexto de permissões
# ──────────────────────────────────────────────

class PermContextMixin(LoginRequiredMixin):
    """
    Injeta `user_perms` no contexto de templates.
    """

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        u = self.request.user

        context["user_perms"] = {
            "pode_editar":           perms._pode_editar(u),
            "is_admin":              perms._is_admin(u),
            "is_supervisor":         perms._is_supervisor(u),
            "pode_acessar_usuarios": perms.pode_acessar_area_usuarios(u),
        }

        return context


# ──────────────────────────────────────────────
# SUPERVISOR MIXIN — Admin ou Supervisor
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
# USUARIO AREA MIXIN — Admin ou Supervisor (lista/cria)
# ──────────────────────────────────────────────

class UsuarioAreaMixin(PermContextMixin):
    """Acesso à área de usuários: Admin e Supervisor."""

    def dispatch(self, request, *args, **kwargs):
        result = super().dispatch(request, *args, **kwargs)
        if not request.user.is_authenticated:
            return result
        if not perms.pode_acessar_area_usuarios(request.user):
            messages.error(request, "Você não tem permissão para acessar esta área.")
            return redirect("dashboard")
        return result


# ──────────────────────────────────────────────
# ADMIN MIXIN — somente Admin
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