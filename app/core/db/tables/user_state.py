from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Table, func
from sqlalchemy.dialects.postgresql import JSONB

from app.core.db.tables.meta import metadata

user_states_table = Table(
    "user_states",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("user_id", Integer, nullable=True),
    Column("source", String(50), nullable=False),
    Column("used_voice_messages", JSONB, nullable=True),
    Column("funnel_stage", String(120), nullable=True),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
    Column("updated_at", DateTime, nullable=False, server_default=func.now()),
)