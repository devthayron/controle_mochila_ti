"""
views.py — Apenas orquestração HTTP.

CONTRATO DE PERMISSÕES:
  - Verificações de ROLE → mixin (SupervisorRequiredMixin, AdminRequiredMixin…)
  - Verificações de OBJETO → view (pode_ver_viagem, pode_editar_checklist)
  - Verificações de CONTEXTO FINO → view (pode_criar_usuario com nível específico)
  - Nenhuma duplicação: se o mixin já garantiu o papel, a view não repete

CONTEXTO DE PERMISSÕES:
  - `user_perms` é injetado automaticamente em todos os templates via
    settings.py → TEMPLATES → context_processors → core.permissions.permission_context
  - Nenhuma view monta ou injeta user_perms manualmente

LOGIN:
  - Todas as views (exceto Login/Logout) exigem autenticação.
  - SupervisorRequiredMixin e AdminRequiredMixin já herdam LoginRequiredMixin.
  - Views que não usam esses mixins declaram LoginRequiredMixin explicitamente.
"""

import json
import logging

from django.contrib import messages
from django.contrib.admin.models import ADDITION, CHANGE, DELETION, LogEntry
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.http import require_POST
from django.views.generic import (
    CreateView, DetailView, ListView, TemplateView, UpdateView,
)
from weasyprint import HTML

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
    ItemForm, LojaForm, MochilaForm,ViagemForm,
    TrocarSenhaForm, UsuarioCreateForm, UsuarioEditForm, ViagemForm,
)
from .mixins import AdminRequiredMixin, SupervisorRequiredMixin, UsuarioAreaMixin
from .models import ChecklistItem, Item, Loja, Mochila, MochilaItem, Viagem,ViagemLoja
from .services.item_service import desativar_item
from .services.loja_service import desativar_loja
from .services.mochila_service import desativar_mochila, sincronizar_itens
from .services.usuario_service import (
    criar_usuario, editar_usuario, excluir_usuario,
    get_nivel, resetar_senha, trocar_senha,
)
from .services.viagem_service import (
    criar_viagem, finalizar_viagem, payload_from_post, salvar_checklist,
)

logger = logging.getLogger("core")


# ──────────────────────────────────────────────
# AUDIT LOG HELPER
# ──────────────────────────────────────────────

def _log(user, obj, flag, message=""):
    if not user or not user.pk:
        return
    LogEntry.objects.create(
        user_id=user.pk,
        content_type_id=ContentType.objects.get_for_model(obj.__class__).pk,
        object_id=str(obj.pk),
        object_repr=str(obj)[:200],
        action_flag=flag,
        change_message=message[:255],
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
# TROCA DE SENHA OBRIGATÓRIA
# ──────────────────────────────────────────────

class TrocarSenhaView(View):
    """
    NÃO usa LoginRequiredMixin intencionalmente: precisa funcionar durante
    o bloqueio do ForcePasswordChangeMiddleware, que redireciona para cá
    antes que o mixin teria chance de redirecionar para o login.
    A autenticação é verificada manualmente nos métodos get/post.
    """
    template_name = "core/trocar_senha.html"

    def get(self, request):
        if not request.user.is_authenticated:
            return redirect("login")
        return render(request, self.template_name, {"form": TrocarSenhaForm()})

    def post(self, request):
        if not request.user.is_authenticated:
            return redirect("login")

        form = TrocarSenhaForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        try:
            trocar_senha(
                user=request.user,
                senha_atual=form.cleaned_data["senha_atual"],
                nova_senha=form.cleaned_data["nova_senha"],
            )
        except (SenhaIncorretaError, SenhaFracaError) as e:
            messages.error(request, str(e))
            return render(request, self.template_name, {"form": form})

        update_session_auth_hash(request, request.user)
        messages.success(request, "Senha alterada com sucesso!")
        return redirect("dashboard")


# ──────────────────────────────────────────────
# DASHBOARD
# ──────────────────────────────────────────────

class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        context    = super().get_context_data(**kwargs)
        now        = timezone.now()
        inicio_mes = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        viagens_qs = perms.filtrar_viagens(
            self.request.user,
            Viagem.objects.select_related("responsavel", "mochila")
                          .prefetch_related("viagem_lojas__loja"),
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

class ViagemChecklistPDFView(LoginRequiredMixin, View):
    def get(self, request, pk):
        viagem = get_object_or_404(Viagem, pk=pk)

        if not perms.pode_ver_viagem(request.user, viagem):
            raise PermissionDenied("Sem acesso a esta viagem.")

        checklist   = viagem.checklist.select_related("item").order_by("item__nome")
        html_string = render_to_string(
            "core/viagem_checklist_pdf.html",
            {"viagem": viagem, "checklist_items": checklist},
        )
        pdf      = HTML(string=html_string).write_pdf()
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'inline; filename="viagem_{viagem.id}_checklist.pdf"'
        )
        return response


class ViagemListView(LoginRequiredMixin, ListView):
    model               = Viagem
    template_name       = "core/viagem_list.html"
    context_object_name = "viagens"
    paginate_by         = 15

    def get_queryset(self):
        qs = perms.filtrar_viagens(
            self.request.user,
            Viagem.objects
                  .select_related("responsavel", "mochila")
                  .prefetch_related("viagem_lojas__loja")
                  .order_by("status", "-id")
        )
        q      = self.request.GET.get("q", "").strip()
        status = self.request.GET.get("status")
        loja   = self.request.GET.get("loja")

        if q:
            qs = qs.filter(
                Q(responsavel__username__icontains=q)        |
                Q(responsavel__first_name__icontains=q)      |
                Q(responsavel__last_name__icontains=q)       |
                Q(viagem_lojas__loja__nome__icontains=q)     # ← era loja__nome
            ).distinct()
        if status:
            qs = qs.filter(status=status)
        if loja:
            qs = qs.filter(viagem_lojas__loja_id=loja)      # ← era loja_id=loja
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["lojas"] = Loja.objects.all()
        return context


class ViagemDetailView(LoginRequiredMixin, DetailView):
    model               = Viagem
    template_name       = "core/viagem_detail.html"
    context_object_name = "viagem"

    def get_object(self, queryset=None):
        viagem = get_object_or_404(
            Viagem.objects
                  .select_related("responsavel", "mochila")
                  .prefetch_related("viagem_lojas__loja"),
            pk=self.kwargs["pk"],
        )
        if not perms.pode_ver_viagem(self.request.user, viagem):
            raise PermissionDenied("Você não tem acesso a esta viagem.")
        return viagem

    def get_context_data(self, **kwargs):
        context       = super().get_context_data(**kwargs)
        checklist     = self.object.checklist.select_related("item").order_by("item__nome")
        total         = checklist.count()
        retornados_ok = checklist.filter(retorno_ok=True).count()
        context.update({
            "checklist_items":     checklist,
            "retornados_ok":       retornados_ok,
            "total_itens":         total,
            "pendentes":           total - retornados_ok,
            "pode_editar_checklist": perms.pode_editar_checklist(
                self.request.user, self.object
            ),
        })
        return context


import json
from django.shortcuts import get_object_or_404, render, redirect
from django.core.exceptions import PermissionDenied
from django.contrib import messages

class ViagemUpdateView(SupervisorRequiredMixin, View):
    template_name = "core/viagem_form.html"

    def get(self, request, pk):
        viagem = get_object_or_404(Viagem, pk=pk)

        if viagem.status != "andamento":
            raise PermissionDenied("Viagem finalizada não pode ser editada.")

        form = ViagemForm(initial={
            "responsavel": viagem.responsavel,
            "mochila": viagem.mochila,
        })

        return render(request, self.template_name, self._build_context(form, viagem))

    def post(self, request, pk):
        from .services.viagem_service import lojas_from_post
        from .models import Loja, ViagemLoja

        viagem = get_object_or_404(Viagem, pk=pk)

        if viagem.status != "andamento":
            raise PermissionDenied("Viagem finalizada não pode ser editada.")

        form = ViagemForm(request.POST)

        if not form.is_valid():
            return render(request, self.template_name, self._build_context(form, viagem))

        lojas = lojas_from_post(request.POST, Loja)

        if not lojas:
            form.add_error(None, "Selecione ao menos uma loja.")
            return render(request, self.template_name, self._build_context(form, viagem))

        # atualiza dados base
        viagem.responsavel = form.cleaned_data["responsavel"]
        viagem.mochila = form.cleaned_data["mochila"]
        viagem.save()

        # recria relação viagem-lojas
        viagem.viagem_lojas.all().delete()

        ViagemLoja.objects.bulk_create([
            ViagemLoja(viagem=viagem, loja=loja, ordem=i)
            for i, loja in enumerate(lojas)
        ])

        messages.success(request, "Viagem atualizada com sucesso!")
        return redirect("viagem_detail", pk=viagem.pk)

    def _build_context(self, form, viagem):
        from .models import Loja, Mochila

        mochilas_dict = {
            str(m.pk): [
                {"item": mi.item.nome, "quantidade": mi.quantidade}
                for mi in m.mochilaitem_set.select_related("item")
            ]
            for m in Mochila.objects.prefetch_related("mochilaitem_set__item")
        }

        lojas_selecionadas = list(
            viagem.viagem_lojas
            .order_by("ordem")
            .values_list("loja_id", flat=True)
        )

        return {
            "form": form,
            "editing": True,
            "viagem": viagem,
            "lojas_selecionadas": json.dumps(lojas_selecionadas),

            "mochilas_json": json.dumps(mochilas_dict),
            "lojas_disponiveis": Loja.objects.order_by("nome"),
        }


class ViagemCreateView(SupervisorRequiredMixin, View):
    template_name = "core/viagem_form.html"

    def get(self, request):
        form = ViagemForm()
        context = self._build_context(form)
        return render(request, self.template_name, context)

    def post(self, request):
        from .services.viagem_service import lojas_from_post
        from .models import Loja

        form = ViagemForm(request.POST)

        if not form.is_valid():
            return render(request, self.template_name, self._build_context(form))

        lojas = lojas_from_post(request.POST, Loja)

        if not lojas:
            form.add_error(None, "Selecione ao menos uma loja de destino.")
            return render(request, self.template_name, self._build_context(form))

        try:
            viagem = criar_viagem(
                user=request.user,
                responsavel=form.cleaned_data["responsavel"],
                lojas=lojas,
                mochila=form.cleaned_data["mochila"],
            )
        except DomainError as e:
            messages.error(request, str(e))
            return render(request, self.template_name, self._build_context(form))

        _log(request.user, viagem, ADDITION, "Viagem criada")
        messages.success(request, "Viagem registrada com sucesso!")
        return redirect(reverse_lazy("viagem_detail", kwargs={"pk": viagem.pk}))

    def _build_context(self, form):
        mochilas_dict = {
            str(m.pk): [
                {"item": mi.item.nome, "quantidade": mi.quantidade}
                for mi in m.mochilaitem_set.all()
            ]
            for m in Mochila.objects.prefetch_related("mochilaitem_set__item")
        }
        from .models import Loja
        return {
            "form":          form,
            "mochilas_json": json.dumps(mochilas_dict),
            "lojas_disponiveis": Loja.objects.order_by("nome"),
        }


@method_decorator(require_POST, name="dispatch")
class FinalizarViagemView(SupervisorRequiredMixin, View):
    def post(self, request, pk):
        viagem = get_object_or_404(Viagem, pk=pk)

        # Object-level: quem pode ver ESTA viagem
        if not perms.pode_ver_viagem(request.user, viagem):
            messages.error(request, "Você não tem acesso a esta viagem.")
            return redirect("viagem_list")

        try:
            finalizar_viagem(user=request.user, viagem=viagem)
        except ViagemJaFinalizada as e:
            messages.error(request, str(e))
            return redirect("viagem_detail", pk=pk)

        _log(request.user, viagem, CHANGE, "Viagem finalizada")
        messages.success(request, "Viagem finalizada com sucesso!")
        return redirect("viagem_detail", pk=pk)


class ChecklistSaveView(LoginRequiredMixin, View):
    def post(self, request, pk):
        viagem = get_object_or_404(Viagem, pk=pk)

        # Object-level: depende do estado da viagem + papel do usuário
        if not perms.pode_editar_checklist(request.user, viagem):
            messages.error(request, "Você não pode editar este checklist.")
            return redirect("viagem_detail", pk=pk)

        checklist_ids = list(viagem.checklist.values_list("pk", flat=True))
        payload       = payload_from_post(request.POST, checklist_ids)

        salvar_checklist(
            user=request.user,
            viagem=viagem,
            payload=payload,
            pode_editar_saida=perms.pode_editar(request.user),
        )

        messages.success(request, "Checklist salvo com sucesso!")
        return redirect("viagem_detail", pk=pk)


# ──────────────────────────────────────────────
# MOCHILAS
# ──────────────────────────────────────────────

class MochilaListView(LoginRequiredMixin, ListView):
    model               = Mochila
    template_name       = "core/mochila_list.html"
    context_object_name = "mochilas"

    def get_queryset(self):
        return Mochila.objects.prefetch_related("mochilaitem_set__item")


class MochilaDetailView(LoginRequiredMixin, DetailView):
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


def _parse_itens_post(post_data) -> dict[int, int]:
    result = {}
    for raw_id in post_data.getlist("item_ids"):
        try:
            item_id         = int(raw_id)
            qty             = int(post_data.get(f"qty_{item_id}", 1))
            result[item_id] = max(1, min(99, qty))
        except (ValueError, TypeError):
            continue
    return result


def _mochila_context(mochila=None) -> dict:
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
    model         = Mochila
    form_class    = MochilaForm
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
    model         = Mochila
    form_class    = MochilaForm
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
        return render(request, "core/confirm_delete.html", {
            "titulo":     "Excluir Mochila",
            "mensagem":   f'Deseja desativar a mochila "{mochila.nome}"?',
            "voltar_url": reverse_lazy("mochila_list"),
        })

    def post(self, request, pk):
        mochila = get_object_or_404(Mochila, pk=pk)
        try:
            desativar_mochila(user=request.user, mochila=mochila)
        except MochilaEmUsoError as e:
            messages.error(request, str(e))
            return redirect("mochila_list")
        _log(request.user, mochila, DELETION, "Mochila desativada")
        messages.success(request, "Mochila desativada.")
        return redirect("mochila_list")


# ──────────────────────────────────────────────
# ITENS
# ──────────────────────────────────────────────

class ItemListView(LoginRequiredMixin, ListView):
    model               = Item
    template_name       = "core/item_list.html"
    context_object_name = "itens"

    def get_queryset(self):
        return Item.objects.annotate(num_mochilas=Count("mochilas")).order_by("nome")


class ItemCreateView(SupervisorRequiredMixin, CreateView):
    model         = Item
    form_class    = ItemForm
    template_name = "core/item_form.html"
    success_url   = reverse_lazy("item_list")

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "editing": False}

    def form_valid(self, form):
        response = super().form_valid(form)
        _log(self.request.user, self.object, ADDITION, "Item criado")
        messages.success(self.request, "Item cadastrado com sucesso!")
        return response


class ItemUpdateView(SupervisorRequiredMixin, UpdateView):
    model         = Item
    form_class    = ItemForm
    template_name = "core/item_form.html"
    success_url   = reverse_lazy("item_list")

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
        except ItemEmUsoError as e:
            messages.error(request, str(e))
            return redirect("item_list")
        _log(request.user, item, DELETION, "Item desativado")
        messages.success(request, "Item desativado com sucesso.")
        return redirect("item_list")


# ──────────────────────────────────────────────
# LOJAS
# ──────────────────────────────────────────────

from django.db.models import Count, Q

class LojaListView(LoginRequiredMixin, ListView):
    model = Loja
    template_name = "core/loja_list.html"
    context_object_name = "lojas"

    def get_queryset(self):
        return Loja.objects.annotate(
            total_viagens=Count("viagens", distinct=True),
            viagens_andamento=Count(
                "viagens",
                filter=Q(viagens__status="andamento"),
                distinct=True
            )
        ).order_by("nome")


class LojaCreateView(SupervisorRequiredMixin, CreateView):
    model         = Loja
    form_class    = LojaForm
    template_name = "core/loja_form.html"
    success_url   = reverse_lazy("loja_list")

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "editing": False}

    def form_valid(self, form):
        response = super().form_valid(form)
        _log(self.request.user, self.object, ADDITION, "Loja criada")
        messages.success(self.request, "Loja cadastrada com sucesso!")
        return response


class LojaUpdateView(SupervisorRequiredMixin, UpdateView):
    model         = Loja
    form_class    = LojaForm
    template_name = "core/loja_form.html"
    success_url   = reverse_lazy("loja_list")

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
        return render(request, "core/confirm_delete.html", {
            "titulo":     "Excluir Loja",
            "mensagem":   f'Deseja desativar a loja "{loja.nome}"?',
            "voltar_url": reverse_lazy("loja_list"),
        })

    def post(self, request, pk):
        loja = get_object_or_404(Loja, pk=pk)
        try:
            desativar_loja(user=request.user, loja=loja)
        except LojaEmUsoError as e:
            messages.error(request, str(e))
            return redirect("loja_list")
        _log(request.user, loja, DELETION, "Loja desativada")
        messages.success(request, "Loja desativada.")
        return redirect("loja_list")


# ══════════════════════════════════════════════
# USUÁRIOS
# ══════════════════════════════════════════════

from django.db.models import Q

class UsuarioListView(UsuarioAreaMixin, ListView):
    model = User
    template_name = "core/usuario_list.html"
    context_object_name = "usuarios"

    def get_queryset(self):
        user = self.request.user

        qs = (
            User.objects
            .filter(is_active=True)
            .prefetch_related("groups", "password_policy")
        )

        # 🔒 Supervisor não vê admin
        if perms.is_supervisor(user):
            qs = qs.exclude(
                Q(is_superuser=True) |
                Q(groups__name="Admin")
            ).distinct()

        usuarios = list(qs)

        def nivel(u):
            if u.pk == user.pk:
                return 0
            if u.is_superuser:
                return 1
            if u.groups.filter(name="Supervisor").exists():
                return 2
            return 3

        return sorted(
            usuarios,
            key=lambda u: (nivel(u), u.username.lower())
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["usuarios"] = perms.annotate_usuario_perms(
            self.request.user,
            context["usuarios"],
        )

        return context


class UsuarioCreateView(UsuarioAreaMixin, View):
    """
    UsuarioAreaMixin garante que apenas Admin/Supervisor chegam aqui.
    A verificação de nível específico (pode criar admin?) é contexto fino
    que depende do valor submetido no form — permanece na view.
    """
    template_name = "core/usuario_form.html"

    def _filtrar_nivel_choices(self, form, user):
        if not perms.is_admin(user):
            form.fields["nivel"].choices = [
                c for c in form.fields["nivel"].choices if c[0] != "admin"
            ]
        return form

    def get(self, request):
        form = self._filtrar_nivel_choices(UsuarioCreateForm(), request.user)
        return render(request, self.template_name, {"form": form, "editing": False})

    def post(self, request):
        form  = UsuarioCreateForm(request.POST)
        nivel = request.POST.get("nivel", "usuario")

        # Contexto fino: mixin garante acesso à área, mas não o nível específico
        if not perms.pode_criar_usuario(request.user, nivel):
            messages.error(request, "Você não tem permissão para criar um usuário com este nível.")
            form = self._filtrar_nivel_choices(form, request.user)
            return render(request, self.template_name, {"form": form, "editing": False})

        if not form.is_valid():
            form = self._filtrar_nivel_choices(form, request.user)
            return render(request, self.template_name, {"form": form, "editing": False})

        try:
            user = criar_usuario(
                actor=request.user,
                username=form.cleaned_data["username"],
                nivel=form.cleaned_data["nivel"],
                first_name=form.cleaned_data.get("first_name", ""),
                last_name=form.cleaned_data.get("last_name", ""),
                email=form.cleaned_data.get("email", ""),
            )
        except DomainError as e:
            messages.error(request, str(e))
            form = self._filtrar_nivel_choices(form, request.user)
            return render(request, self.template_name, {"form": form, "editing": False})

        _log(request.user, user, ADDITION, f"Usuário criado — nível: {form.cleaned_data['nivel']}")
        messages.success(request, f"Usuário {user.username} criado. Senha padrão aplicada.")
        return redirect("usuario_list")


class UsuarioEditView(UsuarioAreaMixin, View):
    """
    UsuarioAreaMixin garante acesso à área.
    A verificação de pode_editar_usuario depende do objeto alvo e do nível
    solicitado — é object-level, permanece na view.
    """
    template_name = "core/usuario_form.html"

    def _filtrar_nivel_choices(self, form, user):
        if not perms.is_admin(user):
            form.fields["nivel"].choices = [
                c for c in form.fields["nivel"].choices if c[0] != "admin"
            ]
        return form

    def get(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        nivel  = get_nivel(target)

        # Object-level: depende de quem é o alvo
        if not perms.pode_editar_usuario(request.user, target, nivel):
            messages.error(request, "Você não tem permissão para editar este usuário.")
            return redirect("usuario_list")

        form = self._filtrar_nivel_choices(
            UsuarioEditForm(instance=target, initial={"nivel": nivel}),
            request.user,
        )
        return render(request, self.template_name, {
            "form": form, "editing": True, "target_user": target,
        })

    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        form   = UsuarioEditForm(request.POST, instance=target)
        nivel  = request.POST.get("nivel", "usuario")

        # Object-level: depende de quem é o alvo e para qual nível
        if not perms.pode_editar_usuario(request.user, target, nivel):
            messages.error(request, "Você não tem permissão para editar este usuário.")
            return redirect("usuario_list")

        if not form.is_valid():
            form = self._filtrar_nivel_choices(form, request.user)
            return render(request, self.template_name, {
                "form": form, "editing": True, "target_user": target,
            })

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
        except DomainError as e:
            messages.error(request, str(e))
            form = self._filtrar_nivel_choices(form, request.user)
            return render(request, self.template_name, {
                "form": form, "editing": True, "target_user": target,
            })

        _log(request.user, target, CHANGE, f"Usuário editado — nível: {form.cleaned_data['nivel']}")
        messages.success(request, f"Usuário {target.username} atualizado!")
        return redirect("usuario_list")


@method_decorator(require_POST, name="dispatch")
class UsuarioResetSenhaView(AdminRequiredMixin, View):
    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        resetar_senha(actor=request.user, target=target)
        _log(request.user, target, CHANGE, "Senha redefinida para padrão")
        messages.success(request, f"Senha de {target.username} redefinida.")
        return redirect("usuario_list")


@method_decorator(require_POST, name="dispatch")
class UsuarioDeleteView(AdminRequiredMixin, View):
    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)

        # Object-level: superuser não pode ser excluído (depende do objeto alvo)
        if not perms.pode_excluir_usuario(request.user, target):
            messages.error(request, "Você não tem permissão para excluir este usuário.")
            return redirect("usuario_list")

        username = target.username
        try:
            excluir_usuario(actor=request.user, target=target)
        except (AutoExclusaoError, DomainError) as e:
            messages.error(request, str(e))
            return redirect("usuario_list")

        _log(request.user, target, DELETION, "Usuário desativado")
        messages.success(request, f"Usuário {username} desativado.")
        return redirect("usuario_list")