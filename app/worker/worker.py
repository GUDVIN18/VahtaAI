from __future__ import annotations

import asyncio
from typing import Any

from app.api.max.resources.schemas.states import UserState
from app.core.db.connection import db_pool
from app.core.db.tables.user_state import user_states_table
from app.api.vahta_ai.graph.step_1 import run_step_1
from app.api.max.bot_worker import client


def _extract_user_state(user_state: UserState | str | dict[str, Any]) -> UserState:
    if isinstance(user_state, dict):
        user_state = user_state.get("funnel_stage")
    return UserState(user_state)


def process_user_state(user_state: UserState | str | dict[str, Any]) -> None:
    state = _extract_user_state(user_state)

    match state:
        case UserState.PENDING_OUTREACH:
            print(UserState.PENDING_OUTREACH.value)
        case UserState.GET_USER_INFO:
            # тут вызов функции step_1.py
            ai_message = run_step_1(session_id="1234", message="Начали")
            ai_message=ai_message['reply']
            client.send_message(
                chat_id=user.caht_id,
                text=f"{ai_message}",
                notify=True
            )


async def fetch_user_states() -> list[dict[str, Any]]:
    async with db_pool.database.connection() as conn:
        rows = await conn.fetch_all(user_states_table.select())
    return [dict(row) for row in rows]


async def run_worker(poll_interval: int = 2) -> None:
    await db_pool.init_db()
    try:
        while True:
            user_states = await fetch_user_states()
            for user_state in user_states:
                process_user_state(user_state)

            await asyncio.sleep(poll_interval)
    finally:
        await db_pool.close_db()


if __name__ == "__main__":
    asyncio.run(run_worker())
