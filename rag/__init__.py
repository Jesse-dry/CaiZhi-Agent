"""
rag/ — RAG 检索管线

PDF 解析 → 语义分块 → 向量库构建 → 双语检索。
不依赖 Streamlit，可被 services/ 和 api/ 直接调用。

核心入口：bilingual_retriever.BilingualRetriever
"""
