import asyncio
from pymax import MaxClient
from pymax.types import User
from pymax.files import File
from pymax.static.enum import AttachType
from app.include.logging_config import logger as log
from .resources.service import download_voice
from app.core.db.connection import db_pool
from .resources.crud import MaxCRUD
from app.api.max.resources.schemas.states import UserState
from app.api.vahta_ai.graph import run_step_1, run_step_2
from app.api.vahta_ai.resources.service import AIModule
from app.api.vahta_ai.resources.redis_client import RedisClient
import random


client = MaxClient(
    phone="+79772810551",
    work_dir="./session_max/cache_2",
    reconnect=True,
)
processed_messages = set()


@client.on_start
async def on_start():
    print(f"Помощник запущен! ID: {client.me.id}")

@client.task(seconds=10)
async def unread_checker():
    await asyncio.sleep(random.randint(5, 15))

    for dialog in client.dialogs:
        if (
            dialog.id == 0
            or not dialog.last_message
            or dialog.last_message.sender == client.me.id
            or dialog.last_message.id in processed_messages
        ):
            continue

        try:
            async with db_pool.database.connection() as conn:
                crud = MaxCRUD(conn)
                last = dialog.last_message

                user_id = last.sender
                chat_id = dialog.id
                source = "max"

                phone = None
                full_name = None

                try:
                    user = await client.get_user(user_id)
                    phone = getattr(user, "phone", None)
                    full_name = getattr(user, "full_name", None)
                except Exception:
                    pass
                created = await crud.create_user(
                    max_user_id=user.id,
                    phone=phone,
                    source=source,
                    chat_id=dialog.id
                )

                if created:
                    # новый пользователь
                    await crud.create_or_update_user_state(
                        phone=phone,
                        source=source,
                        max_user_id=user.id,
                        state=UserState.GET_USER_INFO
                    )
                    log.info(f"Создали нового пользователя {user.id}")

                else:
                    log.info(f"Пользователь сущесвтует {user.id}")
                    pass

        except Exception as exc:
            log.warning(f"Cannot add contact {phone}: {exc}")
            continue

        last = dialog.last_message
        processed_messages.add(last.id)

        message_text = last.text or ""
        attachment_type: str | None = None

        if last.attaches:
            for attach in last.attaches:
                if attach.type == AttachType.AUDIO:
                    print(f"Получено аудио! в {dialog.id}")
                    log.info(f"{attach=}")
                    file_path = await download_voice(attach)
                    if file_path:
                        try:
                            message_text = await AIModule.voice_to_text_pipe(
                                audio_file_path=str(file_path)
                            )
                        except Exception as exc:
                            log.warning(f"ASR error: {exc}")
                            message_text = ""

                elif attach.type == AttachType.PHOTO:
                    attachment_type = "photo"

                elif attach.type == AttachType.FILE:
                    attachment_type = "file"

        log.debug(f"Текст сообщения: {message_text}")
        log.debug(f"Тип вложения: {attachment_type}")

        reply_text: str | None = None

        try:
            async with db_pool.database.connection() as conn:
                crud = MaxCRUD(conn)
                state_row = await crud.get_state_by_max_user_id(last.sender)

            if not state_row:
                log.info(f"State not found for max_user_id={last.sender}")
                continue

            stage = state_row.get("funnel_stage")

            if stage == UserState.GET_USER_INFO.value:
                step_1 = await asyncio.to_thread(
                    run_step_1,
                    str(last.sender),
                    message_text,
                )
                reply_text = step_1.reply

                if step_1.completed and step_1.funnel_state == UserState.STATE_STEP_1_DONE.value:
                    log.debug(f"---- {step_1=}")
                    async with db_pool.database.connection() as conn:
                        filtered_data = {
                            key: (value) 
                            for key, value in step_1.candidate.items()
                            if key not in ['reason_for_change', 'start_date', 'previous_job', 'city']
                        }
                        await MaxCRUD(conn).update(
                            max_user_id=last.sender,
                            **filtered_data
                        )

                        await MaxCRUD(conn).create_or_update_user_state(
                            state=UserState.STATE_STEP_2,
                            max_user_id=last.sender,
                        )
                        log.info(f"User {last.sender} step 1 complited")

            elif stage == UserState.STATE_STEP_2.value:
                step_2 = await asyncio.to_thread(
                    run_step_2,
                    str(last.sender),
                    message_text,
                    attachment_type,
                )
                reply_text = step_2.reply

                if step_2.completed and step_2.funnel_state == UserState.STATE_STEP_2_DONE.value:
                    async with db_pool.database.connection() as conn:
                        await MaxCRUD(conn).create_or_update_user_state(
                            state=UserState.STATE_STEP_3,
                            max_user_id=last.sender,
                        )
                        log.info(f"User {last.sender} step 2 completed")

            elif stage == UserState.STATE_STEP_3.value:
                user_info = ...
                # step_3 = await asyncio.to_thread(
                #     run_step_3,
                #     str(last.sender),
                #     message_text,
                #     user_info,
                # )
                reply_text = 'Ваша завявка...'
            else:
                log.info(f"Unsupported stage={stage} for max_user_id={last.sender}")

            if reply_text:
                user_history = RedisClient(session_id=str(last.sender)).get_session_history_v2()
                log.debug(f"{len(user_history)=}")
                if len(user_history) >= 4:
                    message_type = random.choices(
                        ['text', 'voice'],  # Список вариантов
                        weights=[0.85, 0.15],  # Соотношение 60% текст и 40% голос
                        k=1
                    )[0]
                else:
                    message_type = 'text'


                if message_type == 'text':
                    await client.send_message(
                        chat_id=dialog.id,
                        text=reply_text,
                        notify=True,
                    )
                elif message_type == 'voice':
                    voice_file_path = await AIModule.text_to_voice_pipe(reply_text)
                    await client.send_message(
                        chat_id=dialog.id,
                        text="",
                        attachment=File(path=str(voice_file_path)),
                        notify=True,
                    )
                log.info(f"Отправили {user.id=}: {message_type=} | {reply_text=}")

                # await client.send_message(
                #     chat_id=dialog.id,
                #     text=reply_text,
                #     notify=True,
                # )

        except Exception as exc:
            log.warning(f"Failed to process incoming message for dialog={dialog.id}: {exc}")

        await client.read_message(
            chat_id=dialog.id,
            message_id=last.id
        )


@client.task(seconds=10)
async def process_pending_outreach() -> None:
    await asyncio.sleep(random.randint(10, 35))
    async with db_pool.database.connection() as conn:
        states = await MaxCRUD(conn).get_pending_outreach(limit=20)

    for state in states:
        phone = state.get("phone")
        source = state.get("source")
        if not phone:
            continue

        try:
            user: User = await client.search_by_phone(phone)
            await client.add_contact(user.id)
            
            chat_id = client.get_chat_id(client.me.id, user.id)
            async with db_pool.database.connection() as conn:
                crud = MaxCRUD(conn)
                user_create = await crud.create_user(
                    max_user_id=user.id,
                    phone=phone,
                    source=source,
                    chat_id=chat_id
                )
                if user_create == False:
                    # значит он существует
                    pass
        except Exception as exc:
            log.warning(f"Cannot add contact {phone}: {exc}")
            continue

        async with db_pool.database.connection() as conn:
            await MaxCRUD(conn).create_or_update_user_state(
                phone=phone,
                source=source,
                max_user_id=user.id,
                state=UserState.GET_USER_INFO
            )
            log.info(f"Начали обработку пользователя")

        try:
            step_result = await asyncio.to_thread(run_step_1, str(user.id), "Начали")
            await client.send_message(
                chat_id=chat_id,
                text=step_result.reply,
                notify=True,
            )
        except Exception as exc:
            log.warning(f"Failed to send initial step_1 message for user={user.id}: {exc}")

async def _run_worker() -> None:
    await db_pool.init_db()
    try:
        await client.start()
    finally:
        await db_pool.close_db()


if __name__ == "__main__":
    asyncio.run(_run_worker())

