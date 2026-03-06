from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import FileResponse
from fastapi_restful.cbv import cbv
import uuid
from app.include.config import config
from app.include.logging_config import logger as log
from .resources.schemas.vahta import ResponseFormatAi
from .resources.service import AIModule
from databases.core import Connection
from app.core.db.connection import db_pool


router = APIRouter(prefix="/ai", tags=["Module AI"])

@cbv(router)
class AiRouter:
    conn: Connection = Depends(db_pool.get_connection)

    @router.post(
        "/llm/generate_message",
        response_model=ResponseFormatAi,
        name="Ответ на вопрос пользователя с помощью ИИ",
        description="Yandex-GPT-5.1 на системной инструкции ВАХТА",
    )
    async def llm_send_messages(
        self,
        max_user_id: int,
        question: str
    ):
        response: ResponseFormatAi = await AIModule.generate_text_pipe(
            conn=self.conn,
            max_user_id=max_user_id,
            message=question
        )
        return response


    @router.post(
        "/tts/generate_voice",
        name="Преобразование текста в голлос",
        description="Преобразование текста в голосовой файл",
    )
    async def create_voice_file(text: str):

        file_path = await AIModule.text_to_voice_pipe(text)

        path = Path(file_path)

        if not path.exists():
            raise HTTPException(status_code=404, detail="Файл не найден")

        return FileResponse(
            path=path,
            media_type="audio/ogg",
            filename=path.name,  # имя для скачивания
        )

    @router.post(
        "/asr/create_text_on_voice",
        name="Преобразование голоса в текст",
        description="Преобразование аудио в текст ",
    )
    async def create_text_on_voice(
        audio: UploadFile = File(...)
    ):
        file_extension = Path(audio.filename).suffix or ".ogg"
        filename = f"upload_{uuid.uuid4().hex}{file_extension}"
        file_path = f"app/api/vahta_ai/voice/upload/{filename}"

        with open(file_path, "wb") as buffer:
            content = await audio.read()
            buffer.write(content)
        response = await AIModule.voice_to_text_pipe(audio_file_path=file_path)
        return response
