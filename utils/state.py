# utils/state.py

import streamlit as st


PAGES = {
    "answering": "pages/1_Smart_Answering.py",
    "diagnosis": "pages/2_Error_Diagnosis.py",
    "socratic": "pages/3_Socratic_Guidance.py",
    "feynman": "pages/4_Feynman_Evaluation.py",
    "graph": "pages/5_Knowledge_Graph.py",
    "learning_path": "pages/6_Learning_Path_Recommendation.py",
    "debug": "pages/7_Debug.py",
    "rag_debug": "pages/8_RAG_Debug.py",
}


DEFAULT_STATE = {
    "user_id": "student_test_01",

    # 当前上下文 ID 指针
    "current_knowledge_id": "K001",
    "current_question_id": "Q001",
    "current_chain_id": "C001",
    "current_socratic_id": "S001",
    "current_feynman_id": "F001",

    # 各阶段最新结果
    "last_qa_result": None,
    "last_diagnosis": None,
    "last_socratic_result": None,
    "last_feynman_result": None,
    "last_learning_path": None,

    # 聊天历史
    "qa_messages": [],
    "socratic_history": [],
}


def init_session_state():
    """
    初始化跨页面共享状态。
    每个页面开头都调用一次。
    """
    for key, value in DEFAULT_STATE.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_demo_state():
    """
    重置整个 Demo 流程。
    """
    for key, value in DEFAULT_STATE.items():
        st.session_state[key] = value


def go_to(page_key: str):
    """
    页面跳转。
    page_key 必须是 PAGES 里的 key。
    """
    st.switch_page(PAGES[page_key])