import streamlit as st
from knowledge.terminology import load_terms
from knowledge.knowledge_graph import load_knowledge_graph, format_chain_path

st.set_page_config(
    page_title="知识库调试",
    page_icon="🧪",
    layout="wide"
)

st.title("🧪 知识库调试页面")

st.subheader("1. 术语表 terms.csv")

try:
    terms_df = load_terms()
    st.success(f"terms.csv 读取成功，共 {len(terms_df)} 条术语。")
    st.dataframe(terms_df, use_container_width=True)
except Exception as e:
    st.error("terms.csv 读取失败")
    st.exception(e)


st.subheader("2. 知识图谱 knowledge_graph.json")

try:
    graph = load_knowledge_graph()
    st.success("knowledge_graph.json 读取成功。")

    st.write("节点数量：", len(graph.get("nodes", [])))
    st.write("关系数量：", len(graph.get("edges", [])))
    st.write("因果链数量：", len(graph.get("chains", [])))

    st.markdown("#### C001 因果链展示")
    st.code(format_chain_path("C001"))

except Exception as e:
    st.error("knowledge_graph.json 读取失败")
    st.exception(e)