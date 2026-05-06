from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class FormatRequest(BaseModel):
    content: str
    format: Literal["html", "tabela", "lista"] = Field(default="lista")


def format_response(req: FormatRequest) -> dict[str, Any]:
    """Sem estado/histórico: só transforma o artefato final."""
    if req.format == "html":
        body = f"<article>{_esc(req.content)}</article>"
    elif req.format == "tabela":
        body = "<table><tr><td>" + _esc(req.content).replace("\n", "</td></tr><tr><td>") + "</td></tr></table>"
    else:
        lines = [f"<li>{_esc(line)}</li>" for line in req.content.splitlines() if line.strip()]
        body = "<ul>" + "".join(lines) + "</ul>" if lines else "<p>" + _esc(req.content) + "</p>"
    return {"format": req.format, "body": body}


def _esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
