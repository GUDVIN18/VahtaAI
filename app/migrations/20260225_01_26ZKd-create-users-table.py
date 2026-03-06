"""
create users table
"""

from yoyo import step

__depends__ = {}

steps = [
    step(
        """
        CREATE TABLE IF NOT EXISTS users (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_uuid UUID NOT NULL UNIQUE,
            full_name VARCHAR(255) NOT NULL,
            age INTEGER,
            citizenship VARCHAR(120),
            current_location VARCHAR(255),
            experience TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS user_states (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id INTEGER,
            source VARCHAR(50) NOT NULL,
            used_voice_messages JSONB,
            funnel_stage VARCHAR(120),
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            
        );
        """
    )
]
