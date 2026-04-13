from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


# ───────────────── PERFIL / PERMISSÕES ─────────────────
class UserProfile(models.Model):
    NIVEL_CHOICES = [
        ("admin",      "Administrador"),
        ("supervisor", "Supervisor"),
        ("usuario",    "Usuário"),
    ]

    user  = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    nivel = models.CharField(max_length=20, choices=NIVEL_CHOICES, default="usuario")

    class Meta:
        verbose_name        = "Perfil de Usuário"
        verbose_name_plural = "Perfis de Usuários"

    def __str__(self):
        return f"{self.user.username} ({self.get_nivel_display()})"

    @property
    def is_admin(self):
        return self.nivel == "admin"

    @property
    def is_supervisor(self):
        return self.nivel == "supervisor"

    @property
    def is_usuario(self):
        return self.nivel == "usuario"

    @property
    def pode_editar(self):
        return self.nivel in ("admin", "supervisor")

    @property
    def pode_acessar_admin(self):
        return self.nivel == "admin"


# ───────────────── LOJA ─────────────────
class Loja(models.Model):
    nome       = models.CharField(max_length=100, unique=True)
    ativo      = models.BooleanField(default=True)
    criado_em  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering            = ["nome"]
        verbose_name        = "Loja"
        verbose_name_plural = "Lojas"

    def __str__(self):
        return self.nome


# ───────────────── ITEM ─────────────────
class Item(models.Model):
    nome       = models.CharField(max_length=100, unique=True)
    criado_em  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering            = ["nome"]
        verbose_name        = "Item"
        verbose_name_plural = "Itens"

    def __str__(self):
        return self.nome


# ───────────────── MOCHILA ─────────────────
class Mochila(models.Model):
    nome      = models.CharField(max_length=100, default="Mochila")
    ativo     = models.BooleanField(default=True)
    itens     = models.ManyToManyField(Item, through="MochilaItem", related_name="mochilas")

    class Meta:
        ordering            = ["nome"]
        verbose_name        = "Mochila"
        verbose_name_plural = "Mochilas"

    def __str__(self):
        return self.nome


class MochilaItem(models.Model):
    mochila    = models.ForeignKey("Mochila", on_delete=models.CASCADE)
    item       = models.ForeignKey("Item", on_delete=models.CASCADE)
    quantidade = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ("mochila", "item")

    def __str__(self):
        return f"{self.item} x{self.quantidade}"


# ───────────────── VIAGEM ─────────────────
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

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        # Only create checklist items for brand-new trips
        if is_new and not self.checklist.exists():
            ChecklistItem.objects.bulk_create([
                ChecklistItem(
                    viagem=self,
                    item=mi.item,
                    quantidade=mi.quantidade,
                )
                for mi in self.mochila.mochilaitem_set.all()
            ])

    def __str__(self):
        return f"Viagem #{self.id} — {self.loja}"


# ───────────────── CHECKLIST ─────────────────
class ChecklistItem(models.Model):
    viagem              = models.ForeignKey(Viagem, on_delete=models.CASCADE, related_name="checklist")
    item                = models.ForeignKey(Item,   on_delete=models.PROTECT)
    quantidade          = models.PositiveIntegerField(default=1)

    saida_ok            = models.BooleanField(default=True)
    retorno_ok          = models.BooleanField(default=False)
    observacao_retorno  = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together     = ("viagem", "item")
        verbose_name        = "Item do Checklist"
        verbose_name_plural = "Itens do Checklist"

    def __str__(self):
        return f"{self.item} — Viagem #{self.viagem_id}"
