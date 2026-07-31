"""
agents/ — 受约束 AI Agent 层

每个 Agent 只承担一个明确职责，接收有界资源（AgentContext），
返回结构化结果（AgentResult），包含 evidence 和 trace。

Agent 不直接读写 Streamlit 状态，不决定学习阶段跳转。
阶段转换由 workflows/learning_loop.py 状态机全权负责。

Agent 职责：
    qa_agent                  → 基于教材回答问题（RAG + 术语表 + 知识图谱）
    diagnosis_agent           → 识别错误类型和知识盲区（题库 + 误区库 + 知识图谱）
    socratic_agent            → 判断回答并选择下一步提示（苏格拉底链）
    feynman_agent             → 按 rubric 评价学生解释（费曼标准 + 知识图谱）
    graph_reasoning_agent     → 找到缺失因果链和先修节点（知识图谱）

统一接口：
    class BaseAgent(Protocol):
        async def run(self, context: AgentContext) -> AgentResult:
            ...

不依赖 Streamlit。
"""

# ── Protocol ──
from agents.base import BaseAgent

# ── Agent implementations ──
from agents.qa_agent import QAAgent
from agents.diagnosis_agent import DiagnosisAgent
from agents.socratic_agent import SocraticAgent
from agents.feynman_agent import FeynmanAgent
from agents.graph_reasoning_agent import GraphReasoningAgent

# ── Schema types (re-export for convenience) ──
from schemas.agent import (
    AgentContext,
    AgentResult,
    AgentEvidence,
    AgentTrace,
    AgentResource,
    create_agent_context,
    create_v1_agent_result,
)

__all__ = [
    # Protocol
    "BaseAgent",
    # Agents
    "QAAgent",
    "DiagnosisAgent",
    "SocraticAgent",
    "FeynmanAgent",
    "GraphReasoningAgent",
    # Schemas
    "AgentContext",
    "AgentResult",
    "AgentEvidence",
    "AgentTrace",
    "AgentResource",
    # Factories
    "create_agent_context",
    "create_v1_agent_result",
]
