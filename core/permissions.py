"""
permissions.py — Camada de controle de acesso centralizada.

Hierarquia de acesso:
  Admin       → acesso total (todas as operações, incluindo exclusões e reset de senha)
  Supervisor  → operações + gerenciamento de usuários (criar, listar, editar)
               NÃO pode: apagar usuários, resetar senha
  Usuário     → somente leitura; vê apenas as próprias viagens

Regra de ouro:
  - NUNCA colocar regras de acesso nas views ou services
  - Toda verificação passa por esta camada
  - Funções booleanas puras — sem side effects
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth.models import User

if TYPE_CHECKING:
    from .models import Viagem


# ══════════════════════════════════════════════
# PRIMITIVOS DE ROLE — base de tudo
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
# VIAGENS
# ══════════════════════════════════════════════

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
      2. tem permissão de edição
      3. a viagem ainda está em andamento
    """
    if not pode_ver_viagem(user, viagem):
        return False
    if viagem.status != "andamento":
        return False
    # Usuário comum responsável também pode editar o próprio checklist
    if _pode_editar(user):
        return True
    return viagem.responsavel_id == user.pk


# ══════════════════════════════════════════════
# INVENTÁRIO — Mochilas, Lojas, Itens
# ══════════════════════════════════════════════

def pode_gerenciar_mochila(user: User) -> bool:
    return _pode_editar(user)


def pode_gerenciar_loja(user: User) -> bool:
    return _pode_editar(user)


def pode_gerenciar_item(user: User) -> bool:
    return _pode_editar(user)


# ══════════════════════════════════════════════
# USUÁRIOS — controle granular por operação
# ══════════════════════════════════════════════

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
        if _is_admin(target):           # não mexe em admin
            return False
        if nivel_alvo == "admin":       # não promove para admin
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


# ══════════════════════════════════════════════
# ADMIN DJANGO
# ══════════════════════════════════════════════

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
# CONTEXT PROCESSOR
# ══════════════════════════════════════════════

def permission_context(request) -> dict:
    """Injeta flags de permissão no contexto global de templates."""
    if not request.user.is_authenticated:
        return {"perms_ctx": {}}

    u = request.user
    return {
        "perms_ctx": {
            "pode_editar":             _pode_editar(u),
            "is_admin":                _is_admin(u),
            "is_supervisor":           _is_supervisor(u),
            "pode_acessar_usuarios":   pode_acessar_area_usuarios(u),
        }
    }