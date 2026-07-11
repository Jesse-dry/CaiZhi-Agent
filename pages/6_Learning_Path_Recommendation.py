"""
页面 6：学习路径推荐（Learning Path Recommendation）
学习闭环第 5 步：费曼评价 → 学习路径 → 回到答疑形成闭环

聚合错题诊断 + 苏格拉底引导 + 费曼评价的薄弱点 → 知识单元映射 → 先修排序。
"""

import streamlit as st
from utils.state import init_session_state, go_to
from services.recommendation_service import generate_learning_path, KNOWLEDGE_UNITS

init_session_state()

st.title("🧭 个性化学习路径")

# ── 读取三个来源 ──
diagnosis_result = st.session_state.get("last_diagnosis")
socratic_result = st.session_state.get("last_socratic_result")
feynman_result = st.session_state.get("last_feynman_result")

has_any_result = any([diagnosis_result, socratic_result, feynman_result])

if not has_any_result:
    st.warning("当前还没有完成任何学习环节。系统将展示默认学习路径。")

# ── 生成路径 ──
learning_path = generate_learning_path(
    diagnosis_result=diagnosis_result,
    socratic_result=socratic_result,
    feynman_result=feynman_result,
)

st.session_state["last_learning_path"] = learning_path

# ═══════════════════════════════════
# 一、当前水平
# ═══════════════════════════════════
st.markdown("### 一、当前掌握水平")

level = learning_path.get("current_level", "")
level_emoji = {
    "已掌握": "🟢",
    "基本掌握": "🟡",
    "部分掌握": "🟠",
    "需要加强": "🔴",
}
st.markdown(f"## {level_emoji.get(level, '📊')} {level}")

# ═══════════════════════════════════
# 二、薄弱点来源
# ═══════════════════════════════════
st.markdown("### 二、识别出的薄弱知识点")

weak_points = learning_path.get("weak_points", [])
if weak_points:
    # 追溯来源
    source_map: dict[str, list[str]] = {}
    if diagnosis_result:
        for pt in diagnosis_result.get("missing_concepts", []):
            source_map.setdefault(pt, []).append("错题诊断")
    if socratic_result:
        for pt in socratic_result.get("remaining_weak_points", []):
            source_map.setdefault(pt, []).append("苏格拉底引导")
    if feynman_result:
        for pt in feynman_result.get("missing_points", []):
            source_map.setdefault(pt, []).append("费曼评价")

    for pt in weak_points:
        sources = source_map.get(pt, ["系统默认"])
        src_tags = " · ".join(sources)
        st.markdown(f"- 🔍 **{pt}**（来自：{src_tags}）")
else:
    st.success("未发现明显薄弱点，继续保持！")

# ═══════════════════════════════════
# 三、推荐学习路径
# ═══════════════════════════════════
st.markdown("### 三、推荐学习路径")

steps = learning_path.get("recommended_steps", [])
if steps:
    for step in steps:
        order = step.get("order", "?")
        kid = step.get("knowledge_id", "")
        reason = step.get("reason", "")
        title = step.get("title", kid)
        unit = KNOWLEDGE_UNITS.get(kid, {})

        with st.expander(
            f"Step {order}：{title}（{kid}）",
            expanded=(order == 1),
        ):
            st.markdown(f"**推荐原因**：{reason}")

            # 先修关系
            prereqs = unit.get("prerequisites", [])
            if prereqs:
                prereq_names = [
                    KNOWLEDGE_UNITS.get(p, {}).get("title", p)
                    for p in prereqs
                ]
                st.caption(f"📋 先修要求：{' → '.join(prereq_names)}")

            # 建议行动
            st.markdown("**建议行动**：")
            st.markdown(f"- 查看知识图谱中相关的因果链")
            st.markdown(f"- 用费曼法重新解释{title}")
            if unit.get("keywords"):
                st.markdown(f"- 重点关注术语：{'、'.join(unit['keywords'][:5])}")

else:
    st.info("暂无推荐步骤。")

# ═══════════════════════════════════
# 四、导航
# ═══════════════════════════════════
st.divider()
st.markdown("### 下一步行动")

col1, col2, col3 = st.columns(3)

with col1:
    if st.button("🔗 查看知识图谱", use_container_width=True):
        go_to("graph")

with col2:
    if st.button("🦉 重新进行苏格拉底引导", use_container_width=True):
        st.session_state["socratic_history"] = []
        # 默认使用 S001
        st.session_state["current_socratic_id"] = "S001"
        go_to("socratic")

with col3:
    if st.button("💬 回到智能答疑", use_container_width=True):
        go_to("answering")

# ── 闭环提示 ──
if has_any_result:
    st.success(
        "🔄 学习闭环：答疑 → 诊断 → 苏格拉底引导 → 费曼评价 → 学习路径 → 回到答疑。"
        "建议选择上方任一行动继续深入学习。"
    )
