from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Table, Text, func
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from app.core.db.tables.meta import metadata

dialogs_table = Table(
    "dialogs",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("uuid", UUID(as_uuid=True), nullable=False, unique=True),
    Column("max_user_id", Integer, nullable=True),
    Column("question", Text, nullable=False),
    Column("answer", Text, nullable=True),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
)