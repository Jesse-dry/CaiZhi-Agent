"""构建 RAG Q&A 提示词"""


def _get_meta(meta: dict, key: str, default=""):
    """兼容 metadata key（file_name 优先，source_file 兜底）"""
    if meta is None:
        return default
    return meta.get(key) or meta.get("source_file") or default


def _format_headers(headers: dict) -> str:
    """将 headers dict 格式化为可读的章节路径"""
    if not headers or not isinstance(headers, dict):
        return ""
    parts = [v for v in [headers.get("h1"), headers.get("h2"), headers.get("h3")] if v]
    return " > ".join(parts)


def build_rag_qa_prompt(query, rag_result, graph_chain=None):
    zh_contexts = rag_result.get("zh_contexts", [])
    en_contexts = rag_result.get("en_contexts", [])
    image_contexts = rag_result.get("image_contexts", [])
    terms = rag_result.get("matched_terms", [])

    # 中文教材片段
    zh_parts = []
    for item in zh_contexts:
        meta = item.get("metadata", {})
        source = _get_meta(meta, "file_name")
        chapter_path = _format_headers(meta.get("headers", {}))
        header = f"[中文教材 | {source}"
        if chapter_path:
            header += f" | {chapter_path}"
        header += "]\n"
        zh_parts.append(header + item["text"])
    zh_text = "\n\n".join(zh_parts) if zh_parts else "(无中文教材结果)"

    # 英文教材片段
    en_parts = []
    for item in en_contexts:
        meta = item.get("metadata", {})
        source = _get_meta(meta, "file_name")
        chapter_path = _format_headers(meta.get("headers", {}))
        header = f"[English Textbook | {source}"
        if chapter_path:
            header += f" | {chapter_path}"
        header += "]\n"
        en_parts.append(header + item["text"])
    en_text = "\n\n".join(en_parts) if en_parts else "(无英文教材结果)"

    # 图片描述
    image_text = ""
    if image_contexts:
        img_parts = []
        for item in image_contexts:
            meta = item.get("metadata", {})
            img_name = meta.get("image_name", "")
            img_path = meta.get("image_path", "")
            img_parts.append(f"[图表描述 | {img_name} | {img_path}]\n{item['text']}")
        image_text = "\n\n".join(img_parts)

    # 术语
    term_text = "\n".join([
        f"- {t.get('zh', '')} / {t.get('en', '')}: {t.get('definition_zh', '')}"
        for t in terms
    ]) if terms else "(未匹配到相关术语)"

    # 知识图谱
    graph_text = ""
    if graph_chain:
        graph_text = graph_chain.get("summary", "")

    prompt = f"""
你是一个面向材料专业本科生的 AI 学习助教。

请根据【中文教材依据】【英文教材依据】【图表描述】【术语表】【知识图谱因果链】回答学生问题。
要求：
1. 不要只给一句答案，要按教学结构输出。
2. 中文解释为主，关键术语给出英文。
3. 如果教材依据不足，要明确说明"当前教材依据不足"。
4. 回答必须围绕材料学的"工艺—组织—结构/缺陷—性能"因果链。
5. 输出常见误区和推荐学习路径。

【学生问题】
{query}

【中文教材依据】
{zh_text}

【英文教材依据】
{en_text}

【图表描述】
{image_text}

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

def build_qa_prompt(
    user_question,
    zh_contexts,
    en_contexts,
    terms,
    graph_chain,
    misconceptions,
    image_captions=None
):
    prompt = f"""
你是材料专业学习智能体，不是普通问答机器人。

请基于以下材料回答学生问题。

【学生问题】
{user_question}

【中文教材片段】
{zh_contexts}

【英文教材片段】
{en_contexts}

【术语表】
{terms}

【知识图谱因果链】
{graph_chain}

【常见误区】
{misconceptions}

【图表描述】
{image_captions or "无"}

请按以下结构回答：
1. 简明回答
2. 材料学原理
3. 因果链解释
4. 关键英文术语
5. 教材依据
6. 常见误区提醒
7. 自测题
"""
    return prompt
