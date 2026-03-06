from databases.core import Connection
from app.core.db.tables.dialogs import dialogs_table
import uuid
from fastapi import HTTPException
from loguru import logger as log
import datetime as dt
from typing import List
from ..schemas.dialog_schemas import HistoryFromDB
from sqlalchemy import and_


class AiCRUD:
    def __init__(self, conn: Connection):
        self.conn: Connection = conn

    async def create(
        self,
        max_user_id: int,
        question: str,
    ) -> tuple[int, uuid.UUID]:
        query = (
            dialogs_table
            .insert()
            .values(
                uuid=uuid.uuid4(),
                max_user_id=max_user_id,
                question=question,
            )
            .returning(
                dialogs_table.c.id,
                dialogs_table.c.uuid
            )
        )

        row = await self.conn.fetch_one(query)
        return row["id"], row['uuid']
    
    async def update(
        self,
        record_id: int,
        record_uuid: uuid.UUID,
        answer: str
    ) -> int:
        query = (
            dialogs_table.update()
            .where(
                (dialogs_table.c.id == record_id) &
                (dialogs_table.c.uuid == record_uuid)
            )
            .values(
                answer=answer
            )
            .returning(dialogs_table.c.id)
        )
        return await self.conn.fetch_val(query)

    async def get_many(
        self,
        max_user_id: int,
        date: dt.date,
        limit: int,
        user_uuid: uuid.UUID = None,
        create_at: dt.datetime = None
    ) -> List[HistoryFromDB]:
        # выводим по лимиту с фильром по create_at
        filter_conditions = [
            dialogs_table.c.max_user_id == max_user_id,
            dialogs_table.c.created_at == create_at,   
        ]
        if user_uuid is not None:
            filter_conditions.append(dialogs_table.c.user_uuid == user_uuid)

        query = (
            dialogs_table.select()
            .where(and_(*filter_conditions))
            .order_by(dialogs_table.c.created_at.desc())
            .limit(limit)
        )
        historys = await self.conn.fetch_all(query)
        return [HistoryFromDB(**x) for x in historys]
    
    async def delete(
        self,
        record_id: int,
        record_uuid: uuid.UUID
    ):
        query = (
            dialogs_table.delete()
            .where(
                (dialogs_table.c.id == record_id) &
                (dialogs_table.c.uuid == record_uuid)
            )
        )
        await self.conn.execute(query)