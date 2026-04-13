from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.db import transaction

from .forms import MochilaForm
from .models import (
    ChecklistItem, Item, Loja, Mochila, MochilaItem,
    PasswordPolicy, Viagem,
)
from .services.mochila_service import MochilaEmUsoMochila, desativar_mochila
from .services.usuario_service import resetar_senha


# ──────────────────────────────────────────────
# AUDIT LOG (somente leitura)
# ──────────────────────────────────────────────

@admin.register(LogEntry)
class LogEntryAdmin(admin.ModelAdmin):
    list_display  = ("action_time", "user", "content_type", "object_repr", "action_flag")
    list_filter   = ("action_flag", "content_type", "user")
    search_fields = ("object_repr",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ──────────────────────────────────────────────
# PASSWORD POLICY
# ──────────────────────────────────────────────

@admin.register(PasswordPolicy)
class PasswordPolicyAdmin(admin.ModelAdmin):
    list_display  = ["user", "must_change_password"]
    list_filter   = ["must_change_password"]
    search_fields = ["user__username"]
    actions       = ["forcar_troca", "resetar_senha_padrao"]

    @admin.action(description="Forçar troca de senha no próximo login")
    def forcar_troca(self, request, queryset):
        queryset.update(must_change_password=True)

    @admin.action(description="Redefinir para senha padrão (Dti@paraiba)")
    def resetar_senha_padrao(self, request, queryset):
        for policy in queryset.select_related("user"):
            resetar_senha(actor=request.user, target=policy.user)
        self.message_user(request, "Senhas redefinidas com sucesso.")


# ──────────────────────────────────────────────
# LOJA
# ──────────────────────────────────────────────

@admin.register(Loja)
class LojaAdmin(admin.ModelAdmin):
    search_fields = ["nome"]
    list_display  = ["id", "nome", "ativo", "criado_em"]
    list_filter   = ["ativo"]
    actions       = ["ativar_lojas", "desativar_lojas"]

    @admin.action(description="Ativar lojas selecionadas")
    def ativar_lojas(self, request, queryset):
        queryset.update(ativo=True)

    @admin.action(description="Desativar lojas selecionadas")
    def desativar_lojas(self, request, queryset):
        bloqueadas = []
        for loja in queryset:
            if not loja.pode_ser_desativada():
                bloqueadas.append(loja.nome)
            else:
                loja.ativo = False
                loja.save(update_fields=["ativo"])
        if bloqueadas:
            self.message_user(
                request,
                f"Não foi possível desativar: {', '.join(bloqueadas)} (viagem em andamento).",
                level="warning",
            )


# ──────────────────────────────────────────────
# ITEM
# ──────────────────────────────────────────────

@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    search_fields = ["nome"]
    list_display  = ["id", "nome", "ativo", "criado_em"]
    list_filter   = ["ativo"]
    actions       = ["ativar_itens", "desativar_itens"]

    @admin.action(description="Ativar itens selecionados")
    def ativar_itens(self, request, queryset):
        queryset.update(ativo=True)

    @admin.action(description="Desativar itens selecionados")
    def desativar_itens(self, request, queryset):
        bloqueados = []
        for item in queryset:
            if not item.pode_ser_desativado():
                bloqueados.append(item.nome)
            else:
                item.ativo = False
                item.save(update_fields=["ativo"])
        if bloqueados:
            self.message_user(
                request,
                f"Não foi possível desativar: {', '.join(bloqueados)} (em viagem ativa).",
                level="warning",
            )


# ──────────────────────────────────────────────
# MOCHILA
# ──────────────────────────────────────────────

class MochilaItemInline(admin.TabularInline):
    model               = MochilaItem
    extra               = 1
    autocomplete_fields = ["item"]
    fields              = ["item", "quantidade"]


@admin.register(Mochila)
class MochilaAdmin(admin.ModelAdmin):
    inlines       = [MochilaItemInline]
    list_display  = ["id", "nome", "ativo", "num_itens", "em_viagem_ativa"]
    list_filter   = ["ativo"]
    search_fields = ["nome"]
    actions       = ["ativar_mochilas", "desativar_mochilas"]

    @admin.display(description="Itens")
    def num_itens(self, obj):
        return obj.mochilaitem_set.count()

    @admin.display(description="Em viagem ativa", boolean=True)
    def em_viagem_ativa(self, obj):
        return not obj.pode_ser_desativada()

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            itens = form.cleaned_data.get("itens", [])
            MochilaItem.objects.bulk_create([
                MochilaItem(mochila=obj, item=item, quantidade=1)
                for item in itens
            ])

    def delete_model(self, request, obj):
        try:
            desativar_mochila(user=request.user, mochila=obj)
        except MochilaEmUsoMochila as e:
            self.message_user(request, str(e), level="error")

    def delete_queryset(self, request, queryset):
        bloqueadas = []
        for m in queryset:
            try:
                desativar_mochila(user=request.user, mochila=m)
            except MochilaEmUsoMochila:
                bloqueadas.append(m.nome)
        if bloqueadas:
            self.message_user(
                request,
                f"Não foi possível desativar: {', '.join(bloqueadas)} (em viagem ativa).",
                level="warning",
            )

    @admin.action(description="Ativar mochilas selecionadas")
    def ativar_mochilas(self, request, queryset):
        queryset.update(ativo=True)

    @admin.action(description="Desativar mochilas selecionadas (soft delete)")
    def desativar_mochilas(self, request, queryset):
        self.delete_queryset(request, queryset)


# ──────────────────────────────────────────────
# VIAGEM
# ──────────────────────────────────────────────

class ChecklistInline(admin.TabularInline):
    model      = ChecklistItem
    extra      = 0
    can_delete = False
    fields     = ["item", "quantidade", "saida_ok", "retorno_ok", "observacao_retorno"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Viagem)
class ViagemAdmin(admin.ModelAdmin):
    list_display   = ["id", "responsavel", "loja", "mochila", "status", "data_saida", "data_retorno"]
    list_filter    = ["status", "loja"]
    search_fields  = ["responsavel__username", "loja__nome", "mochila__nome"]
    inlines        = [ChecklistInline]
    date_hierarchy = "data_saida"

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ["mochila", "data_saida"]
        return []


@admin.register(ChecklistItem)
class ChecklistItemAdmin(admin.ModelAdmin):
    list_display  = ["viagem", "item", "quantidade", "saida_ok", "retorno_ok", "observacao_retorno"]
    list_filter   = ["saida_ok", "retorno_ok", "viagem__status"]
    search_fields = ["item__nome", "viagem__id"]
    raw_id_fields = ["viagem"]