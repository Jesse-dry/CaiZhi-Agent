from knowledge.terminology import search_terms
from knowledge.knowledge_graph import get_chain_by_id, format_chain_path


def answer_question(question: str):
    """
    最小 mock 版答疑服务。
    暂时不接大模型，只返回固定结构。
    """

    # 目前先固定匹配 C001，后面再根据问题自动匹配 chain_id
    chain_id = "C001"
    chain = get_chain_by_id(chain_id)
    graph_path = format_chain_path(chain_id)

    # 搜索相关术语
    related_terms = search_terms("淬火")

    terms_list = []
    for _, row in related_terms.iterrows():
        terms_list.append({
            "zh": row.get("zh", ""),
            "en": row.get("en", ""),
            "definition_zh": row.get("definition_zh", "")
        })

    return {
        "question": question,
        "brief_answer": "淬火通过快速冷却抑制碳原子扩散，使奥氏体转变为马氏体；马氏体产生晶格畸变，阻碍位错运动，因此提高钢的硬度。",
        "principle": chain.get("summary", "") if chain else "",
        "graph_path": graph_path,
        "terms": terms_list,
        "common_misconceptions": chain.get("common_misconceptions", []) if chain else [],
        "recommended_next": chain.get("recommended_next", []) if chain else []
    }