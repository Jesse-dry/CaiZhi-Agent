import streamlit as st

from utils.state import init_session_state
from knowledge.rag_retriever import retrieve

init_session_state()

st.set_page_config(
    page_title="RAG Debug",
    page_icon="🔎",
    layout="wide"
)

st.title("🔎 RAG 检索调试")

query = st.text_input(
    "输入测试问题",
    value="淬火为什么会提高钢的硬度？"
)

top_k = st.slider("top_k", 1, 10, 3)

if st.button("开始检索", type="primary"):
    result = retrieve(query, top_k=top_k)

    st.subheader("中英文扩展查询")
    st.write("中文查询：", result.get("zh_query"))
    st.write("英文查询：", result.get("en_query"))

    st.subheader("匹配术语")
    st.dataframe(result.get("matched_terms", []), use_container_width=True)

    st.subheader("中文教材检索结果")
    for item in result.get("zh_contexts", []):
        with st.expander(
            f"{item['metadata'].get('source_file')} | p.{item['metadata'].get('page')} | distance={item.get('distance'):.4f}"
        ):
            st.write(item["text"])

    st.subheader("英文教材检索结果")
    for item in result.get("en_contexts", []):
        with st.expander(
            f"{item['metadata'].get('source_file')} | p.{item['metadata'].get('page')} | distance={item.get('distance'):.4f}"
        ):
            st.write(item["text"])
