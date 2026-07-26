"""
页面 2：错题诊断（Error Diagnosis）
学习闭环第 2 步：答疑 → 自测 → 诊断误区 → 苏格拉底引导

V2 (Phase 3)：使用 typed LearningSession 替代 st.session_state flat keys。
"""

import streamlit as st
from services.diagnosis_service import get_question_for_page, submit_answer_legacy as submit_answer
from schemas.diagnosis import DiagnosisResult
from utils.state import init_session_state, get_session, save_session, go_to

init_session_state()

st.title("🧩 错题诊断")

# ── 读取 session 中的 question_id ──
session = get_session()
question_id = session.current_question_id or "Q001"

question = get_question_for_page(question_id)

if question is None:
    st.error(f"未找到题目：{question_id}，请检查 data/questions.json")
    st.stop()

# ── 题目展示 ──
st.markdown("### 题目")
st.markdown(f"**{question['question']}**")
st.caption(f"编号：{question['question_id']} | 难度：{question.get('difficulty', '')}")

options = question["options"]

selected_option = st.radio(
    "请选择你的答案：",
    options=list(options.keys()),
    format_func=lambda key: f"{key}. {options[key]}",
    horizontal=True,
)

# ── 提交 ──
if st.button("提交答案", type="primary", use_container_width=True):
    result_dict = submit_answer(question_id, selected_option)

    # 写入 typed LearningSession
    session = get_session()
    session.diagnosis_result = DiagnosisResult(**result_dict)
    session.current_chain_id = result_dict.get("recommended_chain_id", "C001")
    session.current_socratic_id = result_dict.get("recommended_socratic_id", "S001")
    save_session(session)

    # 同步扁平 key（过渡期 compat）
    st.session_state["last_diagnosis"] = result_dict

# ── 诊断结果展示 ──
result = session.diagnosis_result

if result:
    st.divider()

    is_correct = result.is_correct
    if is_correct:
        st.success("✅ 回答正确！你已经掌握了这个知识点的核心因果链。")
    else:
        st.error(f"❌ 回答错误 —— 误区：{result.misconception}")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### 你的选择")
        st.markdown(f"**{result.selected_option}**. {options.get(result.selected_option, '')}")
    with col2:
        st.markdown("#### 正确答案")
        correct_opt = question.get("answer", "")
        st.markdown(f"**{correct_opt}**. {options.get(correct_opt, '')}")

    if not is_correct:
        with st.expander("🔍 详细诊断", expanded=True):
            if result.error_reason:
                st.markdown("**错误原因**")
                st.write(result.error_reason)
            if result.feedback:
                st.markdown("**针对性反馈**")
                st.info(result.feedback)
            if result.missing_concepts:
                st.markdown("**缺失知识点**")
                cols = st.columns(min(len(result.missing_concepts), 4))
                for i, concept in enumerate(result.missing_concepts):
                    with cols[i % len(cols)]:
                        st.warning(f"⚠️ {concept}")
            if result.remedial_path:
                st.markdown("**补救路径**")
                path_str = " → ".join(f"`{step}`" for step in result.remedial_path)
                st.markdown(path_str)

    with st.expander("📖 标准解释"):
        st.write(result.answer_explanation or "暂无")

    # ── 下一步 ──
    st.divider()
    st.markdown("### 下一步")

    col_a, col_b, col_c = st.columns(3)

    with col_a:
        if st.button(f"🦉 进入苏格拉底引导（{result.recommended_socratic_id or 'S001'}）", type="primary", use_container_width=True):
            st.session_state["socratic_history"] = []
            go_to("socratic")

    with col_b:
        if st.button("🔗 查看相关知识链", use_container_width=True):
            go_to("graph")

    with col_c:
        if st.button("🗺️ 生成学习路径", use_container_width=True):
            go_to("learning_path")
