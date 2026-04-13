from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_userprofile'),
    ]

    operations = [
        migrations.AddField(
            model_name='loja',
            name='ativo',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='loja',
            name='criado_em',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='item',
            name='criado_em',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='mochila',
            name='ativo',
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name='viagem',
            name='data_saida',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AlterField(
            model_name='checklistitem',
            name='observacao_retorno',
            field=models.CharField(max_length=255, blank=True),
        ),
        migrations.AlterUniqueTogether(
            name='mochilaitem',
            unique_together={('mochila', 'item')},
        ),
        migrations.AlterUniqueTogether(
            name='checklistitem',
            unique_together={('viagem', 'item')},
        ),
    ]
