"""
services/viagem_service.py — Regras de negócio de Viagem.
"""

from __future__ import annotations

import logging

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from core import permissions as perms
from ..models import ChecklistItem, Mochila, Viagem

logger = logging.getLogger("core.services.viagem")


class ViagemJaFinalizada(ValueError):
    """Operação inválida em viagem que já foi encerrada."""


class ViagemNaoEncontrada(ValueError):
    pass


class MochilaEmUso(ValueError):
    """Mochila já está em uma viagem em andamento."""


@transaction.atomic
def criar_viagem(user: User, responsavel: User, loja, mochila: Mochila) -> Viagem:
    """
    Cria uma nova viagem e gera o checklist automaticamente.
    Usa select_for_update para evitar concorrência de mochila duplicada.

    Raises:
        PermissionDenied  — usuário sem permissão para criar viagens
        ValueError        — mochila inativa ou sem itens
        MochilaEmUso      — mochila já está em viagem ativa
    """
    if not perms.pode_criar_viagem(user):
        logger.warning("criar_viagem: acesso negado para %s", user)
        raise PermissionDenied("Você não tem permissão para registrar viagens.")

    # Lock para evitar corrida de concorrência
    mochila = Mochila.objects.select_for_update().get(pk=mochila.pk)

    if not mochila.ativo:
        raise ValueError("A mochila selecionada está inativa.")

    if not mochila.mochilaitem_set.exists():
        raise ValueError("Não é possível iniciar uma viagem com mochila vazia.")

    if Viagem.objects.filter(mochila=mochila, status="andamento").exists():
        raise MochilaEmUso(
            f'A mochila "{mochila.nome}" já está em uma viagem em andamento.'
        )

    viagem = Viagem.objects.create(
        responsavel=responsavel,
        loja=loja,
        mochila=mochila,
        data_saida=timezone.now(),
        status="andamento",
    )

    logger.info("Viagem #%s criada por %s", viagem.pk, user)
    return viagem


@transaction.atomic
def finalizar_viagem(user: User, viagem: Viagem) -> Viagem:
    """
    Finaliza uma viagem em andamento.

    Raises:
        PermissionDenied    — sem permissão
        ViagemJaFinalizada  — viagem já encerrada
    """
    if not perms.pode_finalizar_viagem(user):
        logger.warning("finalizar_viagem: acesso negado para %s (viagem #%s)", user, viagem.pk)
        raise PermissionDenied("Você não tem permissão para finalizar viagens.")

    if viagem.status != "andamento":
        raise ViagemJaFinalizada(f"A viagem #{viagem.pk} já foi finalizada.")

    viagem.status = "finalizada"
    viagem.data_retorno = timezone.now()
    viagem.save(update_fields=["status", "data_retorno"])

    logger.info("Viagem #%s finalizada por %s", viagem.pk, user)
    return viagem


@transaction.atomic
def salvar_checklist(user: User, viagem: Viagem, payload: dict) -> list[ChecklistItem]:
    """
    Atualiza os itens do checklist de uma viagem em andamento.

    Raises:
        PermissionDenied   — sem permissão ou viagem finalizada
    """
    if not perms.pode_editar_checklist(user, viagem):
        raise PermissionDenied(
            "Você não tem permissão para editar o checklist "
            "ou esta viagem já foi finalizada."
        )

    checklist = list(viagem.checklist.select_related("item").all())
    to_update: list[ChecklistItem] = []

    for ci in checklist:
        item_payload = payload.get(ci.pk, {})
        ci.saida_ok = bool(item_payload.get("saida_ok", ci.saida_ok))
        ci.retorno_ok = bool(item_payload.get("retorno_ok", ci.retorno_ok))
        ci.observacao_retorno = str(
            item_payload.get("observacao_retorno", ci.observacao_retorno)
        )[:255]
        to_update.append(ci)

    ChecklistItem.objects.bulk_update(
        to_update, ["saida_ok", "retorno_ok", "observacao_retorno"]
    )

    logger.info(
        "Checklist da viagem #%s atualizado por %s (%d itens)",
        viagem.pk, user, len(to_update),
    )
    return to_update


def payload_from_post(post_data, checklist_ids: list[int]) -> dict:
    result = {}
    for cid in checklist_ids:
        result[cid] = {
            "saida_ok":           f"saida_ok_{cid}" in post_data,
            "retorno_ok":         f"retorno_ok_{cid}" in post_data,
            "observacao_retorno": post_data.get(f"obs_{cid}", ""),
        }
    return result