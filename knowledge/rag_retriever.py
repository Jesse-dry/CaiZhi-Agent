"""
知识检索入口（委托到 services/rag_service）。

保持向后兼容，所有旧代码无需改动。
"""

from services.rag_service import retrieve


# 如需直接使用完整的 search_textbooks：
# from services.rag_service import search_textbooks
