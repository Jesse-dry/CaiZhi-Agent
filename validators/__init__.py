"""
校验器包 — 确定性自动校验（不依赖 LLM）。

5 个校验器：
  - schema_validator:    Pydantic schema + 字段约束
  - evidence_validator:  source_refs 在 ChromaDB 中真实存在
  - graph_validator:     graph_path 与 KG 边关系一致
  - terminology_validator: 术语在 terms.csv 中
  - duplicate_validator: 三层去重

统一入口：validate_all() — 运行所有 5 项检查，返回 ValidationReport。
"""

from validators.schema_validator import validate_item as validate_schema
from validators.evidence_validator import validate_evidence
from validators.graph_validator import validate_graph_in_item
from validators.terminology_validator import validate_terminology_in_item
from validators.duplicate_validator import check_duplicates

from schemas.validation_report import ValidationReport


def validate_all(
    data: dict,
    item_type: str,
    existing_items: list[dict] | None = None,
) -> ValidationReport:
    """
    对单条候选数据运行全部 5 项确定性检查。

    参数:
        data: 候选数据 dict
        item_type: "qa" | "student_answer" | "socratic" | "feynman_task" | "feynman_response"
        existing_items: 已有数据列表（用于去重，None 则自动加载）

    返回:
        ValidationReport
    """
    item_id = data.get("id", "unknown")
    report = ValidationReport(item_id=item_id, item_type=item_type)

    # 1. Schema 校验
    report.schema_valid, report.schema_errors = validate_schema(data, item_type)

    # 2. 证据校验
    report.evidence_valid, report.evidence_errors, report.missing_chunk_ids = (
        validate_evidence(data, item_type)
    )

    # 3. 图谱校验
    report.graph_consistent, report.graph_errors, report.invalid_nodes = (
        validate_graph_in_item(data, item_type)
    )

    # 4. 术语校验
    report.terminology_valid, report.terminology_errors, report.unknown_terms = (
        validate_terminology_in_item(data, item_type)
    )

    # 5. 去重
    report.duplicate_detected, report.duplicate_similarity, report.similar_item_ids = (
        check_duplicates(data, existing_items)
    )

    # 汇总
    report.errors = (
        report.schema_errors
        + report.evidence_errors
        + report.graph_errors
        + report.terminology_errors
    )
    # 去重不算 error，算 warning
    if report.duplicate_detected:
        report.warnings.append(
            f"疑似重复（相似度 {report.duplicate_similarity:.2f}），"
            f"相似条目: {report.similar_item_ids}"
        )

    return report


__all__ = [
    "validate_all",
    "validate_schema",
    "validate_evidence",
    "validate_graph_in_item",
    "validate_terminology_in_item",
    "check_duplicates",
]
