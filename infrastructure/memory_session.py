"""
In-memory session store.

Implements repositories/session_repo.py SessionRepository interface.
Used for Streamlit (current) and dev/testing.

Streamlit adapter:
    Pages use utils/state.py get_learning_session() / save_learning_session().
    These functions build/write LearningSession directly; they do NOT go
    through this repository. The sync_from_streamlit / sync_to_streamlit
    functions here are for transitional use only.

Future:
    infrastructure/sqlite_session.py provides SQLite persistence for FastAPI.
"""

from repositories.session_repo import SessionRepository
from schemas.learning_session import LearningSession, create_default_session


class MemorySessionRepository(SessionRepository):
    """
    In-memory dict-based session store.

    Usage:
        repo = MemorySessionRepository()
        session = repo.get_session("student_01")
        session.qa_result = result.model_dump()
        repo.save_session(session)
    """

    def __init__(self):
        self._store: dict[str, LearningSession] = {}

    def get_session(self, user_id: str) -> LearningSession:
        for s in self._store.values():
            if s.user_id == user_id:
                return s
        session = create_default_session(session_id=user_id, user_id=user_id)
        self._store[user_id] = session
        return session

    def save_session(self, session: LearningSession) -> None:
        session.touch()
        key = session.user_id or session.session_id
        self._store[key] = session

    def reset_session(self, user_id: str) -> LearningSession:
        session = create_default_session(session_id=user_id, user_id=user_id)
        self._store[user_id] = session
        return session

    def delete_session(self, user_id: str) -> None:
        self._store.pop(user_id, None)
