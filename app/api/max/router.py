from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from databases.core import Connection

from app.core.db.connection import db_pool
from .resources.crud import MaxCRUD
from .resources.service import normalize_phone


router = APIRouter(prefix="/max", tags=["Module MAX"])


class StartOutreachRequest(BaseModel):
    phone: str = Field(..., description="Номер телефона кандидата", examples=["+79998887766"])
    source: str = Field(default="base", description="Источник кандидата: avito или база")


@router.post(
    "/outreach/start",
    response_model=None,
    name="Поставить кандидата в очередь на старт диалога в MAX",
    description="Ручка принимает телефон, дальше воркер MAX добавляет контакт и запускает этап сбора данных.",
)
async def start_outreach(
    payload: StartOutreachRequest,
    conn: Connection = Depends(db_pool.get_connection),
):
    try:
        normalized_phone = normalize_phone(payload.phone)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    state = await MaxCRUD(conn).create_or_update_user_state(
        phone=normalized_phone,
        source=(payload.source or "base").strip().lower(),
    )

    return {
        "status": "queued",
        "state_id": state["id"],
        "phone": state["phone"],
        "stage": state["funnel_stage"],
    }
