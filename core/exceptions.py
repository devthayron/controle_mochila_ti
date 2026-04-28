"""
exceptions.py — Exceções de domínio padronizadas.
"""


class DomainError(Exception):
    """Base para todas as exceções de domínio."""


class ItemEmUsoError(DomainError):
    """Item está em uso em viagem ativa e não pode ser desativado."""


class MochilaEmUsoError(DomainError):
    """Mochila está em uso em viagem ativa."""


class MochilaInativaError(DomainError):
    """Mochila está inativa e não pode ser usada."""


class MochilaVaziaError(DomainError):
    """Mochila não possui itens cadastrados."""


class LojaEmUsoError(DomainError):
    """Loja possui viagens em andamento e não pode ser desativada."""


class ViagemJaFinalizada(DomainError):
    """Viagem já está finalizada."""


class SenhaFracaError(DomainError):
    """Senha não atende aos requisitos mínimos."""


class SenhaIncorretaError(DomainError):
    """Senha atual informada está incorreta."""


class AutoExclusaoError(DomainError):
    """Usuário tentou se auto-excluir."""
