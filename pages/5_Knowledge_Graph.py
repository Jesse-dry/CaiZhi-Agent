# pages/5_knowledge graph.py

import streamlit as st
from utils.state import init_session_state, go_to
from knowledge.knowledge_graph import get_chain_by_id, format_chain_path

init_session_state()

st.set_page_config(
    page_title="知识图谱",
    page_icon="🕸️",
    layout="wide"
)

st.title("🕸️ 材料知识图谱")

chain_id = st.session_state.get("current_chain_id", "C001")

st.info(f"当前知识链：{chain_id}")

chain = get_chain_by_id(chain_id)

if chain is None:
    st.error("未找到对应知识链，请检查 data/knowledge_graph.json")
    st.stop()

st.subheader("一、图谱路径")
st.code(format_chain_path(chain_id))

st.subheader("二、因果链解释")
st.write(chain.get("summary", ""))

st.subheader("三、常见误区")
for item in chain.get("common_misconceptions", []):
    st.write(f"- {item}")

st.subheader("四、推荐下一步学习")
for item in chain.get("recommended_next", []):
    st.write(f"- {item}")

st.divider()

col1, col2, col3 = st.columns(3)

with col1:
    if st.button("返回智能答疑"):
        go_to("answering")

with col2:
    if st.button("进入苏格拉底引导"):
        st.session_state["current_socratic_id"] = "S001"
        go_to("socratic")

with col3:
    if st.button("生成学习路径"):
        go_to("learning_path")
# TODO: 接入 knowledge/knowledge_graph.py，可视化展示节点和边
# from knowledge.knowledge_graph import load_knowledge_graph
# graph = load_knowledge_graph()
