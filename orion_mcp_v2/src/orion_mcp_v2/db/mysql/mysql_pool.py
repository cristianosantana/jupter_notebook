from __future__ import annotations

from typing import Any
from urllib.parse import unquote, urlparse

import asyncmy


def _parse_mysql_url(url: str) -> dict[str, Any]:
    u = urlparse(url)
    if u.scheme not in ("mysql", "mysql+asyncmy"):
        raise ValueError("mysql_url must use mysql:// or mysql+asyncmy://")
    db = (u.path or "/").lstrip("/").split("?", 1)[0]
    return {
        "host": u.hostname or "localhost",
        "port": u.port or 3306,
        "user": unquote(u.username or ""),
        "password": unquote(u.password or ""),
        "db": db,
    }


async def create_mysql_pool(
    url: str | None,
    *,
    minsize: int = 1,
    maxsize: int = 10,
) -> Any | None:
    if not url or not url.strip():
        return None
    cfg = _parse_mysql_url(url.strip())
    return await asyncmy.create_pool(
        **cfg,
        minsize=minsize,
        maxsize=maxsize,
        autocommit=True,
    )


async def close_mysql_pool(pool: Any | None) -> None:
    if pool is not None:
        pool.close()
        await pool.wait_closed()
