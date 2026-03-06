from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AvitoTextMessage(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000, description="Текст сообщения")

class AvitoSendMessageRequest(BaseModel):
    message: AvitoTextMessage
    type: Literal["text"] = "text"
