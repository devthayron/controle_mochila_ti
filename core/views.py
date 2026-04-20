"""
views.py — Apenas orquestração HTTP.

Regras:
- Views NUNCA contêm lógica de negócio
- Views NUNCA fazem validações de domínio
- Views chamam services e tratam exceções
- Toda regra de acesso fica em permissions.py
- Toda regra de negócio fica em services/
"""

import json
import logging

from django.contrib import messages
from django.contrib.admin.models import ADDITION, CHANGE, DELETION, LogEntry
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.http import require_POST
from django.views.generic import (
    CreateView, DetailView, ListView,
    TemplateView, UpdateView,
)

from . import permissions as perms
from .exceptions import (
    AutoExclusaoError,
    DomainError,
    ItemEmUsoError,
    LojaEmUsoError,
    MochilaEmUsoError,
    SenhaFracaError,
    SenhaIncorretaError,
    ViagemJaFinalizada,
)
from .forms import (
    ItemForm, LojaForm, MochilaForm,
    TrocarSenhaForm, UsuarioCreateForm, UsuarioEditForm, ViagemForm,
)
from .mixins import AdminRequiredMixin, NivelMixin, PermContextMixin, SupervisorRequiredMixin
from .models import ChecklistItem, Item, Loja, Mochila, MochilaItem, Viagem
from .services.item_service import desativar_item
from .services.loja_service import desativar_loja
from .services.mochila_service import desativar_mochila, sincronizar_itens
from .services.usuario_service import (
    criar_usuario,
    editar_usuario,
    excluir_usuario,
    get_nivel,
    resetar_senha,
    trocar_senha,
)
from .services.viagem_service import (
    criar_viagem,
    finalizar_viagem,
    payload_from_post,
    salvar_checklist,
)

from django.http import HttpResponse
from django.template.loader import render_to_string
from weasyprint import HTML
from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied

from .models import Viagem
from . import permissions as perms


logger = logging.getLogger("core")


# ──────────────────────────────────────────────
# AUDIT LOG HELPER
# ──────────────────────────────────────────────

def _log(user, obj, flag, message=""):
    if not user or not user.pk:
        return
    content_type = ContentType.objects.get_for_model(obj.__class__, for_concrete_model=True)
    LogEntry.objects.create(
        user_id=user.pk,
        content_type_id=content_type.pk,
        object_id=str(obj.pk),
        object_repr=str(obj)[:200],
        action_flag=flag,
        change_message=message[:255],
    )


def _shim(u):
    from .mixins import _LegacyProfileShim
    return _LegacyProfileShim(u)


# ──────────────────────────────────────────────
# AUTH
# ──────────────────────────────────────────────

class CustomLoginView(LoginView):
    template_name = "core/login.html"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["username"].widget.attrs.update({
            "placeholder": "Usuário", "class": "login-input",
            "autocomplete": "username",
        })
        form.fields["password"].widget.attrs.update({
            "placeholder": "Senha", "class": "login-input",
            "autocomplete": "current-password",
        })
        return form

    def form_invalid(self, form):
        logger.warning(
            "Login falhou para: %s — IP: %s",
            form.data.get("username", "?"),
            self.request.META.get("REMOTE_ADDR"),
        )
        return super().form_invalid(form)


class CustomLogoutView(LogoutView):
    next_page = "login"


# ──────────────────────────────────────────────
# TROCA DE SENHA OBRIGATÓRIA
# ──────────────────────────────────────────────

class TrocarSenhaView(View):
    template_name = "core/trocar_senha.html"

    def _ctx(self, request, form):
        u = request.user
        return {
            "form": form,
            "user_profile": _shim(u),
            "user_perms": {
                "pode_editar": perms._pode_editar(u),
                "is_admin":    perms._is_admin(u),
            },
        }

    def get(self, request):
        if not request.user.is_authenticated:
            return redirect("login")
        return render(request, self.template_name, self._ctx(request, TrocarSenhaForm()))

    def post(self, request):
        if not request.user.is_authenticated:
            return redirect("login")

        form = TrocarSenhaForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, self._ctx(request, form))

        try:
            trocar_senha(
                user=request.user,
                senha_atual=form.cleaned_data["senha_atual"],
                nova_senha=form.cleaned_data["nova_senha"],
            )
        except (SenhaIncorretaError, SenhaFracaError) as e:
            messages.error(request, str(e))
            return render(request, self.template_name, self._ctx(request, form))

        update_session_auth_hash(request, request.user)
        messages.success(request, "Senha alterada com sucesso!")
        return redirect("dashboard")


# ──────────────────────────────────────────────
# DASHBOARD
# ──────────────────────────────────────────────

class DashboardView(PermContextMixin, TemplateView):
    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        inicio_mes = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        viagens_qs = perms.filtrar_viagens(
            self.request.user,
            Viagem.objects.select_related("responsavel", "loja", "mochila"),
        )

        context.update({
            "total_andamento":   viagens_qs.filter(status="andamento").count(),
            "total_finalizadas": viagens_qs.filter(
                status="finalizada", data_retorno__gte=inicio_mes
            ).count(),
            "total_mochilas":    Mochila.objects.count(),
            "total_lojas":       Loja.objects.count(),
            "viagens_andamento": viagens_qs.filter(status="andamento").order_by("-data_saida")[:10],
            "ultimas_viagens":   viagens_qs.order_by("-id")[:8],
            "mochilas":          Mochila.objects.prefetch_related("mochilaitem_set__item"),
        })
        return context


# ──────────────────────────────────────────────
# VIAGENS
# ──────────────────────────────────────────────


class ViagemChecklistPDFView(View):
    def get(self, request, pk):
        viagem = get_object_or_404(Viagem, pk=pk)

        if not perms.pode_ver_viagem(request.user, viagem):
            raise PermissionDenied("Sem acesso a esta viagem.")
        checklist = viagem.checklist.select_related("item").order_by("item__nome")

        context = {
            "viagem": viagem,
            "checklist_items": checklist,
        }

        html_string = render_to_string("core/viagem_checklist_pdf.html", context)

        pdf = HTML(string=html_string).write_pdf()

        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="viagem_{viagem.id}_checklist.pdf"'

        return response


class ViagemListView(PermContextMixin, ListView):
    model = Viagem
    template_name = "core/viagem_list.html"
    context_object_name = "viagens"
    paginate_by = 15

    def get_queryset(self):
        qs = perms.filtrar_viagens(
            self.request.user,
            Viagem.objects.select_related("responsavel", "loja", "mochila").order_by("-id"),
        )
        q      = self.request.GET.get("q", "").strip()
        status = self.request.GET.get("status")
        loja   = self.request.GET.get("loja")

        if q:
            qs = qs.filter(
                Q(responsavel__username__icontains=q) |
                Q(responsavel__first_name__icontains=q) |
                Q(responsavel__last_name__icontains=q) |
                Q(loja__nome__icontains=q)
            )
        if status:
            qs = qs.filter(status=status)
        if loja:
            qs = qs.filter(loja_id=loja)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["lojas"] = Loja.objects.all()
        return context


class ViagemDetailView(PermContextMixin, DetailView):
    model = Viagem
    template_name = "core/viagem_detail.html"
    context_object_name = "viagem"

    def get_object(self, queryset=None):
        viagem = get_object_or_404(Viagem, pk=self.kwargs["pk"])
        if not perms.pode_ver_viagem(self.request.user, viagem):
            raise PermissionDenied("Você não tem acesso a esta viagem.")
        return viagem

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        checklist = self.object.checklist.select_related("item").order_by("item__nome")
        total = checklist.count()
        retornados_ok = checklist.filter(retorno_ok=True).count()
        context.update({
            "checklist_items": checklist,
            "retornados_ok":   retornados_ok,
            "total_itens":     total,
            "pendentes":       total - retornados_ok,
            "pode_editar_checklist": perms.pode_editar_checklist(self.request.user, self.object),
        })
        return context


class ViagemCreateView(SupervisorRequiredMixin, CreateView):
    model = Viagem
    form_class = ViagemForm
    template_name = "core/viagem_form.html"

    def get_success_url(self):
        return reverse_lazy("viagem_detail", kwargs={"pk": self.object.pk})

    def form_valid(self, form):
        try:
            self.object = criar_viagem(
                user=self.request.user,
                responsavel=form.cleaned_data["responsavel"],
                loja=form.cleaned_data["loja"],
                mochila=form.cleaned_data["mochila"],
            )
        except (PermissionDenied, DomainError) as e:
            messages.error(self.request, str(e))
            return self.form_invalid(form)

        _log(self.request.user, self.object, ADDITION, "Viagem criada")
        messages.success(self.request, "Viagem registrada com sucesso!")
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        mochilas_dict = {}
        for m in Mochila.objects.prefetch_related("mochilaitem_set__item"):
            mochilas_dict[str(m.pk)] = [
                {"item": mi.item.nome, "quantidade": mi.quantidade}
                for mi in m.mochilaitem_set.all()
            ]
        context["mochilas_json"] = json.dumps(mochilas_dict)
        return context


@method_decorator(require_POST, name="dispatch")
class FinalizarViagemView(SupervisorRequiredMixin, View):
    def post(self, request, pk):
        viagem = get_object_or_404(Viagem, pk=pk)
        if not perms.pode_ver_viagem(request.user, viagem):
            messages.error(request, "Você não tem acesso a esta viagem.")
            return redirect("viagem_list")
        try:
            finalizar_viagem(user=request.user, viagem=viagem)
        except (PermissionDenied, ViagemJaFinalizada) as e:
            messages.error(request, str(e))
            return redirect("viagem_detail", pk=pk)

        _log(request.user, viagem, CHANGE, "Viagem finalizada")
        messages.success(request, "Viagem finalizada com sucesso!")
        return redirect("viagem_detail", pk=pk)


class ChecklistSaveView(PermContextMixin, View):
    def post(self, request, pk):
        viagem = get_object_or_404(Viagem, pk=pk)

        # 🔒 valida permissão correta (edição, não só visualização)
        if not perms.pode_editar_checklist(request.user, viagem):
            messages.error(request, "Você não pode editar este checklist.")
            return redirect("viagem_detail", pk=pk)

        checklist_ids = list(viagem.checklist.values_list("pk", flat=True))
        payload = payload_from_post(request.POST, checklist_ids)

        try:
            salvar_checklist(
                user=request.user,
                viagem=viagem,
                payload=payload
            )
        except PermissionDenied as e:
            messages.error(request, str(e))
            return redirect("viagem_detail", pk=pk)

        messages.success(request, "Checklist salvo com sucesso!")
        return redirect("viagem_detail", pk=pk)


# ──────────────────────────────────────────────
# MOCHILAS
# ──────────────────────────────────────────────

class MochilaListView(PermContextMixin, ListView):
    model = Mochila
    template_name = "core/mochila_list.html"
    context_object_name = "mochilas"

    def get_queryset(self):
        return Mochila.objects.prefetch_related("mochilaitem_set__item")


class MochilaDetailView(PermContextMixin, DetailView):
    model = Mochila
    template_name = "core/mochila_detail.html"
    context_object_name = "mochila"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["viagens"] = (
            Viagem.objects.filter(mochila=self.object)
            .select_related("loja", "responsavel")
            .order_by("-id")
        )
        return context


def _parse_itens_post(post_data) -> dict[int, int]:
    """Extrai {item_id: quantidade} do POST do formulário de mochila."""
    result = {}
    for raw_id in post_data.getlist("item_ids"):
        try:
            item_id = int(raw_id)
            qty     = int(post_data.get(f"qty_{item_id}", 1))
            result[item_id] = max(1, min(99, qty))
        except (ValueError, TypeError):
            continue
    return result


def _mochila_context(mochila=None) -> dict:
    """Contexto compartilhado para criar e editar mochila."""
    itens_qs = Item.objects.order_by("nome")
    qtd_map: dict[int, int] = {}
    if mochila:
        qtd_map = {
            mi.item_id: mi.quantidade
            for mi in MochilaItem.objects.filter(mochila=mochila)
        }

    todos_itens = []
    for item in itens_qs:
        item.quantidade_atual = qtd_map.get(item.id, 1)
        todos_itens.append(item)

    return {
        "todos_itens":        todos_itens,
        "itens_selecionados": {str(k) for k in qtd_map.keys()},
    }


class MochilaCreateView(SupervisorRequiredMixin, CreateView):
    model      = Mochila
    form_class = MochilaForm
    template_name = "core/mochila_form.html"
    success_url   = reverse_lazy("mochila_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(_mochila_context())
        ctx["editing"] = False
        return ctx

    def form_valid(self, form):
        itens_qtd = _parse_itens_post(self.request.POST)

        with transaction.atomic():
            self.object = form.save()
            sincronizar_itens(self.request.user, self.object, itens_qtd)

        _log(self.request.user, self.object, ADDITION, "Mochila criada")
        messages.success(self.request, "Mochila criada com sucesso!")
        return redirect(self.success_url)


class MochilaUpdateView(SupervisorRequiredMixin, UpdateView):
    model      = Mochila
    form_class = MochilaForm
    template_name = "core/mochila_form.html"
    success_url   = reverse_lazy("mochila_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(_mochila_context(mochila=self.object))
        ctx["editing"] = True
        return ctx

    def form_valid(self, form):
        itens_qtd = _parse_itens_post(self.request.POST)

        with transaction.atomic():
            self.object = form.save()
            sincronizar_itens(self.request.user, self.object, itens_qtd)

        _log(self.request.user, self.object, CHANGE, "Mochila editada")
        messages.success(self.request, "Mochila atualizada com sucesso!")
        return redirect(self.success_url)


class MochilaDeleteView(SupervisorRequiredMixin, View):
    def get(self, request, pk):
        mochila = get_object_or_404(Mochila, pk=pk)
        u = request.user
        return render(request, "core/confirm_delete.html", {
            "titulo": "Excluir Mochila",
            "mensagem": f'Deseja desativar a mochila "{mochila.nome}"?',
            "voltar_url": reverse_lazy("mochila_list"),
            "user_profile": _shim(u),
            "user_perms": {"pode_editar": perms._pode_editar(u), "is_admin": perms._is_admin(u)},
        })

    def post(self, request, pk):
        mochila = get_object_or_404(Mochila, pk=pk)
        try:
            desativar_mochila(user=request.user, mochila=mochila)
        except (PermissionDenied, MochilaEmUsoError) as e:
            messages.error(request, str(e))
            return redirect("mochila_list")

        _log(request.user, mochila, DELETION, "Mochila desativada")
        messages.success(request, "Mochila desativada.")
        return redirect("mochila_list")


# ──────────────────────────────────────────────
# ITENS
# ──────────────────────────────────────────────

class ItemListView(PermContextMixin, ListView):
    model = Item
    template_name = "core/item_list.html"
    context_object_name = "itens"

    def get_queryset(self):
        return Item.objects.annotate(num_mochilas=Count("mochilas")).order_by("nome")


class ItemCreateView(SupervisorRequiredMixin, CreateView):
    model = Item
    form_class = ItemForm
    template_name = "core/item_form.html"
    success_url = reverse_lazy("item_list")

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "editing": False}

    def form_valid(self, form):
        response = super().form_valid(form)
        _log(self.request.user, self.object, ADDITION, "Item criado")
        messages.success(self.request, "Item cadastrado com sucesso!")
        return response


class ItemUpdateView(SupervisorRequiredMixin, UpdateView):
    model = Item
    form_class = ItemForm
    template_name = "core/item_form.html"
    success_url = reverse_lazy("item_list")

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "editing": True, "object": self.object}

    def form_valid(self, form):
        response = super().form_valid(form)
        _log(self.request.user, self.object, CHANGE, "Item editado")
        messages.success(self.request, "Item atualizado com sucesso!")
        return response


class ItemDeleteView(SupervisorRequiredMixin, View):
    def post(self, request, pk):
        item = get_object_or_404(Item, pk=pk)
        try:
            desativar_item(user=request.user, item=item)
        except (PermissionDenied, ItemEmUsoError) as e:
            messages.error(request, str(e))
            return redirect("item_list")

        _log(request.user, item, DELETION, "Item desativado")
        messages.success(request, "Item desativado com sucesso.")
        return redirect("item_list")


# ──────────────────────────────────────────────
# LOJAS
# ──────────────────────────────────────────────

class LojaListView(PermContextMixin, ListView):
    model = Loja
    template_name = "core/loja_list.html"
    context_object_name = "lojas"

    def get_queryset(self):
        return Loja.objects.annotate(total_viagens=Count("viagem")).order_by("nome")


class LojaCreateView(SupervisorRequiredMixin, CreateView):
    model = Loja
    form_class = LojaForm
    template_name = "core/loja_form.html"
    success_url = reverse_lazy("loja_list")

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "editing": False}

    def form_valid(self, form):
        response = super().form_valid(form)
        _log(self.request.user, self.object, ADDITION, "Loja criada")
        messages.success(self.request, "Loja cadastrada com sucesso!")
        return response


class LojaUpdateView(SupervisorRequiredMixin, UpdateView):
    model = Loja
    form_class = LojaForm
    template_name = "core/loja_form.html"
    success_url = reverse_lazy("loja_list")

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "editing": True, "object": self.object}

    def form_valid(self, form):
        response = super().form_valid(form)
        _log(self.request.user, self.object, CHANGE, "Loja editada")
        messages.success(self.request, "Loja atualizada com sucesso!")
        return response


class LojaDeleteView(SupervisorRequiredMixin, View):
    def get(self, request, pk):
        loja = get_object_or_404(Loja, pk=pk)
        u = request.user
        return render(request, "core/confirm_delete.html", {
            "titulo": "Excluir Loja",
            "mensagem": f'Deseja desativar a loja "{loja.nome}"?',
            "voltar_url": reverse_lazy("loja_list"),
            "user_profile": _shim(u),
            "user_perms": {"pode_editar": perms._pode_editar(u), "is_admin": perms._is_admin(u)},
        })

    def post(self, request, pk):
        loja = get_object_or_404(Loja, pk=pk)
        try:
            desativar_loja(user=request.user, loja=loja)
        except (PermissionDenied, LojaEmUsoError) as e:
            messages.error(request, str(e))
            return redirect("loja_list")

        _log(request.user, loja, DELETION, "Loja desativada")
        messages.success(request, "Loja desativada.")
        return redirect("loja_list")


# ──────────────────────────────────────────────
# USUÁRIOS
# ──────────────────────────────────────────────

class UsuarioListView(AdminRequiredMixin, ListView):
    model = User
    template_name = "core/usuario_list.html"
    context_object_name = "usuarios"

    def get_queryset(self):
        return (
            User.objects
            .filter(is_active=True)
            .prefetch_related("groups", "password_policy")
            .order_by("username")
        )


class UsuarioCreateView(SupervisorRequiredMixin, View):
    template_name = "core/usuario_form.html"

    def _ctx(self, request, form, editing=False):
        u = request.user
        return {
            "form": form,
            "editing": editing,
            "user_profile": _shim(u),
            "user_perms": {
                "pode_editar": perms._pode_editar(u),
                "is_admin": perms._is_admin(u),
            },
        }

    def get(self, request):
        form = UsuarioCreateForm()
        if not perms._is_admin(request.user):
            form.fields["nivel"].choices = [
                choice for choice in form.fields["nivel"].choices
                if choice[0] in ["usuario", "supervisor"]
            ]

        return render(request, self.template_name, self._ctx(request, form))

    def post(self, request):
        form = UsuarioCreateForm(request.POST)

        if not form.is_valid():
            return render(request, self.template_name, self._ctx(request, form))

        try:
            user = criar_usuario(
                actor=request.user,
                username=form.cleaned_data["username"],
                nivel=form.cleaned_data["nivel"],
                first_name=form.cleaned_data.get("first_name", ""),
                last_name=form.cleaned_data.get("last_name", ""),
                email=form.cleaned_data.get("email", ""),
            )

        except (PermissionDenied, DomainError) as e:
            messages.error(request, str(e))
            return render(request, self.template_name, self._ctx(request, form))

        _log(
            request.user,
            user,
            ADDITION,
            f"Usuário criado — nível: {form.cleaned_data['nivel']}"
        )

        messages.success(
            request,
            f"Usuário {user.username} criado. Senha padrão aplicada."
        )

        if perms._is_admin(request.user):
            return redirect("usuario_list")
        return redirect("dashboard")


class UsuarioEditView(AdminRequiredMixin, View):
    template_name = "core/usuario_form.html"

    def _ctx(self, request, form, target, editing=True):
        u = request.user
        return {
            "form": form, "editing": editing, "target_user": target,
            "user_profile": _shim(u),
            "user_perms": {"pode_editar": perms._pode_editar(u), "is_admin": perms._is_admin(u)},
        }

    def get(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        nivel  = get_nivel(target)
        form   = UsuarioEditForm(instance=target, initial={"nivel": nivel})
        return render(request, self.template_name, self._ctx(request, form, target))

    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        form   = UsuarioEditForm(request.POST, instance=target)
        if not form.is_valid():
            return render(request, self.template_name, self._ctx(request, form, target))

        try:
            editar_usuario(
                actor=request.user,
                target=target,
                username=form.cleaned_data["username"],
                nivel=form.cleaned_data["nivel"],
                first_name=form.cleaned_data.get("first_name", ""),
                last_name=form.cleaned_data.get("last_name", ""),
                email=form.cleaned_data.get("email", ""),
            )
        except (PermissionDenied, DomainError) as e:
            messages.error(request, str(e))
            return render(request, self.template_name, self._ctx(request, form, target))

        _log(request.user, target, CHANGE, f"Usuário editado — nível: {form.cleaned_data['nivel']}")
        messages.success(request, f"Usuário {target.username} atualizado!")
        return redirect("usuario_list")


@method_decorator(require_POST, name="dispatch")
class UsuarioResetSenhaView(AdminRequiredMixin, View):
    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        try:
            resetar_senha(actor=request.user, target=target)
        except PermissionDenied as e:
            messages.error(request, str(e))
            return redirect("usuario_list")

        _log(request.user, target, CHANGE, "Senha redefinida para padrão")
        messages.success(request, f"Senha de {target.username} redefinida.")
        return redirect("usuario_list")


@method_decorator(require_POST, name="dispatch")
class UsuarioDeleteView(AdminRequiredMixin, View):
    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        username = target.username
        try:
            excluir_usuario(actor=request.user, target=target)
        except (PermissionDenied, AutoExclusaoError, DomainError) as e:
            messages.error(request, str(e))
            return redirect("usuario_list")

        _log(request.user, target, DELETION, "Usuário desativado")
        messages.success(request, f"Usuário {username} desativado.")
        return redirect("usuario_list")
