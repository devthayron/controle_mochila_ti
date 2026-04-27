"""
tests.py — Testes unitários da camada de permissões e serviços.
"""

from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.test import TestCase

from core import permissions as perms 
from .exceptions import (
    MochilaEmUsoError,
    MochilaVaziaError,
    ViagemJaFinalizada,
    ItemEmUsoError,
    LojaEmUsoError,
)
from .models import Item, Loja, Mochila, MochilaItem
from .services.viagem_service import criar_viagem, finalizar_viagem, salvar_checklist
from .services.item_service import desativar_item
from .services.loja_service import desativar_loja
from .services.mochila_service import desativar_mochila
from .services.usuario_service import _assign_group, get_nivel


# ─────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────

def make_user(username, nivel="usuario", is_superuser=False):
    user = User.objects.create_user(username=username, password="test1234")
    user.is_superuser = is_superuser
    user.save()
    _assign_group(user, nivel)
    return user


def make_base_viagem():
    loja    = Loja.objects.create(nome="Loja Teste")
    mochila = Mochila.objects.create(nome="Mochila Teste")
    item    = Item.objects.create(nome="Item Teste")
    MochilaItem.objects.create(mochila=mochila, item=item, quantidade=1)
    return loja, mochila


# ─────────────────────────────────────────────
# PERMISSIONS
# ─────────────────────────────────────────────

class PermissionsTest(TestCase):

    def setUp(self):
        self.admin      = make_user("admin", "admin", is_superuser=True)
        self.supervisor = make_user("sup", "supervisor")
        self.usuario    = make_user("user", "usuario")

    def test_admin_pode_tudo(self):
        self.assertTrue(perms._is_admin(self.admin))
        self.assertTrue(perms._pode_editar(self.admin))

    def test_supervisor_pode_editar(self):
        self.assertTrue(perms._pode_editar(self.supervisor))
        self.assertFalse(perms._is_admin(self.supervisor))

    def test_usuario_nao_pode_editar(self):
        self.assertFalse(perms._pode_editar(self.usuario))
        self.assertFalse(perms._is_admin(self.usuario))


# ─────────────────────────────────────────────
# VIAGEM SERVICE
# ─────────────────────────────────────────────

class ViagemServiceTest(TestCase):

    def setUp(self):
        Group.objects.get_or_create(name="Supervisor")
        self.supervisor = make_user("sup", "supervisor")
        self.usuario    = make_user("user", "usuario")
        self.loja, self.mochila = make_base_viagem()

    def test_criar_viagem_ok(self):
        v = criar_viagem(self.supervisor, self.supervisor, self.loja, self.mochila)
        self.assertEqual(v.status, "andamento")
        self.assertTrue(v.checklist.exists())

    def test_usuario_nao_cria(self):
        with self.assertRaises(PermissionDenied):
            criar_viagem(self.usuario, self.usuario, self.loja, self.mochila)

    def test_mochila_em_uso(self):
        criar_viagem(self.supervisor, self.supervisor, self.loja, self.mochila)
        with self.assertRaises(MochilaEmUsoError):
            criar_viagem(self.supervisor, self.supervisor, self.loja, self.mochila)

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

    def test_salvar_checklist(self):
        v  = criar_viagem(self.supervisor, self.supervisor, self.loja, self.mochila)
        ci = v.checklist.first()
        payload = {
            ci.pk: {"saida_ok": True, "retorno_ok": True, "observacao_retorno": "OK"}
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


# ─────────────────────────────────────────────
# SOFT DELETE — ITEM
# ─────────────────────────────────────────────

class ItemSoftDeleteTest(TestCase):

    def setUp(self):
        Group.objects.get_or_create(name="Supervisor")
        self.supervisor = make_user("sup", "supervisor")
        self.item = Item.objects.create(nome="Notebook")

    def test_desativar_item_ok(self):
        desativar_item(self.supervisor, self.item)
        self.item.refresh_from_db()
        self.assertFalse(self.item.ativo)

    def test_item_sumiu_do_queryset_padrao(self):
        desativar_item(self.supervisor, self.item)
        self.assertFalse(Item.objects.filter(pk=self.item.pk).exists())
        self.assertTrue(Item.all_objects.filter(pk=self.item.pk).exists())

    def test_desativar_item_em_uso(self):
        loja, mochila = make_base_viagem()
        # "Item Teste" criado em make_base_viagem() está em mochila
        item_em_uso = Item.objects.get(nome="Item Teste")
        criar_viagem(self.supervisor, self.supervisor, loja, mochila)
        with self.assertRaises(ItemEmUsoError):
            desativar_item(self.supervisor, item_em_uso)


# ─────────────────────────────────────────────
# SOFT DELETE — MOCHILA
# ─────────────────────────────────────────────

class MochilaSoftDeleteTest(TestCase):

    def setUp(self):
        Group.objects.get_or_create(name="Supervisor")
        self.supervisor = make_user("sup", "supervisor")
        self.loja, self.mochila = make_base_viagem()

    def test_desativar_mochila_ok(self):
        desativar_mochila(self.supervisor, self.mochila)
        self.mochila.refresh_from_db()
        self.assertFalse(self.mochila.ativo)

    def test_mochila_sumiu_do_queryset_padrao(self):
        desativar_mochila(self.supervisor, self.mochila)
        self.assertFalse(Mochila.objects.filter(pk=self.mochila.pk).exists())
        self.assertTrue(Mochila.all_objects.filter(pk=self.mochila.pk).exists())

    def test_desativar_mochila_em_uso(self):
        criar_viagem(self.supervisor, self.supervisor, self.loja, self.mochila)
        with self.assertRaises(MochilaEmUsoError):
            desativar_mochila(self.supervisor, self.mochila)


# ─────────────────────────────────────────────
# SOFT DELETE — LOJA
# ─────────────────────────────────────────────

class LojaSoftDeleteTest(TestCase):

    def setUp(self):
        Group.objects.get_or_create(name="Supervisor")
        self.supervisor = make_user("sup", "supervisor")
        self.loja, self.mochila = make_base_viagem()

    def test_desativar_loja_ok(self):
        desativar_loja(self.supervisor, self.loja)
        self.loja.refresh_from_db()
        self.assertFalse(self.loja.ativo)

    def test_loja_sumiu_do_queryset_padrao(self):
        desativar_loja(self.supervisor, self.loja)
        self.assertFalse(Loja.objects.filter(pk=self.loja.pk).exists())
        self.assertTrue(Loja.all_objects.filter(pk=self.loja.pk).exists())

    def test_desativar_loja_em_uso(self):
        criar_viagem(self.supervisor, self.supervisor, self.loja, self.mochila)
        with self.assertRaises(LojaEmUsoError):
            desativar_loja(self.supervisor, self.loja)


# ─────────────────────────────────────────────
# GROUP ASSIGNMENT
# ─────────────────────────────────────────────

class GroupAssignmentTest(TestCase):

    def test_nivel_supervisor(self):
        user = User.objects.create_user("x", password="x")
        _assign_group(user, "supervisor")
        self.assertEqual(get_nivel(user), "supervisor")

    def test_nivel_usuario(self):
        user = User.objects.create_user("y", password="y")
        _assign_group(user, "usuario")
        self.assertEqual(get_nivel(user), "usuario")
