from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from .models import Mochila, Item, Viagem, Loja, UserProfile


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
        # Only show active lojas and mochilas
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


# ─── USUÁRIO ────────────────────────────────────────────
class UsuarioCreateForm(forms.ModelForm):
    password = forms.CharField(
        label="Senha",
        min_length=10,
        widget=forms.PasswordInput(attrs={"class": "form-input", "placeholder": "Mínimo 10 caracteres"}),
    )
    password_confirm = forms.CharField(
        label="Confirmar Senha",
        widget=forms.PasswordInput(attrs={"class": "form-input", "placeholder": "Confirme a senha"}),
    )
    nivel = forms.ChoiceField(
        label="Nível de Acesso",
        choices=UserProfile.NIVEL_CHOICES,
        widget=forms.Select(attrs={"class": "form-input"}),
    )

    class Meta:
        model  = User
        fields = ["username", "first_name", "last_name", "email"]
        widgets = {
            "username":   forms.TextInput(attrs={"class": "form-input", "placeholder": "Nome de usuário"}),
            "first_name": forms.TextInput(attrs={"class": "form-input", "placeholder": "Nome"}),
            "last_name":  forms.TextInput(attrs={"class": "form-input", "placeholder": "Sobrenome"}),
            "email":      forms.EmailInput(attrs={"class": "form-input", "placeholder": "E-mail"}),
        }

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password")
        p2 = cleaned.get("password_confirm")
        if p1 and p2 and p1 != p2:
            raise ValidationError("As senhas não coincidem.")
        return cleaned


class UsuarioEditForm(forms.ModelForm):
    nivel = forms.ChoiceField(
        label="Nível de Acesso",
        choices=UserProfile.NIVEL_CHOICES,
        widget=forms.Select(attrs={"class": "form-input"}),
    )
    new_password = forms.CharField(
        label="Nova Senha (opcional)",
        required=False,
        min_length=10,
        widget=forms.PasswordInput(attrs={"class": "form-input", "placeholder": "Deixe em branco para manter"}),
    )
    new_password_confirm = forms.CharField(
        label="Confirmar Nova Senha",
        required=False,
        widget=forms.PasswordInput(attrs={"class": "form-input", "placeholder": "Confirme a nova senha"}),
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

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("new_password")
        p2 = cleaned.get("new_password_confirm")
        if p1 and p2 and p1 != p2:
            raise ValidationError("As senhas não coincidem.")
        return cleaned
