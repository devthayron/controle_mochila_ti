"""
permissions.py — Camada de controle de acesso centralizada.

Regras:
  - Admin       → acesso total (via core.admin_access)
  - Supervisor  → cria, edita, finaliza viagens; gerencia mochilas/lojas/itens
  - Usuário     → somente leitura; vê apenas as próprias viagens
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth.models import User

if TYPE_CHECKING:
    from .models import Viagem


# ──────────────────────────────────────────────
# HELPERS INTERNOS
# ──────────────────────────────────────────────

def _is_admin(user: User) -> bool:
    return user.is_active and (user.is_superuser or user.has_perm("core.admin_access"))


def _is_supervisor(user: User) -> bool:
    return user.is_active and user.groups.filter(name="Supervisor").exists()


def _pode_editar(user: User) -> bool:
    """Admin ou Supervisor."""
    return _is_admin(user) or _is_supervisor(user)


# ──────────────────────────────────────────────
# VIAGEM
# ──────────────────────────────────────────────

def pode_listar_viagens(user: User) -> bool:
    return user.is_authenticated and user.is_active


def pode_ver_viagem(user: User, viagem: "Viagem") -> bool:
    if not (user.is_authenticated and user.is_active):
        return False
    if _pode_editar(user):
        return True
    return viagem.responsavel_id == user.pk


def pode_criar_viagem(user: User) -> bool:
    return _pode_editar(user)


def pode_finalizar_viagem(user: User) -> bool:
    return _pode_editar(user)


def pode_editar_checklist(user: User, viagem: "Viagem") -> bool:
    """Checklist só pode ser editado por quem tem acesso à viagem e ela está em andamento."""
    if not pode_ver_viagem(user, viagem):
        return False
    if not _pode_editar(user):
        return False
    return viagem.status == "andamento"


# ──────────────────────────────────────────────
# MOCHILA / LOJA / ITEM
# ──────────────────────────────────────────────

def pode_gerenciar_mochila(user: User) -> bool:
    return _pode_editar(user)


def pode_gerenciar_loja(user: User) -> bool:
    return _pode_editar(user)


def pode_gerenciar_item(user: User) -> bool:
    return _pode_editar(user)


# ──────────────────────────────────────────────
# USUÁRIO / ADMIN
# ──────────────────────────────────────────────

def pode_gerenciar_usuarios(user: User) -> bool:
    return _is_admin(user)


def pode_acessar_admin(user: User) -> bool:
    return _is_admin(user)


# ──────────────────────────────────────────────
# QUERYSET FILTERS
# ──────────────────────────────────────────────

def filtrar_viagens(user: User, qs):
    """
    Admin/Supervisor → todas as viagens.
    Usuário comum   → somente as próprias viagens.
    """
    if _pode_editar(user):
        return qs
    return qs.filter(responsavel=user)


# ──────────────────────────────────────────────
# CONTEXT PROCESSOR
# ──────────────────────────────────────────────

def permission_context(request) -> dict:
    if not request.user.is_authenticated:
        return {"perms_ctx": {}}

    u = request.user
    return {
        "perms_ctx": {
            "pode_editar":             _pode_editar(u),
            "is_admin":                _is_admin(u),
            "is_supervisor":           _is_supervisor(u),
            "pode_gerenciar_usuarios": pode_gerenciar_usuarios(u),
        }
    }