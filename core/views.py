import json
import logging

from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.contrib import messages
from django.urls import reverse_lazy

from django.views import View
from django.views.generic import (
    TemplateView, ListView, DetailView,
    CreateView, UpdateView, DeleteView,
)

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.models import User
from django.contrib.admin.models import LogEntry, ADDITION, CHANGE, DELETION
from django.contrib.contenttypes.models import ContentType

from django.db.models import Q, Count
from django.db import transaction
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator
from django.http import HttpResponseForbidden

from .models import Loja, Item, Mochila, Viagem, MochilaItem, UserProfile, ChecklistItem
from .forms import (
    ViagemForm, MochilaForm, LojaForm, ItemForm,
    UsuarioCreateForm, UsuarioEditForm,
)
from .mixins import NivelMixin, SupervisorRequiredMixin, AdminRequiredMixin, get_user_profile
from django.contrib.admin.models import LogEntry, ADDITION, CHANGE, DELETION
from django.contrib.contenttypes.models import ContentType
import logging

logger = logging.getLogger("core")


def log_action(user, obj, action_flag, message=""):
    ct = ContentType.objects.get_for_model(obj)

    LogEntry.objects.log_action(
        user_id=user.pk,
        content_type_id=ct.pk,
        object_id=obj.pk,
        object_repr=str(obj)[:200],
        action_flag=action_flag,
        change_message=message,
    )


# ─────────────────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────────────────
class DashboardView(NivelMixin, TemplateView):
    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now         = timezone.now()
        inicio_mes  = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        context.update({
            "total_andamento":  Viagem.objects.filter(status="andamento").count(),
            "total_finalizadas": Viagem.objects.filter(
                status="finalizada", data_retorno__gte=inicio_mes
            ).count(),
            "total_mochilas":   Mochila.objects.filter(ativo=True).count(),
            "total_lojas":      Loja.objects.filter(ativo=True).count(),
            "viagens_andamento": Viagem.objects.filter(status="andamento")
                .select_related("responsavel", "loja", "mochila")
                .order_by("-data_saida")[:10],
            "ultimas_viagens": Viagem.objects.select_related("responsavel", "loja", "mochila")
                .order_by("-id")[:8],
            "mochilas": Mochila.objects.filter(ativo=True)
                .prefetch_related("mochilaitem_set__item"),
        })
        return context


# ─────────────────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────────────────
class CustomLoginView(LoginView):
    template_name = "core/login.html"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["username"].widget.attrs.update({
            "placeholder": "Usuário",
            "class": "login-input",
            "autocomplete": "username",
        })
        form.fields["password"].widget.attrs.update({
            "placeholder": "Senha",
            "class": "login-input",
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


# ─────────────────────────────────────────────────────────
# VIAGENS
# ─────────────────────────────────────────────────────────
class ViagemListView(NivelMixin, ListView):
    model               = Viagem
    template_name       = "core/viagem_list.html"
    context_object_name = "viagens"
    paginate_by         = 15

    def get_queryset(self):
        qs = Viagem.objects.select_related(
            "responsavel", "loja", "mochila"
        ).order_by("-id")

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


class ViagemDetailView(NivelMixin, DetailView):
    model = Viagem
    template_name = "core/viagem_detail.html"
    context_object_name = "viagem"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        checklist = self.object.checklist.select_related("item").order_by("item__nome")

        total = checklist.count()
        retornados_ok = checklist.filter(retorno_ok=True).count()
        pendentes = total - retornados_ok

        context.update({
            "checklist_items": checklist,
            "retornados_ok": retornados_ok,
            "total_itens": total,
            "pendentes": pendentes,
        })

        return context


class ViagemCreateView(SupervisorRequiredMixin, CreateView):
    model        = Viagem
    form_class   = ViagemForm
    template_name = "core/viagem_form.html"

    def get_success_url(self):
        return reverse_lazy("viagem_detail", kwargs={"pk": self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(self.request.user, self.object, ADDITION, "Viagem criada")
        logger.info("Viagem #%s criada por %s", self.object.pk, self.request.user)
        messages.success(self.request, "Viagem registrada com sucesso!")
        return response

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
    def post(self, request, pk):
        viagem = get_object_or_404(Viagem, pk=pk)
        if viagem.status != "andamento":
            messages.error(request, "Essa viagem não está em andamento.")
            return redirect("viagem_detail", pk=pk)
        viagem.status       = "finalizada"
        viagem.data_retorno = timezone.now()
        viagem.save(update_fields=["status", "data_retorno"])
        log_action(request.user, viagem, CHANGE, "Viagem finalizada")
        logger.info("Viagem #%s finalizada por %s", pk, request.user)
        messages.success(request, "Viagem finalizada com sucesso!")
        return redirect("viagem_detail", pk=pk)


class ChecklistSaveView(NivelMixin, View):
    def post(self, request, pk):
        viagem = get_object_or_404(Viagem, pk=pk, status="andamento")

        items_to_update = []
        for ci in viagem.checklist.all():
            ci.saida_ok          = f"saida_ok_{ci.id}" in request.POST
            ci.retorno_ok        = f"retorno_ok_{ci.id}" in request.POST
            # Truncate to model max_length for safety
            ci.observacao_retorno = request.POST.get(f"obs_{ci.id}", "")[:255]
            items_to_update.append(ci)

        ChecklistItem.objects.bulk_update(
            items_to_update, ["saida_ok", "retorno_ok", "observacao_retorno"]
        )
        messages.success(request, "Checklist salvo com sucesso!")
        return redirect("viagem_detail", pk=pk)


# ─────────────────────────────────────────────────────────
# MOCHILAS
# ─────────────────────────────────────────────────────────
class MochilaListView(NivelMixin, ListView):
    model               = Mochila
    template_name       = "core/mochila_list.html"
    context_object_name = "mochilas"

    def get_queryset(self):
        return Mochila.objects.filter(ativo=True).prefetch_related("mochilaitem_set__item")


class MochilaCreateView(SupervisorRequiredMixin, CreateView):
    model        = Mochila
    form_class   = MochilaForm
    template_name = "core/mochila_form.html"
    success_url  = reverse_lazy("mochila_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["editing"] = False
        return context

    def form_valid(self, form):
        with transaction.atomic():
            self.object = form.save(commit=False)
            self.object.save()
            itens = form.cleaned_data["itens"]
            MochilaItem.objects.filter(mochila=self.object).delete()
            MochilaItem.objects.bulk_create([
                MochilaItem(mochila=self.object, item=item, quantidade=1)
                for item in itens
            ])
        log_action(self.request.user, self.object, ADDITION, "Mochila criada")
        messages.success(self.request, "Mochila criada com sucesso!")
        return redirect(self.success_url)


class MochilaUpdateView(SupervisorRequiredMixin, UpdateView):
    model        = Mochila
    form_class   = MochilaForm
    template_name = "core/mochila_form.html"
    success_url  = reverse_lazy("mochila_list")

    def get_initial(self):
        initial = super().get_initial()
        initial["itens"] = self.object.itens.all()
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["editing"] = True
        context["object"]  = self.object
        return context

    def form_valid(self, form):
        with transaction.atomic():
            self.object = form.save(commit=False)
            self.object.save()
            itens = form.cleaned_data["itens"]
            MochilaItem.objects.filter(mochila=self.object).delete()
            MochilaItem.objects.bulk_create([
                MochilaItem(mochila=self.object, item=item, quantidade=1)
                for item in itens
            ])
        log_action(self.request.user, self.object, CHANGE, "Mochila editada")
        messages.success(self.request, "Mochila atualizada com sucesso!")
        return redirect(self.success_url)


class MochilaDeleteView(SupervisorRequiredMixin, DeleteView):
    model        = Mochila
    template_name = "core/confirm_delete.html"
    success_url  = reverse_lazy("mochila_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["titulo"]    = "Excluir Mochila"
        context["mensagem"]  = f'Tem certeza que deseja excluir a mochila "{self.object.nome}"?'
        context["voltar_url"] = reverse_lazy("mochila_list")
        return context

    def form_valid(self, form):
        log_action(self.request.user, self.object, DELETION, "Mochila excluída")
        messages.success(self.request, "Mochila excluída.")
        return super().form_valid(form)


class MochilaDetailView(NivelMixin, DetailView):
    model               = Mochila
    template_name       = "core/mochila_detail.html"
    context_object_name = "mochila"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["viagens"] = (
            Viagem.objects.filter(mochila=self.object)
            .select_related("loja", "responsavel")
            .order_by("-id")
        )
        return context


# ─────────────────────────────────────────────────────────
# ITENS
# ─────────────────────────────────────────────────────────
class ItemListView(NivelMixin, ListView):
    model               = Item
    template_name       = "core/item_list.html"
    context_object_name = "itens"

    def get_queryset(self):
        return Item.objects.annotate(num_mochilas=Count("mochilas")).order_by("nome")


class ItemCreateView(SupervisorRequiredMixin, CreateView):
    model        = Item
    form_class   = ItemForm
    template_name = "core/item_form.html"
    success_url  = reverse_lazy("item_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["editing"] = False
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(self.request.user, self.object, ADDITION, "Item criado")
        messages.success(self.request, "Item cadastrado com sucesso!")
        return response


class ItemUpdateView(SupervisorRequiredMixin, UpdateView):
    model        = Item
    form_class   = ItemForm
    template_name = "core/item_form.html"
    success_url  = reverse_lazy("item_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["editing"] = True
        context["object"]  = self.object
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(self.request.user, self.object, CHANGE, "Item editado")
        messages.success(self.request, "Item atualizado com sucesso!")
        return response


class ItemDeleteView(SupervisorRequiredMixin, DeleteView):
    model        = Item
    template_name = "core/confirm_delete.html"
    success_url  = reverse_lazy("item_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["titulo"]    = "Excluir Item"
        context["mensagem"]  = f'Tem certeza que deseja excluir o item "{self.object.nome}"?'
        context["voltar_url"] = reverse_lazy("item_list")
        return context

    def form_valid(self, form):
        log_action(self.request.user, self.object, DELETION, "Item excluído")
        messages.success(self.request, "Item excluído.")
        return super().form_valid(form)


# ─────────────────────────────────────────────────────────
# LOJAS
# ─────────────────────────────────────────────────────────
class LojaListView(NivelMixin, ListView):
    model               = Loja
    template_name       = "core/loja_list.html"
    context_object_name = "lojas"

    def get_queryset(self):
        return Loja.objects.filter(ativo=True).annotate(
            total_viagens=Count("viagem"),
        ).order_by("nome")


class LojaCreateView(SupervisorRequiredMixin, CreateView):
    model        = Loja
    form_class   = LojaForm
    template_name = "core/loja_form.html"
    success_url  = reverse_lazy("loja_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["editing"] = False
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(self.request.user, self.object, ADDITION, "Loja criada")
        messages.success(self.request, "Loja cadastrada com sucesso!")
        return response


class LojaUpdateView(SupervisorRequiredMixin, UpdateView):
    model        = Loja
    form_class   = LojaForm
    template_name = "core/loja_form.html"
    success_url  = reverse_lazy("loja_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["editing"] = True
        context["object"]  = self.object
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(self.request.user, self.object, CHANGE, "Loja editada")
        messages.success(self.request, "Loja atualizada com sucesso!")
        return response


class LojaDeleteView(SupervisorRequiredMixin, DeleteView):
    model        = Loja
    template_name = "core/confirm_delete.html"
    success_url  = reverse_lazy("loja_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["titulo"]    = "Excluir Loja"
        context["mensagem"]  = f'Tem certeza que deseja excluir a loja "{self.object.nome}"?'
        context["voltar_url"] = reverse_lazy("loja_list")
        return context

    def form_valid(self, form):
        log_action(self.request.user, self.object, DELETION, "Loja excluída")
        messages.success(self.request, "Loja excluída.")
        return super().form_valid(form)


# ─────────────────────────────────────────────────────────
# USUÁRIOS (somente Admin)
# ─────────────────────────────────────────────────────────
class UsuarioListView(AdminRequiredMixin, ListView):
    model               = User
    template_name       = "core/usuario_list.html"
    context_object_name = "usuarios"

    def get_queryset(self):
        return User.objects.select_related("profile").order_by("username")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Ensure all users have a profile (defensive)
        for u in context["usuarios"]:
            get_user_profile(u)
        return context


class UsuarioCreateView(AdminRequiredMixin, View):
    template_name = "core/usuario_form.html"

    def get(self, request):
        return render(request, self.template_name, {
            "form": UsuarioCreateForm(),
            "editing": False,
            "user_profile": self.user_profile,
        })

    def post(self, request):
        form = UsuarioCreateForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = form.save(commit=False)
                user.set_password(form.cleaned_data["password"])
                nivel = form.cleaned_data["nivel"]
                if nivel == "admin":
                    user.is_staff      = True
                    user.is_superuser  = True
                user.save()
                UserProfile.objects.create(user=user, nivel=nivel)
            log_action(request.user, user, ADDITION, f"Usuário criado — nível: {nivel}")
            logger.info("Usuário %s criado por %s", user.username, request.user)
            messages.success(request, f"Usuário {user.username} criado com sucesso!")
            return redirect("usuario_list")
        return render(request, self.template_name, {
            "form": form,
            "editing": False,
            "user_profile": self.user_profile,
        })


class UsuarioEditView(AdminRequiredMixin, View):
    template_name = "core/usuario_form.html"

    def _get_target(self, pk):
        return get_object_or_404(User, pk=pk)

    def get(self, request, pk):
        target  = self._get_target(pk)
        profile = get_user_profile(target)
        form    = UsuarioEditForm(instance=target, initial={"nivel": profile.nivel})
        return render(request, self.template_name, {
            "form": form, "editing": True,
            "target_user": target, "user_profile": self.user_profile,
        })

    def post(self, request, pk):
        target  = self._get_target(pk)
        profile = get_user_profile(target)
        form    = UsuarioEditForm(request.POST, instance=target)
        if form.is_valid():
            with transaction.atomic():
                user  = form.save(commit=False)
                nivel = form.cleaned_data["nivel"]
                new_pass = form.cleaned_data.get("new_password")
                if new_pass:
                    user.set_password(new_pass)
                user.is_staff     = (nivel == "admin")
                user.is_superuser = (nivel == "admin")
                user.save()
                profile.nivel = nivel
                profile.save()
            log_action(request.user, target, CHANGE, f"Usuário editado — nível: {nivel}")
            messages.success(request, f"Usuário {target.username} atualizado!")
            return redirect("usuario_list")
        return render(request, self.template_name, {
            "form": form, "editing": True,
            "target_user": target, "user_profile": self.user_profile,
        })


@method_decorator(require_POST, name="dispatch")
class UsuarioDeleteView(AdminRequiredMixin, View):
    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        if target == request.user:
            messages.error(request, "Você não pode excluir sua própria conta.")
            return redirect("usuario_list")
        username = target.username
        log_action(request.user, target, DELETION, "Usuário excluído")
        target.delete()
        logger.info("Usuário %s excluído por %s", username, request.user)
        messages.success(request, f"Usuário {username} excluído.")
        return redirect("usuario_list")
