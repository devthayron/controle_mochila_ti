from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from core.models import (
    ChecklistItem, Item, Loja, Mochila, MochilaItem, UserProfile, Viagem,
)


class Command(BaseCommand):
    help = "Cria grupos e permissões do sistema (idempotente)."

    # ──────────────────────────────────────────
    # PERMISSÕES POR GRUPO
    # ──────────────────────────────────────────

    # (app_label, codename)
    SUPERVISOR_PERMS = [
        # Viagem
        ("core", "add_viagem"),
        ("core", "change_viagem"),
        ("core", "view_viagem"),
        ("core", "supervisor_access"),      # custom
        ("core", "finalizar_viagem"),        # custom
        # Checklist
        ("core", "add_checklistitem"),
        ("core", "change_checklistitem"),
        ("core", "view_checklistitem"),
        # Mochila
        ("core", "add_mochila"),
        ("core", "change_mochila"),
        ("core", "delete_mochila"),
        ("core", "view_mochila"),
        # MochilaItem
        ("core", "add_mochilaitem"),
        ("core", "change_mochilaitem"),
        ("core", "delete_mochilaitem"),
        # Loja
        ("core", "add_loja"),
        ("core", "change_loja"),
        ("core", "delete_loja"),
        ("core", "view_loja"),
        # Item
        ("core", "add_item"),
        ("core", "change_item"),
        ("core", "delete_item"),
        ("core", "view_item"),
    ]

    USUARIO_PERMS = [
        ("core", "view_viagem"),
        ("core", "view_checklistitem"),
        ("core", "view_mochila"),
        ("core", "view_loja"),
        ("core", "view_item"),
    ]

    def handle(self, *args, **options):
        self._create_admin_group()
        self._create_supervisor_group()
        self._create_usuario_group()
        self.stdout.write(self.style.SUCCESS("Grupos e permissões configurados com sucesso."))

    def _create_admin_group(self):
        group, created = Group.objects.get_or_create(name="Admin")
        action = "criado" if created else "já existe"
        self.stdout.write(f"  Grupo 'Admin' {action}.")

    def _create_supervisor_group(self):
        group, _ = Group.objects.get_or_create(name="Supervisor")
        perms = self._resolve_permissions(self.SUPERVISOR_PERMS)
        group.permissions.set(perms)
        self.stdout.write(f"  Grupo 'Supervisor' configurado com {len(perms)} permissões.")

    def _create_usuario_group(self):
        group, _ = Group.objects.get_or_create(name="Usuário")
        perms = self._resolve_permissions(self.USUARIO_PERMS)
        group.permissions.set(perms)
        self.stdout.write(f"  Grupo 'Usuário' configurado com {len(perms)} permissões.")

    def _resolve_permissions(self, perm_list: list[tuple[str, str]]) -> list[Permission]:
        resolved = []
        for app_label, codename in perm_list:
            try:
                perm = Permission.objects.get(
                    codename=codename,
                    content_type__app_label=app_label,
                )
                resolved.append(perm)
            except Permission.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(f"    Permissão não encontrada: {app_label}.{codename}")
                )
        return resolved
