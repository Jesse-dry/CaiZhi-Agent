"""
构建约束型 RAG Q&A 提示词。

核心理念：四种数据源各有明确职责边界，LLM 不得越界。
"""


def _fmt_contexts(contexts: list[dict], label: str, max_items: int = 5) -> str:
    """格式化教材片段，带章节信息"""
    if not contexts:
        return f"（无{label}教材结果）"

    parts = []
    for i, item in enumerate(contexts[:max_items]):
        meta = item.get("metadata", {})
        headers = meta.get("headers", {})
        chapter_path = " > ".join(
            v for v in [headers.get("h1"), headers.get("h2"), headers.get("h3")] if v
        )
        source_info = f"[{label} | {meta.get('file_name', '?')}"
        if chapter_path:
            source_info += f" | {chapter_path}"
        if meta.get("page"):
            source_info += f" | p.{meta['page']}"
        source_info += "]"

        parts.append(f"{source_info}\n{item.get('text', '')}")

    return "\n\n---\n\n".join(parts)


def _fmt_terms(terms: list[dict]) -> str:
    """格式化术语表"""
    if not terms:
        return "（无匹配术语）"
    lines = []
    for t in terms:
        zh = t.get("zh", "")
        en = t.get("en", "")
        if zh and en:
            lines.append(f"- {zh} / {en}")
        elif zh:
            lines.append(f"- {zh}")
        else:
            lines.append(f"- {en}")
    return "\n".join(lines)


def _fmt_causal_chain(chain: list[str]) -> str:
    """格式化因果链为箭头路径"""
    if not chain:
        return "（无匹配因果链）"
    return " → ".join(chain)


def _fmt_misconceptions(misconceptions: list[str]) -> str:
    if not misconceptions:
        return "（暂无）"
    return "\n".join(f"- {m}" for m in misconceptions)


def _fmt_self_test(self_test: dict | None) -> str:
    if not self_test:
        return "（暂无匹配的自测题）"
    return f"{self_test['question']}（编号：{self_test['question_id']}）"


def _fmt_sources(sources: list[dict], max_items: int = 5) -> str:
    if not sources:
        return "（无教材来源）"
    lines = []
    for s in sources[:max_items]:
        lang = "中文" if s.get("language") == "zh" else "英文"
        chapter = f" | {s['chapter']}" if s.get("chapter") else ""
        lines.append(f"- [{lang}] {s['file_name']}{chapter}（p.{s.get('page', '?')}）")
    return "\n".join(lines)


def build_constrained_qa_prompt(
    user_question: str,
    zh_contexts: list[dict],
    en_contexts: list[dict],
    image_contexts: list[dict],
    causal_chain: list[str],
    key_terms: list[dict],
    misconceptions: list[str],
    self_test: dict | None,
    sources: list[dict],
) -> str:
    """
    构建"RAG + data"约束型 prompt。

    四个数据源各有职责：
      - 教材 RAG → 事实依据
      - 知识图谱 → 因果链
      - terms.csv → 术语标准
      - questions.json → 自测题
    """

    zh_text = _fmt_contexts(zh_contexts, "中文教材")
    en_text = _fmt_contexts(en_contexts, "English Textbook")
    image_text = _fmt_contexts(image_contexts, "图表描述", max_items=3)
    terms_text = _fmt_terms(key_terms)
    chain_text = _fmt_causal_chain(causal_chain)
    misc_text = _fmt_misconceptions(misconceptions)
    test_text = _fmt_self_test(self_test)
    src_text = _fmt_sources(sources)

    prompt = f"""你是材料科学与工程专业的 AI 助教。请根据以下四种数据源回答学生问题。

══════════════════════════════════════
【数据源职责划分 —— 必须严格遵守】
══════════════════════════════════════

1. 教材片段（中文+英文）→ 负责【事实依据】
   - 用于回答：定义、组织转变、热处理原理、材料性能变化、教材原文表述
   - 如果教材没有覆盖某个知识点，要明确说"当前教材依据不足"

2. 知识图谱因果链 → 负责【逻辑路径】
   - 用于回答：工艺→组织→结构/缺陷→性能 的因果链路
   - 只能使用下方给出的因果链，禁止自行编造节点

3. 术语表 → 负责【翻译标准】
   - 关键术语的中英文翻译必须与术语表一致
   - 禁止自己翻译或使用其他译法

4. 自测题 → 负责【衔接测试】
   - 回答末尾引用的自测题必须是下方给出的题目
   - 禁止临时编造新题目

══════════════════════════════════════
【数据】
══════════════════════════════════════

【学生问题】
{user_question}

【中文教材片段】
{zh_text}

【英文教材片段】
{en_text}

【图表描述】
{image_text}

【知识图谱因果链】
{chain_text}

【标准术语表】
{terms_text}

【常见误区】
{misc_text}

【匹配的自测题】
{test_text}

【教材来源】
{src_text}

══════════════════════════════════════
【输出格式 —— 严格按此顺序】
══════════════════════════════════════

### 1. 简明回答
（用 2-3 句话直接回答问题）

### 2. 材料学原理
（从教材片段中提取，按"工艺→组织→结构→性能"展开，200-400字）

### 3. 因果链
（直接复制下方因果链，无需修改）
{chain_text}

### 4. 中英文术语
（从上方术语表中选取最相关的 3-6 个）

### 5. 教材依据
（列出引用了哪几段教材，标注章节）

### 6. 常见误区
（直接列出上方给出的常见误区）

### 7. 自测题
（直接引用上方匹配的自测题）"""
    return prompt


# ═══════════════════════════════════════════════════════════
# 保留旧接口（向后兼容）
# ═══════════════════════════════════════════════════════════

def build_rag_qa_prompt(query, rag_result, graph_chain=None):
    """旧接口，由 build_constrained_qa_prompt 替代"""
    return build_constrained_qa_prompt(
        user_question=query,
        zh_contexts=rag_result.get("zh_contexts", []),
        en_contexts=rag_result.get("en_contexts", []),
        image_contexts=rag_result.get("image_contexts", []),
        causal_chain=(
            [n.get("label_zh", "") for n in graph_chain.get("path", [])]
            if graph_chain else []
        ),
        key_terms=rag_result.get("matched_terms", []),
        misconceptions=graph_chain.get("common_misconceptions", []) if graph_chain else [],
        self_test=None,
        sources=[],
    )


def build_qa_prompt(
    user_question, zh_contexts, en_contexts, terms,
    graph_chain, misconceptions, image_captions=None,
):
    """旧接口，由 build_constrained_qa_prompt 替代"""
    return build_constrained_qa_prompt(
        user_question=user_question,
        zh_contexts=zh_contexts if isinstance(zh_contexts, list) else [],
        en_contexts=en_contexts if isinstance(en_contexts, list) else [],
        image_contexts=image_captions if isinstance(image_captions, list) else [],
        causal_chain=graph_chain if isinstance(graph_chain, list) else [],
        key_terms=terms if isinstance(terms, list) else [],
        misconceptions=misconceptions if isinstance(misconceptions, list) else [],
        self_test=None,
        sources=[],
    )
