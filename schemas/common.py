"""
共享基础类型

所有业务域 schema 的公共依赖。定义枚举、引用、术语等可复用结构。
这些类型会出现在 OpenAPI schema 中，前端据此生成 TypeScript 类型。
"""

from enum import StrEnum
from typing import Generic, TypeVar
from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════
# 枚举
# ═══════════════════════════════════════════════════════════

class LearningStage(StrEnum):
    """学习闭环五阶段 + 完成态"""
    QA = "qa"
    DIAGNOSIS = "diagnosis"
    SOCRATIC = "socratic"
    FEYNMAN = "feynman"
    RECOMMENDATION = "recommendation"
    COMPLETED = "completed"


class AnswerQuality(StrEnum):
    """苏格拉底引导 — 学生回答质量"""
    COMPLETE = "complete"
    PARTIAL = "partial"
    INCORRECT = "incorrect"


class SocraticAction(StrEnum):
    """苏格拉底引导 — 系统动作"""
    ADVANCE = "advance"
    HINT = "hint"
    RETRY = "retry"
    SIMPLIFY = "simplify"
    COMPLETE = "complete"


class MasteryLevel(StrEnum):
    """知识掌握程度"""
    MASTERED = "已掌握"
    BASIC = "基本掌握"
    PARTIAL = "部分掌握"
    NEEDS_IMPROVEMENT = "需要加强"


class Difficulty(StrEnum):
    """题目难度"""
    BASIC = "basic"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class Language(StrEnum):
    """检索 / 回答语言"""
    ZH = "zh"
    EN = "en"
    AUTO = "auto"


# ═══════════════════════════════════════════════════════════
# 统一 Service 结果 — 所有 service 返回的 wrapper
# ═══════════════════════════════════════════════════════════

class ServiceErrorType(StrEnum):
    """统一的 Service 层错误类型。

    模型输出解析失败时，不直接在页面报错，而应返回明确的错误类型。
    """
    MODEL_TIMEOUT = "model_timeout"
    INVALID_MODEL_OUTPUT = "invalid_model_output"
    RETRIEVAL_EMPTY = "retrieval_empty"
    KNOWLEDGE_NOT_FOUND = "knowledge_not_found"
    INVALID_STAGE_TRANSITION = "invalid_stage_transition"
    DATABASE_ERROR = "database_error"


class ServiceError(BaseModel):
    """单个 Service 错误详情"""
    type: ServiceErrorType = Field(..., description="错误类型")
    message: str = Field(..., description="人类可读的错误描述")
    detail: dict | None = Field(default=None, description="附加调试信息（如堆栈、原始输出等）")


T = TypeVar("T")


class ServiceResult(BaseModel, Generic[T]):
    """
    统一的 Service 层返回 wrapper。

    所有 service 函数都返回 ServiceResult[T]，其中 T 是业务结果类型。
    调用方先检查 success，再取 result。

    用法:
        # 成功
        return ServiceResult(success=True, result=qa_result, trace_id="run_abc123")

        # 失败
        return ServiceResult(
            success=False,
            errors=[ServiceError(type=ServiceErrorType.RETRIEVAL_EMPTY, message="...")],
            trace_id="run_abc123",
        )
    """
    success: bool = Field(..., description="是否成功")
    result: T | None = Field(default=None, description="业务结果（success=True 时有效）")
    warnings: list[str] = Field(default_factory=list, description="非致命的警告信息")
    errors: list[ServiceError] = Field(default_factory=list, description="错误列表（success=False 时有效）")
    trace_id: str = Field(default="", description="追踪 ID，用于日志关联和调试")


# ═══════════════════════════════════════════════════════════
# 可复用值对象
# ═══════════════════════════════════════════════════════════

class SourceReference(BaseModel):
    """
    教材引用 — 指向 RAG 检索到的原文片段。

    所有 QA、费曼评价和评测模块都复用此结构，避免每个页面自行解析 metadata。

    字段命名遵循提案的统一来源模型：
      - source_id 是提案名，chunk_id 是当前主名（过渡期两者共存）
      - excerpt 是提案名，text 是当前主名
      - retrieval_score 是提案名，score 是当前主名
    """

    # ── 当前主字段（过渡期，Phase 4 后切换为提案命名） ──
    chunk_id: str = Field(..., description="ChromaDB chunk 唯一标识")
    file_name: str = Field(..., description="来源 PDF 文件名（不含路径）")
    language: str = Field(default="zh", description="语言：zh / en")
    chapter: str | None = Field(default=None, description="章节标题")
    section: str | None = Field(default=None, description="小节标题")
    page_start: int | None = Field(default=None, description="起始页码")
    page_end: int | None = Field(default=None, description="结束页码")
    text: str = Field(default="", description="引用原文片段（摘要）")
    score: float | None = Field(default=None, description="检索相关度分数")

    # ── 提案新增字段 ──
    doc_id: str = Field(default="", description="来源文档 ID（如 PDF 标识符）")
    book_title: str = Field(default="", description="教材书名（如 '材料科学基础 清华版'）")
    image_refs: list[str] = Field(default_factory=list, description="关联的图片 chunk_id 列表")

    # ── 提案字段别名（向前兼容，Phase 4 后切换为主字段） ──
    @property
    def source_id(self) -> str:
        """提案字段名，等同于 chunk_id"""
        return self.chunk_id

    @property
    def excerpt(self) -> str:
        """提案字段名，等同于 text"""
        return self.text

    @property
    def retrieval_score(self) -> float | None:
        """提案字段名，等同于 score"""
        return self.score


class KeyTerm(BaseModel):
    """双语关键术语"""
    zh: str = Field(..., description="中文术语")
    en: str = Field(default="", description="英文术语")
    category: str | None = Field(default=None, description="术语分类（process/property/structure/condition）")
    definition_zh: str | None = Field(default=None, description="中文定义")


class ImageReference(BaseModel):
    """教材图片引用"""
    chunk_id: str = Field(..., description="图片 chunk ID")
    image_name: str = Field(..., description="图片文件名")
    image_path: str = Field(default="", description="图片文件路径")
    caption: str = Field(default="", description="图片描述文本")
    related_terms: list[str] = Field(default_factory=list, description="相关术语")
    score: float | None = Field(default=None, description="检索相关度分数")


class CausalStep(BaseModel):
    """知识图谱因果链中的一个节点"""
    node_id: str = Field(..., description="图谱节点 ID")
    label_zh: str = Field(..., description="中文标签")
    label_en: str = Field(default="", description="英文标签")
    relation: str = Field(default="", description="与前一个节点的关系（requires/causes/leads_to）")
    explanation: str = Field(default="", description="该步的因果解释")


class ChatMessage(BaseModel):
    """对话消息"""
    role: str = Field(..., description="assistant / user")
    content: str = Field(..., description="消息正文")
    timestamp: str | None = Field(default=None, description="ISO 时间戳")
    metadata: dict = Field(default_factory=dict, description="附加元数据（如引用来源）")
