from __future__ import annotations

import asyncpg

_pool: asyncpg.Pool | None = None


async def get_pg_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        from app.config import get_settings

        st = get_settings()
        if not st.postgres_enabled:
            raise RuntimeError("PostgreSQL não configurado (POSTGRES_*).")
        _pool = await asyncpg.create_pool(
            host=st.postgres_host,
            port=st.postgres_port,
            user=st.postgres_user,
            password=st.postgres_password or None,
            database=st.postgres_database,
            min_size=1,
            max_size=6,
        )
    return _pool
