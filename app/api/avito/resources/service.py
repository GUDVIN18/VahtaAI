import httpx
from app.include.config import config
from fastapi import HTTPException


async def get_avito_messages(
    user_id: int,
    chat_id: str,
    limit: int ,
    offset: int,
):
    if not config.AUTHORIZATION_TOKEN:
        raise HTTPException(status_code=400, detail="Authorization header is required")

    url = f"{config.AVITO_API_BASE_URL}/messenger/v3/accounts/{user_id}/chats/{chat_id}/messages/"
    params = {"limit": limit, "offset": offset}

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                url, 
                params=params, 
                headers={"Authorization": config.AUTHORIZATION_TOKEN}
            )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Avito request failed: {exc!s}") from exc

    return response.json()


async def get_avito_chats(
    user_id: int,
    item_ids: list[int] | None = None,
    unread_only: bool = False,
    chat_types: str = "u2i",
    limit: int = 100,
    offset: int = 0,
):
    if not config.AUTHORIZATION_TOKEN:
        raise HTTPException(status_code=400, detail="Authorization header is required")

    url = f"{config.AVITO_API_BASE_URL}/messenger/v2/accounts/{user_id}/chats/"
    params: dict[str, str | int | bool] = {
        "unread_only": unread_only,
        "limit": limit,
        "offset": offset,
    }
    if item_ids:
        params["item_ids"] = ",".join(str(item_id) for item_id in item_ids)
    if chat_types:
        params["chat_types"] = ",".join(chat_types)

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                url, 
                params=params, 
                headers={"Authorization": config.AUTHORIZATION_TOKEN}
            )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Avito request failed: {exc!s}") from exc

    return response.json()


async def send_avito_message(
    user_id: int,
    chat_id: str,
    payload: dict,
):
    if not config.AUTHORIZATION_TOKEN:
        raise HTTPException(status_code=400, detail="Authorization header is required")

    url = f"{config.AVITO_API_BASE_URL}/messenger/v1/accounts/{user_id}/chats/{chat_id}/messages"

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                url,
                json=payload,
                headers={"Authorization": config.AUTHORIZATION_TOKEN},
            )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Avito request failed: {exc!s}") from exc

    return response.json()


async def read_avito_chat(
    user_id: int,
    chat_id: str,
):
    if not config.AUTHORIZATION_TOKEN:
        raise HTTPException(status_code=400, detail="Authorization header is required")

    url = f"{config.AVITO_API_BASE_URL}/messenger/v1/accounts/{user_id}/chats/{chat_id}/read"

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                url,
                headers={"Authorization": config.AUTHORIZATION_TOKEN},
            )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Avito request failed: {exc!s}") from exc

    return response.json()
