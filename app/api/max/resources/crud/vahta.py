from __future__ import annotations
from app.include.logging_config import logger as log
import uuid
from datetime import datetime
from typing import Any, Optional
from app.api.max.resources.schemas.states import UserState
from sqlalchemy import or_, update, select
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
        chat_id: int
    ) -> dict[str, Any] | bool:

        existing = await self.conn.fetch_one(
            users_table.select().where(
                or_(
                    users_table.c.max_user_id == max_user_id,
                    users_table.c.phone == phone
                )
            )
        )
        log.info(f"{existing=}")

        if existing is not None:
            existing = dict(existing)
            return False

        now = datetime.utcnow()

        inserted = await self.conn.fetch_one(
            users_table.insert()
            .values(
                max_user_id=max_user_id,
                phone=phone,
                chat_id=chat_id,
                user_uuid=uuid.uuid4(),
                created_at=now,
                updated_at=now,
            )
            .returning(users_table)
        )
        return dict(inserted)

    async def get_user(
        self,
        max_user_id: int | None = None,
        phone: str | None = None
    ) -> Optional[dict[str, Any]]:

        query = select(users_table)

        if max_user_id:
            query = query.where(users_table.c.max_user_id == max_user_id)

        if phone:
            query = query.where(users_table.c.phone == phone)

        row = await self.conn.fetch_one(query)

        if row:
            return dict(row)

        return None

    async def update(
        self,
        max_user_id: int,
        **fields
    ) -> Optional[dict[str, Any]]:

        if not fields:
            return None

        fields["updated_at"] = datetime.utcnow()

        row = await self.conn.fetch_one(
            users_table.update()
            .where(users_table.c.max_user_id == max_user_id)
            .values(**fields)
            .returning(users_table)
        )

        if row:
            return dict(row)

        return None

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
        user_row = await self.conn.fetch_one(
            users_table.select().where(users_table.c.chat_id == chat_id)
        )
        if not user_row:
            return None
        user = dict(user_row)
        if not user.get("max_user_id"):
            return None

        row = await self.conn.fetch_one(
            user_states_table.select().where(
                user_states_table.c.max_user_id == user["max_user_id"]
            )
        )
        return dict(row) if row else None

    async def get_state_by_max_user_id(self, max_user_id: int) -> dict[str, Any] | None:
        row = await self.conn.fetch_one(
            user_states_table.select().where(user_states_table.c.max_user_id == max_user_id)
        )
        return dict(row) if row else None

    async def get_state_by_id(self, state_id: int) -> dict[str, Any] | None:
        row = await self.conn.fetch_one(
            user_states_table.select().where(user_states_table.c.id == state_id)
        )
        return dict(row) if row else None
    
    async def create_or_update_user_state(
        self,
        state: UserState,
        source: str| None = None,
        phone: str | None = None,
        max_user_id: int | None = None,
    ) -> dict[str, Any]:
        now = datetime.utcnow()
        filters = []
        if phone:
            filters.append(user_states_table.c.phone == phone)
        if max_user_id is not None:
            filters.append(user_states_table.c.max_user_id == max_user_id)

        if not filters:
            raise ValueError("phone or max_user_id must be provided")

        existing = await self.conn.fetch_one(user_states_table.select().where(or_(*filters)))
        existing = dict(existing) if existing else None

        if existing:
            update_values = dict()
            update_values["funnel_stage"] = state
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
        insert_values.setdefault("funnel_stage", state)
        insert_values["updated_at"] = now

        inserted = await self.conn.fetch_one(
            user_states_table.insert().values(**insert_values).returning(user_states_table)
        )
        return dict(inserted) if inserted else {}
