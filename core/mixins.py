"""
mixins.py — Mixins de autenticação e autorização baseados em Groups + Permissions.

NÃO acessam UserProfile.nivel.
Usam has_perm() via permissions.py.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from . import permissions as perms


# ──────────────────────────────────────────────
# BASE MIXIN — injeta flags de permissão no contexto
# ──────────────────────────────────────────────

class PermContextMixin(LoginRequiredMixin):
    """
    Injeta `user_perms` no contexto de todos os templates.
    Substitui o antigo `user_profile` nos templates.

    Uso nos templates:
        {% if user_perms.pode_editar %}
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
        # Retrocompatibilidade: mantém user_profile.pode_editar funcionando
        # nos templates que ainda não foram migrados.
        context["user_profile"] = _LegacyProfileShim(u)
        return context


class _LegacyProfileShim:
    """
    Shim temporário para manter templates antigos funcionando
    enquanto são migrados para {{ user_perms }}.
    Remove quando todos os templates usarem user_perms.
    """

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

# Mantém imports antigos funcionando sem alterar views legadas:
NivelMixin = PermContextMixin
