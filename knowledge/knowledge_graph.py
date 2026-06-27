import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
GRAPH_PATH = BASE_DIR / "data" / "knowledge_graph.json"


def load_knowledge_graph():
    """
    加载知识图谱 JSON 文件
    返回完整 dict，包含 nodes / edges / chains
    """
    with open(GRAPH_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_chain_by_id(chain_id: str):
    """
    根据 chain_id 获取单条因果链。
    找不到则返回 None。
    """
    graph = load_knowledge_graph()
    for chain in graph.get("chains", []):
        if chain.get("chain_id") == chain_id:
            return chain
    return None


def format_chain_path(chain_id: str):
    """
    将因果链的路径格式化为可读字符串。
    使用节点 label_zh 拼出链路：
      淬火 → 快速冷却 → 碳原子扩散受限 → 奥氏体 → 马氏体 → 晶格畸变 → 位错运动受阻 → 硬度提高
    """
    chain = get_chain_by_id(chain_id)
    if not chain:
        return f"(未找到因果链: {chain_id})"

    graph = load_knowledge_graph()
    node_map = {n["id"]: n for n in graph.get("nodes", [])}

    labels = []
    for node_id in chain.get("path", []):
        node = node_map.get(node_id)
        if node:
            labels.append(node.get("label_zh", node_id))
        else:
            labels.append(node_id)

    return " → ".join(labels)
