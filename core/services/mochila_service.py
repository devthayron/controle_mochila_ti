"""
services/mochila_service.py — Regras de negócio de Mochila (soft delete).
"""

from __future__ import annotations

import logging

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import transaction

from core import permissions as perms
from ..models import Mochila, Viagem

logger = logging.getLogger("core.services.mochila")


class MochilaEmUso(ValueError):
    """Mochila vinculada a uma viagem em andamento — não pode ser desativada."""


@transaction.atomic
def desativar_mochila(user: User, mochila: Mochila) -> Mochila:
    """
    Realiza soft delete da mochila (ativo=False).

    Raises:
        PermissionDenied — sem permissão
        MochilaEmUso     — mochila em viagem ativa
    """
    if not perms.pode_gerenciar_mochila(user):
        raise PermissionDenied("Você não tem permissão para excluir mochilas.")

    if Viagem.objects.filter(mochila=mochila, status="andamento").exists():
        raise MochilaEmUso(
            f'A mochila "{mochila.nome}" está em uma viagem em andamento e não pode ser desativada.'
        )

    mochila.ativo = False
    mochila.save(update_fields=["ativo"])

    logger.info("Mochila #%s (%s) desativada por %s", mochila.pk, mochila.nome, user.username)
    return mochila


@transaction.atomic
def reativar_mochila(user: User, mochila: Mochila) -> Mochila:
    if not perms.pode_gerenciar_mochila(user):
        raise PermissionDenied("Você não tem permissão para reativar mochilas.")

    mochila.ativo = True
    mochila.save(update_fields=["ativo"])

    logger.info("Mochila #%s (%s) reativada por %s", mochila.pk, mochila.nome, user.username)
    return mochila