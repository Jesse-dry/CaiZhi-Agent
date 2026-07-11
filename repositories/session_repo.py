"""
Session persistence interface.

Defines the abstract capability for loading / saving / resetting
LearningSession objects. Implementations in infrastructure/:
    - MemorySessionRepository (in-memory, for Streamlit & testing)
    - SqliteSessionRepository (SQLite, for FastAPI — placeholder)
"""

from abc import ABC, abstractmethod
from schemas.learning_session import LearningSession


class SessionRepository(ABC):
    """Abstract session store for the learning loop."""

    @abstractmethod
    def get_session(self, user_id: str) -> LearningSession:
        """Load session by user_id, or create default if not found."""
        ...

    @abstractmethod
    def save_session(self, session: LearningSession) -> None:
        """Persist a session."""
        ...

    @abstractmethod
    def reset_session(self, user_id: str) -> LearningSession:
        """Reset session to initial state, preserving user_id."""
        ...

    @abstractmethod
    def delete_session(self, user_id: str) -> None:
        """Delete a session permanently."""
        ...
