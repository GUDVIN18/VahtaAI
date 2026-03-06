from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, String, Table, Text, func
from sqlalchemy.dialects.postgresql import JSONB

from app.core.db.tables.meta import metadata

vacancies_table = Table(
    "vacancies",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("title", String(255), nullable=False),
    Column("description", Text, nullable=True),
    Column("location", String(255), nullable=True),
    Column("allowed_citizenships", JSONB, nullable=True),
    Column("min_age", Integer, nullable=True),
    Column("max_age", Integer, nullable=True),
    Column("requires_experience", Boolean, nullable=False, server_default="false"),
    Column("is_active", Boolean, nullable=False, server_default="true"),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
    Column("updated_at", DateTime, nullable=False, server_default=func.now()),
)
