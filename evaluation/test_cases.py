"""
测试用例加载器 — 从 data/*.json 中提取 ground truth，构造评测输入。

数据文件:
    qa_cases.json    → 10 个 QA 测试用例 (QA001-QA010)，含 gold_answer、expected_key_points 等
    questions.json   → 10 道自测题 (Q001-Q010)，每道含正确选项 + 3 个错误选项 + 诊断
    feynman.json     → 10 条费曼评价标准 (F001-F010)，含 checklist + rubric + 范例
    socratic.json    → 1 条苏格拉底链 (S001)，6 步递进式提问

已知问题:
    - qa_cases.json 中 QA001 被意外嵌套在额外数组中，需归一化处理
    - 苏格拉底链 S002-S010 数据缺失
    - 因果链 C002-C010 在 knowledge_graph.json 中不存在
"""

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
QA_CASES_PATH = BASE_DIR / "data" / "qa_cases.json"
QUESTIONS_PATH = BASE_DIR / "data" / "questions.json"
FEYNMAN_PATH = BASE_DIR / "data" / "feynman.json"
SOCRATIC_PATH = BASE_DIR / "data" / "socratic.json"


# ═══════════════════════════════════════════════════════════════
# 1. QA 测试用例 (10 cases)
# ═══════════════════════════════════════════════════════════════

def load_qa_cases() -> list[dict]:
    """
    加载 QA 测试用例，归一化嵌套数组问题。

    qa_cases.json 中 QA001 被包在额外数组中: [[{QA001}], {QA002}, ...]
    此函数将所有 case 展平为一致的 dict 列表。
    """
    with open(QA_CASES_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)

    cases: list[dict] = []
    for item in raw:
        if isinstance(item, list):
            cases.extend(item)
        elif isinstance(item, dict):
            cases.append(item)

    return cases


# ═══════════════════════════════════════════════════════════════
# 2. 自测题测试用例 (10 道题 → 40 个测试点)
# ═══════════════════════════════════════════════════════════════

def load_question_tests() -> list[dict]:
    """
    为每道题生成 4 个测试点:
        - 1 个正确选项测试
        - 3 个错误选项测试

    返回:
        [
            {
                "question_id": "Q001",
                "option": "A",
                "is_correct_expected": False,
                "expected_misconception": "把淬火强化误认为晶粒细化强化",
                ...
            },
            ...
        ]
    """
    with open(QUESTIONS_PATH, "r", encoding="utf-8") as f:
        questions = json.load(f)

    test_points: list[dict] = []
    for q in questions:
        qid = q["question_id"]
        correct = q["answer"].strip().upper()

        for opt in ["A", "B", "C", "D"]:
            is_correct = (opt == correct)
            point: dict = {
                "question_id": qid,
                "option": opt,
                "is_correct_expected": is_correct,
                "expected_misconception": "",
                "expected_missing_concepts": [],
                "expected_remedial_path": [],
            }

            if not is_correct:
                diag = q.get("diagnosis", {}).get(opt, {})
                point["expected_misconception"] = diag.get("misconception", "")
                point["expected_missing_concepts"] = diag.get("missing_points", [])
                point["expected_remedial_path"] = diag.get("remedial_path", [])

            test_points.append(point)

    return test_points


# ═══════════════════════════════════════════════════════════════
# 3. 费曼评价测试用例 (10 条 rubric × 3 种输入 = 30 个测试点)
# ═══════════════════════════════════════════════════════════════

def load_feynman_tests() -> list[dict]:
    """
    为每条 rubric 生成 3 个测试点:
        - excellent: 官方范例 → 预期高分 (≥ excellent_threshold)
        - empty: 空字符串 → 预期低分 (≤ empty_max)
        - partial: 前 3 个 checklist 关键词拼接 → 预期介于两者之间

    返回:
        [
            {
                "feynman_id": "F001",
                "test_type": "excellent",
                "explanation": "淬火时钢从奥氏体区快速冷却...",
                "expected_min": None,   # 下限（excellent ≥ X）
                "expected_max": None,   # 上限（empty ≤ X）
            },
            ...
        ]
    """
    with open(FEYNMAN_PATH, "r", encoding="utf-8") as f:
        rubrics = json.load(f)

    test_points: list[dict] = []
    for rubric in rubrics:
        fid = rubric["feynman_id"]
        excellent = rubric.get("excellent_example", "")
        checklist = rubric.get("checklist", [])

        # 构造部分回答：取前 3 个 checklist 点的关键词拼接
        partial_keywords: list[str] = []
        for item in checklist[:3]:
            partial_keywords.extend(item.get("keywords", [])[:2])

        if partial_keywords:
            partial_text = "。".join(partial_keywords)
        else:
            partial_text = "部分回答"

        # 优秀回答
        test_points.append({
            "feynman_id": fid,
            "test_type": "excellent",
            "explanation": excellent,
            "expected_min": 55,   # ≥ 55/78 (≈ 70/100)
            "expected_max": None,
        })

        # 空回答
        test_points.append({
            "feynman_id": fid,
            "test_type": "empty",
            "explanation": "",
            "expected_min": None,
            "expected_max": 10,   # ≤ 10/78
        })

        # 部分回答
        test_points.append({
            "feynman_id": fid,
            "test_type": "partial",
            "explanation": partial_text,
            "expected_min": None,
            "expected_max": None,
        })

    return test_points


# ═══════════════════════════════════════════════════════════════
# 4. 苏格拉底引导测试用例 (S001 × 6 步 × 3 种回答 = 18 个测试点)
# ═══════════════════════════════════════════════════════════════

def load_socratic_tests() -> list[dict]:
    """
    为 S001 的每步生成 3 个测试点:
        - 完整回答：包含全部 expected_keywords → 预期 "advance"
        - 部分回答：包含 1 个 keyword → 预期 "hint" 或 "retry"
        - 空回答：无关键词 → 预期 "retry" / "simplify" (取决于 attempt_count)

    返回:
        [
            {
                "socratic_id": "S001",
                "step": dict,           # 完整 step 对象
                "student_answer": str,
                "attempt_count": int,
                "expected_action": "advance" | "hint" | "retry" | "simplify",
            },
            ...
        ]
    """
    with open(SOCRATIC_PATH, "r", encoding="utf-8") as f:
        chains = json.load(f)

    test_points: list[dict] = []
    for chain in chains:
        sid = chain["socratic_id"]
        for step in chain.get("steps", []):
            keywords = step.get("expected_keywords", [])
            all_kw_text = "，".join(keywords)
            one_kw = keywords[0] if keywords else "不确定"

            # 完整回答（attempt 1）
            test_points.append({
                "socratic_id": sid,
                "step": step,
                "student_answer": all_kw_text,
                "attempt_count": 1,
                "expected_action": "advance",
            })

            # 部分回答（attempt 1 → hint）
            test_points.append({
                "socratic_id": sid,
                "step": step,
                "student_answer": one_kw,
                "attempt_count": 1,
                "expected_action": {"hint", "retry"},   # accept either
            })

            # 空回答（attempt 1 → retry）
            test_points.append({
                "socratic_id": sid,
                "step": step,
                "student_answer": "",
                "attempt_count": 1,
                "expected_action": "retry",
            })

    return test_points


# ═══════════════════════════════════════════════════════════════
# 5. 学习路径测试场景 (5 个预定义场景)
# ═══════════════════════════════════════════════════════════════

def load_learning_path_scenarios() -> list[dict]:
    """
    5 个场景覆盖边界条件:
        - scenario_all_mastered:  无薄弱点 → 预期 current_level = "已掌握"
        - scenario_partial_weak:  2 个薄弱点 → 预期 "基本掌握"
        - scenario_all_weak:      6+ 个薄弱点 → 预期 "需要加强"
        - scenario_empty_input:   空输入 → 兜底行为
        - scenario_prereq_chain:  需要 K003（先修 K002+K004）→ 验证先修排序

    返回:
        [
            {
                "scenario": "all_mastered",
                "diagnosis_result": None,
                "socratic_result": None,
                "feynman_result": None,
                "checks": {
                    "expected_level": "已掌握",
                    "prereq_compliance": True,
                },
            },
            ...
        ]
    """
    return [
        {
            "scenario": "all_mastered",
            "description": "全部掌握 — 无薄弱点",
            "diagnosis_result": None,
            "socratic_result": None,
            "feynman_result": None,
            "checks": {
                "expected_level": "已掌握",
                "prereq_compliance": True,
            },
        },
        {
            "scenario": "partial_weak",
            "description": "部分薄弱 — 2 个薄弱点",
            "diagnosis_result": {
                "missing_concepts": ["珠光体", "扩散型相变"],
                "misconception": "混淆珠光体和马氏体",
            },
            "socratic_result": None,
            "feynman_result": None,
            "checks": {
                "expected_level": "基本掌握",
                "prereq_compliance": True,
            },
        },
        {
            "scenario": "all_weak",
            "description": "多项薄弱 — 6+ 个薄弱点",
            "diagnosis_result": {
                "missing_concepts": ["淬火", "马氏体", "晶格畸变", "回火", "位错运动"],
                "misconception": "把淬火强化误认为晶粒细化强化",
            },
            "socratic_result": {
                "remaining_weak_points": ["碳原子扩散", "无扩散相变"],
            },
            "feynman_result": {
                "missing_points": ["说明快速冷却会抑制碳原子扩散", "最终连接到硬度提高"],
            },
            "checks": {
                "expected_level": "需要加强",
                "prereq_compliance": True,
            },
        },
        {
            "scenario": "empty_input",
            "description": "空输入 — 兜底行为验证",
            "diagnosis_result": None,
            "socratic_result": None,
            "feynman_result": None,
            "checks": {
                "expected_level": "已掌握",   # 无薄弱点时兜底
                "has_recommended_steps": True,   # 应有默认推荐
                "prereq_compliance": True,
            },
        },
        {
            "scenario": "prereq_chain",
            "description": "先修链测试 — 薄弱点映射到 K003（需 K002+K004 先修）",
            "diagnosis_result": {
                "missing_concepts": ["回火", "马氏体分解", "内应力"],
                "misconception": "",
            },
            "socratic_result": None,
            "feynman_result": {
                "missing_points": ["说明回火能提升韧性、稳定组织与尺寸"],
            },
            "checks": {
                "prereq_compliance": True,   # K003 必须在 K002 和 K004 之后
                "expected_knowledge_ids": ["K001", "K002", "K004", "K003"],  # 期望的拓扑序
            },
        },
    ]


# ═══════════════════════════════════════════════════════════════
# 便利函数
# ═══════════════════════════════════════════════════════════════

def get_statistics() -> dict:
    """返回测试用例统计信息，用于评测报告头部展示。"""
    qa = load_qa_cases()
    qt = load_question_tests()
    ft = load_feynman_tests()
    st = load_socratic_tests()
    lp = load_learning_path_scenarios()

    return {
        "qa_cases": len(qa),
        "question_test_points": len(qt),
        "correct_option_tests": sum(1 for p in qt if p["is_correct_expected"]),
        "wrong_option_tests": sum(1 for p in qt if not p["is_correct_expected"]),
        "feynman_test_points": len(ft),
        "feynman_excellent": sum(1 for p in ft if p["test_type"] == "excellent"),
        "socratic_test_points": len(st),
        "socratic_chains_tested": len(set(p["socratic_id"] for p in st)),
        "learning_path_scenarios": len(lp),
    }
