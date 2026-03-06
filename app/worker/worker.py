import asyncio
import json
from app.include.logging_config import logger
from app.include.config import config
from app.api.avito.resources.service import get_avito_chats, get_avito_messages


async def message_polling_worker():
    logger.info("Worker started. Monitoring items: %s", config.AVITO_ITEM_IDS)
    
    # Хранилище ID последних сообщений, чтобы не обрабатывать их повторно
    # В идеале это должен быть Redis, но для "простого" решения хватит dict в памяти
    last_processed_msg = {} 

    while True:
        try:
            # 1. Запрашиваем чаты с непрочитанными сообщениями по нашим айтемам
            chats_response = await get_avito_chats(
                user_id=config.AVITO_USER_ID,
                item_ids=config.AVITO_ITEM_IDS,
                unread_only=True, # Берем только те, где есть что-то новое
                limit=10
            )
            
            # Извлекаем данные (учитываем, что возвращается JSONResponse)
            chats_data = chats_response.body_decode() if hasattr(chats_response, 'body_decode') else chats_response.content
            # Если используешь FastAPI Response напрямую, достаем payload:
            
            chats = json.loads(chats_response.body).get("chats", [])

            for chat in chats:
                chat_id = chat.get("id")
                last_msg_id = chat.get("last_message", {}).get("id")

                # Проверяем, обрабатывали ли мы это сообщение уже
                if last_processed_msg.get(chat_id) == last_msg_id:
                    continue

                logger.info(f"New activity in chat {chat_id}! Fetching messages...")

                # 2. Дергаем ручку получения сообщений
                messages_response = await get_avito_messages(
                    user_id=config.AVITO_USER_ID,
                    chat_id=chat_id,
                    limit=10
                )
                
                messages = json.loads(messages_response.body).get("messages", [])
                
                # Тут твоя логика обработки (например, переслать в Telegram или БД)
                for msg in messages:
                    logger.info(f"[{chat_id}] New message: {msg.get('content', {}).get('text')}")

                # Запоминаем последнее сообщение
                last_processed_msg[chat_id] = last_msg_id

        except Exception as e:
            logger.error(f"Worker error: {e}")

        # Пауза 1 секунда
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(message_polling_worker())