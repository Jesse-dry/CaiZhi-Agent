"""
共享基础类型

所有业务域 schema 的公共依赖。定义枚举、引用、术语等可复用结构。
这些类型会出现在 OpenAPI schema 中，前端据此生成 TypeScript 类型。
"""

from enum import StrEnum
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
# 可复用值对象
# ═══════════════════════════════════════════════════════════

class SourceReference(BaseModel):
    """教材引用 — 指向 RAG 检索到的原文片段"""
    chunk_id: str = Field(..., description="ChromaDB chunk 唯一标识")
    file_name: str = Field(..., description="来源 PDF 文件名（不含路径）")
    language: str = Field(default="zh", description="语言：zh / en")
    chapter: str | None = Field(default=None, description="章节标题")
    section: str | None = Field(default=None, description="小节标题")
    page_start: int | None = Field(default=None, description="起始页码")
    page_end: int | None = Field(default=None, description="结束页码")
    text: str = Field(default="", description="引用原文片段（摘要）")
    score: float | None = Field(default=None, description="检索相关度分数")


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
