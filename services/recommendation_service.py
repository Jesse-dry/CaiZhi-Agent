# services/recommendation_service.py

def deduplicate(items):
    seen = set()
    result = []

    for item in items:
        if item and item not in seen:
            result.append(item)
            seen.add(item)

    return result


def generate_learning_path(diagnosis_result=None, feynman_result=None):
    """
    根据错题诊断和费曼评价结果生成学习路径。
    第一版先用规则，不接大模型。
    """

    weak_points = []

    if diagnosis_result:
        weak_points.extend(diagnosis_result.get("missing_points", []))

    if feynman_result:
        weak_points.extend(feynman_result.get("missing_points", []))

    weak_points = deduplicate(weak_points)

    if not weak_points:
        weak_points = [
            "奥氏体",
            "马氏体",
            "晶格畸变",
            "位错运动与硬度"
        ]

    learning_steps = []

    for point in weak_points:
        if "马氏体" in point:
            learning_steps.append({
                "title": "复习马氏体转变",
                "reason": "你需要理解快速冷却下奥氏体如何转变为马氏体。",
                "action": "回到知识图谱，查看“奥氏体 → 马氏体”路径。"
            })
        elif "扩散" in point:
            learning_steps.append({
                "title": "复习碳原子扩散受限",
                "reason": "你需要理解为什么快速冷却会抑制碳原子扩散。",
                "action": "重新完成苏格拉底问题链中的第 2 问。"
            })
        elif "晶格畸变" in point:
            learning_steps.append({
                "title": "复习晶格畸变",
                "reason": "你需要理解马氏体中过饱和碳如何引起晶格畸变。",
                "action": "查看知识图谱中的“马氏体 → 晶格畸变”节点。"
            })
        elif "位错" in point:
            learning_steps.append({
                "title": "复习位错运动与硬度",
                "reason": "你需要理解为什么位错运动受阻会让材料更硬。",
                "action": "重新用费曼法解释“晶格畸变如何影响硬度”。"
            })
        else:
            learning_steps.append({
                "title": f"复习：{point}",
                "reason": "这是系统识别出的薄弱知识点。",
                "action": "先查看相关知识链，再完成一次解释练习。"
            })

    return {
        "weak_points": weak_points,
        "learning_steps": learning_steps,
        "next_modes": [
            "查看知识图谱",
            "重新进行苏格拉底引导",
            "再次完成费曼解释"
        ]
    }