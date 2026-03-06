"""
create vacancies table and seed base data
"""

from yoyo import step

__depends__ = {"20260303_01_AcHi4-dialogs-table"}

steps = [
    step(
        """
        CREATE TABLE IF NOT EXISTS vacancies (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            description TEXT,
            location VARCHAR(255),
            allowed_citizenships JSONB,
            min_age INTEGER,
            max_age INTEGER,
            requires_experience BOOLEAN NOT NULL DEFAULT FALSE,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """
    )
]
