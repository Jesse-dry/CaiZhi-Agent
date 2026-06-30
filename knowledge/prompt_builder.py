def build_rag_qa_prompt(query, rag_result, graph_chain=None):
    zh_contexts = rag_result.get("zh_contexts", [])
    en_contexts = rag_result.get("en_contexts", [])
    terms = rag_result.get("matched_terms", [])

    zh_text = "\n\n".join([
        f"[中文教材 | {item['metadata'].get('source_file')} | p.{item['metadata'].get('page')}]\n{item['text']}"
        for item in zh_contexts
    ])

    en_text = "\n\n".join([
        f"[English Textbook | {item['metadata'].get('source_file')} | p.{item['metadata'].get('page')}]\n{item['text']}"
        for item in en_contexts
    ])

    term_text = "\n".join([
        f"- {t.get('zh', '')} / {t.get('en', '')}: {t.get('definition_zh', '')}"
        for t in terms
    ])

    graph_text = ""
    if graph_chain:
        graph_text = graph_chain.get("summary", "")

    prompt = f"""
你是一个面向材料专业本科生的 AI 学习助教。

请根据【中文教材依据】【英文教材依据】【术语表】【知识图谱因果链】回答学生问题。
要求：
1. 不要只给一句答案，要按教学结构输出。
2. 中文解释为主，关键术语给出英文。
3. 如果教材依据不足，要明确说明“当前教材依据不足”。
4. 回答必须围绕材料学的“工艺—组织—结构/缺陷—性能”因果链。
5. 输出常见误区和推荐学习路径。

【学生问题】
{query}

【中文教材依据】
{zh_text}

【英文教材依据】
{en_text}

【术语表】
{term_text}

【知识图谱因果链】
{graph_text}

请按以下格式输出：

【简明回答】
...

【材料学原理】
...

【关键英文术语】
...

【教材依据】
...

【图谱路径】
...

【常见误区】
...

【自测题】
...

【推荐下一步学习】
...
"""

    return prompt