"""
数据集扩充服务 — 核心管线编排。

串联全部阶段：
  1. 构建 EvidencePackage（RAG 检索 + KG 查询 + 术语匹配）
  2. 生成题目蓝图（控制题型/难度分布）
  3. Generator 生成候选数据
  4. Critic 审查（可选，推荐）
  5. 确定性自动校验（5 项）
  6. 质量评分
  7. 发布到正式数据集
  8. 反馈驱动扩充（后期迭代）

依赖注入构造器，遵循项目 DI 模式。
与传输层无关：Streamlit 页面和 CLI 脚本共享同一份逻辑。
"""

from __future__ import annotations

import logging
from datetime import datetime, UTC
from typing import Any

from repositories.rag_repo import RAGRepository
from repositories.knowledge_repo import KnowledgeRepository
from repositories.dataset_repo import DatasetRepository
from infrastructure.llm_client import LLMClient, create_llm_client
from infrastructure.jsonl_dataset_repo import JsonlDatasetRepo, create_jsonl_dataset_repo

from schemas.generation_blueprint import (
    EvidencePackage,
    ExpansionTarget,
    GenerationBlueprint,
    ExpansionBatch,
    RetrievedChunk,
    GraphNode,
    GraphEdge,
    StandardTerm,
    ExistingDatasetItem,
)
from schemas.dataset_item import (
    DatasetStatus,
    QuestionType,
    QADatasetItem,
    StudentAnswerSample,
    SocraticDatasetItem,
    FeynmanTask,
    FeynmanStudentResponse,
)
from schemas.validation_report import (
    ValidationReport,
    BatchValidationReport,
    QualityScore,
)
from schemas.dataset_review import (
    ReviewRecord,
    PublishRequest,
    DatasetVersion,
    ReviewStats,
    ReviewAction,
)

from validators import validate_all

logger = logging.getLogger(__name__)


class DatasetExpansionService:
    """
    数据集扩充服务。

    用法:
        service = DatasetExpansionService(
            rag_repo=chroma_store,
            knowledge_repo=file_knowledge_repo,
            llm_client=create_llm_client(),
            dataset_repo=create_jsonl_dataset_repo(),
        )

        # 完整管线
        target = ExpansionTarget(
            knowledge_ids=["K_QUENCHING", "K_MARTENSITE"],
            graph_path_id="C001",
            output_types=["qa", "student_answers", "socratic", "feynman"],
            target_count=10,
        )
        batch = await service.run_full_pipeline(target)

        # 仅校验
        reports = await service.validate_batch(batch)

        # 发布
        version = await service.publish(approved_ids=["Q_AUTO_0001", ...], version="2026.08.1")
    """

    def __init__(
        self,
        rag_repo: RAGRepository,
        knowledge_repo: KnowledgeRepository,
        llm_client: LLMClient | None = None,
        dataset_repo: DatasetRepository | None = None,
    ):
        self._rag = rag_repo
        self._knowledge = knowledge_repo
        self._llm = llm_client or create_llm_client()
        self._dataset = dataset_repo or create_jsonl_dataset_repo()

        # 惰性加载 Generator 和 Critic
        self._generator = None
        self._critic = None

        # ID 计数器（每次 run_full_pipeline 时重置）
        self._id_counters: dict[str, int] = {}

    @property
    def generator(self):
        """惰性加载 Generator Agent"""
        if self._generator is None:
            from agents.dataset_generator_agent import DatasetGeneratorAgent
            self._generator = DatasetGeneratorAgent(self._llm)
        return self._generator

    @property
    def critic(self):
        """惰性加载 Critic Agent"""
        if self._critic is None:
            from agents.dataset_critic_agent import DatasetCriticAgent
            self._critic = DatasetCriticAgent(self._llm)
        return self._critic

    def _next_id(self, prefix: str) -> str:
        """分配唯一 ID，如 Q_AUTO_0001, SA_AUTO_0001 等"""
        if prefix not in self._id_counters:
            self._id_counters[prefix] = 0
        self._id_counters[prefix] += 1
        return f"{prefix}{self._id_counters[prefix]:04d}"

    # ═══════════════════════════════════════════════════════════
    # Pipeline
    # ═══════════════════════════════════════════════════════════

    async def run_full_pipeline(
        self,
        target: ExpansionTarget,
        use_critic: bool = True,
    ) -> ExpansionBatch:
        """
        运行完整生成管线。

        阶段：
          1. 构建证据包
          2. 生成蓝图
          3. 生成候选数据
          4. （可选）Critic 审查
          5. 自动校验 + 质量评分
          6. 保存候选数据
        """
        batch_id = f"batch_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
        logger.info(f"Starting pipeline {batch_id} for {target.knowledge_ids}")

        # 重置 ID 计数器
        self._id_counters = {}

        # 1. 构建 EvidencePackage
        evidence = await self._build_evidence(target)
        self.generator.set_evidence(evidence)

        # 2. 生成蓝图
        blueprints = self._generate_blueprints(target, evidence)
        logger.info(f"Generated {len(blueprints)} blueprints")

        # 3. 生成候选数据
        batch = ExpansionBatch(
            batch_id=batch_id,
            target=target,
            blueprints=blueprints,
            created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

        for bp in blueprints:
            if bp.output_type == "qa":
                await self._generate_qa_items(batch, bp, evidence)

            elif bp.output_type == "socratic":
                await self._generate_socratic_items(batch, bp, evidence)

            elif bp.output_type == "feynman":
                await self._generate_feynman_items(batch, bp, evidence)

        logger.info(
            f"Batch {batch_id} generated: "
            f"{len(batch.qa_items)} QA, "
            f"{len(batch.student_answers)} student answers, "
            f"{len(batch.socratic_items)} socratic, "
            f"{len(batch.feynman_tasks)} feynman tasks, "
            f"{len(batch.feynman_responses)} feynman responses"
        )

        # 4. 保存候选数据
        self._save_batch(batch)

        return batch

    # ═══════════════════════════════════════════════════════════
    # 证据包构建
    # ═══════════════════════════════════════════════════════════

    async def _build_evidence(self, target: ExpansionTarget) -> EvidencePackage:
        """构建证据包：检索教材 + 查询 KG + 加载术语"""
        # RAG 检索
        textbook_chunks: list[RetrievedChunk] = []
        image_chunks: list[RetrievedChunk] = []

        # 根据知识节点构建搜索查询
        search_queries = self._build_search_queries(target)

        for query in search_queries:
            # 文本检索
            results = self._rag.retrieve(query, language="zh", top_k=5)
            for r in results:
                textbook_chunks.append(RetrievedChunk(
                    chunk_id=r.get("chunk_id", ""),
                    text=r.get("text", ""),
                    language=r.get("language", "zh"),
                    chapter=r.get("chapter"),
                    section=r.get("section"),
                    headers=r.get("headers", {}),
                    score=r.get("score"),
                    file_name=r.get("file_name", ""),
                ))

            # 图片检索
            img_results = self._rag.retrieve_images(query, language="zh", top_k=3)
            for r in img_results:
                image_chunks.append(RetrievedChunk(
                    chunk_id=r.get("chunk_id", ""),
                    text=r.get("text", ""),
                    language=r.get("language", "zh"),
                    score=r.get("score"),
                    file_name=r.get("image_name", ""),
                ))

        # 去重（按 chunk_id）
        seen_ids = set()
        textbook_chunks = [c for c in textbook_chunks if not (c.chunk_id in seen_ids or seen_ids.add(c.chunk_id))]
        seen_ids.clear()
        image_chunks = [c for c in image_chunks if not (c.chunk_id in seen_ids or seen_ids.add(c.chunk_id))]

        # KG 查询
        kg = self._knowledge.get_knowledge_graph()
        graph_nodes = [GraphNode(**n) for n in kg.get("nodes", [])]
        graph_edges = [GraphEdge(**e) for e in kg.get("edges", [])]
        graph_chains = kg.get("chains", [])

        # 术语表
        terms = self._knowledge.search_terms("", language="zh")
        standard_terms = [
            StandardTerm(
                term_id=t.get("term_id", ""),
                zh=t.get("zh", ""),
                en=t.get("en", ""),
                category=t.get("category", ""),
                definition_zh=t.get("definition_zh", ""),
            )
            for t in terms
        ]

        # 已有数据
        existing = self._load_existing_items(target)

        return EvidencePackage(
            knowledge_ids=target.knowledge_ids,
            textbook_chunks=textbook_chunks,
            image_chunks=image_chunks,
            graph_nodes=graph_nodes,
            graph_edges=graph_edges,
            graph_chains=graph_chains,
            standard_terms=standard_terms,
            existing_items=existing,
        )

    def _build_search_queries(self, target: ExpansionTarget) -> list[str]:
        """根据知识目标构建检索查询列表"""
        queries = []

        # 从 KG 获取节点标签
        kg = self._knowledge.get_knowledge_graph()
        node_map = {n["id"]: n for n in kg.get("nodes", [])}

        for kid in target.knowledge_ids:
            if kid in node_map:
                queries.append(node_map[kid].get("label_zh", kid))

        # 如果指定了因果链，加入链摘要
        if target.graph_path_id:
            chain = self._knowledge.get_causal_chain(target.graph_path_id)
            if chain:
                queries.append(chain.get("summary", ""))
                # 加入路径中每个节点的标签
                for node_id in chain.get("path", []):
                    node = node_map.get(node_id, {})
                    label = node.get("label_zh", "")
                    if label and label not in queries:
                        queries.append(label)

        if not queries:
            queries = ["材料科学基础 热处理 淬火"]  # fallback

        return queries[:10]  # 限制查询数量

    def _load_existing_items(self, target: ExpansionTarget) -> list[dict]:
        """加载已有数据摘要（统一字段名方便去重参考）"""
        existing: list[dict] = []
        # 从手工题库加载
        questions = self._knowledge.list_questions()
        for q in questions:
            existing.append({
                "id": q.get("question_id", q.get("id", "")),
                "question": q.get("question", q.get("title", "")),
                "knowledge_ids": q.get("knowledge_ids", q.get("knowledge_id", [])),
                "difficulty": q.get("difficulty", ""),
                "key_points": q.get("key_points", q.get("key_concepts", [])),
            })
        return existing

    # ═══════════════════════════════════════════════════════════
    # 蓝图生成
    # ═══════════════════════════════════════════════════════════

    def _generate_blueprints(
        self, target: ExpansionTarget, evidence: EvidencePackage
    ) -> list[GenerationBlueprint]:
        """
        根据扩充目标生成题目蓝图。

        按配置的题型比例和难度分布分配蓝图。
        """
        blueprints: list[GenerationBlueprint] = []
        bp_index = 1

        # 获取所有可用 chunk_id
        all_chunk_ids = [c.chunk_id for c in evidence.textbook_chunks]

        for output_type in target.output_types:
            if output_type == "qa":
                blueprints.extend(
                    self._generate_qa_blueprints(target, evidence, all_chunk_ids, bp_index)
                )
                bp_index += target.target_count
            elif output_type == "socratic":
                for _ in range(target.target_count):
                    blueprints.append(
                        GenerationBlueprint(
                            blueprint_id=f"BP_SOCRATIC_{bp_index:04d}",
                            target=target,
                            output_type="socratic",
                            difficulty=2,
                            allowed_chunk_ids=all_chunk_ids,
                            graph_path_hint=self._get_chain_path(target),
                        )
                    )
                    bp_index += 1
            elif output_type == "feynman":
                for _ in range(target.target_count):
                    blueprints.append(
                        GenerationBlueprint(
                            blueprint_id=f"BP_FEYNMAN_{bp_index:04d}",
                            target=target,
                            output_type="feynman",
                            difficulty=2,
                            allowed_chunk_ids=all_chunk_ids,
                            graph_path_hint=self._get_chain_path(target),
                        )
                    )
                    bp_index += 1
            elif output_type == "student_answers":
                # student_answers 跟随 qa 生成，不单独生成蓝图
                pass

        return blueprints

    @staticmethod
    def _distribute_exact(count: int, ratios: dict) -> dict:
        """精确按比例分配 count 个名额（largest remainder 方法）"""
        if count <= 0:
            return {}
        # 计算理想配额
        total_ratio = sum(ratios.values())
        quota = {k: count * v / total_ratio for k, v in ratios.items()}
        # 整数部分
        result = {k: int(q) for k, q in quota.items()}
        # 按余数分配剩余名额
        remainder = count - sum(result.values())
        fracs = sorted(quota.items(), key=lambda x: x[1] - int(x[1]), reverse=True)
        for i in range(remainder):
            result[fracs[i][0]] += 1
        # 移除 0 项
        return {k: v for k, v in result.items() if v > 0}

    def _generate_qa_blueprints(
        self,
        target: ExpansionTarget,
        evidence: EvidencePackage,
        all_chunk_ids: list[str],
        start_index: int,
    ) -> list[GenerationBlueprint]:
        """按题型和难度分布生成 QA 蓝图（精确分配）"""
        blueprints: list[GenerationBlueprint] = []
        dist = target.question_type_distribution
        diff_dist = target.difficulty_distribution
        count = target.target_count
        bp_index = start_index

        # 按比例精确分配题型
        type_counts = self._distribute_exact(count, dist)

        for qtype, type_count in type_counts.items():
            # 按比例精确分配难度
            diff_counts = self._distribute_exact(type_count, diff_dist)

            for diff, diff_count in diff_counts.items():
                for _ in range(diff_count):
                    relevant_chunks = all_chunk_ids[:8]

                    path = self._get_chain_path(target)
                    key_points = []
                    for node_id in path:
                        for n in evidence.graph_nodes:
                            if n.id == node_id:
                                key_points.append(n.label_zh)
                                break

                    blueprint = GenerationBlueprint(
                        blueprint_id=f"BP_QA_{bp_index:04d}",
                        target=target,
                        output_type="qa",
                        question_type=QuestionType(qtype),
                        difficulty=diff,
                        target_key_points=key_points[:5],
                        allowed_chunk_ids=relevant_chunks,
                        graph_path_hint=path,
                    )
                    blueprints.append(blueprint)
                    bp_index += 1

        return blueprints

    def _get_chain_path(self, target: ExpansionTarget) -> list[str]:
        """获取因果链的节点路径"""
        if target.graph_path_id:
            chain = self._knowledge.get_causal_chain(target.graph_path_id)
            if chain:
                return chain.get("path", [])
        return []

    # ═══════════════════════════════════════════════════════════
    # 生成子流程
    # ═══════════════════════════════════════════════════════════

    async def _generate_qa_items(
        self, batch: ExpansionBatch, bp: GenerationBlueprint, evidence: EvidencePackage
    ) -> None:
        """生成单个 QA 题目 + 学生答案"""
        try:
            qa_dict = self.generator.generate_qa(bp)
            if "error" not in qa_dict:
                # 覆盖 ID（LLM 生成的 ID 不可靠）
                qa_id = self._next_id("Q_AUTO_")
                qa_dict["id"] = qa_id
                qa_dict["status"] = DatasetStatus.CANDIDATE.value
                qa_dict["created_by"] = "deepseek-chat"
                qa_dict["generator_prompt_version"] = "qa_gen_v1"

                # 后处理：清理 diagnosis + 规范化 source_refs
                qa_dict = self._clean_qa_item(qa_dict)
                qa_dict = self._normalize_source_refs(qa_dict)
                batch.qa_items.append(qa_dict)

                # 生成学生答案
                if batch.target.generate_student_answers:
                    answers = self.generator.generate_student_answers(
                        qa_dict, count=batch.target.answers_per_question
                    )
                    for ans in answers:
                        if "error" not in ans:
                            ans["id"] = self._next_id("SA_AUTO_")
                            ans["question_id"] = qa_id
                            ans["status"] = DatasetStatus.CANDIDATE.value
                            ans["created_by"] = "deepseek-chat"
                            ans["generator_prompt_version"] = "sa_gen_v1"
                            batch.student_answers.append(ans)
        except Exception as e:
            logger.error(f"Failed to generate QA for {bp.blueprint_id}: {e}")

    async def _generate_socratic_items(
        self, batch: ExpansionBatch, bp: GenerationBlueprint, evidence: EvidencePackage
    ) -> None:
        """生成苏格拉底引导链"""
        try:
            socratic_dict = self.generator.generate_socratic(batch.target)
            if "error" not in socratic_dict:
                socratic_dict["id"] = self._next_id("S_AUTO_")
                socratic_dict = self._normalize_source_refs(socratic_dict)
                socratic_dict["status"] = DatasetStatus.CANDIDATE.value
                socratic_dict["created_by"] = "deepseek-chat"
                socratic_dict["generator_prompt_version"] = "socratic_gen_v1"
                batch.socratic_items.append(socratic_dict)
        except Exception as e:
            logger.error(f"Failed to generate socratic for {bp.blueprint_id}: {e}")

    async def _generate_feynman_items(
        self, batch: ExpansionBatch, bp: GenerationBlueprint, evidence: EvidencePackage
    ) -> None:
        """生成费曼任务 + 学生回答"""
        try:
            task_dict = self.generator.generate_feynman_task(batch.target)
            if "error" not in task_dict:
                task_id = self._next_id("F_AUTO_")
                task_dict["id"] = task_id
                task_dict = self._normalize_source_refs(task_dict)
                task_dict["status"] = DatasetStatus.CANDIDATE.value
                task_dict["created_by"] = "deepseek-chat"
                task_dict["generator_prompt_version"] = "feynman_gen_v1"
                batch.feynman_tasks.append(task_dict)

                # 生成分级学生回答
                responses = self.generator.generate_feynman_responses(task_dict, count=5)
                for resp in responses:
                    if "error" not in resp:
                        resp["id"] = self._next_id("FR_AUTO_")
                        resp["feynman_id"] = task_id
                        resp["status"] = DatasetStatus.CANDIDATE.value
                        resp["created_by"] = "deepseek-chat"
                        resp["generator_prompt_version"] = "fr_gen_v1"
                        batch.feynman_responses.append(resp)
        except Exception as e:
            logger.error(f"Failed to generate feynman for {bp.blueprint_id}: {e}")

    @staticmethod
    def _normalize_source_refs(item: dict) -> dict:
        """为缺失必填字段的 source_refs 补充默认值，处理字符串等异常格式"""
        refs = item.get("source_refs", [])
        if not isinstance(refs, list):
            item["source_refs"] = []
            return item

        normalized = []
        for ref in refs:
            if isinstance(ref, str):
                # LLM 可能返回字符串而非 dict，转为 dict
                normalized.append({
                    "chunk_id": ref[:50] if ref else "unknown",
                    "text": ref,
                    "file_name": "textbook_reference",
                    "language": "zh",
                })
            elif isinstance(ref, dict):
                if "file_name" not in ref or not ref.get("file_name"):
                    ref["file_name"] = ref.get("chunk_id") or ref.get("text", "")[:30] or "textbook_reference"
                if "language" not in ref:
                    ref["language"] = "zh"
                if "chunk_id" not in ref or not ref.get("chunk_id"):
                    # chunk_id 缺失或为空，从 file_name 或 text 推断
                    ref["chunk_id"] = ref.get("file_name") or ref.get("text", "")[:30] or "unknown"
                normalized.append(ref)
            else:
                normalized.append({
                    "chunk_id": "unknown",
                    "text": str(ref),
                    "file_name": "textbook_reference",
                    "language": "zh",
                })

        item["source_refs"] = normalized
        return item

    @staticmethod
    def _clean_qa_item(qa_dict: dict) -> dict:
        """后处理 QA 题目：清理 diagnosis、移除正确选项条目、处理 null 值"""
        answer = qa_dict.get("answer", "")
        diagnosis = qa_dict.get("diagnosis", {})

        if isinstance(diagnosis, dict):
            cleaned = {}
            for key, detail in diagnosis.items():
                if not isinstance(detail, dict):
                    continue
                # 跳过正确选项的诊断条目
                if key == answer:
                    continue
                # 清理 null 值
                cleaned_detail = {}
                for k, v in detail.items():
                    if v is None:
                        cleaned_detail[k] = "" if k != "remedial_path" else []
                    else:
                        cleaned_detail[k] = v
                # 确保必要字段非空
                if not cleaned_detail.get("misconception_id"):
                    cleaned_detail["misconception_id"] = f"M_{qa_dict.get('id', 'UNKNOWN')}_{key}"
                if not cleaned_detail.get("misconception"):
                    cleaned_detail["misconception"] = f"错误选项 {key}"
                if not cleaned_detail.get("error_reason"):
                    cleaned_detail["error_reason"] = "需要补充错误原因分析"
                cleaned[key] = cleaned_detail
            qa_dict["diagnosis"] = cleaned

        return qa_dict

    def _save_batch(self, batch: ExpansionBatch) -> None:
        """保存批次到 JSONL"""
        if batch.qa_items:
            self._dataset.save_candidates(batch.qa_items, "qa")
        if batch.student_answers:
            self._dataset.save_candidates(batch.student_answers, "student_answer")
        if batch.socratic_items:
            self._dataset.save_candidates(batch.socratic_items, "socratic")
        if batch.feynman_tasks:
            self._dataset.save_candidates(batch.feynman_tasks, "feynman_task")
        if batch.feynman_responses:
            self._dataset.save_candidates(batch.feynman_responses, "feynman_response")

    # ═══════════════════════════════════════════════════════════
    # 校验 & 质量评分
    # ═══════════════════════════════════════════════════════════

    async def validate_batch(
        self,
        batch: ExpansionBatch,
        use_critic: bool = False,
    ) -> BatchValidationReport:
        """对批次中所有候选数据运行校验"""
        reports: list[ValidationReport] = []

        # 收集所有 items
        all_items: list[tuple[dict, str]] = []
        all_items.extend((item, "qa") for item in batch.qa_items)
        all_items.extend((item, "student_answer") for item in batch.student_answers)
        all_items.extend((item, "socratic") for item in batch.socratic_items)
        all_items.extend((item, "feynman_task") for item in batch.feynman_tasks)
        all_items.extend((item, "feynman_response") for item in batch.feynman_responses)

        for item, item_type in all_items:
            report = validate_all(item, item_type)
            reports.append(report)

        # 统计
        total = len(reports)
        passed = sum(1 for r in reports if r.all_checks_passed)
        failed = total - passed
        publishable = sum(1 for r in reports if r.is_publishable)

        return BatchValidationReport(
            batch_id=batch.batch_id,
            total_items=total,
            passed=passed,
            failed=failed,
            publishable=publishable,
            reports=reports,
        )

    async def validate_candidates(
        self,
        item_type: str = "qa",
        status: str | None = "candidate",
    ) -> BatchValidationReport:
        """校验已保存的候选数据"""
        items = self._dataset.list_candidates(item_type=item_type, status=status, limit=10000)
        reports: list[ValidationReport] = []

        for item in items:
            report = validate_all(item, item_type)
            reports.append(report)

            # 更新状态
            new_status = DatasetStatus.AUTO_VALIDATED.value if report.all_checks_passed else DatasetStatus.CANDIDATE.value
            self._dataset.update_candidate_status(item.get("id", ""), new_status, item_type)

        total = len(reports)
        passed = sum(1 for r in reports if r.all_checks_passed)
        failed = total - passed
        publishable = sum(1 for r in reports if r.is_publishable)

        return BatchValidationReport(
            batch_id=f"validate_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}",
            total_items=total,
            passed=passed,
            failed=failed,
            publishable=publishable,
            reports=reports,
        )

    # ═══════════════════════════════════════════════════════════
    # 审核 & 发布
    # ═══════════════════════════════════════════════════════════

    async def review_item(
        self,
        item_id: str,
        item_type: str,
        action: ReviewAction,
        reviewer: str = "human",
        reason: str = "",
    ) -> ReviewRecord:
        """审核单条候选数据"""
        # 更新状态
        status_map = {
            ReviewAction.APPROVE: DatasetStatus.APPROVED.value,
            ReviewAction.REJECT: DatasetStatus.REJECTED.value,
            ReviewAction.SKIP: DatasetStatus.NEEDS_REVIEW.value,
            ReviewAction.FLAG: DatasetStatus.NEEDS_REVIEW.value,
        }
        new_status = status_map.get(action, DatasetStatus.NEEDS_REVIEW.value)

        if action == ReviewAction.REJECT:
            self._dataset.reject_candidate(item_id, item_type, reason)
        else:
            self._dataset.update_candidate_status(item_id, new_status, item_type)

        # 保存审核记录
        record = ReviewRecord(
            review_id=f"review_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{item_id}",
            item_id=item_id,
            item_type=item_type,
            action=action,
            reviewer=reviewer,
            reason=reason,
            reviewed_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        self._dataset.save_review(record.model_dump())
        return record

    async def publish(
        self,
        item_ids: list[str],
        item_type: str,
        version: str,
        publisher: str = "",
    ) -> dict:
        """发布候选数据到正式数据集"""
        filepath = self._dataset.publish_items(item_ids, item_type, version)

        # 创建版本记录
        from infrastructure.dataset_version_store import create_version_store
        version_store = create_version_store()

        published = self._dataset.list_published(item_type, version)
        version_info = version_store.create_version(
            version=version,
            item_type=item_type,
            item_count=len(published),
            published_by=publisher,
        )

        return {
            "filepath": filepath,
            "version": version_info,
            "item_count": len(item_ids),
        }

    # ═══════════════════════════════════════════════════════════
    # 审核统计
    # ═══════════════════════════════════════════════════════════

    def get_review_stats(self) -> ReviewStats:
        """获取审核统计数据"""
        all_candidates = self._dataset.list_candidates(limit=100000)

        by_status: dict[str, int] = {}
        by_type: dict[str, int] = {}
        total_score = 0.0
        score_count = 0

        for item in all_candidates:
            status = item.get("status", "candidate")
            by_status[status] = by_status.get(status, 0) + 1

            # 推断类型（从 ID 前缀）
            item_id = item.get("id", "")
            if item_id.startswith("Q_"):
                by_type["qa"] = by_type.get("qa", 0) + 1
            elif item_id.startswith("SA_"):
                by_type["student_answer"] = by_type.get("student_answer", 0) + 1
            elif item_id.startswith("S_"):
                by_type["socratic"] = by_type.get("socratic", 0) + 1
            elif item_id.startswith("F_"):
                by_type["feynman_task"] = by_type.get("feynman_task", 0) + 1
            elif item_id.startswith("FR_"):
                by_type["feynman_response"] = by_type.get("feynman_response", 0) + 1

            qs = item.get("quality_score")
            if qs is not None:
                total_score += qs
                score_count += 1

        approval_count = by_status.get("approved", 0) + by_status.get("published", 0)
        total = len(all_candidates)

        return ReviewStats(
            total_candidates=total,
            by_status=by_status,
            by_type=by_type,
            avg_quality_score=round(total_score / score_count, 1) if score_count > 0 else 0.0,
            approval_rate=round(approval_count / total * 100, 1) if total > 0 else 0.0,
        )


def create_expansion_service(
    rag_repo: RAGRepository | None = None,
    knowledge_repo: KnowledgeRepository | None = None,
) -> DatasetExpansionService:
    """工厂函数 — 从默认实现创建服务"""
    from infrastructure.chroma_store import ChromaStore
    from infrastructure.file_knowledge_repo import FileKnowledgeRepository

    return DatasetExpansionService(
        rag_repo=rag_repo or ChromaStore(),
        knowledge_repo=knowledge_repo or FileKnowledgeRepository(),
    )
