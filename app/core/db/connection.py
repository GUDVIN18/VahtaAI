from databases import Database
from app.include.config import config
import traceback
from typing import AsyncGenerator
from databases.core import Connection
from loguru import logger as log

# log = logging.getLogger(__name__)


class DBConnPool:
    db_conn = None

    async def init_db(self):
        log.debug("init_db")
        try:
            self.db_conn = Database(
                url=config.database_url,
                min_size=5,
                max_size=25,
            )
            await self.db_conn.connect()
        except Exception as e:
            log.error(f"(init_db) database not available! Exception: {repr(e)}, {traceback.format_exc()}")
            raise

    @property #позволяет обращаться к методу как к полю
    def database(self):
        return self.db_conn

    async def close_db(self):
        try:
            log.info(f"(close_db) Close pool...")
            await self.db_conn.disconnect()
        except Exception as e:
            log.error(f"(close_db) Exception: {repr(e)}, {traceback.format_exc()}")
            raise

    async def get_connection(self) -> AsyncGenerator[Connection, None]:
        async with self.db_conn.connection() as connection:
            yield connection



db_pool = DBConnPool()