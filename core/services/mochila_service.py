"""
services/mochila_service.py — Regras de negócio de Mochila.

AUTORIZAÇÃO: zero. Toda verificação de permissão acontece na view/mixin
antes de chamar qualquer função deste módulo.
"""

from __future__ import annotations

import logging

from django.contrib.auth.models import User
from django.db import transaction

from ..exceptions import MochilaEmUsoError
from ..models import Mochila, MochilaItem, Viagem

logger = logging.getLogger("core.services.mochila")


# ──────────────────────────────────────────────
# DESATIVAR (SOFT DELETE)
# ──────────────────────────────────────────────

@transaction.atomic
def desativar_mochila(user: User, mochila: Mochila) -> Mochila:
    """
    Soft delete de mochila.
    Pré-condição: o chamador já verificou permissão de gerenciamento.
    """
    mochila = (
        Mochila.all_objects
        .select_for_update()
        .get(pk=mochila.pk)
    )

    if Viagem.objects.filter(mochila=mochila, status="andamento").exists():
        raise MochilaEmUsoError(
            f'A mochila "{mochila.nome}" está em uso e não pode ser desativada.'
        )

    mochila.desativar()

    logger.info(
        "Mochila #%s (%s) desativada por %s",
        mochila.pk, mochila.nome, user.username,
    )

    return mochila


# ──────────────────────────────────────────────
# REATIVAR
# ──────────────────────────────────────────────

@transaction.atomic
def reativar_mochila(user: User, mochila: Mochila) -> Mochila:
    """
    Reativa mochila inativa.
    Pré-condição: o chamador já verificou permissão de gerenciamento.
    """
    mochila = (
        Mochila.all_objects
        .select_for_update()
        .get(pk=mochila.pk)
    )

    mochila.reativar()

    logger.info(
        "Mochila #%s (%s) reativada por %s",
        mochila.pk, mochila.nome, user.username,
    )

    return mochila


# ──────────────────────────────────────────────
# SINCRONIZAR ITENS
# ──────────────────────────────────────────────

@transaction.atomic
def sincronizar_itens(user: User, mochila: Mochila, itens_qtd: dict[int, int]) -> Mochila:
    """
    Substitui todos os itens da mochila pelo conjunto recebido.
    Pré-condição: o chamador já verificou permissão de gerenciamento.
    """
    mochila = (
        Mochila.objects
        .select_for_update()
        .get(pk=mochila.pk)
    )

    MochilaItem.objects.filter(mochila=mochila).delete()

    if itens_qtd:
        MochilaItem.objects.bulk_create([
            MochilaItem(mochila=mochila, item_id=item_id, quantidade=qty)
            for item_id, qty in itens_qtd.items()
        ])

    logger.info(
        "Mochila #%s sincronizada por %s (%d itens)",
        mochila.pk, user.username, len(itens_qtd),
    )

    return mochila