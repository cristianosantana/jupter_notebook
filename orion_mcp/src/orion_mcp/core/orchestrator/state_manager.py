from __future__ import annotations

from orion_mcp.core.state.models import State
from orion_mcp.infra.db.state_repository import StateRepository


class StateManager:
    def __init__(self, repo: StateRepository):
        self._repo = repo

    async def load_state(self, session_id: str) -> State:
        return await self._repo.load(session_id)

    async def save_state(self, session_id: str, state: State) -> None:
        await self._repo.save(session_id, state)
