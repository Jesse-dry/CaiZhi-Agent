"""
学习路径推荐服务。

规则驱动，聚合四个输入源：
  1. 错题诊断 → missing_concepts
  2. 苏格拉底引导 → remaining_weak_points
  3. 费曼评价 → missing_points
  4. 知识图谱 → 先修关系

V1 不接大模型，纯规则映射。
"""

from collections import OrderedDict
from knowledge.knowledge_graph import load_knowledge_graph


# ═══════════════════════════════════════════════════════════
# 知识单元定义（V1 硬编码，后续可从配置文件加载）
# ═══════════════════════════════════════════════════════════

KNOWLEDGE_UNITS: dict[str, dict] = OrderedDict({
    "K001": {
        "title": "淬火与硬度关系",
        "description": "理解淬火工艺如何通过组织转变提高钢的硬度",
        "prerequisites": [],
        "keywords": ["淬火", "硬度", "快速冷却"],
    },
    "K004": {
        "title": "珠光体与马氏体对比",
        "description": "先区分珠光体和马氏体",
        "prerequisites": ["K001"],
        "keywords": ["珠光体", "马氏体", "扩散", "无扩散相变", "冷却速度"],
    },
    "K002": {
        "title": "马氏体组织结构",
        "description": "理解马氏体硬而脆的结构原因",
        "prerequisites": ["K001"],
        "keywords": ["马氏体", "晶格畸变", "过饱和碳", "位错运动", "碳原子"],
    },
    "K003": {
        "title": "回火工艺与原理",
        "description": "继续学习为什么淬火后需要回火",
        "prerequisites": ["K002", "K004"],
        "keywords": ["回火", "韧性", "马氏体分解", "内应力", "脆性"],
    },
})


# ═══════════════════════════════════════════════════════════
# 内部工具
# ═══════════════════════════════════════════════════════════

def _deduplicate(items: list[str]) -> list[str]:
    """去重保序"""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            result.append(item)
            seen.add(item)
    return result


def _collect_weak_points(
    diagnosis_result: dict | None,
    socratic_result: dict | None,
    feynman_result: dict | None,
) -> list[str]:
    """从三个来源聚合薄弱知识点"""
    raw: list[str] = []

    if diagnosis_result:
        raw.extend(diagnosis_result.get("missing_concepts", []))
        # 错题误区本身也是一个薄弱点
        misc = diagnosis_result.get("misconception", "")
        if misc:
            raw.append(misc)

    if socratic_result:
        raw.extend(socratic_result.get("remaining_weak_points", []))

    if feynman_result:
        raw.extend(feynman_result.get("missing_points", []))

    return _deduplicate(raw)


def _map_weak_points_to_units(weak_points: list[str]) -> list[str]:
    """
    将薄弱点关键词映射到知识单元 ID。
    每个薄弱点匹配最相关的知识单元。
    """
    matched_units: set[str] = set()

    for point in weak_points:
        point_lower = point.lower()
        # 找到匹配关键词最多的知识单元
        best_unit = None
        best_score = 0
        for unit_id, unit in KNOWLEDGE_UNITS.items():
            if unit_id in matched_units:
                continue
            score = sum(
                1 for kw in unit.get("keywords", [])
                if kw.lower() in point_lower
            )
            if score > best_score:
                best_score = score
                best_unit = unit_id

        if best_unit:
            matched_units.add(best_unit)
        else:
            # 无法匹配的知识点默认关联 K001
            matched_units.add("K001")

    return list(matched_units)


def _sort_by_prerequisites(unit_ids: list[str]) -> list[str]:
    """
    按先修关系拓扑排序。没有先修要求的在前，有先修的在后。
    同层级按定义顺序。
    """
    # 先建立所有先修集合
    all_ids = set(unit_ids)

    # 拓扑排序（Kahn 简化版）
    sorted_ids: list[str] = []
    remaining = set(unit_ids)

    while remaining:
        # 找到所有先修已满足的单元
        ready = []
        for uid in sorted(remaining, key=lambda x: list(KNOWLEDGE_UNITS.keys()).index(x)):
            prereqs = KNOWLEDGE_UNITS.get(uid, {}).get("prerequisites", [])
            # 只考虑已加载单元的 prereqs
            relevant_prereqs = [p for p in prereqs if p in all_ids]
            if all(p in sorted_ids for p in relevant_prereqs):
                ready.append(uid)

        if ready:
            sorted_ids.extend(ready)
            remaining -= set(ready)
        else:
            # 循环依赖或无先修信息：按原始顺序输出
            sorted_ids.extend(sorted(remaining, key=lambda x: list(KNOWLEDGE_UNITS.keys()).index(x)))
            break

    return sorted_ids


def _determine_level(weak_points: list[str]) -> str:
    """根据薄弱点数量判断掌握程度"""
    count = len(weak_points)
    if count == 0:
        return "已掌握"
    elif count <= 2:
        return "基本掌握"
    elif count <= 5:
        return "部分掌握"
    else:
        return "需要加强"


# ═══════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════

def generate_learning_path(
    diagnosis_result: dict | None = None,
    socratic_result: dict | None = None,
    feynman_result: dict | None = None,
) -> dict:
    """
    聚合三个来源的薄弱点 → 映射知识单元 → 按先修关系排序 → 生成推荐路径。

    返回:
        {
            "current_level": str,
            "weak_points": [str],
            "recommended_steps": [
                {"order": 1, "knowledge_id": "K004", "reason": "..."},
                ...
            ],
        }
    """
    # 1. 聚合薄弱点
    weak_points = _collect_weak_points(diagnosis_result, socratic_result, feynman_result)

    # 兜底：无薄弱点时用默认值
    if not weak_points:
        weak_points = ["淬火", "马氏体", "晶格畸变"]

    # 2. 映射到知识单元
    unit_ids = _map_weak_points_to_units(weak_points)

    # 确保 K001 始终在推荐中（作为基础）
    if "K001" not in unit_ids and len(unit_ids) < 3:
        unit_ids.insert(0, "K001")

    # 3. 按先修关系排序
    sorted_ids = _sort_by_prerequisites(unit_ids)

    # 4. 生成推荐步骤
    recommended_steps: list[dict] = []
    for order, uid in enumerate(sorted_ids, start=1):
        unit = KNOWLEDGE_UNITS.get(uid, {})
        recommended_steps.append({
            "order": order,
            "knowledge_id": uid,
            "reason": unit.get("description", ""),
            "title": unit.get("title", uid),
        })

    # 5. 判断掌握程度
    current_level = _determine_level(weak_points)

    return {
        "current_level": current_level,
        "weak_points": weak_points,
        "recommended_steps": recommended_steps,
    }
