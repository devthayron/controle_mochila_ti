"""
core.py — Infraestrutura estável de permissões.

FLUXO OBRIGATÓRIO:
    template → user_perms (context processor) → engine.has_perm → policies → roles

BLOCOS:
    1. ROLES       — identidade do usuário (quem ele é)
    2. PERMISSIONS — catálogo de constantes (o que existe)
    3. ENGINE      — dispatcher central (has_perm) + _POLICY_MAP
    4. CONTEXT     — user_perms para templates

CONTRATOS:
    - Templates NÃO chamam has_perm diretamente
    - Templates NÃO contêm lógica de role
    - Views NÃO duplicam regras de policies
    - Engine NÃO contém lógica de domínio
    - Policies é a ÚNICA camada com regra de negócio
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib.auth.models import User

if TYPE_CHECKING:
    from core.models import Viagem


# ══════════════════════════════════════════════
# BLOCO 1 — ROLES (identidade do usuário)
#
# Responsabilidade: funções puras que dizem QUEM o usuário é.
# Regras:
#   - NÃO contém regra de negócio
#   - NÃO usa Django permissions (has_perm)
#   - NÃO depende de contexto ou objeto
# ══════════════════════════════════════════════

def is_admin(user: User) -> bool:
    """Admin: superusuário ou com permissão explícita de admin_access."""
    return user.is_active and (
        user.is_superuser or user.has_perm("core.admin_access")
    )


def is_supervisor(user: User) -> bool:
    """Supervisor: membro do grupo Supervisor."""
    return user.is_active and user.groups.filter(name="Supervisor").exists()


def is_usuario(user: User) -> bool:
    """Usuário comum: autenticado, ativo, sem role elevada."""
    return user.is_active and not is_admin(user) and not is_supervisor(user)


def is_staff_level(user: User) -> bool:
    """Qualquer nível com capacidade de edição (admin OU supervisor)."""
    return is_admin(user) or is_supervisor(user)


# ── aliases internos com prefixo _ para manter compatibilidade ──────────────
# (usado por outros módulos que já importavam _is_admin, _is_supervisor etc.)
_is_admin      = is_admin
_is_supervisor = is_supervisor
_is_usuario    = is_usuario
_pode_editar   = is_staff_level


# ══════════════════════════════════════════════
# BLOCO 2 — PERMISSIONS (catálogo de constantes)
#
# Responsabilidade: nomear TODAS as permissões do sistema.
# Regras:
#   - Apenas constantes string
#   - Sem lógica
#   - Sem funções
# ══════════════════════════════════════════════

class Perm:
    # Viagens
    CRIAR_VIAGEM           = "criar_viagem"
    VER_VIAGEM             = "ver_viagem"          # object-level
    LISTAR_VIAGENS         = "listar_viagens"
    FINALIZAR_VIAGEM       = "finalizar_viagem"
    EDITAR_CHECKLIST       = "editar_checklist"    # object-level
    VER_CHECKLIST_SAIDA    = "ver_checklist_saida"
    VER_CHECKLIST_RETORNO  = "ver_checklist_retorno"

    # Inventário
    GERENCIAR_MOCHILA      = "gerenciar_mochila"
    GERENCIAR_LOJA         = "gerenciar_loja"
    GERENCIAR_ITEM         = "gerenciar_item"

    # Usuários
    ACESSAR_AREA_USUARIOS  = "acessar_area_usuarios"
    CRIAR_USUARIO          = "criar_usuario"       # requer context["nivel_alvo"]
    EDITAR_USUARIO         = "editar_usuario"      # object-level + context["nivel_alvo"]
    EXCLUIR_USUARIO        = "excluir_usuario"     # object-level
    RESETAR_SENHA          = "resetar_senha"

    # Admin
    ACESSAR_ADMIN          = "acessar_admin"

    # Meta (atalho para templates)
    PODE_EDITAR            = "pode_editar"         # alias: is_staff_level


# ══════════════════════════════════════════════
# BLOCO 3 — ENGINE (decisão central) + _POLICY_MAP
#
# Responsabilidade: dispatcher. Roteia perm → policy correta.
# Regras:
#   - NÃO contém lógica de domínio
#   - NÃO decide diretamente nada
#   - Deve ser previsível, pequeno, só dispatcher
#
# NOTA: _Policies é importado de policies.py APÓS a definição dos roles
#       para evitar import circular.
# ══════════════════════════════════════════════

# Import tardio das policies — policies.py importa roles deste módulo,
# portanto o import só pode ocorrer depois que os roles estão definidos.
from .policies import _Policies  # noqa: E402  (intencional — evita circular)

# Mapa de despacho: Perm.* → método de _Policies
_POLICY_MAP: dict[str, Any] = {
    Perm.CRIAR_VIAGEM:           _Policies.criar_viagem,
    Perm.VER_VIAGEM:             _Policies.ver_viagem,
    Perm.LISTAR_VIAGENS:         _Policies.listar_viagens,
    Perm.FINALIZAR_VIAGEM:       _Policies.finalizar_viagem,
    Perm.EDITAR_CHECKLIST:       _Policies.editar_checklist,
    Perm.VER_CHECKLIST_SAIDA:    _Policies.ver_checklist_saida,
    Perm.VER_CHECKLIST_RETORNO:  _Policies.ver_checklist_retorno,
    Perm.GERENCIAR_MOCHILA:      _Policies.gerenciar_mochila,
    Perm.GERENCIAR_LOJA:         _Policies.gerenciar_loja,
    Perm.GERENCIAR_ITEM:         _Policies.gerenciar_item,
    Perm.ACESSAR_AREA_USUARIOS:  _Policies.acessar_area_usuarios,
    Perm.CRIAR_USUARIO:          _Policies.criar_usuario,
    Perm.EDITAR_USUARIO:         _Policies.editar_usuario,
    Perm.EXCLUIR_USUARIO:        _Policies.excluir_usuario,
    Perm.RESETAR_SENHA:          _Policies.resetar_senha,
    Perm.ACESSAR_ADMIN:          _Policies.acessar_admin,
    Perm.PODE_EDITAR:            _Policies.pode_editar,
}


def has_perm(
    user: User,
    perm: str,
    obj=None,
    context: dict | None = None,
) -> bool:
    """
    Engine central de permissões.

    Args:
        user:    usuário que solicita acesso.
        perm:    constante de Perm (ex: Perm.CRIAR_VIAGEM).
        obj:     objeto alvo (viagem, user, etc.) — para permissões object-level.
        context: dados adicionais de contexto (ex: {"nivel_alvo": "supervisor"}).

    Returns:
        bool: True se o usuário tem a permissão.
    """
    if not getattr(user, "is_authenticated", False):
        return False

    policy = _POLICY_MAP.get(perm)
    if policy is None:
        return False

    return policy(user, obj=obj, context=context)


# ══════════════════════════════════════════════
# BLOCO 4 — CONTEXT PROCESSOR (user_perms)
#
# Responsabilidade: gerar user_perms para todos os templates.
# Regras:
#   - Retorna sempre {"user_perms": {...}}
#   - Usa has_perm internamente
#   - NÃO expõe engine para template
#   - NÃO contém lógica de domínio
#   - Apenas permissões globais (sem object-level)
# ══════════════════════════════════════════════

# Permissões globais (sem obj) incluídas em user_perms
_GLOBAL_PERMS = (
    Perm.PODE_EDITAR,
    Perm.ACESSAR_ADMIN,
    Perm.ACESSAR_AREA_USUARIOS,
    Perm.CRIAR_VIAGEM,
    Perm.LISTAR_VIAGENS,
    Perm.FINALIZAR_VIAGEM,
    Perm.GERENCIAR_MOCHILA,
    Perm.GERENCIAR_LOJA,
    Perm.GERENCIAR_ITEM,
    Perm.RESETAR_SENHA,
)

_EMPTY_PERMS = {"user_perms": {p: False for p in _GLOBAL_PERMS} | {
    # aliases legados mantidos para compatibilidade com templates existentes
    "is_admin":              False,
    "is_supervisor":         False,
    "pode_acessar_usuarios": False,
}}


def _build_user_perms(user: User) -> dict:
    """
    Constrói o dicionário user_perms para o template.
    Apenas permissões globais (sem obj). Permissões object-level
    são calculadas na view e passadas explicitamente ao contexto.
    """
    base = {perm: has_perm(user, perm) for perm in _GLOBAL_PERMS}

    # aliases legados — mantêm compatibilidade com templates e views existentes
    base["is_admin"]              = is_admin(user)
    base["is_supervisor"]         = is_supervisor(user)
    base["pode_acessar_usuarios"] = has_perm(user, Perm.ACESSAR_AREA_USUARIOS)

    return base


def permission_context(request) -> dict:
    """
    Context processor global.
    Registrado em settings.py → TEMPLATES → context_processors.

    Defensivo por design:
    - Verifica hasattr antes de acessar request.user
    - Verifica is_authenticated antes de qualquer acesso ao banco
    - Nunca lança exceção — retorna contexto vazio em qualquer caso de erro
    """
    try:
        user = getattr(request, "user", None)

        if user is None or not hasattr(user, "is_authenticated"):
            return _EMPTY_PERMS

        if not user.is_authenticated:
            return _EMPTY_PERMS

        return {"user_perms": _build_user_perms(user)}

    except Exception:
        return _EMPTY_PERMS


# ══════════════════════════════════════════════
# API PÚBLICA DE COMPATIBILIDADE
#
# Funções mantidas para não quebrar imports em views.py, mixins.py,
# admin.py e tests.py existentes.
# Internamente delegam para engine ou policies.
# ══════════════════════════════════════════════

def pode_editar(user: User) -> bool:
    return has_perm(user, Perm.PODE_EDITAR)


def pode_listar_viagens(user: User) -> bool:
    return has_perm(user, Perm.LISTAR_VIAGENS)


def pode_ver_viagem(user: User, viagem) -> bool:
    return has_perm(user, Perm.VER_VIAGEM, obj=viagem)


def pode_criar_viagem(user: User) -> bool:
    return has_perm(user, Perm.CRIAR_VIAGEM)


def pode_finalizar_viagem(user: User) -> bool:
    return has_perm(user, Perm.FINALIZAR_VIAGEM)


def pode_editar_checklist(user: User, viagem) -> bool:
    return has_perm(user, Perm.EDITAR_CHECKLIST, obj=viagem)


def pode_ver_checklist_saida_ok(user: User) -> bool:
    return has_perm(user, Perm.VER_CHECKLIST_SAIDA)


def pode_ver_checklist_retorno_ok(user: User) -> bool:
    return has_perm(user, Perm.VER_CHECKLIST_RETORNO)


def pode_gerenciar_mochila(user: User) -> bool:
    return has_perm(user, Perm.GERENCIAR_MOCHILA)


def pode_gerenciar_loja(user: User) -> bool:
    return has_perm(user, Perm.GERENCIAR_LOJA)


def pode_gerenciar_item(user: User) -> bool:
    return has_perm(user, Perm.GERENCIAR_ITEM)


def pode_acessar_area_usuarios(user: User) -> bool:
    return has_perm(user, Perm.ACESSAR_AREA_USUARIOS)


def pode_criar_usuario(user: User, nivel_alvo: str) -> bool:
    return has_perm(user, Perm.CRIAR_USUARIO, context={"nivel_alvo": nivel_alvo})


def pode_editar_usuario(user: User, target: User, nivel_alvo: str) -> bool:
    return has_perm(user, Perm.EDITAR_USUARIO, obj=target, context={"nivel_alvo": nivel_alvo})


def pode_excluir_usuario(user: User, target: User) -> bool:
    return has_perm(user, Perm.EXCLUIR_USUARIO, obj=target)


def pode_resetar_senha(user: User) -> bool:
    return has_perm(user, Perm.RESETAR_SENHA)


def pode_acessar_admin(user: User) -> bool:
    return has_perm(user, Perm.ACESSAR_ADMIN)


def filtrar_viagens(user: User, qs):
    """Filtra queryset de viagens conforme o papel do usuário."""
    if is_staff_level(user):
        return qs
    return qs.filter(responsavel=user)


# ══════════════════════════════════════════════
# HELPERS DE ANOTAÇÃO (object-level em listas)
#
# Responsabilidade: enriquecer objetos com flags de permissão
# para que templates não precisem de lógica de role.
#
# Uso na view:
#   context["usuarios"] = perms.annotate_usuario_perms(request.user, qs)
#
# Uso no template:
#   {% if u.perm_pode_editar %} ... {% endif %}
# ══════════════════════════════════════════════

def _nivel_do_usuario(user: User) -> str:
    """
    Resolve o nível de acesso de um usuário sem importar usuario_service
    (evita risco de importação circular).
    """
    if user.is_superuser:
        return "admin"
    for group in user.groups.all():
        if group.name == "Admin":
            return "admin"
        if group.name == "Supervisor":
            return "supervisor"
    return "usuario"


def annotate_usuario_perms(actor: User, usuarios) -> list:
    """
    Anota cada usuário do queryset/lista com flags de permissão pré-calculadas.

    Flags adicionadas em cada objeto:
        u.perm_pode_editar  — actor pode editar este usuário
        u.perm_pode_excluir — actor pode excluir este usuário
        u.perm_pode_reset   — actor pode resetar a senha deste usuário

    Exemplo de uso na view:
        context["usuarios"] = perms.annotate_usuario_perms(request.user, qs)

    Exemplo de uso no template:
        {% if u.perm_pode_editar %}
            <a href="{% url 'usuario_edit' u.pk %}">Editar</a>
        {% endif %}
    """
    result = []
    for u in usuarios:
        nivel = _nivel_do_usuario(u)
        u.perm_pode_editar  = has_perm(actor, Perm.EDITAR_USUARIO, obj=u, context={"nivel_alvo": nivel})
        u.perm_pode_excluir = has_perm(actor, Perm.EXCLUIR_USUARIO, obj=u) and u != actor
        u.perm_pode_reset   = has_perm(actor, Perm.RESETAR_SENHA) and u != actor
        result.append(u)
    return result