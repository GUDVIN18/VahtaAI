"""
new chat_id column
"""

from yoyo import step

__depends__ = {'20260306_02_hQ7Lx-create-vacancies-table'}

steps = [
    step("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS chat_id BIGINT
    """)
]
