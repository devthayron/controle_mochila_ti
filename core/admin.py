from django.contrib import admin
from .models import Loja, Item, Mochila, Viagem, ChecklistItem, MochilaItem, UserProfile
from .forms import MochilaForm


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "nivel"]
    list_filter = ["nivel"]
    search_fields = ["user__username"]


@admin.register(Loja)
class LojaAdmin(admin.ModelAdmin):
    search_fields = ["nome"]
    list_display = ["id", "nome"]


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    search_fields = ["nome"]
    list_display = ["id", "nome"]


class MochilaItemInline(admin.TabularInline):
    model = MochilaItem
    extra = 1
    autocomplete_fields = ['item']
    fields = ['item', 'quantidade']


@admin.register(Mochila)
class MochilaAdmin(admin.ModelAdmin):
    inlines = [MochilaItemInline]
    form = MochilaForm
    list_display = ["id", "nome"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            itens = form.cleaned_data['itens']
            MochilaItem.objects.bulk_create([
                MochilaItem(mochila=obj, item=item, quantidade=1)
                for item in itens
            ])


class ChecklistInline(admin.TabularInline):
    model = ChecklistItem
    extra = 0
    can_delete = False
    fields = ["item", "quantidade", "saida_ok", "retorno_ok", "observacao_retorno"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Viagem)
class ViagemAdmin(admin.ModelAdmin):
    list_display = ["id", "responsavel", "loja", "mochila", "status"]
    list_filter = ["status", "loja"]
    search_fields = ["responsavel__username"]
    inlines = [ChecklistInline]

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ["mochila"]
        return []

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change and not obj.checklist.exists():
            itens = obj.mochila.itens.all()
            ChecklistItem.objects.bulk_create([
                ChecklistItem(viagem=obj, item=item)
                for item in itens
            ])
