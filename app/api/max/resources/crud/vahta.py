from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import or_
from databases.core import Connection

from app.core.db.tables.user import users_table
from app.core.db.tables.user_state import user_states_table
from app.core.db.tables.vacancy import vacancies_table


class MaxCRUD:
    def __init__(self, conn: Connection):
        self.conn = conn

    async def create_user(
        self,
        max_user_id: int,
        phone: str,
        source: str,
    ) -> dict[str, Any] | bool:

        existing = await self.conn.fetch_one(
            users_table.select().where(
                users_table.c.max_user_id == max_user_id
            )
        )

        if existing:
            return False

        now = datetime.utcnow()

        inserted = await self.conn.fetch_one(
            users_table.insert()
            .values(
                max_user_id=max_user_id,
                phone=phone,
                source=source,
                used_voice_messages=[],
                funnel_stage="pending_outreach",
                updated_at=now,
            )
            .returning(users_table)
        )

        return dict(inserted)

    async def update(
            self, 
            max_user_id: int
    ) -> dict[str, Any]:
        now = datetime.utcnow()
        pass

    # получаем очередь
    async def get_pending_outreach(self, limit: int = 20) -> list[dict[str, Any]]:
        query = (
            user_states_table.select()
            .where(user_states_table.c.funnel_stage == "pending_outreach")
            .order_by(user_states_table.c.updated_at.asc())
            .limit(limit)
        )
        rows = await self.conn.fetch_all(query)
        return [dict(row) for row in rows]

    # Получаем состояние пользователя (на каком он этапе)
    async def get_state_by_chat_id(self, chat_id: int) -> dict[str, Any] | None:
        row = await self.conn.fetch_one(
            user_states_table.select().where(user_states_table.c.max_chat_id == chat_id)
        )
        return dict(row) if row else None

    async def get_state_by_id(self, state_id: int) -> dict[str, Any] | None:
        row = await self.conn.fetch_one(
            user_states_table.select().where(user_states_table.c.id == state_id)
        )
        return dict(row) if row else None
    
    async def create_or_update_user_state(
        self,
        source: str,
        phone: str | None = None,
        max_user_id: int | None = None,
    ) -> dict[str, Any]:
        now = datetime.utcnow()
        filters = []
        if phone:
            filters.append(user_states_table.c.phone == phone)

        existing = await self.conn.fetch_one(
            user_states_table.select().where(or_(*filters))
        )

        if existing:
            update_values = dict()
            update_values["updated_at"] = now
            if source:
                update_values["source"] = source
            if max_user_id is not None and (existing.get("max_user_id") is None):
                update_values["max_user_id"] = max_user_id

            query = (
                user_states_table.update()
                .where(user_states_table.c.id == existing["id"])
                .values(**update_values)
                .returning(user_states_table)
            )
            updated = await self.conn.fetch_one(query)
            return dict(updated) if updated else {}

        # create new
        insert_values = dict()
        insert_values["phone"] = phone
        insert_values["source"] = source
        if max_user_id is not None:
            insert_values["max_user_id"] = max_user_id
        insert_values.setdefault("used_voice_messages", [])
        insert_values.setdefault("funnel_stage", "pending_outreach")
        insert_values["updated_at"] = now

        inserted = await self.conn.fetch_one(
            user_states_table.insert().values(**insert_values).returning(user_states_table)
        )
        return dict(inserted) if inserted else {}