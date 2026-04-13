"""
permissions.py — Camada de controle de acesso centralizada.

Regras:
  - Admin   → acesso total
  - Supervisor → cria, edita, finaliza viagens; gerencia mochilas/lojas/itens
  - Usuário → somente leitura; vê apenas as próprias viagens
  - Futuro  → filtro por loja (multi-tenant) já previsto nas assinaturas
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth.models import User

if TYPE_CHECKING:
    from .models import Viagem, ChecklistItem


# ──────────────────────────────────────────────
# HELPERS INTERNOS
# ──────────────────────────────────────────────

def _is_admin(user: User) -> bool:
    return user.has_perm("core.admin_access")


def _is_supervisor(user: User) -> bool:
    return user.has_perm("core.supervisor_access")


def _pode_editar(user: User) -> bool:
    """Admin ou Supervisor."""
    return _is_admin(user) or _is_supervisor(user)


# ──────────────────────────────────────────────
# VIAGEM
# ──────────────────────────────────────────────

def pode_listar_viagens(user: User) -> bool:
    return user.is_authenticated


def pode_ver_viagem(user: User, viagem: "Viagem") -> bool:
    """
    Admin/Supervisor veem tudo.
    Usuário comum vê somente as próprias viagens.
    Hook multi-tenant: aqui você filtra por loja no futuro.
    """
    if not user.is_authenticated:
        return False
    if _pode_editar(user):
        return True
    return viagem.responsavel_id == user.pk


def pode_criar_viagem(user: User) -> bool:
    return _pode_editar(user)


def pode_finalizar_viagem(user: User) -> bool:
    return _pode_editar(user)


def pode_editar_checklist(user: User, viagem: "Viagem") -> bool:
    """Checklist só pode ser editado enquanto a viagem está em andamento."""
    if not _pode_editar(user):
        return False
    return viagem.status == "andamento"


# ──────────────────────────────────────────────
# MOCHILA
# ──────────────────────────────────────────────

def pode_gerenciar_mochila(user: User) -> bool:
    return _pode_editar(user)


# ──────────────────────────────────────────────
# LOJA
# ──────────────────────────────────────────────

def pode_gerenciar_loja(user: User) -> bool:
    return _pode_editar(user)


# ──────────────────────────────────────────────
# ITEM
# ──────────────────────────────────────────────

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
# QUERYSET FILTERS (multi-tenant ready)
# ──────────────────────────────────────────────

def filtrar_viagens(user: User, qs):
    """
    Retorna o queryset de Viagem filtrado conforme o perfil.

    Admin/Supervisor → todas as viagens.
    Usuário comum   → somente as próprias viagens.

    Extensão multi-tenant: adicione aqui filtro por loja/tenant.
    """
    if _pode_editar(user):
        return qs
    return qs.filter(responsavel=user)


# ──────────────────────────────────────────────
# CONTEXT PROCESSOR HELPER
# Injeta flags de permissão no template context.
# Registre em settings.py > TEMPLATES > context_processors.
# ──────────────────────────────────────────────

def permission_context(request) -> dict:
    """
    Uso em settings.py:
        'core.permissions.permission_context'

    Disponível em todos os templates:
        {{ perms_ctx.pode_editar }}
        {{ perms_ctx.is_admin }}
    """
    if not request.user.is_authenticated:
        return {"perms_ctx": {}}

    u = request.user
    return {
        "perms_ctx": {
            "pode_editar":           _pode_editar(u),
            "is_admin":              _is_admin(u),
            "is_supervisor":         _is_supervisor(u),
            "pode_gerenciar_usuarios": pode_gerenciar_usuarios(u),
        }
    }
