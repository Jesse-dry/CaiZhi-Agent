"""
页面 6：学习路径推荐（Learning Path Recommendation）
学习闭环第 5 步：费曼评价 → 学习路径 → 回到答疑形成闭环

V2 (Phase 3)：使用 typed LearningSession 替代 st.session_state flat keys。
"""

import streamlit as st
from utils.state import init_session_state, get_session, save_session, go_to
from services.recommendation_service import generate_learning_path_legacy as generate_learning_path, KNOWLEDGE_UNITS
from schemas.recommendation import LearningPathResult

init_session_state()

st.title("🧭 个性化学习路径")

# ── 从 typed session 读取三个来源的结果 ──
session = get_session()
diagnosis_dict = session.diagnosis_result.model_dump() if session.diagnosis_result else None
socratic_dict = session.socratic_result.model_dump() if session.socratic_result else None
feynman_dict = session.feynman_result.model_dump() if session.feynman_result else None

has_any_result = any([diagnosis_dict, socratic_dict, feynman_dict])

if not has_any_result:
    st.warning("当前还没有完成任何学习环节。系统将展示默认学习路径。")

# ── 生成路径（使用 legacy wrapper，返回 dict） ──
learning_path = generate_learning_path(
    diagnosis_result=diagnosis_dict,
    socratic_result=socratic_dict,
    feynman_result=feynman_dict,
)

# 写入 typed session
session.recommendation_result = LearningPathResult(
    current_level=learning_path.get("current_level", "需要加强"),
    weak_points=learning_path.get("weak_points", []),
    recommended_steps=learning_path.get("recommended_steps", []),
    total_weak_points=len(learning_path.get("weak_points", [])),
    total_recommended_steps=len(learning_path.get("recommended_steps", [])),
)
save_session(session)

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
    source_map: dict[str, list[str]] = {}
    if diagnosis_dict:
        for pt in diagnosis_dict.get("missing_concepts", []):
            source_map.setdefault(pt, []).append("错题诊断")
    if socratic_dict:
        for pt in socratic_dict.get("remaining_weak_points", []):
            source_map.setdefault(pt, []).append("苏格拉底引导")
    if feynman_dict:
        for pt in feynman_dict.get("missing_points", []):
            source_map.setdefault(pt, []).append("费曼评价")

    for pt in weak_points:
        sources = source_map.get(str(pt), ["系统默认"])
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

        with st.expander(f"Step {order}：{title}（{kid}）", expanded=(order == 1)):
            st.markdown(f"**推荐原因**：{reason}")
            prereqs = unit.get("prerequisites", [])
            if prereqs:
                prereq_names = [
                    KNOWLEDGE_UNITS.get(p, {}).get("title", p) for p in prereqs
                ]
                st.caption(f"📋 先修要求：{' → '.join(prereq_names)}")
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
        if "ui_input_cache" in st.session_state:
            st.session_state["ui_input_cache"].pop("socratic", None)
        st.session_state.pop("socratic_history", None)
        session = get_session()
        session.current_socratic_id = "S001"
        save_session(session)
        go_to("socratic")

with col3:
    if st.button("💬 回到智能答疑", use_container_width=True):
        go_to("answering")

if has_any_result:
    st.success(
        "🔄 学习闭环：答疑 → 诊断 → 苏格拉底引导 → 费曼评价 → 学习路径 → 回到答疑。"
        "建议选择上方任一行动继续深入学习。"
    )
