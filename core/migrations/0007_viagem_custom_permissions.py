"""
0007_viagem_custom_permissions.py

Adiciona as permissões customizadas ao model Viagem:
  - supervisor_access
  - admin_access
  - finalizar_viagem

Execute: python manage.py migrate
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        # Ajuste para a última migration existente no seu projeto
        ("core", "0006_alter_checklistitem_options_alter_item_options_and_more"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="viagem",
            options={
                "ordering": ["-data_saida"],
                "verbose_name": "Viagem",
                "verbose_name_plural": "Viagens",
                "permissions": [
                    ("supervisor_access", "Acesso de Supervisor (pode editar)"),
                    ("admin_access",      "Acesso de Administrador (acesso total)"),
                    ("finalizar_viagem",  "Pode finalizar viagens"),
                ],
            },
        ),
    ]
