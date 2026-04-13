from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.contrib import messages
from .models import UserProfile


def get_user_profile(user):
    """Retorna o perfil do usuário, criando como 'usuario' se não existir."""
    if user.is_superuser:
        profile, _ = UserProfile.objects.get_or_create(user=user, defaults={"nivel": "admin"})
        if profile.nivel != "admin":
            profile.nivel = "admin"
            profile.save()
        return profile
    profile, _ = UserProfile.objects.get_or_create(user=user, defaults={"nivel": "usuario"})
    return profile


class NivelMixin(LoginRequiredMixin):
    """Mixin base que injeta o perfil no contexto."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        self.user_profile = get_user_profile(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["user_profile"] = self.user_profile
        return context


class SupervisorRequiredMixin(NivelMixin):
    """Só Supervisor e Admin podem acessar."""

    def dispatch(self, request, *args, **kwargs):
        result = super().dispatch(request, *args, **kwargs)
        if not request.user.is_authenticated:
            return result
        if not self.user_profile.pode_editar:
            messages.error(request, "Você não tem permissão para realizar essa ação.")
            return redirect("dashboard")
        return result


class AdminRequiredMixin(NivelMixin):
    """Só Admin pode acessar."""

    def dispatch(self, request, *args, **kwargs):
        result = super().dispatch(request, *args, **kwargs)
        if not request.user.is_authenticated:
            return result
        if not self.user_profile.is_admin:
            messages.error(request, "Acesso restrito a administradores.")
            return redirect("dashboard")
        return result
