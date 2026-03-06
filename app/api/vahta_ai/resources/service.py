import os
import json
import uuid
import httpx
import asyncio
import traceback
from typing import List

from pathlib import Path
from dotenv import load_dotenv
from app.include.config import config
from databases.core import Connection
from .redis_client import RedisClient
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from .schemas.vahta import ResponseFormatAi
from app.include.logging_config import logger as log
from langchain_core.messages import (
    HumanMessage, 
    AIMessage, 
    SystemMessage
)
from .crud import AiCRUD

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_TARGET_MODEL = "qwen3-tts-vc-2026-01-22"
DEFAULT_PREFERRED_NAME = "guanyu"
DEFAULT_AUDIO_MIME_TYPE = "audio/mpeg"
VOICE_FILE_PATH = "app/api/vahta_ai/voice_custom/dmitriy.mp3"


try:
    SYSTEM_INSTRUCTION = (BASE_DIR / "context" / "2026-02-26-instruction.txt").read_text(encoding="utf-8")
except FileNotFoundError as e:
    log.error(f"Failed to load prompt templates: {e}")
    raise

class AIModule:
    @staticmethod
    async def generate_text_pipe(
        conn: Connection,
        user_id: int,
        message: str
    ) -> ResponseFormatAi:    
        try:
            dialog_id, dialog_uuid = await AiCRUD(conn=conn).create(
                user_id=user_id,
                question=message
            )
        except Exception as e:
            log.error(f"{user_id=}: Ошибка при создании записи: {e}")
            raise
        try:
            # Получаем историю
            current_history = RedisClient(
                session_id=f"{user_id}"
            ).get_session_history_v2()
            log.info(f"Успешно перешли к инициализации main_agent")
            agent = create_agent(
                model=ChatOpenAI(
                    api_key=f"{config.YANDEX_API_KEY}",
                    model=f"gpt://{config.FOLDER_LLM_YANDEX_ID}/yandexgpt-5-pro/latest",
                    base_url="https://ai.api.cloud.yandex.net/v1",
                    temperature=0.4,
                    top_p=0.95,
                ),
                system_prompt=SYSTEM_INSTRUCTION,
                response_format=ResponseFormatAi,
            )
            log.info(current_history)
            messages = [
                SystemMessage(content=f"Подбирай вакансию на основе данных кондидата. Внимательно изучай историю диалога перед ответом"),
                *current_history,
                HumanMessage(content=message)
            ]
            response = await agent.ainvoke({
                "messages": messages,
            })
            response: ResponseFormatAi=response['structured_response']

            RedisClient(
                session_id=f"{user_id}"
            ).add_message(
                role="user",
                message=message
            )
            
            RedisClient(
                session_id=f"{user_id}"
            ).add_message(
                role="ai",
                message=response.answer
            )

            try:
                await AiCRUD(conn=conn).update(
                    record_id=dialog_id,
                    record_uuid=dialog_uuid,
                    answer=response.answer
                )
            except Exception as e:
                log.error(f"{user_id=}: Ошибка при обновлении диалога {e}")

            try:
                log.success(f"{response} \n\n")
                # log.success(f"{response.choices[0].message.content} ")
                return ResponseFormatAi(answer=response.answer)
            except json.JSONDecodeError as e:
                log.warning(f" JSON parsing failed: {e} — retrying...")
                return

        except Exception as e:
            log.warning(f"QWEN generation failed: {e}")


    @staticmethod
    async def text_to_voice_pipe(
        text: str,
        voice: str = "zahar",
        lang: str = "ru-RU",
    ):
            file_path = Path(f"app/api/vahta_ai/voice/speech/speech_{uuid.uuid4().hex}.ogg")
            headers = {
                "Authorization": f"Api-Key {config.YANDEX_SERVICE_ACCOUNT_API}",
            }
            data = {
                "text": text,
                "lang": lang,
                "voice": voice,
                "folderId": config.FOLDER_TTS_YANDEX_ID,
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                try:
                    response = await client.post(
                        "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize",
                        headers=headers,
                        data=data,
                    )

                except httpx.HTTPStatusError as e:
                    raise RuntimeError(
                        f"TTS HTTP error {e.response.status_code}: {e.response.text}"
                    )
                except httpx.RequestError as e:
                    raise RuntimeError(f"TTS request failed: {str(e)}")
                
                file_path.write_bytes(response.content)
                log.info(f"{response.status_code}: генерация голоса прошла успешно")
            return str(file_path)
            
    @staticmethod
    async def voice_to_text_pipe(
        audio_file_path: str,
        lang: str = "ru-RU",
    ):
            headers = {
                "Authorization": f"Api-Key {config.YANDEX_SERVICE_ACCOUNT_API}",
            }
            audio_bytes = Path(audio_file_path).read_bytes()
            async with httpx.AsyncClient(timeout=30.0) as client:
                try:
                    response = await client.post(
                        f"https://stt.api.cloud.yandex.net/speech/v1/stt:recognize?folderId={config.FOLDER_TTS_YANDEX_ID}&lang={lang}",
                        headers=headers,
                        content=audio_bytes,
                    )
                except httpx.HTTPStatusError as e:
                    raise RuntimeError(
                        f"TTS HTTP error {e.response.status_code}: {e.response.text}"
                    )
                except httpx.RequestError as e:
                    raise RuntimeError(f"TTS request failed: {str(e)}")
            data=response.json()
            log.info(f"{response}: генерация текста из голоса прошла успешно")
            return data['result']



if __name__ == '__main__':
    asyncio.run(AIModule.voice_to_text_pipe(audio_file_path="/vahta-ai/app/api/vahta_ai/voice/speech/speech_2062a9246409474fa157c122fb11970f.ogg"))
