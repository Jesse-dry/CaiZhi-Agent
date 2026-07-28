"""
生成蓝图 — 控制数据生成的分布与约束。

核心理念：不要让生成器随机决定问题类型和难度。
先生成"题目蓝图"，再根据蓝图生成题目，以确保：
  - 题型分布可控（不会生成大量近似题）
  - 难度分布符合教学需要
  - 每条生成都有明确的教材来源约束
  - 与知识图谱节点对齐
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from schemas.common import SourceReference
from schemas.dataset_item import QuestionType


# ═══════════════════════════════════════════════════════════
# 证据包（只读 — 生成器只能使用此包中的信息）
# ═══════════════════════════════════════════════════════════

class RetrievedChunk(BaseModel):
    """从 RAG 检索到的教材片段"""
    chunk_id: str = Field(..., description="ChromaDB chunk 唯一标识")
    text: str = Field(..., description="片段文本")
    language: str = Field(default="zh", description="语言：zh / en")
    chapter: str | None = Field(default=None, description="章节标题")
    section: str | None = Field(default=None, description="小节标题")
    headers: dict = Field(default_factory=dict, description="层级标题 h1/h2/h3")
    score: float | None = Field(default=None, description="检索相关度分数")
    file_name: str = Field(default="", description="来源 PDF 文件名")


class GraphNode(BaseModel):
    """知识图谱节点"""
    id: str = Field(..., description="节点唯一 ID，如 process_quenching")
    label_zh: str = Field(..., description="中文标签")
    label_en: str = Field(default="", description="英文标签")
    type: str = Field(default="", description="节点类型：process/phase/structure/mechanism/property/condition")
    description: str = Field(default="", description="节点描述")


class GraphEdge(BaseModel):
    """知识图谱边"""
    source: str = Field(..., description="源节点 ID")
    target: str = Field(..., description="目标节点 ID")
    relation: str = Field(..., description="关系类型：requires/causes/promotes/transforms_to/hinders/increases")
    label_zh: str = Field(default="", description="关系中文标签")
    explanation: str = Field(default="", description="边解释")


class StandardTerm(BaseModel):
    """术语表条目"""
    term_id: str = Field(..., description="术语 ID，如 T001")
    zh: str = Field(..., description="中文术语")
    en: str = Field(default="", description="英文术语")
    category: str = Field(default="", description="分类：工艺/组织/机制/结构/性能")
    definition_zh: str = Field(default="", description="中文定义")


class ExistingDatasetItem(BaseModel):
    """已有数据条目摘要（用于去重参考，不含完整内容）"""
    id: str = Field(..., description="条目 ID")
    question: str = Field(default="", description="题目/任务文本")
    knowledge_ids: list[str] = Field(default_factory=list, description="关联知识点")
    question_type: str | None = Field(default=None, description="题目类型")
    difficulty: int | None = Field(default=None, description="难度")
    key_points: list[str] = Field(default_factory=list, description="考察的关键点")
    embedding: list[float] | None = Field(default=None, description="文本 embedding 向量（用于相似度计算）")


class EvidencePackage(BaseModel):
    """
    生成器可用的证据包（只读）。

    约束原则：
      - 不得使用证据包之外的事实
      - 不得创造新的知识节点
      - 不得创造术语翻译
      - 每条结论必须能够映射到 source_refs
      - 证据不足时返回 insufficient_evidence
    """
    knowledge_ids: list[str] = Field(default_factory=list, description="目标知识节点 ID")
    textbook_chunks: list[RetrievedChunk] = Field(default_factory=list, description="教材片段")
    image_chunks: list[RetrievedChunk] = Field(default_factory=list, description="图片描述片段")
    graph_nodes: list[GraphNode] = Field(default_factory=list, description="知识图谱节点")
    graph_edges: list[GraphEdge] = Field(default_factory=list, description="知识图谱边")
    graph_chains: list[dict] = Field(default_factory=list, description="因果链（含 path）")
    standard_terms: list[StandardTerm] = Field(default_factory=list, description="标准术语表")
    existing_items: list[dict] = Field(default_factory=list, description="已有数据（用于去重参考）")


# ═══════════════════════════════════════════════════════════
# 扩充目标
# ═══════════════════════════════════════════════════════════

class ExpansionTarget(BaseModel):
    """
    扩充目标 — 定义要生成什么、生成多少。

    从知识图谱节点/因果链出发，而不是随机从教材抽取句子。
    正确顺序：KG 节点或因果链 → 找对应教材证据 → 生成题目与评价标准。
    """
    knowledge_ids: list[str] = Field(..., description="目标知识节点 ID 列表", min_length=1)
    graph_path_id: str | None = Field(default=None, description="关联的因果链 ID")
    output_types: list[str] = Field(
        default_factory=list,
        description="输出类型：qa / socratic / feynman / student_answers",
    )
    target_count: int = Field(default=10, ge=1, le=100, description="目标生成数量")
    difficulty_distribution: dict[int, float] = Field(
        default_factory=lambda: {1: 0.3, 2: 0.5, 3: 0.2},
        description="难度分布比例，key=难度(1-3), value=比例",
    )
    question_type_distribution: dict[str, float] = Field(
        default_factory=lambda: {
            "definition": 0.15,
            "causal_reasoning": 0.30,
            "comparison": 0.20,
            "conditional": 0.15,
            "reverse_reasoning": 0.10,
            "application_transfer": 0.10,
        },
        description="题型分布比例",
    )
    generate_student_answers: bool = Field(
        default=True, description="是否为每道 QA 题目生成分级学生答案"
    )
    answers_per_question: int = Field(
        default=5, ge=3, le=6, description="每道题生成几档学生答案"
    )


# ═══════════════════════════════════════════════════════════
# 生成蓝图（单个）
# ═══════════════════════════════════════════════════════════

class GenerationBlueprint(BaseModel):
    """
    单条数据的生成蓝图。

    先生成蓝图，再根据蓝图生成题目 — 这样题库分布可控，
    不会生成大量近似题。

    QA 蓝图示例:
        GenerationBlueprint(
            blueprint_id="BP_QA_0001",
            target=ExpansionTarget(knowledge_ids=["K_MARTENSITE"], ...),
            question_type=QuestionType.CAUSAL,
            difficulty=2,
            target_key_points=["扩散受限", "晶格畸变"],
            allowed_chunk_ids=["zh_0235", "zh_0236"],
            graph_path_hint=["process_quenching", ..., "property_high_hardness"],
        )
    """
    blueprint_id: str = Field(..., description="蓝图唯一 ID")
    target: ExpansionTarget = Field(..., description="所属扩充目标")
    output_type: str = Field(..., description="输出类型：qa / socratic / feynman / student_answer")
    question_type: QuestionType | None = Field(default=None, description="题目类型（QA 专用）")
    difficulty: int = Field(default=1, ge=1, le=3, description="目标难度")
    target_key_points: list[str] = Field(default_factory=list, description="期望考察的关键知识点")
    allowed_chunk_ids: list[str] = Field(
        default_factory=list, description="允许引用的教材 chunk_id 列表（从 EvidencePackage 筛选）"
    )
    graph_path_hint: list[str] = Field(
        default_factory=list, description="期望的因果链路径（KG 节点 ID 序列）"
    )
    existing_similar: list[str] = Field(
        default_factory=list, description="已有相似题目的 ID 列表（用于避免重复）"
    )


# ═══════════════════════════════════════════════════════════
# 生成批次
# ═══════════════════════════════════════════════════════════

class ExpansionBatch(BaseModel):
    """一次扩充生成的完整批次"""
    batch_id: str = Field(..., description="批次 ID")
    target: ExpansionTarget = Field(..., description="扩充目标")
    blueprints: list[GenerationBlueprint] = Field(default_factory=list, description="生成蓝图列表")
    qa_items: list[dict] = Field(default_factory=list, description="生成的 QA 题目（dict 便于跨模块传递）")
    student_answers: list[dict] = Field(default_factory=list, description="生成的分级学生答案")
    socratic_items: list[dict] = Field(default_factory=list, description="生成的苏格拉底链")
    feynman_tasks: list[dict] = Field(default_factory=list, description="生成的费曼任务")
    feynman_responses: list[dict] = Field(default_factory=list, description="生成的费曼学生回答")
    created_at: str = Field(default="", description="批次创建时间")
