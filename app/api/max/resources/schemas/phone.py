from pydantic import BaseModel, Field
from dataclasses import dataclass
from typing import Any, Dict, List



class StartOutreachRequest(BaseModel):
    phone: str = Field(
        ...,
        description="Номер телефона кандидата",
        examples=["+79998887766"],
    )