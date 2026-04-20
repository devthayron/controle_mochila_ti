"""
services/item_service.py — Regras de negócio de Item.
"""

from __future__ import annotations

import logging

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import transaction

from core import permissions as perms
from ..exceptions import ItemEmUsoError
from ..models import Item

logger = logging.getLogger("core.services.item")


# ──────────────────────────────────────────────
# DESATIVAR (SOFT DELETE)
# ──────────────────────────────────────────────

@transaction.atomic
def desativar_item(user: User, item: Item) -> Item:

    if not perms.pode_gerenciar_item(user):
        raise PermissionDenied("Sem permissão para desativar itens.")

    item = (
        Item.all_objects
        .select_for_update()
        .get(pk=item.pk)
    )

    # 🔒 regra de domínio já delegada ao model (correto)
    if not item.pode_ser_desativado():
        raise ItemEmUsoError(
            f'O item "{item.nome}" está em uso em viagens ativas e não pode ser desativado.'
        )

    # 🔒 idempotência correta
    if not item.ativo:
        logger.info("Item #%s já estava desativado.", item.pk)
        return item

    item.desativar()

    logger.info(
        "Item #%s (%s) desativado por %s",
        item.pk,
        item.nome,
        user.username,
    )

    return item


# ──────────────────────────────────────────────
# REATIVAR
# ──────────────────────────────────────────────

@transaction.atomic
def reativar_item(user: User, item: Item) -> Item:

    if not perms.pode_gerenciar_item(user):
        raise PermissionDenied("Sem permissão para reativar itens.")

    item = (
        Item.all_objects
        .select_for_update()
        .get(pk=item.pk)
    )

    # 🔒 idempotência opcional (boa prática)
    if item.ativo:
        logger.info("Item #%s já estava ativo.", item.pk)
        return item

    item.reativar()

    logger.info(
        "Item #%s (%s) reativado por %s",
        item.pk,
        item.nome,
        user.username,
    )

    return item