"""
页面 4：费曼学习法评价（Feynman Evaluation）
学习闭环第 4 步：苏格拉底引导 → 费曼评价 → 学习路径

学生用自己的话解释 → 五维度评分 → 暴露薄弱点 → 推荐下一步问题。
"""

import streamlit as st
from utils.state import init_session_state, go_to
from services.feynman_service import load_feynman_rubric, evaluate

init_session_state()

st.title("🗣️ 费曼学习法评价")
st.caption("真正理解一个概念，就是能用自己的话把它讲清楚。")

# ── 读取 feynman_id ──
feynman_id = st.session_state.get("current_feynman_id", "F001")
rubric = load_feynman_rubric(feynman_id)

if rubric is None:
    st.error(f"未找到费曼评价标准：{feynman_id}")
    st.stop()

# ── 题目提示 ──
st.markdown("### 🎯 挑战")
st.info(rubric.get("prompt", "请用自己的话解释这个知识点。"))

# ── 参考 checklist（可折叠） ──
with st.expander("📋 评分标准（6 个关键点）"):
    for item in rubric.get("checklist", []):
        st.markdown(f"- {item.get('point', '')}")

# ── 输入区域 ──
feynman_text = st.text_area(
    "请用你自己的话解释：",
    height=150,
    placeholder="试着像一个老师一样，给没学过材料学的同学讲清楚……",
)

# ── 提交 ──
if st.button("提交评价", type="primary", use_container_width=True):
    if not feynman_text.strip():
        st.warning("请先输入你的解释！")
    else:
        with st.spinner("🤖 AI 正在从五个维度评价你的解释..."):
            result = evaluate(feynman_text, feynman_id)

        st.session_state["last_feynman_result"] = result

# ── 评价结果展示 ──
feynman_result = st.session_state.get("last_feynman_result")

if feynman_result:
    st.divider()
    st.markdown("### 📊 评价结果")

    total = feynman_result.get("total_score", 0)
    dims = feynman_result.get("dimension_scores", {})

    # ── 总分 ──
    st.markdown(f"## {total} / 100")
    color = "green" if total >= 80 else ("orange" if total >= 60 else "red")
    st.progress(total / 100)

    # ── 五维度评分 ──
    st.markdown("#### 维度评分")

    dim_labels = {
        "concept_accuracy": ("概念准确性", 18),
        "causal_completeness": ("因果链完整性", 20),
        "term_accuracy": ("术语规范性", 14),
        "clarity": ("表达清晰度", 16),
        "misconception_control": ("误区控制", 10),
    }

    for dim_key, (label, max_pts) in dim_labels.items():
        score = dims.get(dim_key, 0)
        pct = score / max_pts if max_pts > 0 else 0
        emoji = "🟢" if pct >= 0.8 else ("🟡" if pct >= 0.5 else "🔴")
        col1, col2 = st.columns([1, 4])
        with col1:
            st.markdown(f"{emoji} **{label}**")
        with col2:
            st.progress(pct, f"{score} / {max_pts}")

    # ── 覆盖 / 缺失 ──
    covered = feynman_result.get("covered_points", [])
    missing = feynman_result.get("missing_points", [])
    incorrect = feynman_result.get("incorrect_points", [])

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**✅ 讲清楚的部分**")
        if covered:
            for pt in covered:
                st.markdown(f"- {pt}")
        else:
            st.markdown("（无）")
    with col_b:
        st.markdown("**❌ 缺失的部分**")
        if missing:
            for pt in missing:
                st.markdown(f"- {pt}")
        else:
            st.markdown("（无）")

    if incorrect:
        st.markdown("**⚠️ 表述有误的部分**")
        for pt in incorrect:
            st.warning(pt)

    # ── 优秀范例 ──
    with st.expander("📖 参考范例"):
        example = rubric.get("excellent_example", "")
        if example:
            st.markdown(example)

    # ── 推荐下一步问题 ──
    next_q = feynman_result.get("next_question", "")
    if next_q:
        st.info(f"💡 **建议下一步思考**：{next_q}")

    # ── 导航 ──
    st.divider()
    st.markdown("### 下一步")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🗺️ 生成个性化学习路径", type="primary", use_container_width=True):
            go_to("learning_path")
    with col2:
        if st.button("🔄 重新解释", use_container_width=True):
            st.session_state.pop("last_feynman_result", None)
            st.rerun()
