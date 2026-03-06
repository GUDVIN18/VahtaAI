from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

from .resources.service import normalize_phone


router = APIRouter(prefix="/max", tags=["Module MAX"])
class StartOutreachRequest(BaseModel):
    phone: str = Field(
        ...,
        description="Номер телефона кандидата",
        examples=["+79998887766"],
    )

@router.post(
    "/outreach/start",
    response_model=None,
    name="Поставить кандидата в очередь на старт диалога в MAX",
    description="Ручка принимает только телефон, дальше воркер MAX добавляет контакт и запускает этап сбора данных.",
)
async def start_outreach(payload: StartOutreachRequest):
    try:
        normalized_phone = normalize_phone(payload.phone)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return
