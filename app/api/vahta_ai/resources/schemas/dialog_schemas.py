from pydantic import BaseModel
from typing import Optional
import datetime as dt
from uuid import UUID


class HistoryFromDB(BaseModel):
    id: int
    uuid: UUID
    max_user_id: int
    question: str
    answer: Optional[str]
    created_at: dt.datetime
