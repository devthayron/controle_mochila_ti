# core/permissions/__init__.py

from .core import (
    # Roles
    is_admin,
    is_supervisor,
    is_usuario,
    is_staff_level,
    _is_admin,
    _is_supervisor,
    _is_usuario,
    _pode_editar,

    # Perm
    Perm,

    # Engine
    has_perm,
    _POLICY_MAP,

    # Context processor
    permission_context,
    _build_user_perms,
    _GLOBAL_PERMS,
    _EMPTY_PERMS,

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

    # Helpers de anotação
    annotate_usuario_perms,
    _nivel_do_usuario,
)

from .policies import _Policies