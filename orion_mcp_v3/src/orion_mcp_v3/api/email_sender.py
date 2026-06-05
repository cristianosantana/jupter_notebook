"""Compatibilidade para imports antigos do envio de e-mail."""

from orion_mcp_v3.api.email.sender import EmailSender, EmailSendRequest, EmailSendResult

__all__ = ["EmailSender", "EmailSendRequest", "EmailSendResult"]
