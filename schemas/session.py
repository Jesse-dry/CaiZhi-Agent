"""
[deprecated] Session — re-exports from schemas.learning_session.

Old path -> new path:
    AppSession           -> schemas.learning_session.LearningSession
    LearningLoopPhase    -> schemas.common.LearningStage
    create_default_session -> schemas.learning_session.create_default_session
    PAGE_ROUTES          -> schemas.learning_session.PAGE_ROUTES
"""

from schemas.learning_session import (
    LearningSession,
    create_default_session,
    reset_session,
    PAGE_ROUTES,
)
from schemas.common import LearningStage

# Backward-compat alias
AppSession = LearningSession
LearningLoopPhase = LearningStage

__all__ = [
    "AppSession",
    "LearningSession",
    "LearningLoopPhase",
    "LearningStage",
    "create_default_session",
    "reset_session",
    "PAGE_ROUTES",
]
