"""
views.py — Orquestração pura. Sem lógica de negócio ou regras de permissão inline.

Padrão:
  - Views validam HTTP → chamam service → tratam exceções → respondem.
  - Permissões complexas delegadas a permissions.py.
  - Negócio delegado a services/.
"""

import json
import logging

from django.contrib import messages
from django.contrib.admin.models import ADDITION, CHANGE, DELETION
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.http import require_POST
from django.views.generic import (
    CreateView, DeleteView, DetailView, ListView,
    TemplateView, UpdateView,
)

from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.admin.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from . import permissions as perms
from .forms import (
    ItemForm, LojaForm, MochilaForm,
    UsuarioCreateForm, UsuarioEditForm, ViagemForm,
)
from .mixins import AdminRequiredMixin, NivelMixin, PermContextMixin, SupervisorRequiredMixin
from .models import (
    ChecklistItem, Item, Loja, Mochila, MochilaItem,
    UserProfile, Viagem,
)
from .services.viagem_service import (
    ViagemJaFinalizada,
    criar_viagem,
    finalizar_viagem,
    payload_from_post,
    salvar_checklist,
)

logger = logging.getLogger("core")


# ──────────────────────────────────────────────
# AUDIT LOG HELPER
# ──────────────────────────────────────────────
def _log(user, obj, flag, message=""):
    LogEntry.objects.log_actions(
        user_id=user.pk,
        queryset=[obj],
        action_flag=flag,
        change_message=message,
        single_object=True,
    )


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
# DASHBOARD
# ──────────────────────────────────────────────

class DashboardView(PermContextMixin, TemplateView):
    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        inicio_mes = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Respeita visibilidade: usuário comum vê apenas as próprias viagens
        viagens_qs = perms.filtrar_viagens(
            self.request.user,
            Viagem.objects.select_related("responsavel", "loja", "mochila"),
        )

        context.update({
            "total_andamento":   viagens_qs.filter(status="andamento").count(),
            "total_finalizadas": viagens_qs.filter(
                status="finalizada", data_retorno__gte=inicio_mes
            ).count(),
            "total_mochilas":    Mochila.objects.filter(ativo=True).count(),
            "total_lojas":       Loja.objects.filter(ativo=True).count(),
            "viagens_andamento": viagens_qs.filter(status="andamento").order_by("-data_saida")[:10],
            "ultimas_viagens":   viagens_qs.order_by("-id")[:8],
            "mochilas":          Mochila.objects.filter(ativo=True).prefetch_related("mochilaitem_set__item"),
        })
        return context


# ──────────────────────────────────────────────
# VIAGENS
# ──────────────────────────────────────────────

class ViagemListView(PermContextMixin, ListView):
    model = Viagem
    template_name = "core/viagem_list.html"
    context_object_name = "viagens"
    paginate_by = 15

    def get_queryset(self):
        # filtrar_viagens aplica restrição por usuário (multi-tenant ready)
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
        context["lojas"] = Loja.objects.filter(ativo=True)
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
        except PermissionDenied as e:
            messages.error(self.request, str(e))
            return self.form_invalid(form)
        except ValueError as e:
            messages.error(self.request, str(e))
            return self.form_invalid(form)

        _log(self.request.user, self.object, ADDITION, "Viagem criada")
        messages.success(self.request, "Viagem registrada com sucesso!")
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        mochilas_dict = {}
        for m in Mochila.objects.filter(ativo=True).prefetch_related("mochilaitem_set__item"):
            mochilas_dict[str(m.pk)] = [
                {"item": mi.item.nome, "quantidade": mi.quantidade}
                for mi in m.mochilaitem_set.all()
            ]
        context["mochilas_json"] = json.dumps(mochilas_dict)
        return context


@method_decorator(require_POST, name="dispatch")
class FinalizarViagemView(SupervisorRequiredMixin, View):
    """
    POST /viagens/<pk>/finalizar/

    Delega toda a lógica ao service. A view apenas:
      1. Resolve o objeto
      2. Chama o service
      3. Trata exceções → mensagem HTTP
    """

    def post(self, request, pk):
        viagem = get_object_or_404(Viagem, pk=pk)

        try:
            finalizar_viagem(user=request.user, viagem=viagem)
        except PermissionDenied as e:
            messages.error(request, str(e))
            return redirect("viagem_detail", pk=pk)
        except ViagemJaFinalizada as e:
            messages.error(request, str(e))
            return redirect("viagem_detail", pk=pk)

        _log(request.user, viagem, CHANGE, "Viagem finalizada")
        messages.success(request, "Viagem finalizada com sucesso!")
        return redirect("viagem_detail", pk=pk)


class ChecklistSaveView(PermContextMixin, View):
    """
    POST /viagens/<pk>/checklist/

    Converte POST → payload tipado → delega ao service.
    """

    def post(self, request, pk):
        viagem = get_object_or_404(Viagem, pk=pk)

        checklist_ids = list(viagem.checklist.values_list("id", flat=True))
        payload = payload_from_post(request.POST, checklist_ids)

        try:
            salvar_checklist(user=request.user, viagem=viagem, payload=payload)
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
        return Mochila.objects.filter(ativo=True).prefetch_related("mochilaitem_set__item")


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


class MochilaCreateView(SupervisorRequiredMixin, CreateView):
    model = Mochila
    form_class = MochilaForm
    template_name = "core/mochila_form.html"
    success_url = reverse_lazy("mochila_list")

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "editing": False}

    def form_valid(self, form):
        with transaction.atomic():
            self.object = form.save(commit=False)
            self.object.save()
            MochilaItem.objects.filter(mochila=self.object).delete()
            MochilaItem.objects.bulk_create([
                MochilaItem(mochila=self.object, item=item, quantidade=1)
                for item in form.cleaned_data["itens"]
            ])
        _log(self.request.user, self.object, ADDITION, "Mochila criada")
        messages.success(self.request, "Mochila criada com sucesso!")
        return redirect(self.success_url)


class MochilaUpdateView(SupervisorRequiredMixin, UpdateView):
    model = Mochila
    form_class = MochilaForm
    template_name = "core/mochila_form.html"
    success_url = reverse_lazy("mochila_list")

    def get_initial(self):
        return {**super().get_initial(), "itens": self.object.itens.all()}

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "editing": True, "object": self.object}

    def form_valid(self, form):
        with transaction.atomic():
            self.object = form.save(commit=False)
            self.object.save()
            MochilaItem.objects.filter(mochila=self.object).delete()
            MochilaItem.objects.bulk_create([
                MochilaItem(mochila=self.object, item=item, quantidade=1)
                for item in form.cleaned_data["itens"]
            ])
        _log(self.request.user, self.object, CHANGE, "Mochila editada")
        messages.success(self.request, "Mochila atualizada com sucesso!")
        return redirect(self.success_url)


class MochilaDeleteView(SupervisorRequiredMixin, DeleteView):
    model = Mochila
    template_name = "core/confirm_delete.html"
    success_url = reverse_lazy("mochila_list")

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            "titulo": "Excluir Mochila",
            "mensagem": f'Tem certeza que deseja excluir a mochila "{self.object.nome}"?',
            "voltar_url": reverse_lazy("mochila_list"),
        }

    def form_valid(self, form):
        _log(self.request.user, self.object, DELETION, "Mochila excluída")
        messages.success(self.request, "Mochila excluída.")
        return super().form_valid(form)


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


class ItemDeleteView(SupervisorRequiredMixin, DeleteView):
    model = Item
    template_name = "core/confirm_delete.html"
    success_url = reverse_lazy("item_list")

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            "titulo": "Excluir Item",
            "mensagem": f'Tem certeza que deseja excluir o item "{self.object.nome}"?',
            "voltar_url": reverse_lazy("item_list"),
        }

    def form_valid(self, form):
        _log(self.request.user, self.object, DELETION, "Item excluído")
        messages.success(self.request, "Item excluído.")
        return super().form_valid(form)


# ──────────────────────────────────────────────
# LOJAS
# ──────────────────────────────────────────────

class LojaListView(PermContextMixin, ListView):
    model = Loja
    template_name = "core/loja_list.html"
    context_object_name = "lojas"

    def get_queryset(self):
        return Loja.objects.filter(ativo=True).annotate(total_viagens=Count("viagem")).order_by("nome")


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


class LojaDeleteView(SupervisorRequiredMixin, DeleteView):
    model = Loja
    template_name = "core/confirm_delete.html"
    success_url = reverse_lazy("loja_list")

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            "titulo": "Excluir Loja",
            "mensagem": f'Tem certeza que deseja excluir a loja "{self.object.nome}"?',
            "voltar_url": reverse_lazy("loja_list"),
        }

    def form_valid(self, form):
        _log(self.request.user, self.object, DELETION, "Loja excluída")
        messages.success(self.request, "Loja excluída.")
        return super().form_valid(form)


# ──────────────────────────────────────────────
# USUÁRIOS
# ──────────────────────────────────────────────

class UsuarioListView(AdminRequiredMixin, ListView):
    model = User
    template_name = "core/usuario_list.html"
    context_object_name = "usuarios"

    def get_queryset(self):
        return User.objects.prefetch_related("groups").order_by("username")


class UsuarioCreateView(AdminRequiredMixin, View):
    template_name = "core/usuario_form.html"

    def _ctx(self, form, editing=False):
        return {"form": form, "editing": editing, "user_perms": self._user_perms()}

    def _user_perms(self):
        u = self.request.user
        return {
            "pode_editar": perms._pode_editar(u),
            "is_admin":    perms._is_admin(u),
        }

    def get(self, request):
        return render(request, self.template_name, self._ctx(UsuarioCreateForm()))

    def post(self, request):
        form = UsuarioCreateForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, self._ctx(form))

        with transaction.atomic():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data["password"])
            nivel = form.cleaned_data["nivel"]
            if nivel == "admin":
                user.is_staff = user.is_superuser = True
            user.save()
            _assign_group(user, nivel)

        _log(request.user, user, ADDITION, f"Usuário criado — nível: {nivel}")
        logger.info("Usuário %s criado por %s", user.username, request.user)
        messages.success(request, f"Usuário {user.username} criado com sucesso!")
        return redirect("usuario_list")


class UsuarioEditView(AdminRequiredMixin, View):
    template_name = "core/usuario_form.html"

    def _ctx(self, form, target, editing=True):
        u = self.request.user
        return {
            "form": form, "editing": editing,
            "target_user": target,
            "user_perms": {"pode_editar": perms._pode_editar(u), "is_admin": perms._is_admin(u)},
            "user_profile": _LegacyShim(u),
        }

    def get(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        nivel  = _get_nivel(target)
        form   = UsuarioEditForm(instance=target, initial={"nivel": nivel})
        return render(request, self.template_name, self._ctx(form, target))

    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        form   = UsuarioEditForm(request.POST, instance=target)
        if not form.is_valid():
            return render(request, self.template_name, self._ctx(form, target))

        with transaction.atomic():
            user  = form.save(commit=False)
            nivel = form.cleaned_data["nivel"]
            new_pass = form.cleaned_data.get("new_password")
            if new_pass:
                user.set_password(new_pass)
            user.is_staff = user.is_superuser = (nivel == "admin")
            user.save()
            _assign_group(user, nivel)

        _log(request.user, target, CHANGE, f"Usuário editado — nível: {nivel}")
        messages.success(request, f"Usuário {target.username} atualizado!")
        return redirect("usuario_list")


@method_decorator(require_POST, name="dispatch")
class UsuarioDeleteView(AdminRequiredMixin, View):
    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        if target == request.user:
            messages.error(request, "Você não pode excluir sua própria conta.")
            return redirect("usuario_list")
        username = target.username
        _log(request.user, target, DELETION, "Usuário excluído")
        target.delete()
        logger.info("Usuário %s excluído por %s", username, request.user)
        messages.success(request, f"Usuário {username} excluído.")
        return redirect("usuario_list")


# ──────────────────────────────────────────────
# HELPERS INTERNOS DE GRUPOS
# ──────────────────────────────────────────────

_NIVEL_TO_GROUP = {
    "admin":      "Admin",
    "supervisor": "Supervisor",
    "usuario":    "Usuário",
}

_GROUP_TO_NIVEL = {v: k for k, v in _NIVEL_TO_GROUP.items()}


def _assign_group(user: User, nivel: str) -> None:
    """Remove todos os grupos e atribui o grupo correto."""
    from django.contrib.auth.models import Group
    user.groups.clear()
    group_name = _NIVEL_TO_GROUP.get(nivel)
    if group_name:
        group, _ = Group.objects.get_or_create(name=group_name)
        user.groups.add(group)


def _get_nivel(user: User) -> str:
    """Resolve o nível a partir dos grupos do usuário."""
    for group in user.groups.all():
        nivel = _GROUP_TO_NIVEL.get(group.name)
        if nivel:
            return nivel
    if user.is_superuser:
        return "admin"
    return "usuario"


class _LegacyShim:
    """Shim temporário para templates ainda usando user_profile."""
    def __init__(self, u):
        self._u = u
    @property
    def pode_editar(self): return perms._pode_editar(self._u)
    @property
    def is_admin(self): return perms._is_admin(self._u)
    @property
    def is_supervisor(self): return perms._is_supervisor(self._u)
