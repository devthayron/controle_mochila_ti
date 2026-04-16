"""
services/usuario_service.py — Criação, edição, exclusão e reset de senha.
"""

from __future__ import annotations

import logging

from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.db import transaction

from core import permissions as perms
from ..exceptions import AutoExclusaoError, SenhaFracaError, SenhaIncorretaError
from ..models import PasswordPolicy

logger = logging.getLogger("core.services.usuario")

DEFAULT_PASSWORD = "Dti@paraiba"

_NIVEL_TO_GROUP = {
    "admin":      "Admin",
    "supervisor": "Supervisor",
    "usuario":    "Usuário",
}

_GROUP_TO_NIVEL = {v: k for k, v in _NIVEL_TO_GROUP.items()}


# ──────────────────────────────────────────────
# HELPERS INTERNOS
# ──────────────────────────────────────────────

def _assign_group(user: User, nivel: str) -> None:
    user.groups.clear()
    group_name = _NIVEL_TO_GROUP.get(nivel, "Usuário")
    group, _ = Group.objects.get_or_create(name=group_name)
    user.groups.add(group)


def _ensure_password_policy(user: User) -> PasswordPolicy:
    policy, _ = PasswordPolicy.objects.get_or_create(
        user=user,
        defaults={"must_change_password": True},
    )
    return policy


# ──────────────────────────────────────────────
# CONSULTAS
# ──────────────────────────────────────────────

def get_nivel(user: User) -> str:
    for group in user.groups.all():
        nivel = _GROUP_TO_NIVEL.get(group.name)
        if nivel:
            return nivel
    return "admin" if user.is_superuser else "usuario"


def must_change_password(user: User) -> bool:
    policy = _ensure_password_policy(user)
    return policy.must_change_password


# ──────────────────────────────────────────────
# CRIAR USUÁRIO
# ──────────────────────────────────────────────

@transaction.atomic
def criar_usuario(
    actor: User,
    username: str,
    nivel: str = "usuario",
    first_name: str = "",
    last_name: str = "",
    email: str = "",
) -> User:

    if not perms.pode_gerenciar_usuarios(actor):
        raise PermissionDenied("Sem permissão para gerenciar usuários.")

    # 🔒 REGRA: supervisor não cria admin
    if perms._is_supervisor(actor) and nivel == "admin":
        raise PermissionDenied("Supervisor não pode criar admin.")

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
def editar_usuario(
    actor: User,
    target: User,
    username: str,
    nivel: str,
    first_name: str = "",
    last_name: str = "",
    email: str = "",
) -> User:

    if not perms.pode_gerenciar_usuarios(actor):
        raise PermissionDenied("Sem permissão para gerenciar usuários.")

    # 🔒 supervisor não mexe com admin
    if perms._is_supervisor(actor):
        if nivel == "admin":
            raise PermissionDenied("Supervisor não pode promover para admin.")

        if get_nivel(target) == "admin":
            raise PermissionDenied("Supervisor não pode editar admin.")

    target.username   = username
    target.first_name = first_name
    target.last_name  = last_name
    target.email      = email
    target.is_staff     = (nivel == "admin")
    target.is_superuser = (nivel == "admin")
    target.save()

    _assign_group(target, nivel)

    logger.info("Usuário editado: %s por %s", target.username, actor.username)
    return target


# ──────────────────────────────────────────────
# RESET DE SENHA
# ──────────────────────────────────────────────

@transaction.atomic
def resetar_senha(actor: User, target: User) -> None:
    """
    Redefine a senha de um usuário para o padrão e força troca.

    Raises:
        PermissionDenied: ator sem permissão
    """
    if not perms._is_admin(actor):
        raise PermissionDenied("Apenas administradores podem resetar senhas.")

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
    """
    Troca a senha do usuário e libera a flag de troca obrigatória.

    Raises:
        SenhaIncorretaError: senha atual incorreta
        SenhaFracaError: nova senha não atende critérios
    """
    if not user.check_password(senha_atual):
        raise SenhaIncorretaError("Senha atual incorreta.")

    if len(nova_senha) < 8:
        raise SenhaFracaError("A senha deve ter no mínimo 8 caracteres.")

    if nova_senha == DEFAULT_PASSWORD:
        raise SenhaFracaError("A nova senha não pode ser igual à senha padrão do sistema.")

    user.set_password(nova_senha)
    user.save()

    policy = _ensure_password_policy(user)
    policy.must_change_password = False
    policy.save(update_fields=["must_change_password"])

    logger.info("Senha alterada: %s", user.username)


# ──────────────────────────────────────────────
# EXCLUSÃO (SOFT DELETE — desativa usuário)
# ──────────────────────────────────────────────

@transaction.atomic
def excluir_usuario(actor: User, target: User) -> None:
    """
    Desativa um usuário (soft delete via is_active=False).

    Raises:
        PermissionDenied: ator sem permissão ou tentativa de excluir admin master
        AutoExclusaoError: ator tentou se auto-excluir
    """
    if not perms.pode_gerenciar_usuarios(actor):
        raise PermissionDenied("Sem permissão para gerenciar usuários.")

    if target == actor:
        raise AutoExclusaoError("Você não pode excluir sua própria conta.")

    if target.is_superuser:
        raise PermissionDenied("Não é possível excluir um administrador master.")

    target.is_active = False
    target.save(update_fields=["is_active"])

    logger.info("Usuário desativado: %s por %s", target.username, actor.username)
