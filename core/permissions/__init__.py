# core/permissions/__init__.py

from .core import (
    # Roles (API pública)
    is_admin,
    is_supervisor,
    is_usuario,
    is_staff_level,

    # Perm / Engine (API pública)
    Perm,
    has_perm,

    # Context processor (API pública)
    permission_context,

    # API pública de compatibilidade
    pode_editar,
    pode_listar_viagens,
    pode_ver_viagem,
    pode_criar_viagem,
    pode_finalizar_viagem,
    pode_editar_checklist,
    pode_ver_checklist_saida_ok,
    pode_ver_checklist_retorno_ok,
    pode_gerenciar_mochila,
    pode_gerenciar_loja,
    pode_gerenciar_item,
    pode_acessar_area_usuarios,
    pode_criar_usuario,
    pode_editar_usuario,
    pode_excluir_usuario,
    pode_resetar_senha,
    pode_acessar_admin,
    filtrar_viagens,

    # Helpers úteis (somente os que fazem sentido fora)
    annotate_usuario_perms,
)

# NÃO exporta Policies diretamente (mantém encapsulado)


# Define explicitamente o que é público
__all__ = [
    # Roles
    "is_admin",
    "is_supervisor",
    "is_usuario",
    "is_staff_level",

    # Engine
    "Perm",
    "has_perm",

    # Context
    "permission_context",

    # API compatível
    "pode_editar",
    "pode_listar_viagens",
    "pode_ver_viagem",
    "pode_criar_viagem",
    "pode_finalizar_viagem",
    "pode_editar_checklist",
    "pode_ver_checklist_saida_ok",
    "pode_ver_checklist_retorno_ok",
    "pode_gerenciar_mochila",
    "pode_gerenciar_loja",
    "pode_gerenciar_item",
    "pode_acessar_area_usuarios",
    "pode_criar_usuario",
    "pode_editar_usuario",
    "pode_excluir_usuario",
    "pode_resetar_senha",
    "pode_acessar_admin",
    "filtrar_viagens",

    # Helpers
    "annotate_usuario_perms",
]