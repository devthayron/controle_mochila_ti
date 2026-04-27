"""
services/viagem_service.py — lógica de negócio pura de viagens.

AUTORIZAÇÃO: zero. Toda verificação de permissão acontece na view/mixin
antes de chamar qualquer função deste módulo.
"""

from __future__ import annotations

import logging
from zoneinfo import ZoneInfo

from django.utils import timezone
from django.contrib.auth.models import User
from django.db import transaction

from ..exceptions import (
    MochilaEmUsoError,
    MochilaInativaError,
    MochilaVaziaError,
    ViagemJaFinalizada,
    DomainError,
)
from ..models import ChecklistItem, Loja, Mochila, Viagem, ViagemLoja

logger = logging.getLogger("core.services.viagem")

FUSO_LOCAL = ZoneInfo("America/Fortaleza")


# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────

def _to_aware(dt):
    """Converte datetime naive para aware no fuso local."""
    if dt is None:
        return timezone.now()
    if timezone.is_naive(dt):
        return dt.replace(tzinfo=FUSO_LOCAL)
    return dt


def _fmt(dt) -> str:
    """Formata datetime aware para exibição no fuso local."""
    return dt.astimezone(FUSO_LOCAL).strftime("%d/%m/%Y %H:%M")


def _deduplicate_lojas(lojas: list[Loja]) -> list[Loja]:
    seen = set()
    result = []
    for loja in lojas:
        if loja.pk not in seen:
            seen.add(loja.pk)
            result.append(loja)
    return result


def _get_mochila_locked(mochila: Mochila) -> Mochila:
    return (
        Mochila.all_objects
        .select_for_update()
        .get(pk=mochila.pk)
    )


def _create_viagem(responsavel, mochila, data_saida):
    return Viagem.objects.create(
        responsavel=responsavel,
        mochila=mochila,
        status="andamento",
        data_saida=_to_aware(data_saida),
    )


# ──────────────────────────────────────────────
# CRIAR VIAGEM
# ──────────────────────────────────────────────

@transaction.atomic
def criar_viagem(
    user: User,
    responsavel: User,
    lojas: list[Loja],
    mochila: Mochila,
    data_saida=None,
) -> Viagem:

    if not lojas:
        raise DomainError("Selecione ao menos uma loja de destino.")

    lojas = _deduplicate_lojas(lojas)
    mochila = _get_mochila_locked(mochila)

    if not mochila.ativo:
        raise MochilaInativaError("Mochila inativa.")

    itens = list(mochila.mochilaitem_set.select_related("item"))

    if not itens:
        raise MochilaVaziaError("Mochila sem itens.")

    if Viagem.objects.filter(mochila=mochila, status="andamento").exists():
        raise MochilaEmUsoError("Mochila já está em uso.")

    viagem = _create_viagem(responsavel, mochila, data_saida)

    ViagemLoja.objects.bulk_create([
        ViagemLoja(viagem=viagem, loja=loja, ordem=i)
        for i, loja in enumerate(lojas)
    ])

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

    viagem = (
        Viagem.objects
        .select_for_update()
        .get(pk=viagem.pk)
    )

    if viagem.status != "andamento":
        raise ViagemJaFinalizada("Viagem já finalizada.")

    data_retorno = timezone.now()

    if data_retorno < viagem.data_saida:
        raise DomainError(
            f"Atenção: o retorno ({_fmt(data_retorno)}) ficou registrado "
            f"antes da saída ({_fmt(viagem.data_saida)}). "
            f"Verifique a data de saída cadastrada."
        )

    viagem.status = "finalizada"
    viagem.data_retorno = data_retorno
    viagem.save(update_fields=["status", "data_retorno"])

    logger.info("Viagem #%s finalizada por %s", viagem.pk, user.username)
    return viagem


# ──────────────────────────────────────────────
# CHECKLIST
# ──────────────────────────────────────────────

@transaction.atomic
def salvar_checklist(
    user: User,
    viagem: Viagem,
    payload: dict,
    pode_editar_saida: bool = False,
):

    viagem = (
        Viagem.objects
        .select_for_update()
        .get(pk=viagem.pk)
    )

    if viagem.status != "andamento":
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("Checklist bloqueado — viagem finalizada.")

    checklist = viagem.checklist.select_related("item")
    to_update = []

    for ci in checklist:
        data = payload.get(ci.pk)
        if not data:
            continue

        if pode_editar_saida:
            ci.saida_ok = bool(data.get("saida_ok"))

        ci.retorno_ok = bool(data.get("retorno_ok"))
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
# HELPERS EXTERNOS
# ──────────────────────────────────────────────

def payload_from_post(post_data, checklist_ids: list[int]) -> dict:
    return {
        cid: {
            "saida_ok": post_data.get(f"saida_ok_{cid}") == "on",
            "retorno_ok": post_data.get(f"retorno_ok_{cid}") == "on",
            "observacao_retorno": post_data.get(f"obs_{cid}", ""),
        }
        for cid in checklist_ids
    }


def lojas_from_post(post_data, loja_model) -> list[Loja]:
    raw_ids = post_data.getlist("lojas")

    seen = set()
    pks = []

    for raw in raw_ids:
        try:
            pk = int(raw)
            if pk not in seen:
                seen.add(pk)
                pks.append(pk)
        except (ValueError, TypeError):
            continue

    if not pks:
        return []

    loja_map = {l.pk: l for l in loja_model.objects.filter(pk__in=pks)}
    return [loja_map[pk] for pk in pks if pk in loja_map]