from knowledge.rag_retriever import retrieve
from knowledge.knowledge_graph import match_chain
from knowledge.prompt_builder import build_rag_qa_prompt


def answer_question(question: str):
    rag_result = retrieve(question, top_k=3)
    graph_chain = match_chain(question)

    prompt = build_rag_qa_prompt(
        query=question,
        rag_result=rag_result,
        graph_chain=graph_chain
    )

    # 第一阶段可以先不接大模型，直接把 prompt 和检索结果展示出来
    # 后面再 response = call_llm(prompt)

    return {
        "question": question,
        "rag_result": rag_result,
        "graph_chain": graph_chain,
        "prompt": prompt,

        # 临时 mock 回答，等接 LLM 后替换
        "answer": "这里将由大模型根据中文教材、英文教材、术语表和知识图谱生成回答。"
    }
