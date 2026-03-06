import asyncio
from pymax import MaxClient
from pymax.types import Message, User
from pymax.static.enum import AttachType
from app.include.logging_config import logger as log
from .resources.service import download_voice
from app.core.db.connection import db_pool
from .resources.crud import MaxCRUD

client = MaxClient(
    phone="+79206786941",
    work_dir="./session_max/cache_3",
    reconnect=True,
)
# потом на Redis
processed_messages = set()


@client.on_start
async def on_start():
    print(f"Помощник запущен! ID: {client.me.id}")

@client.task(seconds=5)
async def unread_checker():
    # Основной воркер для отслеживания новых сообщений
    for dialog in client.dialogs:
        if (dialog.id == 0
            or not dialog.last_message
            or dialog.last_message.sender == client.me.id # пропускаем свои сообщения
            or dialog.last_message.id in processed_messages
        ):
            continue

        last = dialog.last_message
        processed_messages.add(last.id)
        user: User | None = await client.get_user(last.sender)
        name = user.names[0].first_name if user and user.names else ""
        message_text = last.text
        # проверяем тип сообщения
        if last.attaches:
            for attach in last.attaches:
                if attach.type == AttachType.AUDIO:
                    print(f"Получено аудио! в {dialog.id}")
                    log.info(f'{attach=}')
                    await download_voice(attach)
                
                    # Тут будет расшифровка аудио
                    message_text = "Расшифрованное аудио"
                if attach.type == AttachType.PHOTO:
                    log.info(f'ПОЛУЧЕНО ФОТО: {attach=}')
        log.debug(f"Текст сообщения: {message_text}")
        try:
            await client.send_message(
                chat_id=dialog.id,
                text=f"Привет {name}! Это заглушка проекта Вахта",
                notify=True
            )
        except Exception:
            print(f"Пропускаем системный чат: {dialog.id}")

        await client.read_message(
            chat_id=dialog.id,
            message_id=last.id
        )


@client.task(seconds=10)
async def process_pending_outreach() -> None:
    await asyncio.sleep(30)
    async with db_pool.database.connection() as conn:
        states = await MaxCRUD(conn).get_pending_outreach(limit=20)

    for state in states:
        phone = state.get("phone")
        source = state.get("source")
        if not phone:
            continue

        try:
            user: User = await client.search_by_phone(phone)
            async with db_pool.database.connection() as conn:
                crud = MaxCRUD(conn)
                user_create = await crud.create_user(
                    max_user_id=user.id,
                    phone=phone,
                    source=source
                )
                if user_create == False:
                    # значит он существует
                    pass
            await client.add_contact(user.id)
            chat_id = client.get_chat_id(client.me.id, user.id)
        except Exception as exc:
            log.warning(f"Cannot add contact {phone}: {exc}")
            continue

        async with db_pool.database.connection() as conn:
            crud = MaxCRUD(conn)
            await crud.create_or_update_user_state(
                phone=phone,
                state="get_user_info"
            )
            log.info(f"Начали обработку пользователя")

        # await _send_message(chat_id, state["id"], GREETING_TEXT, allow_voice=False)

async def _run_worker() -> None:
    await db_pool.init_db()
    try:
        await client.start()
    finally:
        await db_pool.close_db()


if __name__ == "__main__":
    asyncio.run(_run_worker())


