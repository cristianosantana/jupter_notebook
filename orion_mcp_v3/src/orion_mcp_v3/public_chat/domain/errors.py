"""Exceções de domínio do Chat Público."""

from __future__ import annotations


class PublicChatDomainError(Exception):
    """Erro de regra de negócio do Chat Público."""


class InvalidParentQuestionError(PublicChatDomainError):
    """``parent_question_id`` não existe."""
