"""
数据集条目 — 所有数据生产管线产出的 Pydantic 模型。

四类数据：
  1. QA 题目（6 种题型 + 错误选项误区诊断）
  2. 分级学生答案（每题 5-6 档，用于测试诊断/苏格拉底/费曼 Agent）
  3. 苏格拉底引导链（有分支的教学状态图）
  4. 费曼评价数据（任务标准 + 分级学生回答）

每条数据都带完整生命周期溯源字段。
"""

from __future__ import annotations

from datetime import datetime, UTC
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from schemas.common import SourceReference


# ═══════════════════════════════════════════════════════════
# 枚举
# ═══════════════════════════════════════════════════════════

class DatasetStatus(StrEnum):
    """数据生命周期状态"""
    CANDIDATE = "candidate"            # 刚生成，未校验
    AUTO_VALIDATED = "auto_validated"  # 自动校验通过
    NEEDS_REVIEW = "needs_review"      # 等待人工审核
    APPROVED = "approved"              # 审核通过
    REJECTED = "rejected"              # 审核拒绝（保留用于去重）
    PUBLISHED = "published"            # 已发布到正式数据集
    DEPRECATED = "deprecated"          # 已废弃


class QuestionType(StrEnum):
    """QA 题目类型"""
    DEFINITION = "definition"                # 定义题：什么是马氏体？
    CAUSAL = "causal_reasoning"              # 因果题：为什么淬火会提高硬度？
    COMPARISON = "comparison"                # 比较题：退火和正火有什么区别？
    CONDITIONAL = "conditional"              # 条件题：哪些因素影响马氏体形成？
    REVERSE = "reverse_reasoning"            # 反向推理题：硬度升高可能对应什么组织变化？
    APPLICATION = "application_transfer"     # 应用迁移题：某零件需要高硬度，应如何设计热处理？


class AnswerLevel(StrEnum):
    """学生答案质量分级"""
    COMPLETELY_WRONG = "completely_wrong"            # 完全错误（概念混淆）
    PARTIAL_INCOMPLETE = "partial_incomplete"        # 结论部分正确但因果链不完整
    TERMS_RIGHT_LOGIC_WRONG = "terms_right_logic_wrong"  # 术语正确但逻辑关系错误
    MOSTLY_CORRECT_UNCLEAR = "mostly_correct_unclear"    # 基本正确但表达不清晰
    HIGH_QUALITY = "high_quality"                    # 高质量（完整、清晰）
    EXCELLENT_TRANSFER = "excellent_transfer"        # 含迁移应用/跨知识域联想


class SocraticBranchAction(StrEnum):
    """苏格拉底分支动作"""
    ADVANCE = "advance"       # 进入下一步
    HINT = "hint"             # 给提示后重试
    REMEDIAL = "remedial"     # 进入补救分支
    SIMPLIFY = "simplify"     # 降低难度，重新表述问题
    COMPLETE = "complete"     # 完成引导


class FeynmanAudience(StrEnum):
    """费曼解释的目标听众"""
    MATERIALS_BEGINNER = "materials_beginner"        # 刚接触材料学的学生
    MATERIALS_INTERMEDIATE = "materials_intermediate"  # 有一定基础的学生
    GENERAL_AUDIENCE = "general_audience"             # 无材料学背景的普通人


# ═══════════════════════════════════════════════════════════
# 生命周期 Mixin
# ═══════════════════════════════════════════════════════════

class DatasetLifecycle(BaseModel):
    """所有数据集条目的公共生命周期字段"""
    status: DatasetStatus = Field(default=DatasetStatus.CANDIDATE, description="生命周期状态")
    created_by: str = Field(default="", description="生成模型标识，如 deepseek-chat")
    generator_prompt_version: str = Field(default="v1.0", description="生成 prompt 版本号")
    critic_model: str | None = Field(default=None, description="审查模型标识")
    quality_score: float | None = Field(default=None, description="质量评分 0-100")
    reviewer: str | None = Field(default=None, description="审核人标识")
    review_notes: str | None = Field(default=None, description="审核备注")
    created_at: str = Field(
        default_factory=lambda: datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        description="创建时间 ISO 8601",
    )
    approved_at: str | None = Field(default=None, description="审核通过时间")
    dataset_version: str | None = Field(default=None, description="所属数据集版本，如 2026.08.1")


# ═══════════════════════════════════════════════════════════
# 1. QA 题目数据
# ═══════════════════════════════════════════════════════════

class MisconceptionDetail(BaseModel):
    """单个错误选项的误区诊断"""
    misconception_id: str = Field(..., description="误区唯一 ID，如 M_Q001_A")
    misconception: str = Field(..., description="误区名称/简述")
    error_reason: str = Field(default="", description="错误原因分析")
    missing_concepts: list[str] = Field(default_factory=list, description="缺失的知识点")
    feedback: str = Field(default="", description="针对性反馈文本")
    remedial_path: list[str] = Field(default_factory=list, description="补救学习路径（知识点列表）")


class QADatasetItem(DatasetLifecycle):
    """
    正式 QA 数据集条目。

    包含题目、选项、答案、误区诊断、教材引用和 KG 路径。
    支持 6 种题型，每条可追踪到教材原文和知识图谱节点。
    """
    id: str = Field(..., description="题目唯一 ID，如 Q_AUTO_0001", examples=["Q_AUTO_0001"])
    knowledge_ids: list[str] = Field(default_factory=list, description="关联的知识单元 ID")
    question_type: QuestionType = Field(..., description="题目类型")
    difficulty: int = Field(default=1, ge=1, le=3, description="难度：1=basic, 2=intermediate, 3=advanced")
    question: str = Field(..., description="题目文本", min_length=1)
    options: dict[str, str] = Field(..., description="选项映射，如 {'A': '...', 'B': '...'}")
    answer: str = Field(..., description="正确选项，如 'B'", min_length=1, max_length=1)
    reference_answer: str = Field(..., description="完整参考答案", min_length=1)
    key_points: list[str] = Field(default_factory=list, description="考察的关键知识点")
    source_refs: list[SourceReference] = Field(default_factory=list, description="教材证据引用")
    graph_path: list[str] = Field(default_factory=list, description="KG 节点 ID 序列，从原因到结果")
    misconceptions: list[str] = Field(default_factory=list, description="常见误区提示（面向学生的简要版）")
    diagnosis: dict[str, MisconceptionDetail] = Field(
        default_factory=dict,
        description="每个错误选项的详细误区诊断，key 为选项字母",
    )
    next_chain_id: str | None = Field(default=None, description="推荐复习的因果链 ID")
    next_socratic_id: str | None = Field(default=None, description="推荐的苏格拉底引导链 ID")


# ═══════════════════════════════════════════════════════════
# 2. 分级学生答案
# ═══════════════════════════════════════════════════════════

class StudentAnswerSample(DatasetLifecycle):
    """
    分级学生答案 — 模拟不同质量水平的学生回答。

    用途：
      - 测试错题诊断 Agent 是否识别误区
      - 测试苏格拉底分支是否触发正确路径
      - 测试费曼评分稳定性和一致性
      - 构建自动化回归测试

    每题建议生成 5-6 档。
    """
    id: str = Field(..., description="答案样本唯一 ID，如 SA_AUTO_0001", examples=["SA_AUTO_0001"])
    question_id: str = Field(..., description="关联的 QA 题目 ID")
    student_answer: str = Field(..., description="模拟的学生回答文本", min_length=1)
    answer_level: AnswerLevel = Field(..., description="答案质量等级")
    misconception_id: str | None = Field(
        default=None, description="关联的误区 ID（completely_wrong / terms_right_logic_wrong 时填写）"
    )
    missing_nodes: list[str] = Field(
        default_factory=list, description="缺失的 KG 节点 ID 列表"
    )
    expected_diagnosis: str = Field(
        default="", description="预期的诊断结论 — 诊断 Agent 应给出的判断"
    )
    recommended_next_step: str | None = Field(
        default=None, description="预期的苏格拉底分支推荐"
    )
    expected_score_range: list[int] = Field(
        default_factory=list, description="费曼评分预期范围 [min, max]"
    )
    expected_feedback: str = Field(
        default="", description="预期的费曼反馈关键点"
    )


# ═══════════════════════════════════════════════════════════
# 3. 苏格拉底引导链（有分支）
# ═══════════════════════════════════════════════════════════

class CompletionCondition(BaseModel):
    """苏格拉底链完成条件"""
    required_concepts: list[str] = Field(
        default_factory=list,
        description="学生必须理解的概念列表（全部覆盖才算完成）",
    )
    min_steps_completed: int = Field(default=0, description="最少完成步骤数")
    allow_skip_if_mastered: bool = Field(default=True, description="已掌握的概念是否允许跳过")


class SocraticStep(BaseModel):
    """
    单步苏格拉底引导 — 支持分支。

    每一步只推进一个认知环节，不直接泄露最终答案。
    问题之间对应知识图谱中的相邻节点。
    对正确/部分正确/错误回答有不同分支。
    """
    step_id: str = Field(..., description="步骤唯一 ID，如 S1、S1_HINT、S1_REMEDIAL")
    question: str = Field(..., description="引导问题", min_length=1)
    expected_concepts: list[str] = Field(default_factory=list, description="期望学生说出的概念")
    hint: str = Field(default="", description="提示文本（学生部分正确时展示）")
    explanation_if_wrong: str = Field(default="", description="错误时的解释")
    next_if_correct: str | None = Field(
        default=None, description="正确回答 → 跳转到该 step_id（None 表示完成）"
    )
    next_if_partial: str | None = Field(
        default=None, description="部分正确 → 跳转到提示节点"
    )
    next_if_wrong: str | None = Field(
        default=None, description="错误 → 跳转到补救节点"
    )
    kg_node_ref: str | None = Field(
        default=None, description="对应的 KG 节点 ID（保证与知识图谱对齐）"
    )
    is_remedial: bool = Field(default=False, description="是否为补救分支节点")
    is_entry: bool = Field(default=False, description="是否为入口节点（引导链启动时从此节点开始）")


class SocraticDatasetItem(DatasetLifecycle):
    """
    苏格拉底引导链 — 有分支的教学状态图。

    核心理念：
      - 每一步只推进一个认知环节
      - 不直接泄露最终答案
      - 问题之间对应知识图谱中的相邻节点
      - 对错误、部分正确、正确回答有不同分支
      - 最终能够覆盖目标因果链
    """
    id: str = Field(..., description="引导链唯一 ID，如 S_AUTO_0001", examples=["S_AUTO_0001"])
    title: str = Field(..., description="引导链标题")
    chain_id: str | None = Field(default=None, description="关联的知识图谱因果链 ID")
    target_question_id: str | None = Field(default=None, description="关联的 QA 题目 ID")
    target_knowledge_ids: list[str] = Field(default_factory=list, description="目标知识点 ID 列表")
    trigger_misconceptions: list[str] = Field(
        default_factory=list, description="触发该引导链的误区 ID 列表"
    )
    steps: list[SocraticStep] = Field(default_factory=list, description="所有步骤（构成有向图）")
    completion_condition: CompletionCondition = Field(
        default_factory=CompletionCondition, description="完成条件"
    )
    final_summary: str = Field(default="", description="引导完成后的总结文本")
    source_refs: list[SourceReference] = Field(default_factory=list, description="教材证据引用")
    graph_path: list[str] = Field(default_factory=list, description="对应的 KG 因果链节点 ID 序列")


# ═══════════════════════════════════════════════════════════
# 4. 费曼评价数据（两部分：任务标准 + 分级学生回答）
# ═══════════════════════════════════════════════════════════

class ChecklistItem(BaseModel):
    """费曼评分清单条目"""
    point: str = Field(..., description="评分点描述")
    keywords: list[str] = Field(default_factory=list, description="关键词")


class FeynmanRubric(BaseModel):
    """费曼评价五维度权重"""
    concept_accuracy: int = Field(default=30, ge=0, description="概念准确性权重")
    causal_chain_completeness: int = Field(default=30, ge=0, description="因果链完整性权重")
    terminology: int = Field(default=15, ge=0, description="术语规范性权重")
    application_transfer: int = Field(default=15, ge=0, description="应用迁移权重")
    clarity: int = Field(default=10, ge=0, description="表达清晰度权重")


class FeynmanTask(DatasetLifecycle):
    """
    费曼任务与评分标准。

    这是"考卷"部分 — 定义学生需要解释什么、按什么标准评分。
    与 FeynmanStudentResponse（学生回答样本）配对使用。
    """
    id: str = Field(..., description="费曼任务唯一 ID，如 F_AUTO_0001", examples=["F_AUTO_0001"])
    topic: str = Field(..., description="主题简述")
    chain_id: str | None = Field(default=None, description="关联的知识图谱因果链 ID")
    knowledge_ids: list[str] = Field(default_factory=list, description="关联的知识单元 ID")
    prompt: str = Field(..., description="费曼挑战描述（对学生的提问）", min_length=1)
    audience: FeynmanAudience = Field(
        default=FeynmanAudience.MATERIALS_BEGINNER, description="目标听众"
    )
    mandatory_points: list[str] = Field(
        default_factory=list, description="必须覆盖的知识点（缺一则扣分）"
    )
    optional_points: list[str] = Field(
        default_factory=list, description="加分知识点（覆盖则加分）"
    )
    forbidden_claims: list[str] = Field(
        default_factory=list, description="不允许的错误陈述（出现即严重扣分）"
    )
    checklist: list[ChecklistItem] = Field(default_factory=list, description="评分清单")
    rubric: FeynmanRubric = Field(default_factory=FeynmanRubric, description="五维度评分权重")
    excellent_example: str = Field(default="", description="优秀范例文本")
    source_refs: list[SourceReference] = Field(default_factory=list, description="教材证据引用")
    graph_path: list[str] = Field(default_factory=list, description="对应的 KG 因果链节点 ID 序列")


class FeynmanStudentResponse(DatasetLifecycle):
    """
    分级学生费曼回答。

    每个费曼任务至少生成 5 档回答：
      completely_wrong → partial_incomplete → mostly_correct_unclear
      → high_quality → excellent_transfer

    用途：
      - 测试费曼 Agent 是否区分不同质量答案
      - 验证评分稳定性（同一回答多次评分是否一致）
      - 验证反馈与分数的对应关系
    """
    id: str = Field(..., description="回答样本唯一 ID，如 FR_AUTO_001", examples=["FR_AUTO_001"])
    feynman_id: str = Field(..., description="关联的费曼任务 ID")
    response: str = Field(..., description="模拟的学生费曼解释文本", min_length=1)
    expected_level: AnswerLevel = Field(..., description="预期评级")
    expected_missing_points: list[str] = Field(
        default_factory=list, description="预期缺失的知识点"
    )
    expected_score_range: list[int] = Field(
        default_factory=list, description="预期评分范围 [min, max]"
    )
    expected_feedback: str = Field(
        default="", description="预期反馈关键点"
    )


# ═══════════════════════════════════════════════════════════
# 类型别名 — 方便批量操作
# ═══════════════════════════════════════════════════════════

# 任意数据集条目类型
DatasetItem = QADatasetItem | StudentAnswerSample | SocraticDatasetItem | FeynmanTask | FeynmanStudentResponse

# 按类别分组
QABundle = tuple[QADatasetItem, list[StudentAnswerSample]]
FeynmanBundle = tuple[FeynmanTask, list[FeynmanStudentResponse]]
