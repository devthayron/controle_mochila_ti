"""
services/viagem_service.py — Toda a lógica de negócio de viagens.
"""

from __future__ import annotations

import logging

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from core import permissions as perms
from ..exceptions import (
    MochilaEmUsoError,
    MochilaInativaError,
    MochilaVaziaError,
    ViagemJaFinalizada,
)
from ..models import ChecklistItem, Mochila, Viagem

logger = logging.getLogger("core.services.viagem")


# ──────────────────────────────────────────────
# CRIAR VIAGEM
# ──────────────────────────────────────────────

@transaction.atomic
def criar_viagem(user: User, responsavel: User, loja, mochila: Mochila) -> Viagem:
    """
    Cria uma nova viagem e gera o checklist automaticamente.

    Raises:
        PermissionDenied: usuário sem permissão
        MochilaInativaError: mochila desativada
        MochilaVaziaError: mochila sem itens
        MochilaEmUsoError: mochila já em viagem ativa
    """
    if not perms.pode_criar_viagem(user):
        raise PermissionDenied("Sem permissão para criar viagens.")

    # trava mochila — previne race condition
    mochila = Mochila.all_objects.select_for_update().get(pk=mochila.pk)

    if not mochila.ativo:
        raise MochilaInativaError(f'A mochila "{mochila.nome}" está inativa.')

    itens = list(mochila.mochilaitem_set.select_related("item"))

    if not itens:
        raise MochilaVaziaError(f'A mochila "{mochila.nome}" não possui itens.')

    if Viagem.objects.select_for_update().filter(
        mochila=mochila,
        status="andamento",
    ).exists():
        raise MochilaEmUsoError(
            f'A mochila "{mochila.nome}" já está em uso em outra viagem.'
        )

    viagem = Viagem.objects.create(
        responsavel=responsavel,
        loja=loja,
        mochila=mochila,
        data_saida=timezone.now(),
        status="andamento",
    )

    ChecklistItem.objects.bulk_create([
        ChecklistItem(
            viagem=viagem,
            item=mi.item,
            quantidade=mi.quantidade,
        )
        for mi in itens
    ])

    logger.info("Viagem #%s criada por %s", viagem.pk, user.username)
    return viagem


# ──────────────────────────────────────────────
# FINALIZAR VIAGEM
# ──────────────────────────────────────────────

@transaction.atomic
def finalizar_viagem(user: User, viagem: Viagem) -> Viagem:
    """
    Finaliza uma viagem em andamento.

    Raises:
        PermissionDenied: usuário sem permissão
        ViagemJaFinalizada: viagem já estava finalizada
    """
    if not perms.pode_finalizar_viagem(user):
        raise PermissionDenied("Sem permissão para finalizar viagens.")

    if viagem.status != "andamento":
        raise ViagemJaFinalizada("Esta viagem já foi finalizada.")

    viagem.status = "finalizada"
    viagem.data_retorno = timezone.now()
    viagem.save(update_fields=["status", "data_retorno"])

    logger.info("Viagem #%s finalizada por %s", viagem.pk, user.username)
    return viagem


# ──────────────────────────────────────────────
# SALVAR CHECKLIST
# ──────────────────────────────────────────────

@transaction.atomic
def salvar_checklist(user: User, viagem: Viagem, payload: dict) -> list[ChecklistItem]:

    # 🔒 lock da viagem (evita race condition)
    viagem = Viagem.objects.select_for_update().get(pk=viagem.pk)

    if not perms.pode_editar_checklist(user, viagem):
        raise PermissionDenied("Sem permissão para editar este checklist.")

    # 🔒 reforço de regra crítica
    if viagem.status != "andamento":
        raise PermissionDenied("Checklist não pode ser alterado após finalização.")

    checklist = list(viagem.checklist.select_related("item"))
    to_update = []

    for ci in checklist:
        if ci.pk not in payload:
            continue

        data = payload[ci.pk]
        ci.saida_ok           = bool(data.get("saida_ok"))
        ci.retorno_ok         = bool(data.get("retorno_ok"))
        ci.observacao_retorno = str(data.get("observacao_retorno", ""))[:255]
        to_update.append(ci)

    if to_update:
        ChecklistItem.objects.bulk_update(
            to_update,
            ["saida_ok", "retorno_ok", "observacao_retorno"],
        )

    logger.info(
        "Checklist viagem #%s atualizado por %s (%d itens)",
        viagem.pk, user.username, len(to_update),
    )
    return to_update


# ──────────────────────────────────────────────
# HELPER — constrói payload a partir do POST
# ──────────────────────────────────────────────

def payload_from_post(post_data, checklist_ids: list[int]) -> dict:
    """Constrói o dict de payload a partir de dados brutos do POST."""
    return {
        cid: {
            "saida_ok":           post_data.get(f"saida_ok_{cid}") == "on",
            "retorno_ok":         post_data.get(f"retorno_ok_{cid}") == "on",
            "observacao_retorno": post_data.get(f"obs_{cid}", ""),
        }
        for cid in checklist_ids
    }
