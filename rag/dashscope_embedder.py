"""
DashScope Text Embedding API 封装（OpenAI 兼容接口）。

使用阿里云百炼 text-embedding-v4 模型，1024 维向量。
API Key 从环境变量 DASHSCOPE_API_KEY 读取，不硬编码。

用法:
    embedder = DashScopeEmbedder()
    vectors = embedder.encode(["淬火是什么？", "马氏体相变"])
    # vectors: [[0.123, -0.456, ...], [0.789, ...]]
"""

from __future__ import annotations

import os
import time
import logging
from typing import overload

import numpy as np

logger = logging.getLogger(__name__)

DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "text-embedding-v4"
DEFAULT_DIMENSIONS = 1024
MAX_BATCH_SIZE = 5   # DashScope text-embedding-v4: 长文本时单次最多约 5-10 条


class DashScopeEmbedder:
    """DashScope 文本向量化封装。API Key 从环境变量读取。"""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        dimensions: int = DEFAULT_DIMENSIONS,
        base_url: str | None = None,
        api_key: str | None = None,
    ):
        self.model = model
        self.dimensions = dimensions
        self.base_url = base_url or os.getenv(
            "CAPTION_BASE_URL", DASHSCOPE_BASE_URL
        )
        self._api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        self._client = None

    @property
    def api_key(self) -> str:
        if self._api_key is None:
            raise ValueError(
                "DASHSCOPE_API_KEY 未设置，请在 .env 文件中配置"
            )
        return self._api_key

    @property
    def client(self):
        """惰性创建 OpenAI 兼容客户端。"""
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._client

    @overload
    def encode(self, texts: str, normalize_embeddings: bool = True) -> list[float]: ...

    @overload
    def encode(self, texts: list[str], normalize_embeddings: bool = True) -> list[list[float]]: ...

    def encode(
        self, texts: str | list[str], normalize_embeddings: bool = True,
    ) -> list[float] | list[list[float]]:
        """将文本编码为向量。单条文本 → list[float]，多条 → list[list[float]]。"""
        single_input = isinstance(texts, str)
        batch = [texts] if single_input else list(texts)

        all_embeddings: list[list[float]] = []
        for i in range(0, len(batch), MAX_BATCH_SIZE):
            sub_batch = batch[i:i + MAX_BATCH_SIZE]
            all_embeddings.extend(self._call_api(sub_batch))

        if normalize_embeddings:
            all_embeddings = [self._normalize(v) for v in all_embeddings]

        return all_embeddings[0] if single_input else all_embeddings

    def _call_api(self, texts: list[str]) -> list[list[float]]:
        """单次 API 调用（最多 25 条），指数退避重试。"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                resp = self.client.embeddings.create(
                    model=self.model,
                    input=texts,
                    dimensions=self.dimensions,
                )
                sorted_data = sorted(resp.data, key=lambda d: d.index)
                return [d.embedding for d in sorted_data]
            except Exception as e:
                logger.warning(
                    "Embedding API 失败 (attempt %d/%d): %s",
                    attempt + 1, max_retries, e,
                )
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    raise RuntimeError(
                        f"DashScope embedding API 连续 {max_retries} 次失败: {e}"
                    ) from e
        return []

    @staticmethod
    def _normalize(vec: list[float]) -> list[float]:
        arr = np.asarray(vec, dtype=np.float32)
        norm = np.linalg.norm(arr)
        return (arr / norm).tolist() if norm > 0 else arr.tolist()

    def get_embedding_dimension(self) -> int:
        return self.dimensions
