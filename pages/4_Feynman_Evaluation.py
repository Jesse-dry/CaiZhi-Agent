"""
页面 4：费曼学习法评价（Feynman Evaluation）
学习闭环第 4 步：苏格拉底引导 → 费曼评价 → 学习路径

V2 (Phase 3)：使用 typed LearningSession 替代 st.session_state flat keys。
"""

import streamlit as st
from utils.state import init_session_state, get_session, save_session, go_to
from services.feynman_service import load_feynman_rubric, evaluate_legacy as evaluate
from schemas.feynman import FeynmanResult

init_session_state()

st.title("🗣️ 费曼学习法评价")
st.caption("真正理解一个概念，就是能用自己的话把它讲清楚。")

# ── 读取 session 中的 feynman_id ──
session = get_session()
feynman_id = session.current_feynman_id or "F001"
rubric = load_feynman_rubric(feynman_id)

if rubric is None:
    st.error(f"未找到费曼评价标准：{feynman_id}")
    st.stop()

st.markdown("### 🎯 挑战")
st.info(rubric.get("prompt", "请用自己的话解释这个知识点。"))

with st.expander("📋 评分标准（6 个关键点）"):
    for item in rubric.get("checklist", []):
        st.markdown(f"- {item.get('point', '')}")

feynman_text = st.text_area(
    "请用你自己的话解释：",
    height=150,
    placeholder="试着像一个老师一样，给没学过材料学的同学讲清楚……",
)

if st.button("提交评价", type="primary", use_container_width=True):
    if not feynman_text.strip():
        st.warning("请先输入你的解释！")
    else:
        with st.spinner("🤖 AI 正在从五个维度评价你的解释..."):
            result_dict = evaluate(feynman_text, feynman_id)

        # 写入 typed LearningSession
        session = get_session()
        session.feynman_result = FeynmanResult(**result_dict)
        save_session(session)

        # 同步 flat key
        st.session_state["last_feynman_result"] = result_dict

# ── 评价结果展示 ──
result = session.feynman_result

if result:
    st.divider()
    st.markdown("### 📊 评价结果")

    total = result.total_score
    dims = result.dimension_scores

    st.markdown(f"## {total} / 78")
    color = "green" if total >= 60 else ("orange" if total >= 40 else "red")
    st.progress(total / 78)

    st.markdown("#### 维度评分")

    dim_labels = {
        "concept_accuracy": ("概念准确性", 18),
        "causal_completeness": ("因果链完整性", 20),
        "term_accuracy": ("术语规范性", 14),
        "clarity": ("表达清晰度", 16),
        "misconception_control": ("误区控制", 10),
    }

    for dim_key, (label, max_pts) in dim_labels.items():
        score = getattr(dims, dim_key, 0)
        pct = score / max_pts if max_pts > 0 else 0
        emoji = "🟢" if pct >= 0.8 else ("🟡" if pct >= 0.5 else "🔴")
        col1, col2 = st.columns([1, 4])
        with col1:
            st.markdown(f"{emoji} **{label}**")
        with col2:
            st.progress(pct, f"{score} / {max_pts}")

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**✅ 讲清楚的部分**")
        if result.covered_points:
            for pt in result.covered_points:
                st.markdown(f"- {pt}")
        else:
            st.markdown("（无）")
    with col_b:
        st.markdown("**❌ 缺失的部分**")
        if result.missing_points:
            for pt in result.missing_points:
                st.markdown(f"- {pt}")
        else:
            st.markdown("（无）")

    if result.incorrect_points:
        st.markdown("**⚠️ 表述有误的部分**")
        for pt in result.incorrect_points:
            st.warning(pt)

    with st.expander("📖 参考范例"):
        example = rubric.get("excellent_example", "")
        if example:
            st.markdown(example)

    if result.next_question:
        st.info(f"💡 **建议下一步思考**：{result.next_question}")

    st.divider()
    st.markdown("### 下一步")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🗺️ 生成个性化学习路径", type="primary", use_container_width=True):
            go_to("learning_path")
    with col2:
        if st.button("🔄 重新解释", use_container_width=True):
            session = get_session()
            session.feynman_result = None
            save_session(session)
            st.session_state.pop("last_feynman_result", None)
            st.rerun()
