"""
services/mochila_service.py — Regras de negócio de Mochila.
"""

from __future__ import annotations

import logging

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import transaction

from core import permissions as perms
from ..exceptions import MochilaEmUsoError
from ..models import Mochila, MochilaItem, Viagem

logger = logging.getLogger("core.services.mochila")


# ──────────────────────────────────────────────
# DESATIVAR (SOFT DELETE)
# ──────────────────────────────────────────────

@transaction.atomic
def desativar_mochila(user: User, mochila: Mochila) -> Mochila:

    if not perms.pode_gerenciar_mochila(user):
        raise PermissionDenied("Sem permissão para desativar mochilas.")

    mochila = (
        Mochila.all_objects
        .select_for_update()
        .get(pk=mochila.pk)
    )

    # 🔒 regra de domínio (não permissão)
    if Viagem.objects.filter(
        mochila=mochila,
        status="andamento"
    ).exists():
        raise MochilaEmUsoError(
            f'A mochila "{mochila.nome}" está em uso e não pode ser desativada.'
        )

    mochila.desativar()

    logger.info(
        "Mochila #%s (%s) desativada por %s",
        mochila.pk,
        mochila.nome,
        user.username,
    )

    return mochila


# ──────────────────────────────────────────────
# REATIVAR
# ──────────────────────────────────────────────

@transaction.atomic
def reativar_mochila(user: User, mochila: Mochila) -> Mochila:

    if not perms.pode_gerenciar_mochila(user):
        raise PermissionDenied("Sem permissão para reativar mochilas.")

    mochila = (
        Mochila.all_objects
        .select_for_update()
        .get(pk=mochila.pk)
    )

    mochila.reativar()

    logger.info(
        "Mochila #%s (%s) reativada por %s",
        mochila.pk,
        mochila.nome,
        user.username,
    )

    return mochila


# ──────────────────────────────────────────────
# SINCRONIZAR ITENS
# ──────────────────────────────────────────────

@transaction.atomic
def sincronizar_itens(user: User, mochila: Mochila, itens_qtd: dict[int, int]) -> Mochila:

    if not perms.pode_gerenciar_mochila(user):
        raise PermissionDenied("Sem permissão para editar mochilas.")

    mochila = (
        Mochila.objects
        .select_for_update()
        .get(pk=mochila.pk)
    )

    MochilaItem.objects.filter(mochila=mochila).delete()

    if itens_qtd:
        MochilaItem.objects.bulk_create([
            MochilaItem(
                mochila=mochila,
                item_id=item_id,
                quantidade=qty,
            )
            for item_id, qty in itens_qtd.items()
        ])

    logger.info(
        "Mochila #%s sincronizada por %s (%d itens)",
        mochila.pk,
        user.username,
        len(itens_qtd),
    )

    return mochila