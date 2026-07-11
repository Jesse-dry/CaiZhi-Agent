"""
智能答疑 — 请求与结果

POST /api/qa/ask 的契约定义。
"""

from pydantic import BaseModel, Field
from schemas.common import SourceReference, KeyTerm, ImageReference, CausalStep


class QARequest(BaseModel):
    """智能答疑请求"""
    session_id: str = Field(..., description="会话 ID", examples=["sess_abc123"])
    question: str = Field(..., description="学生提问", min_length=1, max_length=5000)
    knowledge_id: str | None = Field(default=None, description="指定知识单元 ID，空则自动匹配")
    language: str = Field(default="zh", description="期望回答语言：zh / en / auto")


class QAResult(BaseModel):
    """
    智能答疑完整结果。

    services/qa_service.answer_question() 的返回值。
    页面渲染时直接读取字段，不做二次解析。
    """
    # ── 基础标识 ──
    question: str = Field(..., description="原始提问")
    knowledge_id: str | None = Field(default=None, description="匹配到的知识单元 ID")
    chain_id: str | None = Field(default=None, description="匹配到的因果链 ID")

    # ── 回答内容 ──
    short_answer: str = Field(default="", description="简明回答（1-3 句）")
    principle: str = Field(default="", description="核心原理解释")

    # ── 因果链 ──
    causal_chain: list[CausalStep] = Field(default_factory=list, description="从原因到结果的因果链步骤")

    # ── 术语 ──
    key_terms: list[KeyTerm] = Field(default_factory=list, description="涉及的关键术语（双语）")

    # ── 误区 ──
    misconceptions: list[str] = Field(default_factory=list, description="常见误区提示")

    # ── 自测 ──
    recommended_question_id: str | None = Field(default=None, description="推荐自测题 ID，用于进入错题诊断")

    # ── 引用 ──
    sources: list[SourceReference] = Field(default_factory=list, description="教材引用来源")
    images: list[ImageReference] = Field(default_factory=list, description="相关教材图片")

    # ── 调试（V1 阶段保留，后续移除） ──
    prompt: str = Field(default="", description="[调试] 组装的完整 LLM prompt")
    retrieval_debug: dict = Field(default_factory=dict, description="[调试] RAG 检索过程数据")


class QAStreamChunk(BaseModel):
    """SSE 流式响应的单个 chunk"""
    chunk_type: str = Field(..., description="chunk 类型：short_answer / principle / causal_step / term / source / done")
    index: int = Field(default=0, description="chunk 序号")
    content: str = Field(default="", description="文本内容")
    data: dict = Field(default_factory=dict, description="结构化附加数据")
