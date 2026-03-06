from loguru import logger
import sys
import os
from pathlib import Path
from app.include.config import config


BASE_DIR = Path(__file__).resolve().parents[2]  # project_root
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

logger.remove()  # убираем дефолтный логгер Loguru
logger.add(
    sys.stdout,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    level="DEBUG",
)

# В файл info.log
logger.add(
    LOG_DIR / "info.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    level="DEBUG",
    rotation="500 MB",
    retention="30 days",
    compression="zip",
    enqueue=True,
)
# при необходимости файл логов внутри контейнера
# logger.add("/app/logs/app.log", rotation="10 MB", level=LOG_LEVEL)