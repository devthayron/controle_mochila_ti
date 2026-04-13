from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from .models import Mochila, Item, Viagem, Loja

NIVEL_CHOICES = [
    ("usuario",    "Usuário"),
    ("supervisor", "Supervisor"),
    ("admin",      "Administrador"),
]


class MochilaForm(forms.ModelForm):
    itens = forms.ModelMultipleChoiceField(
        queryset=Item.objects.all().order_by("nome"),
        widget=forms.SelectMultiple(attrs={"class": "multi-select"}),
        label="Itens / Equipamentos",
    )

    class Meta:
        model  = Mochila
        fields = ["nome", "itens"]
        widgets = {
            "nome": forms.TextInput(attrs={"class": "form-input", "placeholder": "Nome da mochila"})
        }


class ViagemForm(forms.ModelForm):
    class Meta:
        model  = Viagem
        fields = ["responsavel", "loja", "mochila"]
        widgets = {
            "responsavel": forms.Select(attrs={"class": "form-input"}),
            "loja":        forms.Select(attrs={"class": "form-input"}),
            "mochila":     forms.Select(attrs={"class": "form-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["loja"].queryset    = Loja.objects.filter(ativo=True).order_by("nome")
        self.fields["mochila"].queryset = Mochila.objects.filter(ativo=True).order_by("nome")


class LojaForm(forms.ModelForm):
    class Meta:
        model  = Loja
        fields = ["nome"]
        widgets = {
            "nome": forms.TextInput(attrs={"class": "form-input", "placeholder": "Nome da loja"})
        }


class ItemForm(forms.ModelForm):
    class Meta:
        model  = Item
        fields = ["nome"]
        widgets = {
            "nome": forms.TextInput(attrs={"class": "form-input", "placeholder": "Nome do item / equipamento"})
        }


# ─── CRIAÇÃO DE USUÁRIO — sem campo senha ───────────────────────
class UsuarioCreateForm(forms.ModelForm):
    """
    Admin preenche apenas username, nome e nível.
    Senha padrão é definida automaticamente no service.
    """
    nivel = forms.ChoiceField(
        label="Nível de Acesso",
        choices=NIVEL_CHOICES,
        initial="usuario",
        widget=forms.Select(attrs={"class": "form-input"}),
    )

    class Meta:
        model  = User
        fields = ["username", "first_name", "last_name", "email"]
        widgets = {
            "username":   forms.TextInput(attrs={"class": "form-input", "placeholder": "Nome de usuário"}),
            "first_name": forms.TextInput(attrs={"class": "form-input", "placeholder": "Nome"}),
            "last_name":  forms.TextInput(attrs={"class": "form-input", "placeholder": "Sobrenome"}),
            "email":      forms.EmailInput(attrs={"class": "form-input", "placeholder": "E-mail (opcional)"}),
        }


# ─── EDIÇÃO DE USUÁRIO — sem campo senha ────────────────────────
class UsuarioEditForm(forms.ModelForm):
    """
    Edita apenas dados e nível. Senha nunca é alterada aqui.
    Reset de senha é operação separada (somente admin).
    """
    nivel = forms.ChoiceField(
        label="Nível de Acesso",
        choices=NIVEL_CHOICES,
        widget=forms.Select(attrs={"class": "form-input"}),
    )

    class Meta:
        model  = User
        fields = ["username", "first_name", "last_name", "email"]
        widgets = {
            "username":   forms.TextInput(attrs={"class": "form-input"}),
            "first_name": forms.TextInput(attrs={"class": "form-input"}),
            "last_name":  forms.TextInput(attrs={"class": "form-input"}),
            "email":      forms.EmailInput(attrs={"class": "form-input"}),
        }


# ─── TROCA DE SENHA (primeiro acesso) ───────────────────────────
class TrocarSenhaForm(forms.Form):
    senha_atual = forms.CharField(
        label="Senha atual",
        widget=forms.PasswordInput(attrs={
            "class": "form-input",
            "placeholder": "Senha atual",
            "autocomplete": "current-password",
        }),
    )
    nova_senha = forms.CharField(
        label="Nova senha",
        min_length=8,
        widget=forms.PasswordInput(attrs={
            "class": "form-input",
            "placeholder": "Mínimo 8 caracteres",
            "autocomplete": "new-password",
        }),
    )
    nova_senha_confirm = forms.CharField(
        label="Confirmar nova senha",
        widget=forms.PasswordInput(attrs={
            "class": "form-input",
            "placeholder": "Repita a nova senha",
            "autocomplete": "new-password",
        }),
    )

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("nova_senha")
        p2 = cleaned.get("nova_senha_confirm")
        if p1 and p2 and p1 != p2:
            raise ValidationError("As novas senhas não coincidem.")
        return cleaned