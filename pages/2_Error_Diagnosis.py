"""
页面 2：错题诊断（Error Diagnosis）
学习闭环第 2 步：答疑 → 自测 → 诊断误区 → 苏格拉底引导
"""

import streamlit as st
from services.diagnosis_service import get_question_for_page, submit_answer
from utils.state import init_session_state, go_to

init_session_state()

st.title("🧩 错题诊断")

# ── 读取上一页传递的 question_id ──
question_id = st.session_state.get("current_question_id", "Q001")

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
    result = submit_answer(question_id, selected_option)

    # 写入 session_state（指定 key 名）
    st.session_state["last_diagnosis"] = result
    st.session_state["current_chain_id"] = result.get("recommended_chain_id", "C001")
    st.session_state["current_socratic_id"] = result.get("recommended_socratic_id", "S001")

# ── 诊断结果展示 ──
result = st.session_state.get("last_diagnosis")

if result:
    st.divider()

    # 正误判断
    is_correct = result.get("is_correct", False)
    if is_correct:
        st.success("✅ 回答正确！你已经掌握了这个知识点的核心因果链。")
    else:
        st.error(f"❌ 回答错误 —— 误区：{result.get('misconception', '')}")

    # 选择 vs 正确答案
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### 你的选择")
        st.markdown(f"**{result['selected_option']}**. {options.get(result['selected_option'], '')}")
    with col2:
        st.markdown("#### 正确答案")
        correct_opt = question.get("answer", "")
        st.markdown(f"**{correct_opt}**. {options.get(correct_opt, '')}")

    # 详细诊断（仅错误时）
    if not is_correct:
        with st.expander("🔍 详细诊断", expanded=True):
            # 错误原因
            error_reason = result.get("error_reason", "")
            if error_reason:
                st.markdown("**错误原因**")
                st.write(error_reason)

            # 针对性反馈
            feedback = result.get("feedback", "")
            if feedback:
                st.markdown("**针对性反馈**")
                st.info(feedback)

            # 缺失知识点
            missing = result.get("missing_concepts", [])
            if missing:
                st.markdown("**缺失知识点**")
                cols = st.columns(min(len(missing), 4))
                for i, concept in enumerate(missing):
                    with cols[i % len(cols)]:
                        st.warning(f"⚠️ {concept}")

            # 补救路径
            remedial = result.get("remedial_path", [])
            if remedial:
                st.markdown("**补救路径**")
                path_str = " → ".join(f"`{step}`" for step in remedial)
                st.markdown(path_str)

    # 标准解释（始终展示）
    with st.expander("📖 标准解释"):
        st.write(result.get("answer_explanation", "暂无"))

    # ── 下一步：苏格拉底引导 ──
    st.divider()
    st.markdown("### 下一步")

    col_a, col_b, col_c = st.columns(3)

    socratic_id = result.get("recommended_socratic_id", "S001")

    with col_a:
        if st.button(f"🦉 进入苏格拉底引导（{socratic_id}）", type="primary", use_container_width=True):
            st.session_state["socratic_history"] = []
            go_to("socratic")

    with col_b:
        if st.button("🔗 查看相关知识链", use_container_width=True):
            go_to("graph")

    with col_c:
        if st.button("🗺️ 生成学习路径", use_container_width=True):
            go_to("learning_path")
