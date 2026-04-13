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
    pass


class MochilaEmUsoViagem(ValueError):
    """Mochila já está vinculada a uma viagem em andamento."""


# ──────────────────────────────────────────────
# CRIAR VIAGEM (VERSÃO SEGURA)
# ──────────────────────────────────────────────

@transaction.atomic
def criar_viagem(user: User, responsavel: User, loja, mochila: Mochila) -> Viagem:

    if not perms.pode_criar_viagem(user):
        raise PermissionDenied("Sem permissão.")

    # trava mochila
    mochila = Mochila.objects.select_for_update().get(pk=mochila.pk)

    if not mochila.ativo:
        raise ValueError("Mochila inativa.")

    itens = list(mochila.mochilaitem_set.select_related("item"))

    if not itens:
        raise ValueError("Mochila vazia.")

    # 🔴 FIX: trava real de concorrência
    if Viagem.objects.select_for_update().filter(
        mochila=mochila,
        status="andamento"
    ).exists():
        raise MochilaEmUsoViagem("Mochila já está em uso.")

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

    if not perms.pode_finalizar_viagem(user):
        raise PermissionDenied()

    if viagem.status != "andamento":
        raise ViagemJaFinalizada()

    viagem.status = "finalizada"
    viagem.data_retorno = timezone.now()
    viagem.save(update_fields=["status", "data_retorno"])

    return viagem


# ──────────────────────────────────────────────
# SALVAR CHECKLIST (SEM SILÊNCIO)
# ──────────────────────────────────────────────

@transaction.atomic
def salvar_checklist(user: User, viagem: Viagem, payload: dict) -> list[ChecklistItem]:

    if not perms.pode_editar_checklist(user, viagem):
        raise PermissionDenied()

    checklist = list(viagem.checklist.select_related("item"))

    to_update = []

    for ci in checklist:
        if ci.pk not in payload:
            raise ValueError(f"Item {ci.pk} não enviado no payload.")

        data = payload[ci.pk]

        ci.saida_ok = bool(data.get("saida_ok"))
        ci.retorno_ok = bool(data.get("retorno_ok"))
        ci.observacao_retorno = str(data.get("observacao_retorno", ""))[:255]

        to_update.append(ci)

    ChecklistItem.objects.bulk_update(
        to_update,
        ["saida_ok", "retorno_ok", "observacao_retorno"]
    )

    return to_update


# ──────────────────────────────────────────────
# PAYLOAD HELPERS (SEM ARMADILHA SILENCIOSA)
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