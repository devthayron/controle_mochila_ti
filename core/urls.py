from django.urls import path
from .views import *

urlpatterns = [
    # AUTH
    path("login/",        CustomLoginView.as_view(),  name="login"),
    path("logout/",       CustomLogoutView.as_view(), name="logout"),
    path("trocar-senha/", TrocarSenhaView.as_view(),  name="trocar_senha"),

    # DASHBOARD
    path("", DashboardView.as_view(), name="dashboard"),

    # VIAGENS
    path("viagens/",                      ViagemListView.as_view(),     name="viagem_list"),
    path("viagens/nova/",                 ViagemCreateView.as_view(),   name="viagem_create"),
    path("viagens/<int:pk>/",             ViagemDetailView.as_view(),   name="viagem_detail"),
    path("viagens/<int:pk>/finalizar/",   FinalizarViagemView.as_view(),name="viagem_finalizar"),
    path("viagens/<int:pk>/checklist/",   ChecklistSaveView.as_view(),  name="viagem_checklist_save"),

    # MOCHILAS
    path("mochilas/",                  MochilaListView.as_view(),   name="mochila_list"),
    path("mochilas/<int:pk>/",         MochilaDetailView.as_view(), name="mochila_detail"),
    path("mochilas/nova/",             MochilaCreateView.as_view(), name="mochila_create"),
    path("mochilas/<int:pk>/editar/",  MochilaUpdateView.as_view(), name="mochila_edit"),
    path("mochilas/<int:pk>/excluir/", MochilaDeleteView.as_view(), name="mochila_delete"),

    # ITENS
    path("itens/",                  ItemListView.as_view(),   name="item_list"),
    path("itens/nova/",             ItemCreateView.as_view(), name="item_create"),
    path("itens/<int:pk>/editar/",  ItemUpdateView.as_view(), name="item_edit"),
    path("itens/<int:pk>/excluir/", ItemDeleteView.as_view(), name="item_delete"),

    # LOJAS
    path("lojas/",                  LojaListView.as_view(),   name="loja_list"),
    path("lojas/nova/",             LojaCreateView.as_view(), name="loja_create"),
    path("lojas/<int:pk>/editar/",  LojaUpdateView.as_view(), name="loja_edit"),
    path("lojas/<int:pk>/excluir/", LojaDeleteView.as_view(), name="loja_delete"),

    # USUÁRIOS (só admin)
    path("usuarios/",                          UsuarioListView.as_view(),        name="usuario_list"),
    path("usuarios/novo/",                     UsuarioCreateView.as_view(),      name="usuario_create"),
    path("usuarios/<int:pk>/editar/",          UsuarioEditView.as_view(),        name="usuario_edit"),
    path("usuarios/<int:pk>/excluir/",         UsuarioDeleteView.as_view(),      name="usuario_delete"),
    path("usuarios/<int:pk>/reset-senha/",     UsuarioResetSenhaView.as_view(),  name="usuario_reset_senha"),
]