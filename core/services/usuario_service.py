"""
services/usuario_service.py — Criação, edição, exclusão (soft delete) e reset de senha.
"""

from __future__ import annotations

import logging
from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from core import permissions as perms
from ..models import PasswordPolicy

logger = logging.getLogger("core.services.usuario")

DEFAULT_PASSWORD = "Dti@paraiba"

_NIVEL_TO_GROUP = {
    "admin": "Admin",
    "supervisor": "Supervisor",
    "usuario": "Usuário",
}

_GROUP_TO_NIVEL = {v: k for k, v in _NIVEL_TO_GROUP.items()}


# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────

def _assign_group(user: User, nivel: str) -> None:
    user.groups.clear()
    group_name = _NIVEL_TO_GROUP.get(nivel, "Usuário")
    group, _ = Group.objects.get_or_create(name=group_name)
    user.groups.add(group)


def _ensure_password_policy(user: User) -> PasswordPolicy:
    return PasswordPolicy.objects.get_or_create(user=user)[0]


def get_nivel(user: User) -> str:
    for group in user.groups.all():
        nivel = _GROUP_TO_NIVEL.get(group.name)
        if nivel:
            return nivel
    return "admin" if user.is_superuser else "usuario"


def must_change_password(user: User) -> bool:
    policy, _ = PasswordPolicy.objects.get_or_create(user=user, defaults={"must_change_password": True})
    return policy.must_change_password


# ──────────────────────────────────────────────
# CRIAR USUÁRIO
# ──────────────────────────────────────────────

@transaction.atomic
def criar_usuario(actor: User, username: str, nivel: str = "usuario",
                  first_name: str = "", last_name: str = "", email: str = "") -> User:

    if not perms.pode_gerenciar_usuarios(actor):
        raise PermissionDenied("Sem permissão.")

    user = User.objects.create(
        username=username,
        first_name=first_name,
        last_name=last_name,
        email=email,
        is_staff=(nivel == "admin"),
        is_superuser=(nivel == "admin"),
    )

    user.set_password(DEFAULT_PASSWORD)
    user.save()

    _assign_group(user, nivel)
    PasswordPolicy.objects.create(user=user, must_change_password=True)

    logger.info("Usuário criado: %s por %s", user.username, actor.username)
    return user


# ──────────────────────────────────────────────
# EDITAR USUÁRIO
# ──────────────────────────────────────────────

@transaction.atomic
def editar_usuario(actor: User, target: User, username: str, nivel: str,
                   first_name: str = "", last_name: str = "", email: str = "") -> User:

    if not perms.pode_gerenciar_usuarios(actor):
        raise PermissionDenied("Sem permissão.")

    target.username = username
    target.first_name = first_name
    target.last_name = last_name
    target.email = email
    target.is_staff = (nivel == "admin")
    target.is_superuser = (nivel == "admin")
    target.save()

    _assign_group(target, nivel)

    logger.info("Usuário editado: %s por %s", target.username, actor.username)
    return target


# ──────────────────────────────────────────────
# RESET SENHA
# ──────────────────────────────────────────────

@transaction.atomic
def resetar_senha(actor: User, target: User) -> None:

    if not perms.pode_gerenciar_usuarios(actor):
        raise PermissionDenied("Sem permissão.")

    target.set_password(DEFAULT_PASSWORD)
    target.save()

    policy = _ensure_password_policy(target)
    policy.must_change_password = True
    policy.save(update_fields=["must_change_password"])

    logger.info("Senha resetada: %s por %s", target.username, actor.username)


# ──────────────────────────────────────────────
# TROCA DE SENHA
# ──────────────────────────────────────────────

@transaction.atomic
def trocar_senha(user: User, senha_atual: str, nova_senha: str) -> None:

    if not user.check_password(senha_atual):
        raise ValueError("Senha incorreta.")

    if len(nova_senha) < 8:
        raise ValueError("Senha fraca.")

    if nova_senha == DEFAULT_PASSWORD:
        raise ValueError("Senha inválida.")

    user.set_password(nova_senha)
    user.save()

    policy = _ensure_password_policy(user)
    policy.must_change_password = False
    policy.save(update_fields=["must_change_password"])

    logger.info("Senha alterada: %s", user.username)


# ──────────────────────────────────────────────
# EXCLUSÃO (SOFT DELETE REAL)
# ──────────────────────────────────────────────

@transaction.atomic
def excluir_usuario(actor: User, target: User) -> None:

    if not perms.pode_gerenciar_usuarios(actor):
        raise PermissionDenied("Sem permissão.")

    if target == actor:
        raise ValueError("Auto-exclusão bloqueada.")

    if target.is_superuser:
        raise PermissionDenied("Não pode excluir admin master.")

    target.is_active = False
    target.save(update_fields=["is_active"])

    logger.info(
        "Usuário desativado: %s por %s",
        target.username,
        actor.username
    )