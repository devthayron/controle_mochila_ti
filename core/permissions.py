"""
permissions.py — Camada de controle de acesso centralizada.

Hierarquia de acesso:
  Admin       → acesso total
  Supervisor  → operações + gerenciamento de usuários (criar, listar, editar)
               NÃO pode: apagar usuários, resetar senha
  Usuário     → somente leitura; vê apenas as próprias viagens

Regras de ouro:
  - NUNCA colocar regras de acesso nas views, services ou templates via perms.*
  - Toda verificação passa por esta camada
  - Funções com prefixo _ são internas — NÃO importar fora deste módulo
  - Services são lógica de negócio pura — NÃO importam este módulo
  - permission_context() é registrado em settings.py como context processor global
    e injeta user_perms em todos os templates automaticamente
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth.models import User

if TYPE_CHECKING:
    from .models import Viagem

# Contexto vazio reutilizado em qualquer situação sem usuário autenticado
_EMPTY_PERMS = {
    "user_perms": {
        "pode_editar":           False,
        "is_admin":              False,
        "is_supervisor":         False,
        "pode_acessar_usuarios": False,
    }
}


# ══════════════════════════════════════════════
# PRIMITIVOS DE ROLE — internos, não importar fora daqui
# ══════════════════════════════════════════════

def _is_admin(user: User) -> bool:
    return user.is_active and (
        user.is_superuser or user.has_perm("core.admin_access")
    )


def _is_supervisor(user: User) -> bool:
    return user.is_active and user.groups.filter(name="Supervisor").exists()


def _is_usuario(user: User) -> bool:
    return user.is_active and not _is_admin(user) and not _is_supervisor(user)


def _pode_editar(user: User) -> bool:
    return _is_admin(user) or _is_supervisor(user)


# ══════════════════════════════════════════════
# API PÚBLICA
# ══════════════════════════════════════════════

def is_admin(user: User) -> bool:
    return _is_admin(user)


def is_supervisor(user: User) -> bool:
    return _is_supervisor(user)


def pode_editar(user: User) -> bool:
    return _pode_editar(user)


# ── Viagens ────────────────────────────────────────────

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
    if not pode_ver_viagem(user, viagem):
        return False
    if viagem.status != "andamento":
        return False
    if _pode_editar(user):
        return True
    return viagem.responsavel_id == user.pk


def pode_ver_checklist_saida_ok(user: User) -> bool:
    return _pode_editar(user)


def pode_ver_checklist_retorno_ok(user: User) -> bool:
    return _pode_editar(user)


# ── Inventário ─────────────────────────────────────────

def pode_gerenciar_mochila(user: User) -> bool:
    return _pode_editar(user)


def pode_gerenciar_loja(user: User) -> bool:
    return _pode_editar(user)


def pode_gerenciar_item(user: User) -> bool:
    return _pode_editar(user)


# ── Usuários ───────────────────────────────────────────

def pode_acessar_area_usuarios(user: User) -> bool:
    return _is_admin(user) or _is_supervisor(user)


def pode_criar_usuario(user: User, nivel_alvo: str) -> bool:
    if _is_admin(user):
        return True
    if _is_supervisor(user):
        return nivel_alvo in ("usuario", "supervisor")
    return False


def pode_editar_usuario(user: User, target: User, nivel_alvo: str) -> bool:
    if _is_admin(user):
        return True
    if _is_supervisor(user):
        if _is_admin(target):
            return False
        if nivel_alvo == "admin":
            return False
        return True
    return False


def pode_excluir_usuario(user: User, target: User) -> bool:
    if not _is_admin(user):
        return False
    if target.is_superuser:
        return False
    return True


def pode_resetar_senha(user: User) -> bool:
    return _is_admin(user)


def pode_acessar_admin(user: User) -> bool:
    return _is_admin(user)


# ══════════════════════════════════════════════
# QUERYSET HELPERS
# ══════════════════════════════════════════════

def filtrar_viagens(user: User, qs):
    if _pode_editar(user):
        return qs
    return qs.filter(responsavel=user)


# ══════════════════════════════════════════════
# CONTEXT PROCESSOR GLOBAL
# ══════════════════════════════════════════════
# Registrado em settings.py → TEMPLATES → context_processors:
#   'core.permissions.permission_context'
#
# Injeta automaticamente `user_perms` em TODOS os templates.
# Nenhuma view deve replicar ou complementar este contexto.

def permission_context(request) -> dict:
    """
    Context processor global.

    Defensivo por design:
    - Verifica hasattr antes de acessar request.user
    - Verifica is_authenticated antes de qualquer acesso ao banco
    - Nunca lança exceção — retorna contexto vazio em qualquer caso de erro
    """
    try:
        user = getattr(request, "user", None)

        # user ausente, não resolvido ou não é um objeto User/AnonymousUser válido
        if user is None or not hasattr(user, "is_authenticated"):
            return _EMPTY_PERMS

        if not user.is_authenticated:
            return _EMPTY_PERMS

        return {
            "user_perms": {
                "pode_editar":           _pode_editar(user),
                "is_admin":              _is_admin(user),
                "is_supervisor":         _is_supervisor(user),
                "pode_acessar_usuarios": pode_acessar_area_usuarios(user),
            }
        }
    except Exception:
        return _EMPTY_PERMS