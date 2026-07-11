"""
文件知识库实现

实现 repositories/knowledge_repo.py 的 KnowledgeRepository 接口。
从 JSON/CSV 文件加载数据（V1 数据源）。

这是临时的 V1 实现，后续替换为 SQLite / PostgreSQL。
"""

import json
import csv
from pathlib import Path
from repositories.knowledge_repo import KnowledgeRepository


class FileKnowledgeRepository(KnowledgeRepository):
    """
    基于文件的知识库实现。

    数据源:
        data/knowledge_graph.json  → 知识图谱 + 因果链
        data/terms.csv             → 双语术语表
        data/questions.json        → 题库 + 误区诊断
        data/socratic.json         → 苏格拉底引导链
        data/feynman.json          → 费曼评价标准

    用法:
        repo = FileKnowledgeRepository()
        chain = repo.get_causal_chain("C001")
        terms = repo.search_terms("淬火")
    """

    def __init__(self, base_dir: Path | None = None):
        if base_dir is None:
            base_dir = Path(__file__).resolve().parent.parent / "data"
        self.base_dir = Path(base_dir)

    # ═══════════════════════════════════════════════════════
    # 知识图谱
    # ═══════════════════════════════════════════════════════

    def get_knowledge_graph(self) -> dict:
        path = self.base_dir / "knowledge_graph.json"
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_causal_chain(self, chain_id: str) -> dict | None:
        graph = self.get_knowledge_graph()
        for chain in graph.get("chains", []):
            if chain.get("chain_id") == chain_id:
                return chain
        return None

    def match_chain(self, question: str) -> dict | None:
        """关键词匹配因果链（V1 简单实现）"""
        graph = self.get_knowledge_graph()
        question_lower = question.lower()
        best_chain = None
        best_score = 0
        for chain in graph.get("chains", []):
            patterns = chain.get("question_patterns", [])
            score = sum(1 for p in patterns if p.lower() in question_lower)
            if score > best_score:
                best_score = score
                best_chain = chain
        return best_chain

    # ═══════════════════════════════════════════════════════
    # 术语
    # ═══════════════════════════════════════════════════════

    def search_terms(self, query: str, language: str = "zh") -> list[dict]:
        path = self.base_dir / "terms.csv"
        results = []
        query_lower = query.lower()
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # 搜索 zh、en、aliases_zh、aliases_en、search_keywords
                searchable = " ".join([
                    row.get("zh", ""), row.get("en", ""),
                    row.get("aliases_zh", ""), row.get("aliases_en", ""),
                    row.get("search_keywords_zh", ""), row.get("search_keywords_en", ""),
                ])
                if query_lower in searchable.lower():
                    results.append(dict(row))
        return results

    def get_term(self, term: str, language: str = "zh") -> dict | None:
        path = self.base_dir / "terms.csv"
        field = "zh" if language == "zh" else "en"
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get(field, "").lower() == term.lower():
                    return dict(row)
        return None

    # ═══════════════════════════════════════════════════════
    # 题库
    # ═══════════════════════════════════════════════════════

    def get_question(self, question_id: str) -> dict | None:
        path = self.base_dir / "questions.json"
        with open(path, "r", encoding="utf-8") as f:
            questions = json.load(f)
        for q in questions:
            if q.get("question_id") == question_id:
                return q
        return None

    def list_questions(self) -> list[dict]:
        path = self.base_dir / "questions.json"
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def diagnose_answer(self, question_id: str, selected_option: str) -> dict:
        """委托给 knowledge.misconception_mapper"""
        from knowledge.misconception_mapper import diagnose_answer
        return diagnose_answer(question_id, selected_option)

    # ═══════════════════════════════════════════════════════
    # 苏格拉底引导
    # ═══════════════════════════════════════════════════════

    def get_socratic_chain(self, socratic_id: str) -> dict | None:
        path = self.base_dir / "socratic.json"
        with open(path, "r", encoding="utf-8") as f:
            chains = json.load(f)
        for chain in chains:
            if chain.get("socratic_id") == socratic_id:
                return chain
        return None

    # ═══════════════════════════════════════════════════════
    # 费曼评价
    # ═══════════════════════════════════════════════════════

    def get_feynman_rubric(self, feynman_id: str) -> dict | None:
        path = self.base_dir / "feynman.json"
        with open(path, "r", encoding="utf-8") as f:
            rubrics = json.load(f)
        for r in rubrics:
            if r.get("feynman_id") == feynman_id:
                return r
        return None
