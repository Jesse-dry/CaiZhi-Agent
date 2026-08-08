"""
核心评测器 — 7 个度量方法 + 汇总输出。

纯规则驱动，不依赖 LLM。每个 _eval_*() 方法对比服务输出与 ground truth，
返回标准化的 {score, details} dict。

用法:
    from evaluation.evaluator import Evaluator
    ev = Evaluator()
    results = ev.run_all()       # → list[dict], 7 项指标
    report  = ev.format_table(results)  # → 格式化终端表格
"""

from __future__ import annotations

import json
import logging
import traceback
from pathlib import Path
from typing import Any

from evaluation.test_cases import (
    load_qa_cases,
    load_question_tests,
    load_feynman_tests,
    load_socratic_tests,
    load_learning_path_scenarios,
    get_statistics,
)

logger = logging.getLogger(__name__)

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent

# 7 项指标的显示名称和权重
METRIC_META: dict[str, dict[str, Any]] = {
    "retrieval":        {"name": "双语检索指标",         "weight": 0.15},
    "keypoint_coverage": {"name": "回答关键点覆盖率",     "weight": 0.15},
    "causal_chain":      {"name": "因果链完整度",         "weight": 0.15},
    "diagnosis":         {"name": "误区诊断准确率",       "weight": 0.15},
    "socratic":          {"name": "苏格拉底引导匹配率",   "weight": 0.15},
    "feynman":           {"name": "费曼评价一致性",       "weight": 0.15},
    "learning_path":     {"name": "学习路径规则正确率",   "weight": 0.10},
}


class Evaluator:
    """
    自动评测器 — 初始化所有被测服务，运行 7 项度量。

    容错策略: 单个 case 异常不中断评测，在 details 中记录错误信息。
    """

    def __init__(self) -> None:
        # 惰性初始化—首次调用时加载
        self._retriever = None
        self._qas = None      # QA "service" 模块 (函数式)
        self._qa_rule = None  # 规则路径 QAService（llm_client=None，评测不调用 LLM）
        self._stats = get_statistics()

    # ── 惰性属性 ────────────────────────────────────────────

    @property
    def retriever(self):
        if self._retriever is None:
            from rag.bilingual_retriever import BilingualRetriever
            self._retriever = BilingualRetriever()
        return self._retriever

    @property
    def qa_rule(self):
        """规则路径 QAService — 不注入 LLM，走 V1 关键词/图谱 fallback。

        评测基线声称"纯规则驱动、不依赖 LLM"。
        旧版 answer_question() 重构后会强制创建真实 LLM client
        （DeepSeek 网络调用，无超时会导致评测卡死），故这里直接构造
        llm_client=None 的服务，测的是规则引擎本身。
        """
        if self._qa_rule is None:
            from infrastructure.chroma_store import ChromaStore
            from infrastructure.file_knowledge_repo import FileKnowledgeRepository
            from services.qa_service import QAService

            self._qa_rule = QAService(
                rag_repo=ChromaStore(),
                knowledge_repo=FileKnowledgeRepository(),
                llm_client=None,  # 关键：禁用 LLM
            )
        return self._qa_rule

    @staticmethod
    def _unwrap_sr(sr, fallback: dict | None = None) -> dict:
        """把 ServiceResult 拆成普通 dict；失败时返回 fallback 或空 dict。

        ServiceResult 重构后（schemas/common.py），services 返回
        ServiceResult[T] 而非裸 dict。评测器统一在此拆包 .result。
        """
        if sr is not None and getattr(sr, "success", False) and sr.result is not None:
            if isinstance(sr.result, dict):
                return sr.result
            return sr.result.model_dump()
        return fallback if fallback is not None else {}

    @staticmethod
    def _flatten_answer(result: dict) -> str:
        """把 QAResult dict 中的生成文本拼成一段（含因果链步骤）。"""
        parts = [
            result.get("short_answer", ""),
            result.get("principle", ""),
        ]
        for step in result.get("causal_chain", []):
            if isinstance(step, dict):
                parts.append(step.get("label_zh", ""))
                parts.append(step.get("explanation", ""))
        return " ".join(parts).lower()

    # ═══════════════════════════════════════════════════════════
    # 主入口
    # ═══════════════════════════════════════════════════════════

    def run_all(self) -> list[dict]:
        """运行全部 7 项指标，返回标准化的结果列表。"""
        results: list[dict] = []

        for metric_key, meta in METRIC_META.items():
            method = getattr(self, f"_eval_{metric_key}", None)
            if method is None:
                logger.warning("Unknown metric: %s", metric_key)
                continue

            try:
                score_detail = method()
            except Exception as exc:
                logger.exception("Metric %s failed", metric_key)
                score_detail = {
                    "score": 0.0,
                    "details": {"error": str(exc), "traceback": traceback.format_exc()},
                }

            score_detail["metric_key"] = metric_key
            score_detail["name"] = meta["name"]
            score_detail["weight"] = meta["weight"]
            results.append(score_detail)

        return results

    def run_one(self, metric_key: str) -> dict | None:
        """运行单项指标。"""
        meta = METRIC_META.get(metric_key)
        if meta is None:
            logger.error("Unknown metric: %s", metric_key)
            return None

        method = getattr(self, f"_eval_{metric_key}", None)
        if method is None:
            return None

        result = method()
        result["metric_key"] = metric_key
        result["name"] = meta["name"]
        result["weight"] = meta["weight"]
        return result

    def format_table(self, results: list[dict]) -> str:
        """格式化为终端表格。"""
        lines: list[str] = []
        sep = "=" * 63
        thin = "-" * 63

        lines.append(sep)
        lines.append("          材智 Agent 自动评测基线报告")
        lines.append(sep)
        stats = self._stats
        lines.append(
            f"测试用例: {stats['qa_cases']} QA cases / "
            f"{stats['question_test_points']} question tests / "
            f"{stats['feynman_excellent']}×3 feynman tests / "
            f"{stats['socratic_test_points']} socratic tests / "
            f"{stats['learning_path_scenarios']} path scenarios"
        )
        lines.append("")

        # 表头
        lines.append(f"  {'#':<2} {'指标':<22} {'得分':<8} {'说明':<30}")
        lines.append(f"  {thin}")

        total_weighted = 0.0
        total_weight = 0.0

        for i, r in enumerate(results, 1):
            score = r.get("score", 0.0)
            name = r.get("name", "?")
            weight = r.get("weight", 0.0)
            note = r.get("details", {}).get("note", self._score_note(score))
            # 截断说明文字
            note_short = note[:28] + ".." if len(note) > 30 else note

            bar = self._score_bar(score)
            lines.append(f"  {i:<2} {name:<22} {score:>5.1f}% {bar} {note_short:<30}")

            total_weighted += score * weight
            total_weight += weight

        lines.append(f"  {thin}")

        if total_weight > 0:
            overall = total_weighted / total_weight
            bar = self._score_bar(overall)
            lines.append(f"  {'':<2} {'综合得分':<22} {overall:>5.1f}% {bar} (加权平均)")

        lines.append(sep)

        # 局限说明
        lines.append("")
        lines.append("  已知局限:")
        lines.append("    1. 苏格拉底链仅 S001 测试（S002-S010 数据缺失）")
        lines.append("    2. 因果链仅 C001 存在定义（C002-C010 缺失）")
        lines.append("    3. 检索用关键词命中率近似（无精确 chunk ground truth）")
        lines.append("    4. 评测走 V1 规则引擎（不注入 LLM）；Agent 层需单独评测")
        lines.append("    5. 费曼维度映射为 F001 特化，F002-F010 维度分配可能不准")
        lines.append("")

        return "\n".join(lines)

    def format_json(self, results: list[dict]) -> str:
        """格式化为 JSON。"""
        output = {
            "statistics": self._stats,
            "metrics": [],
            "overall_score": None,
        }

        total_weighted = 0.0
        total_weight = 0.0

        for r in results:
            entry = {
                "metric_key": r["metric_key"],
                "name": r["name"],
                "score": r["score"],
                "weight": r["weight"],
                "details": r.get("details", {}),
            }
            output["metrics"].append(entry)
            total_weighted += r["score"] * r["weight"]
            total_weight += r["weight"]

        if total_weight > 0:
            output["overall_score"] = round(total_weighted / total_weight, 1)

        return json.dumps(output, ensure_ascii=False, indent=2)

    # ═══════════════════════════════════════════════════════════
    # 1. 双语检索指标
    # ═══════════════════════════════════════════════════════════

    def _eval_retrieval(self) -> dict:
        """
        对 10 个 case 各做中英文检索，用 retrieval_keywords 在返回 chunk
        文本中的命中率作为 recall 近似。
        """
        cases = load_qa_cases()
        if not cases:
            return {"score": 0.0, "details": {"error": "No QA cases loaded"}}

        zh_hits: list[float] = []
        en_hits: list[float] = []
        empty_count = 0
        case_details: list[dict] = []

        for case in cases:
            cid = case.get("case_id", "?")
            question_zh = case.get("question_zh", "")
            question_en = case.get("question_en", "")
            kw_zh = case.get("retrieval_keywords_zh", [])
            kw_en = case.get("retrieval_keywords_en", [])

            # 中文检索
            zh_recall = 0.0
            try:
                result = self.retriever.retrieve(question_zh, top_k_each=5)
                zh_contexts = result.get("zh_contexts", [])
                zh_recall = self._keyword_recall(zh_contexts, kw_zh)
                zh_hits.append(zh_recall)

                if not zh_contexts:
                    empty_count += 1
            except Exception as exc:
                logger.warning("ZH retrieval failed for %s: %s", cid, exc)
                zh_hits.append(0.0)

            # 英文检索
            en_recall = 0.0
            try:
                result = self.retriever.retrieve(question_en, top_k_each=5)
                en_contexts = result.get("en_contexts", [])
                en_recall = self._keyword_recall(en_contexts, kw_en)
                en_hits.append(en_recall)
            except Exception as exc:
                logger.warning("EN retrieval failed for %s: %s", cid, exc)
                en_hits.append(0.0)

            case_details.append({
                "case_id": cid,
                "zh_recall": round(zh_recall * 100, 1),
                "en_recall": round(en_recall * 100, 1),
            })

        avg_zh = sum(zh_hits) / len(zh_hits) * 100 if zh_hits else 0.0
        avg_en = sum(en_hits) / len(en_hits) * 100 if en_hits else 0.0
        avg = (avg_zh + avg_en) / 2
        empty_rate = empty_count / len(cases) * 100 if cases else 0.0

        return {
            "score": round(avg, 1),
            "details": {
                "zh_recall_pct": round(avg_zh, 1),
                "en_recall_pct": round(avg_en, 1),
                "avg_recall_pct": round(avg, 1),
                "empty_rate_pct": round(empty_rate, 1),
                "case_details": case_details,
                "note": f"关键词命中率近似 Recall (ZH={avg_zh:.1f}% EN={avg_en:.1f}%)",
            },
        }

    @staticmethod
    def _keyword_recall(contexts: list[dict], keywords: list[str]) -> float:
        """在检索结果中计算关键词命中率。"""
        if not keywords:
            return 0.0
        all_text = " ".join(
            ctx.get("text", "") for ctx in (contexts or [])
        ).lower()
        hits = sum(1 for kw in keywords if kw.lower() in all_text)
        return hits / len(keywords)

    # ═══════════════════════════════════════════════════════════
    # 2. 回答关键点覆盖率
    # ═══════════════════════════════════════════════════════════

    def _eval_keypoint_coverage(self) -> dict:
        """
        对 10 个 case 调用 qa_rule.answer(), 检查返回文本中
        expected_key_points 的覆盖比例。
        """
        import asyncio

        from schemas.qa import QARequest

        cases = load_qa_cases()
        if not cases:
            return {"score": 0.0, "details": {"error": "No QA cases loaded"}}

        coverages: list[float] = []
        case_details: list[dict] = []

        for case in cases:
            cid = case.get("case_id", "?")
            question = case.get("question_zh", "")
            expected_points = case.get("expected_key_points", [])

            cov = 0.0
            covered: list[str] = []
            missed: list[str] = []

            try:
                req = QARequest(session_id="eval", question=question)
                sr = asyncio.run(self.qa_rule.answer(req))
                result = self._unwrap_sr(sr)
                # 合并所有生成文本（V1 用 graph summary + 因果链步骤）
                answer_text = self._flatten_answer(result)

                for point in expected_points:
                    if self._text_covers_point(answer_text, point):
                        covered.append(point)
                    else:
                        missed.append(point)

                cov = len(covered) / len(expected_points) if expected_points else 1.0
            except Exception as exc:
                logger.warning("Keypoint coverage failed for %s: %s", cid, exc)

            coverages.append(cov)
            case_details.append({
                "case_id": cid,
                "coverage_pct": round(cov * 100, 1),
                "covered_points": covered,
                "missed_points": missed,
            })

        avg_coverage = sum(coverages) / len(coverages) * 100 if coverages else 0.0

        return {
            "score": round(avg_coverage, 1),
            "details": {
                "avg_coverage_pct": round(avg_coverage, 1),
                "case_details": case_details,
                "note": f"V1 占位文本覆盖率 {avg_coverage:.1f}%（LLM 接入后可提升）",
            },
        }

    @staticmethod
    def _text_covers_point(text: str, point: str) -> bool:
        """检查文本是否覆盖了某个 key point（关键词交集法）。"""
        # 从 point 中提取关键实词
        keywords = [w for w in point if len(w) >= 2 and not w.isspace()]
        # 简化：取 point 中的 2-3 字片段做匹配
        # 更好的办法：直接检查较长的子串
        # 用滑动窗口取 3-4 字的片段
        point_clean = point.replace(" ", "").lower()
        text_clean = text.replace(" ", "").lower()

        # 取 3-gram 匹配
        if len(point_clean) <= 4:
            return point_clean in text_clean

        # 取 3-4 字的子串，至少一半匹配则视为覆盖
        n = min(4, len(point_clean) // 2)
        fragments: list[str] = []
        for i in range(0, len(point_clean) - n + 1, max(1, n // 2)):
            frag = point_clean[i:i + n]
            if len(frag) >= 2:
                fragments.append(frag)

        if not fragments:
            return point_clean in text_clean

        matched = sum(1 for frag in fragments if frag in text_clean)
        return matched / len(fragments) >= 0.5

    # ═══════════════════════════════════════════════════════════
    # 3. 因果链完整度
    # ═══════════════════════════════════════════════════════════

    def _eval_causal_chain(self) -> dict:
        """
        对 10 个 case 调用 match_chain(), 检查:
        - chain_id 是否匹配 expected_chain_id
        - 返回 answer 中是否包含链节点的关键标签
        """
        import asyncio

        from knowledge.knowledge_graph import match_chain, get_chain_by_id, load_knowledge_graph
        from schemas.qa import QARequest

        cases = load_qa_cases()
        graph = load_knowledge_graph()
        node_map = {n["id"]: n for n in graph.get("nodes", [])}

        chain_matches = 0
        node_coverages: list[float] = []
        case_details: list[dict] = []

        for case in cases:
            cid = case.get("case_id", "?")
            question = case.get("question_zh", "")
            expected_chain_id = case.get("expected_chain_id", "")

            # 匹配因果链
            chain = match_chain(question)
            matched_id = chain.get("chain_id", "") if chain else ""
            is_match = (matched_id == expected_chain_id)
            if is_match:
                chain_matches += 1

            # 节点覆盖：检查 answer 文本中是否包含链节点标签
            node_cov = 0.0
            nodes_covered: list[str] = []
            nodes_missed: list[str] = []

            try:
                req = QARequest(session_id="eval", question=question)
                sr = asyncio.run(self.qa_rule.answer(req))
                result = self._unwrap_sr(sr)
                answer_text = " ".join([
                    result.get("short_answer", ""),
                    result.get("principle", ""),
                ]).lower()

                chain_obj = get_chain_by_id(expected_chain_id) or chain
                if chain_obj:
                    for node_id in chain_obj.get("path", []):
                        node = node_map.get(node_id, {})
                        label = node.get("label_zh", node_id).lower()
                        if label in answer_text:
                            nodes_covered.append(node_id)
                        else:
                            nodes_missed.append(node_id)

                    total_nodes = len(chain_obj.get("path", []))
                    node_cov = len(nodes_covered) / total_nodes if total_nodes > 0 else 0.0
            except Exception as exc:
                logger.warning("Node coverage failed for %s: %s", cid, exc)

            node_coverages.append(node_cov)
            case_details.append({
                "case_id": cid,
                "expected_chain": expected_chain_id,
                "matched_chain": matched_id,
                "chain_match": is_match,
                "node_coverage_pct": round(node_cov * 100, 1),
                "nodes_covered": nodes_covered,
                "nodes_missed": nodes_missed,
            })

        chain_match_rate = chain_matches / len(cases) * 100 if cases else 0.0
        avg_node_cov = sum(node_coverages) / len(node_coverages) * 100 if node_coverages else 0.0
        score = (chain_match_rate * 0.3 + avg_node_cov * 0.7)  # chain_id 匹配权重 30%，节点覆盖 70%

        return {
            "score": round(score, 1),
            "details": {
                "chain_match_rate_pct": round(chain_match_rate, 1),
                "avg_node_coverage_pct": round(avg_node_cov, 1),
                "case_details": case_details,
                "note": f"C001 匹配率 {chain_match_rate:.0f}%（仅 C001 存在；C002-C010 缺失）",
            },
        }

    # ═══════════════════════════════════════════════════════════
    # 4. 误区诊断准确率
    # ═══════════════════════════════════════════════════════════

    def _eval_diagnosis(self) -> dict:
        """
        对 10 道题的 40 个测试点调用 submit_answer(), 验证:
        - 正确答案 → is_correct=True
        - 错误选项 → misconception 非空、missing_concepts 非空、remedial_path 非空
        """
        from services.diagnosis_service import submit_answer

        test_points = load_question_tests()
        if not test_points:
            return {"score": 0.0, "details": {"error": "No question tests loaded"}}

        correct_tests = [p for p in test_points if p["is_correct_expected"]]
        wrong_tests = [p for p in test_points if not p["is_correct_expected"]]

        # 正确选项测试
        correct_ok = 0
        for p in correct_tests:
            try:
                r = self._unwrap_sr(submit_answer(p["question_id"], p["option"]))
                if r.get("is_correct") is True:
                    correct_ok += 1
            except Exception as exc:
                logger.warning("Diagnosis correct test failed %s/%s: %s", p["question_id"], p["option"], exc)

        correct_acc = correct_ok / len(correct_tests) * 100 if correct_tests else 100.0

        # 错误选项测试: misconception / missing_concepts / remedial_path 非空
        wrong_misconception_ok = 0
        wrong_missing_ok = 0
        wrong_path_ok = 0
        wrong_all_ok = 0

        for p in wrong_tests:
            try:
                r = self._unwrap_sr(submit_answer(p["question_id"], p["option"]))
                has_misconception = bool(r.get("misconception", ""))
                has_missing = bool(r.get("missing_concepts", []))
                has_path = bool(r.get("remedial_path", []))

                if has_misconception:
                    wrong_misconception_ok += 1
                if has_missing:
                    wrong_missing_ok += 1
                if has_path:
                    wrong_path_ok += 1
                if has_misconception and has_missing and has_path:
                    wrong_all_ok += 1
            except Exception as exc:
                logger.warning("Diagnosis wrong test failed %s/%s: %s", p["question_id"], p["option"], exc)

        n_wrong = len(wrong_tests) if wrong_tests else 1
        misconception_cov = wrong_misconception_ok / n_wrong * 100
        missing_cov = wrong_missing_ok / n_wrong * 100
        path_cov = wrong_path_ok / n_wrong * 100
        all_cov = wrong_all_ok / n_wrong * 100

        # 综合得分: 正确识别 50% + 错误诊断完整性 50%
        score = correct_acc * 0.5 + (
            misconception_cov * 0.2 + missing_cov * 0.15 + path_cov * 0.15
        )

        return {
            "score": round(score, 1),
            "details": {
                "correct_answer_accuracy_pct": round(correct_acc, 1),
                "misconception_coverage_pct": round(misconception_cov, 1),
                "missing_concepts_coverage_pct": round(missing_cov, 1),
                "remedial_path_coverage_pct": round(path_cov, 1),
                "all_fields_coverage_pct": round(all_cov, 1),
                "total_correct_tests": len(correct_tests),
                "total_wrong_tests": len(wrong_tests),
                "note": f"正确识别 {correct_acc:.0f}% / 错误诊断完整性 {all_cov:.0f}%",
            },
        }

    # ═══════════════════════════════════════════════════════════
    # 5. 苏格拉底引导匹配率
    # ═══════════════════════════════════════════════════════════

    def _eval_socratic(self) -> dict:
        """
        对 S001 的 18 个测试点调用 judge_answer(), 验证:
        - 完整回答 → advance
        - 部分回答 → hint 或 retry
        - 空回答 → retry
        """
        from services.socratic_service import judge_answer

        test_points = load_socratic_tests()
        if not test_points:
            return {"score": 0.0, "details": {"error": "No socratic tests loaded"}}

        correct = 0
        step_details: list[dict] = []

        for p in test_points:
            step = p["step"]
            expected_action = p["expected_action"]
            step_id = step.get("step", 0)

            try:
                result = self._unwrap_sr(
                    judge_answer(step, p["student_answer"], p["attempt_count"])
                )
                actual_action = result.get("action", "?")

                # expected_action 可能是字符串或集合
                if isinstance(expected_action, set):
                    is_correct = actual_action in expected_action
                else:
                    is_correct = (actual_action == expected_action)

                if is_correct:
                    correct += 1

                step_details.append({
                    "step_id": step_id,
                    "test_type": (
                        "complete" if expected_action == "advance" else
                        "partial" if isinstance(expected_action, set) else
                        "empty"
                    ),
                    "student_answer_preview": p["student_answer"][:30],
                    "expected_action": (
                        list(expected_action) if isinstance(expected_action, set)
                        else expected_action
                    ),
                    "actual_action": actual_action,
                    "correct": is_correct,
                })
            except Exception as exc:
                logger.warning("Socratic test failed step %s: %s", step_id, exc)
                step_details.append({
                    "step_id": step_id,
                    "error": str(exc),
                    "correct": False,
                })

        total = len(test_points)
        accuracy = correct / total * 100 if total > 0 else 0.0

        return {
            "score": round(accuracy, 1),
            "details": {
                "action_accuracy_pct": round(accuracy, 1),
                "correct_actions": correct,
                "total_actions": total,
                "step_details": step_details,
                "note": f"S001 的 6 步 × 3 种回答 = 18 测试点，准确 {correct}/{total}",
            },
        }

    # ═══════════════════════════════════════════════════════════
    # 6. 费曼评价一致性
    # ═══════════════════════════════════════════════════════════

    def _eval_feynman(self) -> dict:
        """
        对每条 rubric 的 3 种输入验证 score 单调性:
        score(excellent) > score(partial) > score(empty)
        """
        from services.feynman_service import evaluate

        test_points = load_feynman_tests()
        if not test_points:
            return {"score": 0.0, "details": {"error": "No feynman tests loaded"}}

        # 按 feynman_id 分组
        groups: dict[str, dict[str, Any]] = {}
        for p in test_points:
            fid = p["feynman_id"]
            if fid not in groups:
                groups[fid] = {}
            groups[fid][p["test_type"]] = p

        monotonic_ok = 0
        excellent_pass = 0
        rubric_details: list[dict] = []

        for fid, group in groups.items():
            scores: dict[str, float] = {}

            for ttype in ["excellent", "partial", "empty"]:
                tp = group.get(ttype)
                if tp is None:
                    scores[ttype] = 0.0
                    continue

                try:
                    result = self._unwrap_sr(evaluate(tp["explanation"], fid))
                    scores[ttype] = result.get("total_score", 0)
                except Exception as exc:
                    logger.warning("Feynman test failed %s/%s: %s", fid, ttype, exc)
                    scores[ttype] = 0.0

            # 单调性: excellent > partial > empty
            is_monotonic = (
                scores["excellent"] > scores["partial"] > scores["empty"]
            )
            if is_monotonic:
                monotonic_ok += 1

            # 优秀范例得分阈值
            if scores["excellent"] >= 55:  # 55/78 ≈ 70/100
                excellent_pass += 1

            rubric_details.append({
                "feynman_id": fid,
                "score_excellent": round(scores["excellent"], 1),
                "score_partial": round(scores["partial"], 1),
                "score_empty": round(scores["empty"], 1),
                "monotonic": is_monotonic,
                "excellent_pass": scores["excellent"] >= 55,
            })

        n_rubrics = len(groups) if groups else 1
        monotonicity = monotonic_ok / n_rubrics * 100
        excellent_rate = excellent_pass / n_rubrics * 100
        score = monotonicity * 0.6 + excellent_rate * 0.4

        return {
            "score": round(score, 1),
            "details": {
                "monotonicity_pct": round(monotonicity, 1),
                "excellent_threshold_pass_pct": round(excellent_rate, 1),
                "rubric_details": rubric_details,
                "note": f"单调性 {monotonic_ok}/{len(groups)} / 优秀范例通过 {excellent_pass}/{len(groups)}",
            },
        }

    # ═══════════════════════════════════════════════════════════
    # 7. 学习路径规则正确率
    # ═══════════════════════════════════════════════════════════

    def _eval_learning_path(self) -> dict:
        """
        对 5 个场景调用 generate_learning_path(), 验证:
        - 先修关系合规（K002 在 K001 之后，K003 在 K002/K004 之后，K004 在 K001 之后）
        - current_level 合理性
        """
        from services.recommendation_service import generate_learning_path

        scenarios = load_learning_path_scenarios()
        if not scenarios:
            return {"score": 0.0, "details": {"error": "No learning path scenarios"}}

        prereq_ok = 0
        level_ok = 0
        scenario_details: list[dict] = []

        for sc in scenarios:
            checks = sc.get("checks", {})

            try:
                result = self._unwrap_sr(
                    generate_learning_path(
                        diagnosis_result=sc.get("diagnosis_result"),
                        socratic_result=sc.get("socratic_result"),
                        feynman_result=sc.get("feynman_result"),
                    )
                )

                steps = result.get("recommended_steps", [])
                step_ids = [s.get("knowledge_id", "") for s in steps]
                actual_level = result.get("current_level", "")

                # 先修关系验证
                prereq_pass = self._check_prerequisites(step_ids)
                if prereq_pass:
                    prereq_ok += 1

                # current_level 验证
                expected_level = checks.get("expected_level", "")
                level_pass = (actual_level == expected_level) if expected_level else True
                if level_pass:
                    level_ok += 1

                # 期望的 knowledge_ids 顺序检查
                expected_ids = checks.get("expected_knowledge_ids")
                ids_match = True
                if expected_ids:
                    ids_match = (step_ids == expected_ids)

                scenario_details.append({
                    "scenario": sc["scenario"],
                    "description": sc["description"],
                    "recommended_steps": step_ids,
                    "current_level": actual_level,
                    "expected_level": expected_level,
                    "prereq_pass": prereq_pass,
                    "level_pass": level_pass,
                    "ids_match": ids_match if expected_ids else None,
                    "has_steps": len(steps) > 0,
                })
            except Exception as exc:
                logger.warning("Learning path test failed %s: %s", sc["scenario"], exc)
                scenario_details.append({
                    "scenario": sc["scenario"],
                    "error": str(exc),
                    "prereq_pass": False,
                    "level_pass": False,
                })

        n = len(scenarios) if scenarios else 1
        prereq_rate = prereq_ok / n * 100
        level_rate = level_ok / n * 100
        score = prereq_rate * 0.7 + level_rate * 0.3

        return {
            "score": round(score, 1),
            "details": {
                "prereq_compliance_pct": round(prereq_rate, 1),
                "level_accuracy_pct": round(level_rate, 1),
                "scenario_details": scenario_details,
                "note": f"先修合规 {prereq_ok}/{len(scenarios)} / 等级判定 {level_ok}/{len(scenarios)}",
            },
        }

    @staticmethod
    def _check_prerequisites(step_ids: list[str]) -> bool:
        """
        验证推荐步骤的先修关系:
        - K002 依赖 K001 → K002 必须在 K001 之后
        - K004 依赖 K001 → K004 必须在 K001 之后
        - K003 依赖 K002 + K004 → K003 必须在两者之后
        """
        # 获取每个 ID 的索引
        positions: dict[str, int] = {}
        for i, sid in enumerate(step_ids):
            positions[sid] = i

        # K002 在 K001 之后
        if "K002" in positions and "K001" in positions:
            if positions["K002"] <= positions["K001"]:
                return False

        # K004 在 K001 之后
        if "K004" in positions and "K001" in positions:
            if positions["K004"] <= positions["K001"]:
                return False

        # K003 在 K002 之后
        if "K003" in positions and "K002" in positions:
            if positions["K003"] <= positions["K002"]:
                return False

        # K003 在 K004 之后
        if "K003" in positions and "K004" in positions:
            if positions["K003"] <= positions["K004"]:
                return False

        return True

    # ═══════════════════════════════════════════════════════════
    # 内部工具
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _score_bar(score: float, width: int = 8) -> str:
        """ASCII 分数条: [====    ]"""
        filled = int(round(score / 100 * width))
        empty = width - filled
        return "[" + "=" * filled + " " * empty + "]"

    @staticmethod
    def _score_note(score: float) -> str:
        """分数等级描述。"""
        if score >= 90:
            return "优秀"
        elif score >= 75:
            return "良好"
        elif score >= 60:
            return "及格"
        else:
            return "待改进"
