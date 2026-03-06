"""
dialogs-table
"""

from yoyo import step

__depends__ = {'20260225_01_26ZKd-create-users-table'}

steps = [
    step("""
        CREATE TABLE IF NOT EXISTS dialogs (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            uuid UUID NOT NULL UNIQUE,
            user_id INTEGER,
            question TEXT NOT NULL,
            answer TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
""")
]