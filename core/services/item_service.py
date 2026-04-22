"""
services/item_service.py — Regras de negócio de Item.

AUTORIZAÇÃO: zero. Toda verificação de permissão acontece na view/mixin
antes de chamar qualquer função deste módulo.
"""

from __future__ import annotations

import logging

from django.contrib.auth.models import User
from django.db import transaction

from ..exceptions import ItemEmUsoError
from ..models import Item

logger = logging.getLogger("core.services.item")


# ──────────────────────────────────────────────
# DESATIVAR (SOFT DELETE)
# ──────────────────────────────────────────────

@transaction.atomic
def desativar_item(user: User, item: Item) -> Item:
    """
    Soft delete de item.
    Pré-condição: o chamador já verificou permissão de gerenciamento.
    """
    item = (
        Item.all_objects
        .select_for_update()
        .get(pk=item.pk)
    )

    if not item.pode_ser_desativado():
        raise ItemEmUsoError(
            f'O item "{item.nome}" está em uso em viagens ativas e não pode ser desativado.'
        )

    if not item.ativo:
        logger.info("Item #%s já estava desativado.", item.pk)
        return item

    item.desativar()

    logger.info(
        "Item #%s (%s) desativado por %s",
        item.pk, item.nome, user.username,
    )

    return item


# ──────────────────────────────────────────────
# REATIVAR
# ──────────────────────────────────────────────

@transaction.atomic
def reativar_item(user: User, item: Item) -> Item:
    """
    Reativa item inativo.
    Pré-condição: o chamador já verificou permissão de gerenciamento.
    """
    item = (
        Item.all_objects
        .select_for_update()
        .get(pk=item.pk)
    )

    if item.ativo:
        logger.info("Item #%s já estava ativo.", item.pk)
        return item

    item.reativar()

    logger.info(
        "Item #%s (%s) reativado por %s",
        item.pk, item.nome, user.username,
    )

    return item