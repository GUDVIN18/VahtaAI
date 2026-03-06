from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Table, Text, func
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from app.core.db.tables.meta import metadata

users_table = Table(
    "users",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("user_uuid", UUID(as_uuid=True), nullable=False, unique=True),
    Column("full_name", String(255), nullable=False),
    Column("age", Integer, nullable=True),
    Column("citizenship", String(120), nullable=True),
    Column("current_location", String(255), nullable=True),
    Column("experience", Text, nullable=True),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
    Column("updated_at", DateTime, nullable=False, server_default=func.now()),
)