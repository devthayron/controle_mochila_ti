"""
tests.py — Testes unitários da camada de permissões e serviços.
"""

from django.contrib.auth.models import User, Group
from django.core.exceptions import PermissionDenied
from django.test import TestCase

from . import permissions as perms
from .models import Item, Loja, Mochila, MochilaItem
from .services.viagem_service import (
    ViagemJaFinalizada,
    MochilaEmUsoViagem,
    criar_viagem,
    finalizar_viagem,
    salvar_checklist,
)
from .services.usuario_service import _assign_group, get_nivel


# ───────────────────────── FIXTURES ─────────────────────────

def make_user(username, nivel="usuario", is_superuser=False):
    user = User.objects.create_user(username=username, password="test1234")
    user.is_superuser = is_superuser
    user.save()

    _assign_group(user, nivel)
    return user


def make_base_viagem():
    loja = Loja.objects.create(nome="Loja Teste")
    mochila = Mochila.objects.create(nome="Mochila Teste")
    item = Item.objects.create(nome="Item Teste")

    MochilaItem.objects.create(
        mochila=mochila,
        item=item,
        quantidade=1
    )

    return loja, mochila


# ───────────────────────── PERMISSIONS ─────────────────────────

class PermissionsTest(TestCase):

    def setUp(self):
        self.admin = make_user("admin", "admin", is_superuser=True)
        self.supervisor = make_user("sup", "supervisor")
        self.usuario = make_user("user", "usuario")

    def test_admin_pode_tudo(self):
        self.assertTrue(perms._is_admin(self.admin))

    def test_usuario_nao_pode_editar(self):
        self.assertFalse(perms._pode_editar(self.usuario))


# ───────────────────────── VIAGEM SERVICE ─────────────────────────

class ViagemServiceTest(TestCase):

    def setUp(self):
        Group.objects.get_or_create(name="Supervisor")

        self.supervisor = make_user("sup", "supervisor")
        self.usuario = make_user("user", "usuario")

        self.loja, self.mochila = make_base_viagem()

    # ───── criar viagem ─────

    def test_criar_viagem_ok(self):
        v = criar_viagem(self.supervisor, self.supervisor, self.loja, self.mochila)
        self.assertEqual(v.status, "andamento")
        self.assertTrue(v.checklist.exists())

    def test_usuario_nao_cria(self):
        with self.assertRaises(PermissionDenied):
            criar_viagem(self.usuario, self.usuario, self.loja, self.mochila)

    def test_mochila_em_uso(self):
        criar_viagem(self.supervisor, self.supervisor, self.loja, self.mochila)

        with self.assertRaises(MochilaEmUsoViagem):
            criar_viagem(self.supervisor, self.supervisor, self.loja, self.mochila)

    # ───── finalizar viagem ─────

    def test_finalizar_viagem(self):
        v = criar_viagem(self.supervisor, self.supervisor, self.loja, self.mochila)
        finalizar_viagem(self.supervisor, v)

        v.refresh_from_db()
        self.assertEqual(v.status, "finalizada")

    def test_finalizar_duas_vezes(self):
        v = criar_viagem(self.supervisor, self.supervisor, self.loja, self.mochila)
        finalizar_viagem(self.supervisor, v)

        with self.assertRaises(ViagemJaFinalizada):
            finalizar_viagem(self.supervisor, v)

    # ───── checklist ─────

    def test_salvar_checklist(self):
        v = criar_viagem(self.supervisor, self.supervisor, self.loja, self.mochila)
        ci = v.checklist.first()

        payload = {
            ci.pk: {
                "saida_ok": True,
                "retorno_ok": True,
                "observacao_retorno": "OK"
            }
        }

        salvar_checklist(self.supervisor, v, payload)

        ci.refresh_from_db()
        self.assertTrue(ci.retorno_ok)
        self.assertEqual(ci.observacao_retorno, "OK")

    def test_checklist_viagem_finalizada(self):
        v = criar_viagem(self.supervisor, self.supervisor, self.loja, self.mochila)
        finalizar_viagem(self.supervisor, v)

        with self.assertRaises(PermissionDenied):
            salvar_checklist(self.supervisor, v, {})


# ───────────────────────── GROUP TEST ─────────────────────────

class GroupAssignmentTest(TestCase):

    def test_nivel(self):
        user = User.objects.create_user("x", password="x")
        _assign_group(user, "supervisor")
        self.assertEqual(get_nivel(user), "supervisor")