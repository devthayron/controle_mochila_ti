"""
permissions.py — Camada de controle de acesso centralizada.

Hierarquia de acesso:
  Admin       → acesso total
  Supervisor  → operações + gerenciamento de usuários (criar, listar, editar)
               NÃO pode: apagar usuários, resetar senha
  Usuário     → somente leitura; vê apenas as próprias viagens

Regra de ouro:
  - NUNCA colocar regras de acesso nas views, services ou templates via perms.*
  - Toda verificação passa por esta camada
  - Views e mixins consomem APENAS as funções públicas deste módulo
  - O contexto de permissões para templates é construído por build_user_perms_context()
  - Funções com prefixo _ são internas; não as importe fora deste módulo
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth.models import User

if TYPE_CHECKING:
    from .models import Viagem


# ══════════════════════════════════════════════
# PRIMITIVOS DE ROLE — internos, não importar fora daqui
# ══════════════════════════════════════════════

def _is_admin(user: User) -> bool:
    """Admin total: superuser ou com permissão explícita core.admin_access."""
    return user.is_active and (
        user.is_superuser or user.has_perm("core.admin_access")
    )


def _is_supervisor(user: User) -> bool:
    """Membro do grupo Supervisor."""
    return user.is_active and user.groups.filter(name="Supervisor").exists()


def _is_usuario(user: User) -> bool:
    """Usuário comum (somente leitura)."""
    return user.is_active and not _is_admin(user) and not _is_supervisor(user)


def _pode_editar(user: User) -> bool:
    """Admin ou Supervisor — pode realizar operações de escrita."""
    return _is_admin(user) or _is_supervisor(user)


# ══════════════════════════════════════════════
# API PÚBLICA — use estas funções fora deste módulo
# ══════════════════════════════════════════════

# ── Roles ──────────────────────────────────────────────

def is_admin(user: User) -> bool:
    """Alias público de _is_admin."""
    return _is_admin(user)


def is_supervisor(user: User) -> bool:
    """Alias público de _is_supervisor."""
    return _is_supervisor(user)


def pode_editar(user: User) -> bool:
    """Admin ou Supervisor — alias público de _pode_editar."""
    return _pode_editar(user)


# ── Viagens ────────────────────────────────────────────

def pode_listar_viagens(user: User) -> bool:
    """Qualquer usuário autenticado e ativo pode listar viagens (filtradas pelo queryset)."""
    return user.is_authenticated and user.is_active


def pode_ver_viagem(user: User, viagem: "Viagem") -> bool:
    """
    Admin/Supervisor veem qualquer viagem.
    Usuário comum vê apenas as suas próprias.
    """
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
    """
    Só edita checklist quem:
      1. tem acesso à viagem
      2. a viagem ainda está em andamento
      3. tem permissão de edição ou é o responsável
    """
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


# ── Inventário — Mochilas, Lojas, Itens ────────────────

def pode_gerenciar_mochila(user: User) -> bool:
    return _pode_editar(user)


def pode_gerenciar_loja(user: User) -> bool:
    return _pode_editar(user)


def pode_gerenciar_item(user: User) -> bool:
    return _pode_editar(user)


# ── Usuários — controle granular por operação ──────────

def pode_acessar_area_usuarios(user: User) -> bool:
    """Acesso à listagem de usuários: Admin e Supervisor."""
    return _is_admin(user) or _is_supervisor(user)


def pode_criar_usuario(user: User, nivel_alvo: str) -> bool:
    """
    Admin pode criar qualquer nível.
    Supervisor pode criar apenas usuário e supervisor.
    """
    if _is_admin(user):
        return True
    if _is_supervisor(user):
        return nivel_alvo in ("usuario", "supervisor")
    return False


def pode_editar_usuario(user: User, target: User, nivel_alvo: str) -> bool:
    """
    Admin pode editar qualquer usuário para qualquer nível.
    Supervisor pode editar usuários não-admin, mas não pode promover para admin.
    """
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
    """Somente Admin pode excluir. Nunca pode excluir superuser."""
    if not _is_admin(user):
        return False
    if target.is_superuser:
        return False
    return True


def pode_resetar_senha(user: User) -> bool:
    """Somente Admin pode resetar senha de outros usuários."""
    return _is_admin(user)


# ── Admin Django ───────────────────────────────────────

def pode_acessar_admin(user: User) -> bool:
    return _is_admin(user)


# ══════════════════════════════════════════════
# QUERYSET HELPERS
# ══════════════════════════════════════════════

def filtrar_viagens(user: User, qs):
    """
    Admin/Supervisor → todas as viagens.
    Usuário comum   → apenas as próprias.
    """
    if _pode_editar(user):
        return qs
    return qs.filter(responsavel=user)


# ══════════════════════════════════════════════
# CONTEXT BUILDER — única fonte de verdade para templates
# ══════════════════════════════════════════════

def permission_context(request):
    if not request.user.is_authenticated:
        return {"user_perms": {
            "pode_editar": False,
            "is_admin": False,
            "is_supervisor": False,
            "pode_acessar_usuarios": False,
        }}

    user = request.user

    return {
        "user_perms": {
            "pode_editar": _pode_editar(user),
            "is_admin": _is_admin(user),
            "is_supervisor": _is_supervisor(user),
            "pode_acessar_usuarios": pode_acessar_area_usuarios(user),
        }
    }