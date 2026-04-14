"""
models.py — Dados, relações e validações simples.

Padrões aplicados:
- AtivoManager como manager padrão em todos os models principais
- Método desativar() padronizado
- all_objects para acesso irrestrito (admin, migrations, etc.)
"""

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


# ─────────────────────────────────────────────
# MANAGER PADRÃO — filtra ativo=True automaticamente
# ─────────────────────────────────────────────

class AtivoManager(models.Manager):
    """
    Manager padrão que filtra registros inativos em TODAS as queries.
    Use Model.all_objects para acesso irrestrito.
    """
    def get_queryset(self):
        return super().get_queryset().filter(ativo=True)


# ─────────────────────────────────────────────
# MIXIN DE SOFT DELETE
# ─────────────────────────────────────────────

class SoftDeleteMixin(models.Model):
    """
    Mixin que adiciona soft delete padronizado.
    Nunca deleta fisicamente — apenas marca ativo=False.
    """
    ativo = models.BooleanField(default=True)

    objects     = AtivoManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def desativar(self):
        """Soft delete: marca como inativo."""
        self.ativo = False
        self.save(update_fields=["ativo"])

    def reativar(self):
        """Restaura registro inativo."""
        self.ativo = True
        self.save(update_fields=["ativo"])


# ─────────────────────────────────────────────
# POLÍTICA DE SENHA
# ─────────────────────────────────────────────

class PasswordPolicy(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="password_policy",
    )
    must_change_password = models.BooleanField(default=True)

    class Meta:
        verbose_name        = "Política de Senha"
        verbose_name_plural = "Políticas de Senha"

    def __str__(self):
        return f"{self.user.username} — trocar: {self.must_change_password}"


# ─────────────────────────────────────────────
# LOJA
# ─────────────────────────────────────────────

class Loja(SoftDeleteMixin):
    nome      = models.CharField(max_length=100, unique=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering            = ["nome"]
        verbose_name        = "Loja"
        verbose_name_plural = "Lojas"

    def __str__(self):
        return self.nome

    def pode_ser_desativada(self) -> bool:
        return not self.viagem_set.filter(status="andamento").exists()


# ─────────────────────────────────────────────
# ITEM
# ─────────────────────────────────────────────

class Item(SoftDeleteMixin):
    nome      = models.CharField(max_length=100, unique=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering            = ["nome"]
        verbose_name        = "Item"
        verbose_name_plural = "Itens"

    def __str__(self):
        return self.nome

    def pode_ser_desativado(self) -> bool:
        return not ChecklistItem.objects.filter(
            item=self,
            viagem__status="andamento",
        ).exists()


# ─────────────────────────────────────────────
# MOCHILA
# ─────────────────────────────────────────────

class Mochila(SoftDeleteMixin):
    nome  = models.CharField(max_length=100, default="Mochila")
    itens = models.ManyToManyField(Item, through="MochilaItem", related_name="mochilas")

    class Meta:
        ordering            = ["nome"]
        verbose_name        = "Mochila"
        verbose_name_plural = "Mochilas"

    def __str__(self):
        return self.nome

    def pode_ser_desativada(self) -> bool:
        return not self.viagem_set.filter(status="andamento").exists()


class MochilaItem(models.Model):
    mochila    = models.ForeignKey("Mochila", on_delete=models.CASCADE)
    item       = models.ForeignKey("Item", on_delete=models.CASCADE)
    quantidade = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ("mochila", "item")

    def __str__(self):
        return f"{self.item} x{self.quantidade}"


# ─────────────────────────────────────────────
# VIAGEM
# ─────────────────────────────────────────────

class Viagem(models.Model):
    STATUS_CHOICES = [
        ("andamento",  "Em andamento"),
        ("finalizada", "Finalizada"),
    ]

    responsavel  = models.ForeignKey(User,    on_delete=models.PROTECT)
    loja         = models.ForeignKey(Loja,    on_delete=models.PROTECT)
    mochila      = models.ForeignKey(Mochila, on_delete=models.PROTECT)

    data_saida   = models.DateTimeField(default=timezone.now)
    data_retorno = models.DateTimeField(null=True, blank=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="andamento",
    )

    class Meta:
        ordering            = ["-data_saida"]
        verbose_name        = "Viagem"
        verbose_name_plural = "Viagens"
        permissions = [
            ("supervisor_access", "Acesso de Supervisor (pode editar)"),
            ("admin_access",      "Acesso de Administrador (acesso total)"),
            ("finalizar_viagem",  "Pode finalizar viagens"),
        ]

    def __str__(self):
        return f"Viagem #{self.id} — {self.loja}"

    @property
    def em_andamento(self) -> bool:
        return self.status == "andamento"


# ─────────────────────────────────────────────
# CHECKLIST
# ─────────────────────────────────────────────

class ChecklistItem(models.Model):
    viagem             = models.ForeignKey(Viagem, on_delete=models.CASCADE, related_name="checklist")
    item               = models.ForeignKey(Item,   on_delete=models.PROTECT)
    quantidade         = models.PositiveIntegerField(default=1)

    saida_ok           = models.BooleanField(default=True)
    retorno_ok         = models.BooleanField(default=False)
    observacao_retorno = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together     = ("viagem", "item")
        verbose_name        = "Item do Checklist"
        verbose_name_plural = "Itens do Checklist"

    def __str__(self):
        return f"{self.item} — Viagem #{self.viagem_id}"
