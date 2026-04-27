"""
policies.py — Regras de negócio de acesso (BLOCO 3).

CONTRATO:
    - Pode importar roles de core.py
    - NÃO importa has_perm
    - NÃO importa context processor
    - NÃO importa annotate helpers
    - ÚNICA camada com regra de negócio de acesso
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth.models import User

if TYPE_CHECKING:
    from core.models import Viagem

# Importa apenas as funções de role — sem risco de import circular
# pois core.py importa policies DEPOIS de definir os roles.
from .core import is_admin, is_supervisor, is_staff_level


class _Policies:
    """
    Namespace de políticas. Cada método corresponde a uma entrada de Perm.
    Assinatura: policy(user, obj=None, context=None) → bool
    """

    # ── Viagens ────────────────────────────────────────────────────────────

    @staticmethod
    def criar_viagem(user: User, obj=None, context=None) -> bool:
        return is_staff_level(user)

    @staticmethod
    def ver_viagem(user: User, obj: "Viagem | None" = None, context=None) -> bool:
        if not (user.is_authenticated and user.is_active):
            return False
        if is_staff_level(user):
            return True
        if obj is not None:
            return obj.responsavel_id == user.pk
        return False

    @staticmethod
    def listar_viagens(user: User, obj=None, context=None) -> bool:
        return user.is_authenticated and user.is_active

    @staticmethod
    def finalizar_viagem(user: User, obj=None, context=None) -> bool:
        return is_staff_level(user)

    @staticmethod
    def editar_checklist(user: User, obj: "Viagem | None" = None, context=None) -> bool:
        if obj is None:
            return False
        if not _Policies.ver_viagem(user, obj):
            return False
        if obj.status != "andamento":
            return False
        if is_staff_level(user):
            return True
        return obj.responsavel_id == user.pk

    @staticmethod
    def ver_checklist_saida(user: User, obj=None, context=None) -> bool:
        return is_staff_level(user)

    @staticmethod
    def ver_checklist_retorno(user: User, obj=None, context=None) -> bool:
        return is_staff_level(user)

    # ── Inventário ─────────────────────────────────────────────────────────

    @staticmethod
    def gerenciar_mochila(user: User, obj=None, context=None) -> bool:
        return is_staff_level(user)

    @staticmethod
    def gerenciar_loja(user: User, obj=None, context=None) -> bool:
        return is_staff_level(user)

    @staticmethod
    def gerenciar_item(user: User, obj=None, context=None) -> bool:
        return is_staff_level(user)

    # ── Usuários ───────────────────────────────────────────────────────────

    @staticmethod
    def acessar_area_usuarios(user: User, obj=None, context=None) -> bool:
        return is_admin(user) or is_supervisor(user)

    @staticmethod
    def criar_usuario(user: User, obj=None, context: dict | None = None) -> bool:
        nivel_alvo = (context or {}).get("nivel_alvo", "usuario")
        if is_admin(user):
            return True
        if is_supervisor(user):
            return nivel_alvo in ("usuario", "supervisor")
        return False

    @staticmethod
    def editar_usuario(user: User, obj: User | None = None, context: dict | None = None) -> bool:
        nivel_alvo = (context or {}).get("nivel_alvo", "usuario")
        target = obj
        if is_admin(user):
            return True
        if is_supervisor(user):
            if target is not None and is_admin(target):
                return False
            if nivel_alvo == "admin":
                return False
            return True
        return False

    @staticmethod
    def excluir_usuario(user: User, obj: User | None = None, context=None) -> bool:
        if not is_admin(user):
            return False
        if obj is not None and obj.is_superuser:
            return False
        return True

    @staticmethod
    def resetar_senha(user: User, obj=None, context=None) -> bool:
        return is_admin(user)

    # ── Admin ──────────────────────────────────────────────────────────────

    @staticmethod
    def acessar_admin(user: User, obj=None, context=None) -> bool:
        return is_admin(user)

    # ── Meta ───────────────────────────────────────────────────────────────

    @staticmethod
    def pode_editar(user: User, obj=None, context=None) -> bool:
        return is_staff_level(user)