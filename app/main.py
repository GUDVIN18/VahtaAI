import uvicorn
from fastapi import FastAPI
from loguru import logger as log
from contextlib import asynccontextmanager
from starlette.middleware.cors import CORSMiddleware
from app.core.db.connection import db_pool

from app.api.router import main_router



@asynccontextmanager #асинхронный декоратор
async def lifespan(app: FastAPI):
    await db_pool.init_db()
    yield
    await db_pool.close_db()

app = FastAPI(
    title="Microservice Vahta-AI",
    version="0.1.0",
    openapi_tags=[{"name": "Vahta-ai", "description": "Vahta-ai API endpoints"}],
    lifespan=lifespan
)





app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(main_router)




if __name__ == "__main__":
    log.info("Starting debug uvicorn")
    uvicorn.run(
        "app.main:app",
        host='0.0.0.0',
        port=8081,
        reload=True,
        workers=1,
        log_level='debug',
    )
    log.info("Uvicorn stopped")
