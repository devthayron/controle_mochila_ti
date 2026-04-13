"""
services/mochila_service.py — Regras de negócio de Mochila (soft delete).
"""

from __future__ import annotations

import logging
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from core import permissions as perms
from ..models import Mochila, Viagem

logger = logging.getLogger("core.services.mochila")


class MochilaEmUsoMochila(ValueError):
    """Mochila não pode ser desativada pois está em uso."""


# ──────────────────────────────────────────────
# DESATIVAR MOCHILA (SOFT DELETE)
# ──────────────────────────────────────────────

@transaction.atomic
def desativar_mochila(user: User, mochila: Mochila) -> Mochila:
    """
    Soft delete da mochila.
    """

    if not perms.pode_gerenciar_mochila(user):
        raise PermissionDenied("Você não tem permissão para desativar mochilas.")

    # trava a mochila (evita corrida de atualização)
    mochila = Mochila.objects.select_for_update().get(pk=mochila.pk)

    # valida uso ativo
    if Viagem.objects.filter(
        mochila=mochila,
        status="andamento"
    ).exists():
        raise MochilaEmUsoMochila(
            f'A mochila "{mochila.nome}" está em uso e não pode ser desativada.'
        )

    # soft delete
    mochila.ativo = False

    if hasattr(mochila, "desativado_em"):
        mochila.desativado_em = timezone.now()

    if hasattr(mochila, "desativado_por"):
        mochila.desativado_por = user

    fields = ["ativo"]

    if hasattr(mochila, "desativado_em"):
        fields.append("desativado_em")

    if hasattr(mochila, "desativado_por"):
        fields.append("desativado_por")

    mochila.save(update_fields=fields)

    logger.info(
        "Mochila #%s (%s) desativada por %s",
        mochila.pk,
        mochila.nome,
        user.username
    )

    return mochila


# ──────────────────────────────────────────────
# REATIVAR MOCHILA
# ──────────────────────────────────────────────

@transaction.atomic
def reativar_mochila(user: User, mochila: Mochila) -> Mochila:
    """
    Reativa mochila (soft restore).
    """

    if not perms.pode_gerenciar_mochila(user):
        raise PermissionDenied("Você não tem permissão para reativar mochilas.")

    mochila = Mochila.objects.select_for_update().get(pk=mochila.pk)

    mochila.ativo = True

    if hasattr(mochila, "desativado_em"):
        mochila.desativado_em = None

    if hasattr(mochila, "desativado_por"):
        mochila.desativado_por = None

    fields = ["ativo"]

    if hasattr(mochila, "desativado_em"):
        fields.append("desativado_em")

    if hasattr(mochila, "desativado_por"):
        fields.append("desativado_por")

    mochila.save(update_fields=fields)

    logger.info(
        "Mochila #%s (%s) reativada por %s",
        mochila.pk,
        mochila.nome,
        user.username
    )

    return mochila