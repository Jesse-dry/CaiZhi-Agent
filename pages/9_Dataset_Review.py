"""
数据集审核页面 — 人工审核候选数据。

布局：
  左侧：候选数据列表 + 过滤器
  右侧：详情 + 证据面板 + 操作按钮

功能：
  - 按类型/状态/质量分/校验结果过滤
  - 逐条审核（批准/拒绝/标记）
  - 查看教材原文、KG 路径、术语表、校验结果
  - 批量操作
  - 统计面板
"""

import streamlit as st
import json
import sys
from pathlib import Path
from datetime import datetime, UTC

# 添加项目根目录
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schemas.dataset_item import DatasetStatus
from schemas.dataset_review import ReviewAction
from infrastructure.jsonl_dataset_repo import create_jsonl_dataset_repo
from validators import validate_all
from validators.evidence_validator import clear_cache as clear_evidence_cache
from validators.graph_validator import clear_kg_cache
from validators.terminology_validator import clear_terms_cache
from services.dataset_expansion_service import DatasetExpansionService
from schemas.generation_blueprint import ExpansionTarget

st.set_page_config(page_title="数据集审核", page_icon="📋", layout="wide")


# ═══════════════════════════════════════════════════════════
# 初始化
# ═══════════════════════════════════════════════════════════

@st.cache_resource
def get_dataset_repo():
    return create_jsonl_dataset_repo()


def init_session():
    """初始化 session state"""
    defaults = {
        "review_filter_type": "all",
        "review_filter_status": "all",
        "review_filter_verdict": "all",
        "review_selected_id": None,
        "review_page_offset": 0,
        "review_page_size": 20,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_session()
repo = get_dataset_repo()


# ═══════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════

def load_candidates(item_type: str | None = None, status: str | None = None) -> list[dict]:
    """加载候选数据"""
    return repo.list_candidates(
        item_type=item_type if item_type != "all" else None,
        status=status if status != "all" else None,
        limit=2000,
    )


def get_item_display_text(item: dict) -> str:
    """获取条目的显示文本"""
    # QA
    if "question" in item and "options" in item:
        return item["question"][:100]
    # Student answer
    if "student_answer" in item:
        return item["student_answer"][:100]
    # Socratic
    if "steps" in item:
        return item.get("title", item.get("id", ""))[:100]
    # Feynman task
    if "prompt" in item and "mandatory_points" in item:
        return item.get("prompt", "")[:100]
    # Feynman response
    if "response" in item and "feynman_id" in item:
        return item["response"][:100]
    return item.get("id", "unknown")[:100]


def get_item_type_from_id(item: dict) -> str:
    """从 ID 推断类型"""
    item_id = item.get("id", "")
    if item_id.startswith("Q_"):
        return "qa"
    elif item_id.startswith("SA_"):
        return "student_answer"
    elif item_id.startswith("S_"):
        return "socratic"
    elif item_id.startswith("F_"):
        return "feynman_task"
    elif item_id.startswith("FR_"):
        return "feynman_response"
    return "unknown"


def run_validation(item: dict, item_type: str):
    """对单条数据运行校验"""
    clear_evidence_cache()
    clear_kg_cache()
    clear_terms_cache()
    report = validate_all(item, item_type)
    return report


# ═══════════════════════════════════════════════════════════
# 侧边栏 — 过滤器
# ═══════════════════════════════════════════════════════════

with st.sidebar:
    st.title("📋 数据集审核")

    # 统计面板
    st.subheader("📊 统计")
    candidates = load_candidates()
    total = len(candidates)

    by_status = {}
    for c in candidates:
        s = c.get("status", "candidate")
        by_status[s] = by_status.get(s, 0) + 1

    col1, col2 = st.columns(2)
    with col1:
        st.metric("候选总数", total)
        st.metric("已批准", by_status.get("approved", 0))
        st.metric("已拒绝", by_status.get("rejected", 0))
    with col2:
        st.metric("待审核", by_status.get("candidate", 0) + by_status.get("auto_validated", 0) + by_status.get("needs_review", 0))
        st.metric("已发布", by_status.get("published", 0))
        st.metric("已废弃", by_status.get("deprecated", 0))

    st.divider()

    # 过滤器
    st.subheader("🔍 过滤")

    item_type = st.selectbox(
        "数据类型",
        ["all", "qa", "student_answer", "socratic", "feynman_task", "feynman_response"],
        key="review_filter_type",
    )

    status = st.selectbox(
        "状态",
        ["all", "candidate", "auto_validated", "needs_review", "approved", "rejected", "published"],
        key="review_filter_status",
    )

    st.divider()

    # 生成新数据
    st.subheader("🔄 生成新数据")
    with st.expander("扩充设置"):
        gen_knowledge_ids = st.text_input("知识点 ID（逗号分隔）", value="K_QUENCHING,K_MARTENSITE")
        gen_count = st.number_input("生成数量", min_value=1, max_value=50, value=5)
        gen_types = st.multiselect(
            "数据类型",
            ["qa", "student_answers", "socratic", "feynman"],
            default=["qa", "student_answers"],
        )

        if st.button("🚀 开始生成", type="primary", use_container_width=True):
            with st.spinner("正在生成候选数据..."):
                try:
                    knowledge_ids = [k.strip() for k in gen_knowledge_ids.split(",") if k.strip()]
                    target = ExpansionTarget(
                        knowledge_ids=knowledge_ids,
                        graph_path_id="C001",
                        output_types=gen_types,
                        target_count=gen_count,
                        generate_student_answers="student_answers" in gen_types,
                    )

                    # 创建 service 并运行
                    from infrastructure.chroma_store import ChromaStore
                    from infrastructure.file_knowledge_repo import FileKnowledgeRepository

                    service = DatasetExpansionService(
                        rag_repo=ChromaStore(),
                        knowledge_repo=FileKnowledgeRepository(),
                        dataset_repo=repo,
                    )

                    import asyncio
                    batch = asyncio.run(service.run_full_pipeline(target, use_critic=False))
                    st.success(
                        f"生成完成！\n"
                        f"- QA 题目：{len(batch.qa_items)}\n"
                        f"- 学生答案：{len(batch.student_answers)}\n"
                        f"- 苏格拉底链：{len(batch.socratic_items)}\n"
                        f"- 费曼任务：{len(batch.feynman_tasks)}\n"
                        f"- 费曼回答：{len(batch.feynman_responses)}"
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"生成失败：{e}")

    st.divider()

    # 发布
    st.subheader("📦 发布")
    with st.expander("发布设置"):
        pub_version = st.text_input("版本号", value=datetime.now(UTC).strftime("%Y.%m.%d"))
        pub_type = st.selectbox("发布类型", ["qa", "socratic", "feynman_task"])

        if st.button("📤 发布所有已批准数据", use_container_width=True):
            approved = [
                c for c in candidates
                if c.get("status") == "approved" and get_item_type_from_id(c) == pub_type
            ]
            if approved:
                repo.publish_items(
                    [a["id"] for a in approved],
                    pub_type,
                    pub_version,
                )
                st.success(f"已发布 {len(approved)} 条数据到 v{pub_version}")
                st.rerun()
            else:
                st.warning("没有已批准的数据")


# ═══════════════════════════════════════════════════════════
# 主区域 — 候选列表 + 详情
# ═══════════════════════════════════════════════════════════

# 加载过滤后的候选数据
filtered = load_candidates(
    item_type=item_type if item_type != "all" else None,
    status=status if status != "all" else None,
)

# 分页
page_size = st.session_state.review_page_size
total_pages = max(1, (len(filtered) + page_size - 1) // page_size)
offset = st.session_state.review_page_offset

# 分页控制
col_page, col_count = st.columns([3, 1])
with col_page:
    if total_pages > 1:
        page = st.number_input(
            "页码", min_value=1, max_value=total_pages,
            value=offset // page_size + 1,
            key="review_page_num",
        )
        offset = (page - 1) * page_size
        st.session_state.review_page_offset = offset
with col_count:
    st.caption(f"共 {len(filtered)} 条")

page_items = filtered[offset:offset + page_size]

# 两栏布局
col_left, col_right = st.columns([1, 2])

with col_left:
    st.subheader("候选列表")

    if not page_items:
        st.info("暂无候选数据。点击左侧「开始生成」创建新数据。")

    for item in page_items:
        item_id = item.get("id", "unknown")
        item_status = item.get("status", "candidate")
        display_text = get_item_display_text(item)
        item_type_detected = get_item_type_from_id(item)

        # 状态标签
        status_emoji = {
            "candidate": "⚪",
            "auto_validated": "🟡",
            "needs_review": "🔶",
            "approved": "✅",
            "rejected": "❌",
            "published": "📗",
            "deprecated": "⬛",
        }
        emoji = status_emoji.get(item_status, "⚪")

        # 类型标签
        type_label = {
            "qa": "QA",
            "student_answer": "SA",
            "socratic": "SC",
            "feynman_task": "FT",
            "feynman_response": "FR",
        }.get(item_type_detected, "??")

        # 质量分
        qs = item.get("quality_score")
        score_str = f" [{qs:.0f}]" if qs is not None else ""

        label = f"{emoji} [{type_label}]{score_str} {display_text[:80]}"
        if st.button(label, key=f"select_{item_id}", use_container_width=True):
            st.session_state.review_selected_id = item_id


with col_right:
    selected_id = st.session_state.review_selected_id

    if selected_id:
        # 找到选中的 item
        selected_item = None
        selected_type = None
        for item in page_items:
            if item.get("id") == selected_id:
                selected_item = item
                selected_type = get_item_type_from_id(item)
                break

        if selected_item is None:
            # 尝试从 repo 中查找
            selected_item = repo.get_candidate(selected_id)
            if selected_item:
                selected_type = get_item_type_from_id(selected_item)

        if selected_item:
            st.subheader(f"详情：{selected_id}")

            # ── 操作按钮 ──
            col_btn1, col_btn2, col_btn3, col_btn4 = st.columns(4)
            with col_btn1:
                if st.button("✅ 批准", type="primary", use_container_width=True, key=f"approve_{selected_id}"):
                    repo.update_candidate_status(selected_id, "approved", selected_type)
                    repo.save_review({
                        "review_id": f"r_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{selected_id}",
                        "item_id": selected_id,
                        "item_type": selected_type,
                        "action": "approve",
                        "reviewer": "human",
                        "reviewed_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    })
                    st.success(f"已批准 {selected_id}")
                    st.rerun()
            with col_btn2:
                if st.button("❌ 拒绝", use_container_width=True, key=f"reject_{selected_id}"):
                    reason = st.text_area("拒绝原因", key=f"reject_reason_{selected_id}")
                    repo.reject_candidate(selected_id, selected_type, reason)
                    repo.save_review({
                        "review_id": f"r_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{selected_id}",
                        "item_id": selected_id,
                        "item_type": selected_type,
                        "action": "reject",
                        "reviewer": "human",
                        "reason": reason,
                        "reviewed_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    })
                    st.success(f"已拒绝 {selected_id}")
                    st.rerun()
            with col_btn3:
                if st.button("🔍 校验", use_container_width=True, key=f"validate_{selected_id}"):
                    with st.spinner("正在校验..."):
                        report = run_validation(selected_item, selected_type)
                        st.session_state[f"report_{selected_id}"] = report
                        st.rerun()
            with col_btn4:
                if st.button("⏭️ 跳过", use_container_width=True, key=f"skip_{selected_id}"):
                    repo.update_candidate_status(selected_id, "needs_review", selected_type)
                    st.rerun()

            # ── 详情 Tab ──
            tab1, tab2, tab3 = st.tabs(["📝 数据内容", "📚 证据 & 校验", "📋 JSON 原始"])

            with tab1:
                _render_item_content(selected_item, selected_type)

            with tab2:
                _render_evidence_panel(selected_item, selected_type)

            with tab3:
                st.json(selected_item)
    else:
        st.info("👈 从左侧列表选择一条候选数据查看详情")


# ═══════════════════════════════════════════════════════════
# 渲染函数
# ═══════════════════════════════════════════════════════════

def _render_item_content(item: dict, item_type: str):
    """渲染数据内容"""
    # QA 题目
    if item_type == "qa":
        st.markdown(f"**题目类型**: {item.get('question_type', '?')}")
        st.markdown(f"**难度**: {'⭐' * item.get('difficulty', 1)}")
        st.markdown(f"**知识点**: {', '.join(item.get('knowledge_ids', []))}")
        st.divider()
        st.markdown(f"### 题目\n{item.get('question', '')}")

        options = item.get("options", {})
        answer = item.get("answer", "")
        for k, v in options.items():
            prefix = "✅" if k == answer else "  "
            st.markdown(f"{prefix} **{k}**: {v}")

        st.divider()
        st.markdown(f"### 参考答案\n{item.get('reference_answer', '')}")
        st.markdown(f"**关键点**: {', '.join(item.get('key_points', []))}")

        # 误区诊断
        diagnosis = item.get("diagnosis", {})
        if diagnosis:
            st.divider()
            st.markdown("### 误区诊断")
            for opt_key, diag in diagnosis.items():
                with st.expander(f"选项 {opt_key}: {diag.get('misconception', '')}"):
                    st.markdown(f"**错误原因**: {diag.get('error_reason', '')}")
                    st.markdown(f"**缺失概念**: {', '.join(diag.get('missing_concepts', []))}")
                    st.markdown(f"**反馈**: {diag.get('feedback', '')}")
                    st.markdown(f"**补救路径**: {' → '.join(diag.get('remedial_path', []))}")

    # 学生答案
    elif item_type == "student_answer":
        st.markdown(f"**关联题目**: {item.get('question_id', '?')}")
        st.markdown(f"**答案等级**: {item.get('answer_level', '?')}")
        st.markdown(f"**误区 ID**: {item.get('misconception_id', '无')}")
        st.divider()
        st.markdown(f"### 学生回答\n{item.get('student_answer', '')}")
        st.divider()
        st.markdown(f"**预期诊断**: {item.get('expected_diagnosis', '')}")
        st.markdown(f"**缺失节点**: {', '.join(item.get('missing_nodes', []))}")
        er = item.get('expected_score_range', [])
        if er:
            st.markdown(f"**预期评分范围**: {er[0]}-{er[1]}")
        st.markdown(f"**预期反馈**: {item.get('expected_feedback', '')}")

    # 苏格拉底链
    elif item_type == "socratic":
        st.markdown(f"**标题**: {item.get('title', '')}")
        st.markdown(f"**目标知识点**: {', '.join(item.get('target_knowledge_ids', []))}")
        st.markdown(f"**触发误区**: {', '.join(item.get('trigger_misconceptions', []))}")
        st.divider()

        steps = item.get("steps", [])
        st.markdown(f"### 步骤（共 {len(steps)} 步）")
        for step in steps:
            is_entry = "🚪 " if step.get("is_entry") else ""
            is_remedial = "🔧 " if step.get("is_remedial") else ""
            with st.expander(f"{is_entry}{is_remedial}{step.get('step_id')}: {step.get('question', '')[:60]}"):
                st.markdown(f"**问题**: {step.get('question', '')}")
                st.markdown(f"**期望概念**: {', '.join(step.get('expected_concepts', []))}")
                st.markdown(f"**提示**: {step.get('hint', '')}")
                st.markdown(f"**错误解释**: {step.get('explanation_if_wrong', '')}")
                st.markdown(f"**KG 节点**: `{step.get('kg_node_ref', '')}`")
                st.markdown(
                    f"**分支**: 正确→`{step.get('next_if_correct')}` | "
                    f"部分→`{step.get('next_if_partial')}` | "
                    f"错误→`{step.get('next_if_wrong')}`"
                )

        st.divider()
        cc = item.get("completion_condition", {})
        st.markdown(f"**完成条件**: {', '.join(cc.get('required_concepts', []))}")
        st.markdown(f"**总结**: {item.get('final_summary', '')}")

    # 费曼任务
    elif item_type == "feynman_task":
        st.markdown(f"**主题**: {item.get('topic', '')}")
        st.markdown(f"**听众**: {item.get('audience', 'materials_beginner')}")
        st.divider()
        st.markdown(f"### 费曼挑战\n{item.get('prompt', '')}")
        st.divider()
        st.markdown(f"**必须覆盖**: {', '.join(item.get('mandatory_points', []))}")
        st.markdown(f"**加分点**: {', '.join(item.get('optional_points', []))}")
        st.markdown(f"**禁止陈述**: {', '.join(item.get('forbidden_claims', []))}")

        st.divider()
        st.markdown("### 评分清单")
        for ci in item.get("checklist", []):
            st.markdown(f"- {ci.get('point', '')} (关键词: {', '.join(ci.get('keywords', []))})")

        st.divider()
        st.markdown(f"### 优秀范例\n{item.get('excellent_example', '')}")

    # 费曼学生回答
    elif item_type == "feynman_response":
        st.markdown(f"**关联费曼任务**: {item.get('feynman_id', '?')}")
        st.markdown(f"**预期等级**: {item.get('expected_level', '?')}")
        st.divider()
        st.markdown(f"### 学生回答\n{item.get('response', '')}")
        st.divider()
        st.markdown(f"**预期缺失**: {', '.join(item.get('expected_missing_points', []))}")
        er = item.get('expected_score_range', [])
        if er:
            st.markdown(f"**预期评分**: {er[0]}-{er[1]}")
        st.markdown(f"**预期反馈**: {item.get('expected_feedback', '')}")


def _render_evidence_panel(item: dict, item_type: str):
    """渲染证据和校验面板"""
    # KG 路径
    graph_path = item.get("graph_path", [])
    if graph_path:
        st.markdown("### 🔗 知识图谱路径")
        st.markdown(" → ".join(f"`{n}`" for n in graph_path))

    # 教材引用
    source_refs = item.get("source_refs", [])
    if source_refs:
        st.markdown("### 📚 教材引用")
        for ref in source_refs:
            chunk_id = ref.get("chunk_id", "?")
            text = ref.get("text", "") or ref.get("excerpt", "")
            lang = ref.get("language", "?")
            with st.expander(f"[{lang}] {chunk_id} — {text[:80]}..."):
                st.text(text[:1000])

    # 校验结果
    report_key = f"report_{item.get('id', '')}"
    if report_key in st.session_state:
        report = st.session_state[report_key]
        st.markdown("### 🔍 自动校验结果")
        _render_validation_report(report)
    else:
        if st.button("🔍 运行校验", key=f"run_validate_{item.get('id', '')}"):
            with st.spinner("校验中..."):
                report = run_validation(item, item_type)
                st.session_state[report_key] = report
                st.rerun()


def _render_validation_report(report):
    """渲染校验报告"""
    # Schema
    icon = "✅" if report.schema_valid else "❌"
    st.markdown(f"{icon} **Schema 校验**")
    if report.schema_errors:
        for e in report.schema_errors:
            st.caption(f"  - {e}")

    # Evidence
    icon = "✅" if report.evidence_valid else "❌"
    st.markdown(f"{icon} **证据校验**")
    if report.evidence_errors:
        for e in report.evidence_errors:
            st.caption(f"  - {e}")

    # Graph
    icon = "✅" if report.graph_consistent else "❌"
    st.markdown(f"{icon} **图谱一致性**")
    if report.graph_errors:
        for e in report.graph_errors:
            st.caption(f"  - {e}")

    # Terminology
    icon = "✅" if report.terminology_valid else "⚠️"
    st.markdown(f"{icon} **术语校验**")
    if report.terminology_errors:
        for e in report.terminology_errors:
            st.caption(f"  - {e}")
    if report.unknown_terms:
        st.caption(f"  未知术语: {', '.join(report.unknown_terms[:5])}")

    # Duplicate
    icon = "⚠️" if report.duplicate_detected else "✅"
    st.markdown(f"{icon} **去重检查** (相似度: {report.duplicate_similarity:.2f})")
    if report.similar_item_ids:
        st.caption(f"  相似条目: {', '.join(report.similar_item_ids[:5])}")

    # Quality Score
    qs = report.quality_score
    if qs:
        st.divider()
        st.markdown("### 📊 质量评分")
        st.markdown(f"**总分**: {qs.total}/100 — **判定**: {qs.verdict}")
        st.progress(qs.total / 100)
        st.caption(
            f"证据支持: {qs.evidence_support}/30 | "
            f"图谱一致: {qs.graph_consistency}/20 | "
            f"答案清晰: {qs.answer_clarity}/15 | "
            f"教学价值: {qs.teaching_value}/15 | "
            f"差异性: {qs.distinctiveness}/10 | "
            f"术语规范: {qs.terminology_accuracy}/10"
        )

    # Warnings
    if report.warnings:
        st.divider()
        for w in report.warnings:
            st.warning(w)
