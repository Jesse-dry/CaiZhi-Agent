"""
utils/state.py — Streamlit session state adapter.

Bridges Streamlit's st.session_state (local UI cache) and the canonical
LearningSession model (schemas/learning_session.py).

Architecture:
    pages/ -> utils/state.py (adapter) -> schemas/learning_session.py (authority)
    pages/ -> services/ -> schemas/qa.py, diagnosis.py, ... (pure data)

Key rule:
    services/, workflows/, rag/, agents/ NEVER import this module.
    They work with LearningSession directly, not st.session_state.
"""

import streamlit as st

from schemas.learning_session import (
    PAGE_ROUTES,
    LearningSession,
    create_default_session,
)
from schemas.common import LearningStage


# ================================================================
# Page routes (Streamlit-specific)
# ================================================================

PAGES = PAGE_ROUTES


# ================================================================
# Legacy flat keys — kept for backward compat with existing pages
# ================================================================

_LEGACY_DEFAULTS: dict[str, object] = {
    "user_id": "student_test_01",
    "current_knowledge_id": "K001",
    "current_question_id": "Q001",
    "current_chain_id": "C001",
    "current_socratic_id": "S001",
    "current_feynman_id": "F001",
    "current_phase": LearningStage.QA.value,
    "last_user_question": "",
    "last_answer": None,
    "last_qa_result": None,
    "last_diagnosis": None,
    "last_socratic_result": None,
    "last_feynman_result": None,
    "last_learning_path": None,
    "qa_messages": [],
    "socratic_history": [],
}


# ================================================================
# Session state init
# ================================================================

def init_session_state():
    """
    Initialise cross-page state. Call once at the top of every page.

    The canonical session is stored as st.session_state["learning_session"]
    (a plain dict from LearningSession.model_dump()). Legacy flat keys
    are filled for backward compat with existing pages.
    """
    # Canonical session object (as dict cache)
    if "learning_session" not in st.session_state:
        session = create_default_session()
        st.session_state["learning_session"] = session.model_dump()

    # Legacy flat keys (pages still read them directly)
    for key, value in _LEGACY_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_demo_state():
    """Reset the entire demo flow to defaults."""
    session = create_default_session()
    st.session_state["learning_session"] = session.model_dump()
    for key, value in _LEGACY_DEFAULTS.items():
        st.session_state[key] = value


def go_to(page_key: str):
    """Navigate to a Streamlit page. page_key must be a key in PAGES."""
    st.switch_page(PAGES[page_key])


# ================================================================
# LearningSession access (the canonical API)
# ================================================================

def get_learning_session() -> LearningSession:
    """
    Build a LearningSession from the st.session_state cache.

    Pages call this before passing the session to services.
    Services return results; pages write them back via save_learning_session().
    """
    data = st.session_state.get("learning_session")
    if data is None:
        return create_default_session()
    return LearningSession(**data)


def save_learning_session(session: LearningSession) -> None:
    """
    Write a LearningSession back to the st.session_state cache.

    Also updates legacy flat keys so existing pages can still read
    st.session_state["last_qa_result"] etc. directly.
    """
    session.touch()
    data = session.model_dump()

    # Update canonical cache
    st.session_state["learning_session"] = data

    # Sync legacy flat keys for backward compat
    _sync_legacy_keys(data)


def _sync_legacy_keys(data: dict) -> None:
    """Map LearningSession fields back to legacy flat keys."""
    # Stage
    if "current_stage" in data:
        st.session_state["current_phase"] = data["current_stage"]

    # Context pointers
    for key in (
        "current_knowledge_id", "current_question_id", "current_chain_id",
        "current_socratic_id", "current_feynman_id",
    ):
        if key in data:
            st.session_state[key] = data[key]

    # Results (old names <- new names)
    _map_result(data, "qa_result", "last_qa_result")
    _map_result(data, "diagnosis_result", "last_diagnosis")
    _map_result(data, "socratic_result", "last_socratic_result")
    _map_result(data, "feynman_result", "last_feynman_result")
    _map_result(data, "recommendation_result", "last_learning_path")

    if "user_id" in data:
        st.session_state["user_id"] = data["user_id"]


def _map_result(data: dict, new_key: str, old_key: str) -> None:
    if new_key in data:
        st.session_state[old_key] = data[new_key]


# ================================================================
# Deprecated aliases (remove once pages migrate to new names)
# ================================================================

def get_app_session() -> LearningSession:
    """[deprecated] Use get_learning_session() instead."""
    return get_learning_session()


def set_app_session(session: LearningSession) -> None:
    """[deprecated] Use save_learning_session() instead."""
    save_learning_session(session)
