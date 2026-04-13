"""
services/usuario_service.py — Criação, edição, exclusão e reset de senha.

Regras:
  - Senha nunca é recebida na criação — sempre "Dti@paraiba" automaticamente.
  - Todo usuário criado nasce com must_change_password=True.
  - Reset de senha: apenas admin. Redefine para "Dti@paraiba" + must_change=True.
  - Supervisor não tem acesso a nenhuma operação de senha.
"""

from __future__ import annotations

import logging

from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.db import transaction

from core import permissions as perms
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
    policy, _ = PasswordPolicy.objects.get_or_create(user=user)
    return policy


def get_nivel(user: User) -> str:
    for group in user.groups.all():
        nivel = _GROUP_TO_NIVEL.get(group.name)
        if nivel:
            return nivel
    if user.is_superuser:
        return "admin"
    return "usuario"


def must_change_password(user: User) -> bool:
    try:
        return user.password_policy.must_change_password
    except PasswordPolicy.DoesNotExist:
        # Se não existe policy, cria e força troca por segurança
        PasswordPolicy.objects.create(user=user, must_change_password=True)
        return True


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
    """
    Cria usuário com senha padrão automática e must_change_password=True.
    Senha NUNCA é recebida como parâmetro.

    Raises:
        PermissionDenied — apenas admin pode criar usuários
    """
    if not perms.pode_gerenciar_usuarios(actor):
        raise PermissionDenied("Apenas administradores podem criar usuários.")

    nivel = nivel or "usuario"

    user = User(
        username=username,
        first_name=first_name,
        last_name=last_name,
        email=email,
    )
    user.set_password(DEFAULT_PASSWORD)
    user.is_staff = user.is_superuser = (nivel == "admin")
    user.save()

    _assign_group(user, nivel)
    PasswordPolicy.objects.create(user=user, must_change_password=True)

    logger.info(
        "Usuário '%s' criado por '%s' (nível: %s, must_change=True)",
        user.username, actor.username, nivel,
    )
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
    """
    Edita dados do usuário. Nunca altera senha.

    Raises:
        PermissionDenied — apenas admin
    """
    if not perms.pode_gerenciar_usuarios(actor):
        raise PermissionDenied("Apenas administradores podem editar usuários.")

    nivel = nivel or "usuario"

    target.username   = username
    target.first_name = first_name
    target.last_name  = last_name
    target.email      = email
    target.is_staff   = target.is_superuser = (nivel == "admin")
    target.save()

    _assign_group(target, nivel)

    logger.info(
        "Usuário '%s' editado por '%s' (nível: %s)",
        target.username, actor.username, nivel,
    )
    return target


# ──────────────────────────────────────────────
# RESET DE SENHA (somente admin)
# ──────────────────────────────────────────────

@transaction.atomic
def resetar_senha(actor: User, target: User) -> None:
    """
    Redefine senha para o padrão e força troca no próximo login.
    Apenas admin pode executar.

    Raises:
        PermissionDenied — actor não é admin
    """
    if not perms.pode_gerenciar_usuarios(actor):
        raise PermissionDenied("Apenas administradores podem redefinir senhas.")

    target.set_password(DEFAULT_PASSWORD)
    target.save(update_fields=["password"])

    policy = _ensure_password_policy(target)
    policy.must_change_password = True
    policy.save(update_fields=["must_change_password"])

    logger.info(
        "Senha de '%s' redefinida por '%s' (must_change=True)",
        target.username, actor.username,
    )


# ──────────────────────────────────────────────
# TROCA DE SENHA (pelo próprio usuário)
# ──────────────────────────────────────────────

@transaction.atomic
def trocar_senha(user: User, senha_atual: str, nova_senha: str) -> None:
    """
    Troca de senha pelo próprio usuário após primeiro login.
    Valida a senha atual antes de alterar.

    Raises:
        ValueError — senha atual incorreta ou nova senha inválida
    """
    if not user.check_password(senha_atual):
        raise ValueError("Senha atual incorreta.")

    if len(nova_senha) < 8:
        raise ValueError("A nova senha deve ter no mínimo 8 caracteres.")

    if nova_senha == DEFAULT_PASSWORD:
        raise ValueError("A nova senha não pode ser igual à senha padrão do sistema.")

    user.set_password(nova_senha)
    user.save(update_fields=["password"])

    policy = _ensure_password_policy(user)
    policy.must_change_password = False
    policy.save(update_fields=["must_change_password"])

    logger.info("Usuário '%s' trocou a senha com sucesso.", user.username)


# ──────────────────────────────────────────────
# EXCLUIR USUÁRIO
# ──────────────────────────────────────────────

@transaction.atomic
def excluir_usuario(actor: User, target: User) -> None:
    """
    Raises:
        PermissionDenied — apenas admin
        ValueError       — auto-exclusão bloqueada
    """
    if not perms.pode_gerenciar_usuarios(actor):
        raise PermissionDenied("Apenas administradores podem excluir usuários.")

    if target == actor:
        raise ValueError("Você não pode excluir sua própria conta.")

    username = target.username
    target.delete()
    logger.info("Usuário '%s' excluído por '%s'.", username, actor.username)


# ──────────────────────────────────────────────
# RETROCOMPAT — usado em views.py
# ──────────────────────────────────────────────

def _assign_group_compat(user: User, nivel: str) -> None:
    _assign_group(user, nivel)