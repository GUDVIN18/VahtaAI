from pydantic import BaseModel, Field
from dataclasses import dataclass
from typing import Any, Dict, List



class ResponseFormatAi(BaseModel):
    answer: str = Field(
        description="Краткий и Живой ответ на вопрос пользователя согласно инструкции"
    )

