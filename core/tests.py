"""
tests.py — Testes unitários da camada de permissões e serviços.

Execute: python manage.py test core
"""

from django.contrib.auth.models import Group, Permission, User
from django.core.exceptions import PermissionDenied
from django.test import TestCase

from . import permissions as perms
from .models import ChecklistItem, Item, Loja, Mochila, MochilaItem, Viagem
from .services.viagem_service import (
    ViagemJaFinalizada,
    criar_viagem,
    finalizar_viagem,
    payload_from_post,
    salvar_checklist,
)
from .views import _assign_group, _get_nivel


# ──────────────────────────────────────────────
# FIXTURES
# ──────────────────────────────────────────────

def make_user(username, nivel="usuario"):
    user = User.objects.create_user(username=username, password="test1234")
    _assign_group(user, nivel)
    return user


def _make_supervisor():
    """Cria supervisor com a permissão customizada atribuída ao grupo."""
    sup = make_user(f"sup_{User.objects.count()}", "supervisor")
    perm = Permission.objects.get(codename="supervisor_access")
    Group.objects.get(name="Supervisor").permissions.add(perm)
    return sup


def make_viagem(responsavel=None):
    """
    FIX: usa criar_viagem() do service para garantir que o checklist
    seja criado corretamente, já que Viagem.save() não faz mais isso.
    """
    loja    = Loja.objects.create(nome=f"Loja {Loja.objects.count() + 1}")
    mochila = Mochila.objects.create(nome=f"Mochila {Mochila.objects.count() + 1}")
    item    = Item.objects.create(nome=f"Item {Item.objects.count() + 1}")
    MochilaItem.objects.create(mochila=mochila, item=item, quantidade=1)

    if responsavel is None:
        responsavel = _make_supervisor()

    return criar_viagem(
        user=responsavel,
        responsavel=responsavel,
        loja=loja,
        mochila=mochila,
    )


# ──────────────────────────────────────────────
# PERMISSIONS TESTS
# ──────────────────────────────────────────────

class PermissionsTest(TestCase):

    def setUp(self):
        self.admin = make_user("admin_user", "admin")
        self.admin.is_superuser = True
        self.admin.save()

        self.supervisor = make_user("supervisor_user", "supervisor")
        perm = Permission.objects.get(codename="supervisor_access")
        group = Group.objects.get(name="Supervisor")
        group.permissions.add(perm)

        self.usuario = make_user("usuario_user", "usuario")

    def test_supervisor_pode_editar(self):
        self.assertTrue(perms._pode_editar(self.supervisor))

    def test_usuario_nao_pode_editar(self):
        self.assertFalse(perms._pode_editar(self.usuario))

    def test_admin_pode_tudo(self):
        self.assertTrue(perms._pode_editar(self.admin))
        self.assertTrue(perms._is_admin(self.admin))

    def test_usuario_ve_propria_viagem(self):
        viagem = make_viagem(responsavel=self.supervisor)
        viagem.responsavel = self.usuario
        viagem.save(update_fields=["responsavel"])
        self.assertTrue(perms.pode_ver_viagem(self.usuario, viagem))

    def test_usuario_nao_ve_viagem_alheia(self):
        outro = _make_supervisor()
        viagem = make_viagem(responsavel=outro)
        self.assertFalse(perms.pode_ver_viagem(self.usuario, viagem))

    def test_supervisor_ve_qualquer_viagem(self):
        viagem = make_viagem()
        self.assertTrue(perms.pode_ver_viagem(self.supervisor, viagem))

    def test_filtrar_viagens_usuario(self):
        v1 = make_viagem(responsavel=self.supervisor)
        v1.responsavel = self.usuario
        v1.save(update_fields=["responsavel"])
        v2 = make_viagem()
        qs = perms.filtrar_viagens(self.usuario, Viagem.objects.all())
        self.assertIn(v1, qs)
        self.assertNotIn(v2, qs)

    def test_filtrar_viagens_supervisor(self):
        v1 = make_viagem(responsavel=self.supervisor)
        v2 = make_viagem()
        qs = perms.filtrar_viagens(self.supervisor, Viagem.objects.all())
        self.assertIn(v1, qs)
        self.assertIn(v2, qs)


# ──────────────────────────────────────────────
# SERVICE TESTS
# ──────────────────────────────────────────────

class ViagemServiceTest(TestCase):

    def setUp(self):
        self.supervisor = make_user("sup", "supervisor")
        perm = Permission.objects.get(codename="supervisor_access")
        Group.objects.get(name="Supervisor").permissions.add(perm)

        self.usuario = make_user("usr", "usuario")

        self.loja    = Loja.objects.create(nome="Loja Teste")
        self.mochila = Mochila.objects.create(nome="Mochila Teste")
        self.item    = Item.objects.create(nome="Notebook")
        MochilaItem.objects.create(mochila=self.mochila, item=self.item, quantidade=1)

    # --- criar_viagem ---

    def test_supervisor_cria_viagem(self):
        v = criar_viagem(self.supervisor, self.supervisor, self.loja, self.mochila)
        self.assertEqual(v.status, "andamento")
        self.assertEqual(v.checklist.count(), 1)

    def test_usuario_nao_cria_viagem(self):
        with self.assertRaises(PermissionDenied):
            criar_viagem(self.usuario, self.usuario, self.loja, self.mochila)

    def test_nao_cria_viagem_mochila_vazia(self):
        mochila_vazia = Mochila.objects.create(nome="Vazia")
        with self.assertRaises(ValueError):
            criar_viagem(self.supervisor, self.supervisor, self.loja, mochila_vazia)

    # --- finalizar_viagem ---

    def test_supervisor_finaliza_viagem(self):
        v = criar_viagem(self.supervisor, self.supervisor, self.loja, self.mochila)
        finalizar_viagem(self.supervisor, v)
        v.refresh_from_db()
        self.assertEqual(v.status, "finalizada")
        self.assertIsNotNone(v.data_retorno)

    def test_usuario_nao_finaliza_viagem(self):
        v = criar_viagem(self.supervisor, self.supervisor, self.loja, self.mochila)
        with self.assertRaises(PermissionDenied):
            finalizar_viagem(self.usuario, v)

    def test_nao_finaliza_viagem_ja_finalizada(self):
        v = criar_viagem(self.supervisor, self.supervisor, self.loja, self.mochila)
        finalizar_viagem(self.supervisor, v)
        with self.assertRaises(ViagemJaFinalizada):
            finalizar_viagem(self.supervisor, v)

    # --- salvar_checklist ---

    def test_salvar_checklist(self):
        v  = criar_viagem(self.supervisor, self.supervisor, self.loja, self.mochila)
        ci = v.checklist.first()
        # FIX: ci nunca é None aqui porque criar_viagem() gera o checklist
        self.assertIsNotNone(ci, "Checklist deve ser criado por criar_viagem()")
        payload = {ci.pk: {"saida_ok": True, "retorno_ok": True, "observacao_retorno": "OK"}}
        salvar_checklist(self.supervisor, v, payload)
        ci.refresh_from_db()
        self.assertTrue(ci.retorno_ok)
        self.assertEqual(ci.observacao_retorno, "OK")

    def test_nao_salva_checklist_viagem_finalizada(self):
        v = criar_viagem(self.supervisor, self.supervisor, self.loja, self.mochila)
        finalizar_viagem(self.supervisor, v)
        with self.assertRaises(PermissionDenied):
            salvar_checklist(self.supervisor, v, {})

    # --- payload_from_post ---

    def test_payload_from_post(self):
        post   = {"saida_ok_1": "on", "obs_1": "Testando"}
        result = payload_from_post(post, [1])
        self.assertTrue(result[1]["saida_ok"])
        self.assertFalse(result[1]["retorno_ok"])
        self.assertEqual(result[1]["observacao_retorno"], "Testando")


# ──────────────────────────────────────────────
# GROUP ASSIGNMENT TESTS
# ──────────────────────────────────────────────

class GroupAssignmentTest(TestCase):

    def test_assign_and_read_nivel(self):
        user = User.objects.create_user("tester", password="x")
        _assign_group(user, "supervisor")
        self.assertEqual(_get_nivel(user), "supervisor")

    def test_reassign_changes_group(self):
        user = User.objects.create_user("tester2", password="x")
        _assign_group(user, "supervisor")
        _assign_group(user, "usuario")
        self.assertEqual(_get_nivel(user), "usuario")
        self.assertEqual(user.groups.count(), 1)