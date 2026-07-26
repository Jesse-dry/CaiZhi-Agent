"""
数据集生成 Agent — 根据 EvidencePackage 生成候选数据。

使用现有 LLMClient，通过约束型 prompt 保证：
  - 只能使用证据包中的信息
  - 不得创造知识节点、术语翻译或编造教材依据
  - 所有结论可追溯到 source_refs
  - 证据不足时返回 insufficient_evidence

生成四类数据：
  1. QA 题目（6 种题型 + 4 选项 + 误区诊断）
  2. 分级学生答案（5-6 档，每档不同质量水平）
  3. 苏格拉底引导链（有分支的教学状态图）
  4. 费曼评价数据（任务标准 + 分级学生回答）

注意：Generator 和 Critic 是两个独立的 Agent，不同时生成和自评。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from infrastructure.llm_client import LLMClient, create_llm_client
from schemas.generation_blueprint import (
    EvidencePackage,
    GenerationBlueprint,
    ExpansionTarget,
    RetrievedChunk,
    GraphNode,
    GraphEdge,
    StandardTerm,
)

logger = logging.getLogger(__name__)


def _fmt_chunks(chunks: list[RetrievedChunk], max_items: int = 5) -> str:
    """格式化教材片段"""
    if not chunks:
        return "（无教材片段）"

    parts = []
    for i, c in enumerate(chunks[:max_items]):
        chapter_info = ""
        if c.chapter:
            chapter_info = f" | {c.chapter}"
        if c.section:
            chapter_info += f" > {c.section}"
        parts.append(
            f"[chunk_id: {c.chunk_id} | {c.language}{chapter_info}]\n{c.text[:800]}"
        )
    return "\n\n---\n\n".join(parts)


def _fmt_nodes(nodes: list[GraphNode]) -> str:
    """格式化知识图谱节点"""
    if not nodes:
        return "（无图谱节点）"
    lines = []
    for n in nodes:
        lines.append(f"- [{n.id}] {n.label_zh} ({n.type}): {n.description}")
    return "\n".join(lines)


def _fmt_edges(edges: list[GraphEdge]) -> str:
    """格式化知识图谱边"""
    if not edges:
        return "（无图谱边）"
    lines = []
    for e in edges:
        lines.append(f"- {e.source} → {e.target} ({e.relation}): {e.explanation}")
    return "\n".join(lines)


def _fmt_terms(terms: list[StandardTerm]) -> str:
    """格式化术语表"""
    if not terms:
        return "（无术语）"
    lines = []
    for t in terms:
        lines.append(f"- [{t.term_id}] {t.zh} / {t.en} ({t.category})")
    return "\n".join(lines)


def _fmt_existing(existing: list[dict], max_items: int = 10) -> str:
    """格式化已有数据摘要（用于去重参考）"""
    if not existing:
        return "（无已有数据）"
    lines = []
    for item in existing[:max_items]:
        q = item.get("question", "") or item.get("prompt", "") or item.get("title", "")
        lines.append(f"- [{item.get('id', '?')}] {q[:100]}")
    return "\n".join(lines)


class DatasetGeneratorAgent:
    """
    数据集生成器 Agent。

    构造器注入 LLMClient（遵循项目 DI 模式）。
    每次生成前需要先 set_evidence() 载入证据包。
    """

    def __init__(self, llm_client: LLMClient | None = None):
        self._llm = llm_client or create_llm_client()
        self._evidence: EvidencePackage | None = None

    def set_evidence(self, evidence: EvidencePackage) -> None:
        """设置当前生成任务的证据包（只读）"""
        self._evidence = evidence

    # ═══════════════════════════════════════════════════════════
    # 1. QA 题目生成
    # ═══════════════════════════════════════════════════════════

    def generate_qa(self, blueprint: GenerationBlueprint) -> dict:
        """
        根据蓝图生成一道 QA 题目。

        返回 dict（可被 QADatasetItem(**result) 校验）。
        """
        if self._evidence is None:
            raise RuntimeError("Must call set_evidence() before generating")

        prompt = self._build_qa_prompt(blueprint)
        system = self._qa_system_prompt()

        raw = self._llm.chat(prompt, system=system, temperature=0.7)
        return self._parse_json_output(raw, "QA")

    def _qa_system_prompt(self) -> str:
        return """你是材料科学与工程专业的 AI 出题助手。你的任务是生成高质量的教学题目。

【核心约束 —— 必须严格遵守】
1. 只能使用下方【证据包】中的信息。不得编造事实、知识节点或术语。
2. 每条关键结论必须能对应到 source_refs 中的 chunk_id。
3. 术语必须使用【标准术语表】中的中英文对照，禁止自己翻译。
4. 因果链路径只能使用【知识图谱】中给出的节点和边。
5. 如果证据包不足以支撑某类题目，返回 insufficient_evidence，不要强行编造。

【输出格式】
必须严格返回 JSON，格式如下：
```json
{
  "id": "Q_AUTO_XXXX",
  "knowledge_ids": [...],
  "question_type": "causal_reasoning",
  "difficulty": 2,
  "question": "...",
  "options": {"A": "...", "B": "...", "C": "...", "D": "..."},
  "answer": "B",
  "reference_answer": "...",
  "key_points": [...],
  "source_refs": [{"chunk_id": "...", "text": "...", "language": "zh", "file_name": "..."}],
  "graph_path": ["process_quenching", "condition_rapid_cooling", ...],
  "misconceptions": [...],
  "diagnosis": {
    "A": {"misconception_id": "M_AUTO_001_A", "misconception": "...", "error_reason": "...", "missing_concepts": [...], "feedback": "...", "remedial_path": [...]},
    ...
  },
  "next_chain_id": "...",
  "next_socratic_id": null
}
```

【选项设计原则】
- 正确选项必须明确唯一
- 3 个干扰项应分别对应不同的常见误区
- 干扰项不应过于明显或荒谬
- 每个错误选项在 diagnosis 中应有完整的误区诊断"""

    def _build_qa_prompt(self, blueprint: GenerationBlueprint) -> str:
        """构建 QA 生成的完整 prompt"""
        e = self._evidence

        # 根据 blueprint 筛选相关 chunk
        allowed_ids = set(blueprint.allowed_chunk_ids)
        chunks = [c for c in e.textbook_chunks if c.chunk_id in allowed_ids] if allowed_ids else e.textbook_chunks[:5]

        # 根据 graph_path_hint 筛选节点
        path_ids = set(blueprint.graph_path_hint)
        nodes = [n for n in e.graph_nodes if n.id in path_ids] if path_ids else e.graph_nodes
        edges = [
            edge for edge in e.graph_edges
            if edge.source in path_ids or edge.target in path_ids
        ] if path_ids else e.graph_edges

        type_descriptions = {
            "definition": "定义题：直接询问概念的定义。示例：什么是马氏体？",
            "causal_reasoning": "因果题：询问原因-结果关系。示例：为什么淬火会提高硬度？",
            "comparison": "比较题：比较两个相似概念/工艺的区别。示例：退火和正火有什么区别？",
            "conditional": "条件题：询问影响某现象的因素。示例：哪些因素影响马氏体形成？",
            "reverse_reasoning": "反向推理题：从结果反推原因。示例：硬度升高可能对应什么组织变化？",
            "application_transfer": "应用迁移题：将知识应用于实际问题。示例：某零件需要高硬度，应如何设计热处理？",
        }

        type_desc = type_descriptions.get(
            blueprint.question_type.value if hasattr(blueprint.question_type, 'value') else str(blueprint.question_type),
            "通用题",
        )

        prompt = f"""══════════════════════════════════════
【题目蓝图】
══════════════════════════════════════
- 题目类型：{type_desc}
- 目标难度：{blueprint.difficulty}（1=基础, 2=中等, 3=进阶）
- 期望考察的关键点：{', '.join(blueprint.target_key_points)}
- 期望的因果链路径：{' → '.join(blueprint.graph_path_hint) if blueprint.graph_path_hint else '（无指定）'}

══════════════════════════════════════
【证据包（只能使用以下信息）】
══════════════════════════════════════

【教材片段】
{_fmt_chunks(chunks)}

【知识图谱节点】
{_fmt_nodes(nodes)}

【知识图谱边】
{_fmt_edges(edges)}

【标准术语表】
{_fmt_terms(e.standard_terms)}

【已有题目（请避免生成重复题目）】
{_fmt_existing(e.existing_items)}

══════════════════════════════════════
【生成要求】
══════════════════════════════════════
1. 根据蓝图和证据包生成一道 {blueprint.question_type} 类型的题目
2. 难度为 {blueprint.difficulty} 级
3. 重点考察：{', '.join(blueprint.target_key_points) if blueprint.target_key_points else '与知识图谱因果链相关的内容'}
4. source_refs 必须引用上方【教材片段】中的真实 chunk_id
5. graph_path 必须使用上方【知识图谱节点】中的真实节点 ID
6. 术语翻译必须与【标准术语表】一致
7. 如果证据不足以生成该题目，请返回 {{"error": "insufficient_evidence", "reason": "..."}}
"""
        return prompt

    # ═══════════════════════════════════════════════════════════
    # 2. 分级学生答案生成
    # ═══════════════════════════════════════════════════════════

    def generate_student_answers(self, qa_item: dict, count: int = 5) -> list[dict]:
        """
        为一道 QA 题目生成分级学生答案。

        生成 5-6 档不同质量水平的答案，用于测试：
          - 错题诊断 Agent 是否识别误区
          - 苏格拉底分支是否触发正确路径
          - 费曼评分稳定性和一致性
        """
        if self._evidence is None:
            raise RuntimeError("Must call set_evidence() before generating")

        prompt = self._build_student_answer_prompt(qa_item, count)
        system = """你是材料科学教育领域的学生模拟器。你需要模拟不同水平的学生对同一道题的回答。

【输出格式】
必须严格返回 JSON 数组，每个元素格式：
```json
[
  {
    "id": "SA_AUTO_XXXX",
    "question_id": "...",
    "student_answer": "...",
    "answer_level": "completely_wrong",
    "misconception_id": "M_...",
    "missing_nodes": [...],
    "expected_diagnosis": "...",
    "recommended_next_step": null,
    "expected_score_range": [0, 20],
    "expected_feedback": "..."
  },
  ...
]
```

【5 档要求】
1. completely_wrong — 完全错误（概念混淆、因果颠倒），用于测试诊断 Agent 是否能识别严重误区
2. partial_incomplete — 结论部分正确但因果链不完整（缺少 2-3 个中间环节）
3. terms_right_logic_wrong — 术语正确但逻辑关系错误（概念都对但推理方向反了）
4. mostly_correct_unclear — 基本正确但表达不清晰、缺乏条理
5. high_quality — 高质量答案（完整、清晰、术语准确）

答案要自然、真实，包含学生常见的表达特点。"""

        raw = self._llm.chat(prompt, system=system, temperature=0.8)
        return self._parse_json_output(raw, "student_answers", expect_array=True)

    def _build_student_answer_prompt(self, qa_item: dict, count: int) -> str:
        """构建学生答案生成的 prompt"""
        options_text = "\n".join(f"{k}: {v}" for k, v in qa_item.get("options", {}).items())
        correct_answer = qa_item.get("answer", "")
        correct_text = qa_item.get("options", {}).get(correct_answer, "")

        wrong_options = []
        for k, v in qa_item.get("options", {}).items():
            if k != correct_answer:
                diagnosis = qa_item.get("diagnosis", {}).get(k, {})
                wrong_options.append(
                    f"  - {k}: {v}（典型误区：{diagnosis.get('misconception', '未知')}）"
                )

        return f"""请为以下题目生成 {count} 档不同水平的学生答案。

【题目】
{qa_item.get('question', '')}

【选项】
{options_text}

【正确答案】{correct_answer}：{correct_text}

【错误选项的典型误区】
{chr(10).join(wrong_options) if wrong_options else '无'}

【参考答案】
{qa_item.get('reference_answer', '')}

【关键知识点】
{', '.join(qa_item.get('key_points', []))}

【知识图谱路径】
{' → '.join(qa_item.get('graph_path', []))}

请生成 {count} 档答案，从完全错误到高质量。"""

    # ═══════════════════════════════════════════════════════════
    # 3. 苏格拉底引导链生成
    # ═══════════════════════════════════════════════════════════

    def generate_socratic(self, target: ExpansionTarget) -> dict:
        """
        根据扩充目标生成一条有分支的苏格拉底引导链。

        核心原则：
          - 每一步只推进一个认知环节
          - 不直接泄露最终答案
          - 问题之间对应知识图谱中的相邻节点
          - 对正确/部分正确/错误回答有不同分支
          - 最终能够覆盖目标因果链
        """
        if self._evidence is None:
            raise RuntimeError("Must call set_evidence() before generating")

        prompt = self._build_socratic_prompt(target)
        system = """你是材料科学教育领域的苏格拉底式引导专家。
你设计的是"有分支的教学状态图"，而非线性问答链。

【核心设计原则】
1. 每一步只推进一个认知环节（不要一步跨越多个概念）
2. 不直接泄露最终答案（让学生自己推导）
3. 问题之间对应知识图谱中的相邻节点
4. 对正确/部分正确/错误回答有不同分支：
   - 正确 → 进入下一步（深入下一个认知环节）
   - 部分正确 → 给提示后重试当前步骤
   - 错误 → 进入补救分支（降低难度，补充前置知识）

【输出格式】
```json
{
  "id": "S_AUTO_XXXX",
  "title": "...",
  "chain_id": "...",
  "target_knowledge_ids": [...],
  "trigger_misconceptions": [...],
  "steps": [
    {
      "step_id": "S1",
      "question": "...",
      "expected_concepts": [...],
      "hint": "...",
      "explanation_if_wrong": "...",
      "next_if_correct": "S2",
      "next_if_partial": "S1_HINT",
      "next_if_wrong": "S1_REMEDIAL",
      "kg_node_ref": "process_quenching",
      "is_entry": true,
      "is_remedial": false
    },
    ...
  ],
  "completion_condition": {
    "required_concepts": [...],
    "min_steps_completed": 3
  },
  "final_summary": "...",
  "source_refs": [...],
  "graph_path": [...]
}
```

【步骤设计规范】
- 入口节点（is_entry=true）只有一个
- 主路径（S1→S2→S3→...）对应 KG 因果链的每一步
- 提示节点（S1_HINT）和补救节点（S1_REMEDIAL）的 is_remedial=true
- 所有 next_if_* 指针必须指向存在的 step_id 或 null（null 表示完成）
"""

        raw = self._llm.chat(prompt, system=system, temperature=0.6)
        return self._parse_json_output(raw, "socratic")

    def _build_socratic_prompt(self, target: ExpansionTarget) -> str:
        """构建苏格拉底链生成的 prompt"""
        e = self._evidence

        # 获取目标因果链的完整路径
        chain_path: list[str] = []
        if target.graph_path_id:
            for chain in e.graph_chains:
                if chain.get("chain_id") == target.graph_path_id:
                    chain_path = chain.get("path", [])
                    break

        return f"""请为以下知识目标设计一条苏格拉底引导链。

══════════════════════════════════════
【目标知识点】
{', '.join(target.knowledge_ids)}

【知识图谱因果链】（每一步应对应一个引导步骤）
{' → '.join(chain_path) if chain_path else '（无指定因果链）'}

【图谱节点详情】
{_fmt_nodes(e.graph_nodes)}

【图谱边详情】
{_fmt_edges(e.graph_edges)}

【教材证据】
{_fmt_chunks(e.textbook_chunks)}

【标准术语】
{_fmt_terms(e.standard_terms)}

══════════════════════════════════════
【设计要求】
══════════════════════════════════════
1. 主路径步骤数 = 因果链节点数（每个节点一个引导问题）
2. 每一步 kg_node_ref 必须指向【图谱节点详情】中的真实节点 ID
3. 为每个主步骤设计 hint 和 remedial 分支
4. 每一步的 expected_concepts 应与对应 KG 节点的描述一致
5. completion_condition 应覆盖因果链的所有关键概念
6. source_refs 必须引用【教材证据】中的真实 chunk_id"""

    # ═══════════════════════════════════════════════════════════
    # 4. 费曼评价数据生成
    # ═══════════════════════════════════════════════════════════

    def generate_feynman_task(self, target: ExpansionTarget) -> dict:
        """
        生成费曼任务（评分标准 + checklist + 优秀范例）。

        这是"出卷"部分——定义学生要解释什么、按什么标准评分。
        """
        if self._evidence is None:
            raise RuntimeError("Must call set_evidence() before generating")

        prompt = self._build_feynman_task_prompt(target)
        system = """你是材料科学教育领域的费曼学习法评价专家。
你设计费曼任务——让学生"用自己的话"解释概念，然后按标准评分。

【输出格式】
```json
{
  "id": "F_AUTO_XXXX",
  "topic": "...",
  "chain_id": "...",
  "knowledge_ids": [...],
  "prompt": "请向一名刚接触材料学的学生解释...",
  "audience": "materials_beginner",
  "mandatory_points": [...],
  "optional_points": [...],
  "forbidden_claims": [...],
  "checklist": [
    {"point": "...", "keywords": [...]},
    ...
  ],
  "rubric": {
    "concept_accuracy": 30,
    "causal_chain_completeness": 30,
    "terminology": 15,
    "application_transfer": 15,
    "clarity": 10
  },
  "excellent_example": "...",
  "source_refs": [...],
  "graph_path": [...]
}
```

【设计原则】
- mandatory_points 必须覆盖因果链的关键环节
- forbidden_claims 列出常见错误陈述（来源于 misconceptions）
- checklist 每项对应一个 mandatory_point
- excellent_example 应是完整、清晰、包含所有 mandatory_points 的示范"""

        raw = self._llm.chat(prompt, system=system, temperature=0.6)
        return self._parse_json_output(raw, "feynman_task")

    def _build_feynman_task_prompt(self, target: ExpansionTarget) -> str:
        """构建费曼任务生成的 prompt"""
        e = self._evidence

        chain_path: list[str] = []
        if target.graph_path_id:
            for chain in e.graph_chains:
                if chain.get("chain_id") == target.graph_path_id:
                    chain_path = chain.get("path", [])
                    break

        return f"""请为以下知识目标设计一个费曼学习法评价任务。

══════════════════════════════════════
【目标知识点】
{', '.join(target.knowledge_ids)}

【知识图谱因果链】
{' → '.join(chain_path) if chain_path else '（无指定）'}

【图谱节点详情】
{_fmt_nodes(e.graph_nodes)}

【教材证据】
{_fmt_chunks(e.textbook_chunks)}

【标准术语】
{_fmt_terms(e.standard_terms)}

══════════════════════════════════════
【设计要求】
══════════════════════════════════════
1. prompt 应让学生"用自己的话向初学者解释"
2. mandatory_points 必须覆盖因果链的所有关键环节
3. forbidden_claims 列出 2-3 个常见错误
4. checklist 的 point 与 mandatory_points 一一对应
5. excellent_example 必须包含所有 mandatory_points
6. 术语必须与【标准术语】一致
7. source_refs 必须引用真实 chunk_id"""

    def generate_feynman_responses(self, task: dict, count: int = 5) -> list[dict]:
        """为费曼任务生成分级学生回答"""
        if self._evidence is None:
            raise RuntimeError("Must call set_evidence() before generating")

        prompt = f"""请为以下费曼任务生成 {count} 档不同水平的学生回答。

【费曼任务】
{task.get('prompt', '')}

【必须覆盖的知识点】
{', '.join(task.get('mandatory_points', []))}

【加分知识点】
{', '.join(task.get('optional_points', []))}

【不允许的错误陈述】
{', '.join(task.get('forbidden_claims', []))}

【优秀范例】
{task.get('excellent_example', '')}

请生成 {count} 档回答，从 completely_wrong 到 excellent_transfer。
输出 JSON 数组格式，每个元素：
{{
  "id": "FR_AUTO_XXXX",
  "feynman_id": "{task.get('id', '')}",
  "response": "...",
  "expected_level": "completely_wrong",
  "expected_missing_points": [...],
  "expected_score_range": [0, 20],
  "expected_feedback": "..."
}}"""

        system = """你是材料科学教育领域的费曼学习法评价专家。
你需要模拟不同水平的学生对费曼任务的回答。

5 档要求：
1. completely_wrong — 存在 forbidden_claims 中的错误
2. partial_incomplete — 只覆盖 1-2 个 mandatory_points
3. mostly_correct_unclear — 覆盖大部分但表达混乱
4. high_quality — 覆盖所有 mandatory_points，清晰准确
5. excellent_transfer — 包含 optional_points 或跨知识域联想

expected_score_range 给出 [min, max] 区间（满分 78）。"""

        raw = self._llm.chat(prompt, system=system, temperature=0.8)
        return self._parse_json_output(raw, "feynman_responses", expect_array=True)

    # ═══════════════════════════════════════════════════════════
    # JSON 解析工具
    # ═══════════════════════════════════════════════════════════

    def _parse_json_output(
        self, raw: str, context: str, expect_array: bool = False
    ) -> dict | list[dict]:
        """
        从 LLM 原始输出中提取 JSON。

        处理 LLM 可能包裹在 ```json...``` 中的情况。
        """
        # 尝试提取 ```json ... ``` 块
        json_block_pattern = r"```(?:json)?\s*\n?(.*?)\n?```"
        matches = re.findall(json_block_pattern, raw, re.DOTALL)
        if matches:
            # 使用最后一个 JSON 块（通常是主输出）
            raw = matches[-1]

        # 尝试直接解析
        try:
            result = json.loads(raw.strip())
            return result
        except json.JSONDecodeError:
            pass

        # 尝试找到第一个 { 或 [ 开始的部分
        if expect_array:
            start = raw.find("[")
            if start >= 0:
                try:
                    # 从 [ 开始，找到匹配的 ]
                    depth = 0
                    end = start
                    for i in range(start, len(raw)):
                        if raw[i] == "[":
                            depth += 1
                        elif raw[i] == "]":
                            depth -= 1
                            if depth == 0:
                                end = i + 1
                                break
                    return json.loads(raw[start:end])
                except json.JSONDecodeError:
                    pass
        else:
            start = raw.find("{")
            if start >= 0:
                try:
                    depth = 0
                    end = start
                    for i in range(start, len(raw)):
                        if raw[i] == "{":
                            depth += 1
                        elif raw[i] == "}":
                            depth -= 1
                            if depth == 0:
                                end = i + 1
                                break
                    return json.loads(raw[start:end])
                except json.JSONDecodeError:
                    pass

        logger.error(f"Failed to parse JSON from {context} output. Raw: {raw[:500]}...")
        return {"error": "json_parse_failed", "raw": raw[:500]}


def create_generator_agent() -> DatasetGeneratorAgent:
    """工厂函数"""
    return DatasetGeneratorAgent()
