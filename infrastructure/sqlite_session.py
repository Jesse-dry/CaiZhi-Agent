"""
SQLite session store (placeholder).

Implements repositories/session_repo.py SessionRepository interface.
For FastAPI backend — persists LearningSession as JSON in SQLite.

Status: placeholder — implement during FastAPI migration.
"""

# TODO (FastAPI migration):
#   CREATE TABLE sessions (
#       session_id TEXT PRIMARY KEY,
#       user_id TEXT,
#       session_json TEXT NOT NULL,   -- LearningSession.model_dump_json()
#       version INTEGER DEFAULT 1,
#       created_at TEXT,
#       updated_at TEXT
#   );

from repositories.session_repo import SessionRepository
from schemas.learning_session import LearningSession, create_default_session


class SqliteSessionRepository(SessionRepository):
    """SQLite session store — placeholder implementation."""

    def __init__(self, db_path: str = "data/sessions.db"):
        self.db_path = db_path

    def get_session(self, user_id: str) -> LearningSession:
        # TODO: SELECT session_json FROM sessions WHERE user_id = ?
        return create_default_session(user_id=user_id)

    def save_session(self, session: LearningSession) -> None:
        # TODO: INSERT OR REPLACE INTO sessions ...
        pass

    def reset_session(self, user_id: str) -> LearningSession:
        # TODO: DELETE + INSERT default
        return create_default_session(user_id=user_id)

    def delete_session(self, user_id: str) -> None:
        # TODO: DELETE FROM sessions WHERE user_id = ?
        pass
