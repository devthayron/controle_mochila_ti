"""
services/viagem_service.py — lógica de negócio pura de viagens.

AUTORIZAÇÃO: zero. Toda verificação de permissão acontece na view/mixin
antes de chamar qualquer função deste módulo.
"""

from __future__ import annotations

import logging
from django.utils import timezone

from django.contrib.auth.models import User
from django.db import transaction

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
    Cria uma viagem com checklist automático.
    Pré-condição: o chamador já verificou permissão de criação.
    """
    mochila = (
        Mochila.all_objects
        .select_for_update()
        .get(pk=mochila.pk)
    )

    if not mochila.ativo:
        raise MochilaInativaError("Mochila inativa.")

    itens = list(mochila.mochilaitem_set.select_related("item"))

    if not itens:
        raise MochilaVaziaError("Mochila sem itens.")

    if Viagem.objects.filter(mochila=mochila, status="andamento").exists():
        raise MochilaEmUsoError("Mochila já está em uso.")

    viagem = Viagem.objects.create(
        responsavel=responsavel,
        loja=loja,
        mochila=mochila,
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
    Pré-condição: o chamador já verificou permissão de finalização.
    """
    viagem = (
        Viagem.objects
        .select_for_update()
        .get(pk=viagem.pk)
    )

    if viagem.status != "andamento":
        raise ViagemJaFinalizada("Viagem já finalizada.")

    viagem.status = "finalizada"
    viagem.data_retorno = viagem.data_retorno or timezone.now()
    viagem.save(update_fields=["status", "data_retorno"])

    logger.info("Viagem #%s finalizada por %s", viagem.pk, user.username)
    return viagem


# ──────────────────────────────────────────────
# CHECKLIST
# ──────────────────────────────────────────────

@transaction.atomic
def salvar_checklist(user: User, viagem: Viagem, payload: dict, pode_editar_saida: bool = False):
    """
    Atualiza itens do checklist de uma viagem.

    Pré-condição: o chamador já verificou permissão de edição do checklist.

    Args:
        user:              usuário que executa a ação (para log).
        viagem:            viagem cujo checklist será atualizado.
        payload:           {checklist_item_pk: {saida_ok, retorno_ok, observacao_retorno}}.
        pode_editar_saida: True se o usuário tem permissão para alterar saida_ok
                           (calculado pela view via permissions.pode_editar).
    """
    viagem = (
        Viagem.objects
        .select_for_update()
        .get(pk=viagem.pk)
    )

    checklist = viagem.checklist.select_related("item")
    to_update = []

    for ci in checklist:
        data = payload.get(ci.pk)
        if not data:
            continue

        if pode_editar_saida:
            ci.saida_ok = bool(data.get("saida_ok"))

        ci.retorno_ok         = bool(data.get("retorno_ok"))
        ci.observacao_retorno = (data.get("observacao_retorno") or "")[:255]
        to_update.append(ci)

    if to_update:
        ChecklistItem.objects.bulk_update(
            to_update,
            ["saida_ok", "retorno_ok", "observacao_retorno"],
        )

    logger.info(
        "Checklist viagem #%s atualizado por %s (%d itens)",
        viagem.pk,
        user.username,
        len(to_update),
    )

    return to_update


# ──────────────────────────────────────────────
# HELPER (VIEW → SERVICE MAPPER)
# ──────────────────────────────────────────────

def payload_from_post(post_data, checklist_ids: list[int]) -> dict:
    return {
        cid: {
            "saida_ok":           post_data.get(f"saida_ok_{cid}") == "on",
            "retorno_ok":         post_data.get(f"retorno_ok_{cid}") == "on",
            "observacao_retorno": post_data.get(f"obs_{cid}", ""),
        }
        for cid in checklist_ids
    }