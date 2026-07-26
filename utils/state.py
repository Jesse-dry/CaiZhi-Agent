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

V2 (Phase 3): st.session_state 精简为 3 个 key:
    - session_id
    - current_page
    - ui_input_cache
    所有业务状态从 typed LearningSession 存取。
"""

import streamlit as st

from schemas.learning_session import (
    PAGE_ROUTES,
    LearningSession,
    create_default_session,
    SessionSummary,
)
from schemas.common import LearningStage


# ================================================================
# Page routes (Streamlit-specific)
# ================================================================

PAGES = PAGE_ROUTES


# ================================================================
# V2 精简 API — 推荐使用
# ================================================================

def init_session() -> LearningSession:
    """
    V2 精简初始化。只创建 typed LearningSession 缓存在 st.session_state。

    st.session_state 布局:
        "learning_session" — typed LearningSession 的 model_dump() 字典
        "session_id"       — 当前 session ID
        "current_page"     — 当前所在页面标识
        "ui_input_cache"   — 页面特定的 UI 临时状态（如 socratic 步骤计数器）
    """
    if "learning_session" not in st.session_state:
        session = create_default_session()
        st.session_state["learning_session"] = session.model_dump()

    for key, default in [
        ("session_id", "default"),
        ("current_page", "qa"),
        ("ui_input_cache", {}),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    return _build_session()


def get_session() -> LearningSession:
    """
    V2 获取 typed LearningSession。推荐所有新页面使用。

    如果 learning_session 不存在则自动初始化。
    """
    if "learning_session" not in st.session_state:
        return init_session()
    return _build_session()


def save_session(session: LearningSession) -> None:
    """
    V2 保存 typed LearningSession 到 st.session_state 缓存。

    同时同步 session_id 和 current_page。
    """
    session.touch()
    st.session_state["learning_session"] = session.model_dump()
    st.session_state["session_id"] = session.session_id


def _build_session() -> LearningSession:
    """从 st.session_state 缓存重建 typed LearningSession"""
    data = st.session_state.get("learning_session")
    if data is None:
        return create_default_session()
    return LearningSession(**data)


# ================================================================
# V1 兼容 API — deprecated，Phase 4 移除
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


def init_session_state():
    """
    [deprecated] V1 旧版初始化。请使用 init_session()。

    同时初始化 typed LearningSession 和 legacy flat keys。
    """
    # Canonical session
    if "learning_session" not in st.session_state:
        session = create_default_session()
        st.session_state["learning_session"] = session.model_dump()

    # V2 keys
    for key, default in [
        ("session_id", "default"),
        ("current_page", "qa"),
        ("ui_input_cache", {}),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    # Legacy flat keys
    for key, value in _LEGACY_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_demo_state():
    """Reset the entire demo flow to defaults."""
    session = create_default_session()
    st.session_state["learning_session"] = session.model_dump()
    st.session_state["session_id"] = "default"
    st.session_state["current_page"] = "qa"
    st.session_state["ui_input_cache"] = {}
    for key, value in _LEGACY_DEFAULTS.items():
        st.session_state[key] = value


def go_to(page_key: str):
    """Navigate to a Streamlit page. page_key must be a key in PAGES."""
    st.session_state["current_page"] = page_key
    st.switch_page(PAGES[page_key])


# ================================================================
# LearningSession access (the canonical API, V1+V2 compatible)
# ================================================================

def get_learning_session() -> LearningSession:
    """
    Build a typed LearningSession from the st.session_state cache.

    Pydantic v2 auto-coerces nested dicts to typed models (QAResult etc.).
    """
    data = st.session_state.get("learning_session")
    if data is None:
        return create_default_session()
    return LearningSession(**data)


def save_learning_session(session: LearningSession) -> None:
    """
    Write a typed LearningSession back to st.session_state.

    Also syncs legacy flat keys for V1 page backward compat.
    """
    session.touch()
    data = session.model_dump()
    st.session_state["learning_session"] = data
    st.session_state["session_id"] = session.session_id
    _sync_legacy_keys(data)


def _sync_legacy_keys(data: dict) -> None:
    """[deprecated] Map LearningSession fields to legacy flat keys."""
    if "current_stage" in data:
        st.session_state["current_phase"] = data["current_stage"]
    for key in (
        "current_knowledge_id", "current_question_id", "current_chain_id",
        "current_socratic_id", "current_feynman_id",
    ):
        if key in data and data[key] is not None:
            st.session_state[key] = data[key]
    _map_result(data, "qa_result", "last_qa_result")
    _map_result(data, "diagnosis_result", "last_diagnosis")
    _map_result(data, "socratic_result", "last_socratic_result")
    _map_result(data, "feynman_result", "last_feynman_result")
    _map_result(data, "recommendation_result", "last_learning_path")
    if "student_id" in data:
        st.session_state["user_id"] = data["student_id"]
    elif "user_id" in data:
        st.session_state["user_id"] = data["user_id"]


def _map_result(data: dict, new_key: str, old_key: str) -> None:
    if new_key in data:
        st.session_state[old_key] = data[new_key]


# ================================================================
# Deprecated aliases (Phase 4 移除)
# ================================================================

def get_app_session() -> LearningSession:
    """[deprecated] Use get_learning_session() instead."""
    return get_learning_session()


def set_app_session(session: LearningSession) -> None:
    """[deprecated] Use save_learning_session() instead."""
    save_learning_session(session)
