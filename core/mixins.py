"""
mixins.py — Guards de acesso HTTP.

Responsabilidade única: barrar a requisição antes que a view execute,
quando o usuário não tem o papel (role) necessário para aquela área.

PRINCÍPIO DE SEPARAÇÃO:
  - Verificações de ROLE (quem pode acessar esta área) → mixin
  - Verificações de OBJETO (pode ver/editar ESTE item) → view
  - Verificações de CONTEXTO FINO (pode criar usuário NESTE nível) → view
  - Nenhuma lógica de negócio aqui
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect

from . import permissions as perms


class SupervisorRequiredMixin(LoginRequiredMixin):
    """
    Requer permissão de Supervisor ou Admin.
    Cobre: criar/editar/excluir viagens, mochilas, lojas e itens.
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not perms.pode_editar(request.user):
            messages.error(request, "Você não tem permissão para realizar essa ação.")
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)


class UsuarioAreaMixin(LoginRequiredMixin):
    """
    Acesso à área de usuários (Admin e Supervisor).
    A granularidade fina (pode criar admin? pode editar este usuário?)
    é verificada dentro de cada view, pois depende do contexto do objeto.
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not perms.pode_acessar_area_usuarios(request.user):
            messages.error(request, "Você não tem permissão para acessar esta área.")
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)


class AdminRequiredMixin(LoginRequiredMixin):
    """
    Somente Admin.
    Cobre: reset de senha, exclusão de usuários.
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not perms.is_admin(request.user):
            messages.error(request, "Acesso restrito a administradores.")
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)