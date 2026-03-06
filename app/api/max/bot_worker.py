import asyncio
from pymax import MaxClient
from pymax.types import Message, User
from pymax.static.enum import AttachType
from app.include.logging_config import logger as log
from .resources.service import download_voice

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

if __name__ == "__main__":
    asyncio.run(client.start())
