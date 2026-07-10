import streamlit as st

st.set_page_config(
    page_title="RAG Debug",
    page_icon="🔎",
    layout="wide"
)

from utils.state import init_session_state
from services.rag_service import search_textbooks

init_session_state()

st.title("RAG Debug：教材检索测试")

query = st.text_input(
    "输入测试问题（中文或英文）",
    value="淬火为什么会提高钢的硬度？"
)

top_k_each = st.slider("每个语种返回片段数", 1, 10, 5)

if st.button("检索教材", type="primary"):
    results = search_textbooks(query=query, top_k_each=top_k_each)

    # 术语匹配
    matched_terms = results.get("matched_terms", [])
    if matched_terms:
        st.subheader("📖 匹配术语")
        term_cols = st.columns(min(len(matched_terms), 4))
        for idx, term in enumerate(matched_terms):
            with term_cols[idx % len(term_cols)]:
                st.info(f"{term.get('zh', '')} / {term.get('en', '')}")

    # 扩展查询
    with st.expander("🔍 术语扩展查询"):
        st.write("**中文查询**: ", results.get("zh_query", query))
        st.write("**英文查询**: ", results.get("en_query", query))

    # 中文教材检索结果
    st.subheader("🇨🇳 中文教材检索结果")

    zh_results = results.get("zh_contexts", [])
    if zh_results:
        for idx, item in enumerate(zh_results, start=1):
            meta = item.get("metadata", {})
            file_name = meta.get("file_name", "?")
            chapter = meta.get("chapter", "")
            section = meta.get("section", "")
            headers = meta.get("headers", {})

            # 构建章节显示
            chapter_str = " > ".join(
                v for v in [headers.get("h1"), headers.get("h2"), headers.get("h3")] if v
            ) or chapter or section or "无章节信息"

            with st.expander(
                f"{idx}. {file_name} | {chapter_str} | distance={item['distance']:.4f}"
            ):
                st.caption(f"章节: {chapter_str}")
                st.caption(f"doc_id: {meta.get('doc_id', '?')} | "
                          f"chunk_index: {meta.get('chunk_index', '?')}")
                st.write(item["text"])
    else:
        st.warning("中文教材检索无结果（可能向量库未构建）")

    # 英文教材检索结果
    st.subheader("🇺🇸 英文教材检索结果")

    en_results = results.get("en_contexts", [])
    if en_results:
        for idx, item in enumerate(en_results, start=1):
            meta = item.get("metadata", {})
            file_name = meta.get("file_name", "?")
            headers = meta.get("headers", {})

            chapter_str = " > ".join(
                v for v in [headers.get("h1"), headers.get("h2"), headers.get("h3")] if v
            ) or meta.get("chapter", "") or "No section info"

            with st.expander(
                f"{idx}. {file_name} | {chapter_str} | distance={item['distance']:.4f}"
            ):
                st.caption(f"Section: {chapter_str}")
                st.write(item["text"])
    else:
        st.warning("英文教材检索无结果（可能向量库未构建）")

    # 图片描述
    image_contexts = results.get("image_contexts", [])
    if image_contexts:
        st.subheader("🖼️ 相关图表描述")
        for idx, item in enumerate(image_contexts, start=1):
            meta = item.get("metadata", {})
            img_name = meta.get("image_name", "")
            img_path = meta.get("image_path", "")

            with st.expander(
                f"{idx}. {img_name} — 图表描述 | distance={item['distance']:.4f}"
            ):
                st.write(item["text"])
                if img_path:
                    st.caption(f"图片路径: {img_path}")
