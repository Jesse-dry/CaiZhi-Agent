"""
知识库数据访问接口

定义了 services 层需要的所有知识库查询能力。
当前实现：JSON/CSV 文件（见 infrastructure/file_knowledge_repo.py）
未来实现：SQLite / PostgreSQL
"""

from abc import ABC, abstractmethod


class KnowledgeRepository(ABC):
    """
    知识库抽象接口。

    涵盖：知识图谱、术语表、题库、苏格拉底链、费曼评价标准。
    """

    # ── 知识图谱 ──

    @abstractmethod
    def get_knowledge_graph(self) -> dict:
        """返回完整知识图谱（nodes + edges）"""
        ...

    @abstractmethod
    def get_causal_chain(self, chain_id: str) -> dict | None:
        """获取单条因果链"""
        ...

    @abstractmethod
    def match_chain(self, question: str) -> dict | None:
        """根据问题文本匹配最相关的因果链"""
        ...

    # ── 术语 ──

    @abstractmethod
    def search_terms(self, query: str, language: str = "zh") -> list[dict]:
        """双语术语搜索"""
        ...

    @abstractmethod
    def get_term(self, term: str, language: str = "zh") -> dict | None:
        """精确获取单个术语"""
        ...

    # ── 题库 ──

    @abstractmethod
    def get_question(self, question_id: str) -> dict | None:
        """获取题目详情（含选项和解释）"""
        ...

    @abstractmethod
    def list_questions(self) -> list[dict]:
        """列出所有题目"""
        ...

    @abstractmethod
    def diagnose_answer(self, question_id: str, selected_option: str) -> dict:
        """诊断学生答案，返回误区信息"""
        ...

    # ── 苏格拉底引导 ──

    @abstractmethod
    def get_socratic_chain(self, socratic_id: str) -> dict | None:
        """获取苏格拉底引导链（含所有步骤）"""
        ...

    # ── 费曼评价 ──

    @abstractmethod
    def get_feynman_rubric(self, feynman_id: str) -> dict | None:
        """获取费曼评价标准"""
        ...
