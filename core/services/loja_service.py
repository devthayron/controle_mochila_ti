"""
services/loja_service.py — Regras de negócio de Loja.
"""

from __future__ import annotations

import logging

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import transaction

from core import permissions as perms
from ..exceptions import LojaEmUsoError
from ..models import Loja, Viagem

logger = logging.getLogger("core.services.loja")


# ──────────────────────────────────────────────
# DESATIVAR (SOFT DELETE)
# ──────────────────────────────────────────────

@transaction.atomic
def desativar_loja(user: User, loja: Loja) -> Loja:
    """
    Soft delete da loja.

    Raises:
        PermissionDenied: usuário sem permissão
        LojaEmUsoError: loja com viagem em andamento
    """
    if not perms.pode_gerenciar_loja(user):
        raise PermissionDenied("Sem permissão para desativar lojas.")

    loja = Loja.all_objects.select_for_update().get(pk=loja.pk)

    if Viagem.objects.filter(loja=loja, status="andamento").exists():
        raise LojaEmUsoError(
            f'A loja "{loja.nome}" possui viagens em andamento e não pode ser desativada.'
        )

    loja.desativar()

    logger.info("Loja #%s (%s) desativada por %s", loja.pk, loja.nome, user.username)
    return loja


# ──────────────────────────────────────────────
# REATIVAR
# ──────────────────────────────────────────────

@transaction.atomic
def reativar_loja(user: User, loja: Loja) -> Loja:
    """
    Reativa uma loja desativada.

    Raises:
        PermissionDenied: usuário sem permissão
    """
    if not perms.pode_gerenciar_loja(user):
        raise PermissionDenied("Sem permissão para reativar lojas.")

    loja = Loja.all_objects.select_for_update().get(pk=loja.pk)
    loja.reativar()

    logger.info("Loja #%s (%s) reativada por %s", loja.pk, loja.nome, user.username)
    return loja
