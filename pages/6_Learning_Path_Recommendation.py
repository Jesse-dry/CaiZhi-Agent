# pages/6_Learning path recommendation.py

import streamlit as st

st.set_page_config(
    page_title="学习路径推荐",
    page_icon="🧭",
    layout="wide"
)

from utils.state import init_session_state, go_to
from services.recommendation_service import generate_learning_path

init_session_state()

st.title("🧭 学习路径推荐")

diagnosis_result = st.session_state.get("last_diagnosis")
feynman_result = st.session_state.get("last_feynman_result")

if diagnosis_result is None and feynman_result is None:
    st.warning("当前还没有错题诊断或费曼评价结果。系统将展示默认学习路径。")

learning_path = generate_learning_path(
    diagnosis_result=diagnosis_result,
    feynman_result=feynman_result
)

st.session_state["last_learning_path"] = learning_path

st.subheader("一、系统识别出的薄弱知识点")

for point in learning_path["weak_points"]:
    st.write(f"- {point}")

st.subheader("二、推荐学习路径")

for idx, step in enumerate(learning_path["learning_steps"], start=1):
    with st.expander(f"Step {idx}: {step['title']}", expanded=True):
        st.markdown("**推荐原因：**")
        st.write(step["reason"])

        st.markdown("**建议行动：**")
        st.write(step["action"])

st.subheader("三、下一步建议")

for mode in learning_path["next_modes"]:
    st.write(f"- {mode}")

st.divider()

col1, col2, col3 = st.columns(3)

with col1:
    if st.button("查看知识图谱"):
        go_to("graph")

with col2:
    if st.button("重新进行苏格拉底引导"):
        st.session_state["socratic_history"] = []
        go_to("socratic")

with col3:
    if st.button("回到智能答疑"):
        go_to("answering")
# TODO: 接入 services/recommendation_service.py
# from services.recommendation_service import get_recommended_path
# path = get_recommended_path(user_id=st.session_state.user_id)
