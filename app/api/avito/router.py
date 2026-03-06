from fastapi import APIRouter, Query

from .resources.schemas.vahta import AvitoSendMessageRequest
from .resources.service import (
    get_avito_chats as get_avito_chats_service,
    get_avito_messages as get_avito_messages_service,
    read_avito_chat as read_avito_chat_service,
    send_avito_message as send_avito_message_service,
)


router = APIRouter(prefix="/avito", tags=["Module Avito"])

@router.get(
    "/accounts/{user_id}/chats/{chat_id}/messages",
    name="Get Avito messages for a specific chat",
    description="Получить сообщения из чата Avito для указанного пользователя и чата.",
)
async def get_avito_messages(
    user_id: int,
    chat_id: str,
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=1000),
):
    return await get_avito_messages_service(
        user_id=user_id,
        chat_id=chat_id,
        limit=limit,
        offset=offset
    )


@router.get(
    "/accounts/{user_id}/chats",
    name="Get Avito chats",
    description="Получить список чатов Avito с фильтрацией по объявлениям (item_ids).",
)
async def get_avito_chats(
    user_id: int,
    item_ids: list[int] | None = Query(default=None),
    unread_only: bool = Query(default=False),
    chat_types: str = Query(default="u2i"),
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=1000),
):
    return await get_avito_chats_service(
        user_id=user_id,
        item_ids=item_ids,
        unread_only=unread_only,
        chat_types=chat_types,
        limit=limit,
        offset=offset
    )


@router.post(
    "/accounts/{user_id}/chats/{chat_id}/messages",
    name="Send Avito message for a specific chat",
    description="Отправить текстовое сообщение в чат Avito для указанного пользователя и чата.",
)
async def send_avito_message(
    user_id: int,
    chat_id: str,
    payload: AvitoSendMessageRequest,
):
    return await send_avito_message_service(
        user_id=user_id,
        chat_id=chat_id,
        payload=payload.model_dump(),
    )


@router.post(
    "/accounts/{user_id}/chats/{chat_id}/read",
    name="Read Avito chat",
    description="Пометить чат Avito как прочитанный для указанного пользователя и чата.",
)
async def read_avito_chat(
    user_id: int,
    chat_id: str,
):
    return await read_avito_chat_service(
        user_id=user_id,
        chat_id=chat_id,
    )
