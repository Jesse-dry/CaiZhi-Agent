"""
LLM 客户端封装

统一封装 Anthropic / DeepSeek / OpenAI 的调用接口。
支持同步和流式调用（SSE 推送准备）。

当前状态：占位实现，等待 LLM 接入。
V1 阶段 services 仍使用关键词匹配；
V2 阶段将替换为真实 LLM 调用。

用法:
    client = create_llm_client()            # 从 .env 读取配置
    answer = client.chat(prompt, system="...")
    async for chunk in client.chat_stream(prompt):
        yield chunk
"""

import os
from dataclasses import dataclass
from enum import Enum
from typing import AsyncIterator


class LLMProvider(str, Enum):
    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"
    OPENAI = "openai"


@dataclass
class LLMConfig:
    """LLM 配置"""
    provider: LLMProvider = LLMProvider.ANTHROPIC
    model: str = "claude-sonnet-4-6"
    api_key: str = ""
    base_url: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.3


def _load_config_from_env() -> LLMConfig:
    """从 .env 读取 LLM 配置"""
    provider_str = os.getenv("LLM_PROVIDER", "anthropic").lower()
    provider_map = {
        "anthropic": LLMProvider.ANTHROPIC,
        "deepseek": LLMProvider.DEEPSEEK,
        "openai": LLMProvider.OPENAI,
    }
    provider = provider_map.get(provider_str, LLMProvider.ANTHROPIC)

    api_key = ""
    model = "claude-sonnet-4-6"
    base_url = None

    if provider == LLMProvider.ANTHROPIC:
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    elif provider == LLMProvider.DEEPSEEK:
        api_key = os.getenv("DEEPSEEK_API_KEY", "")
        model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    elif provider == LLMProvider.OPENAI:
        api_key = os.getenv("OPENAI_API_KEY", "")
        model = os.getenv("OPENAI_MODEL", "gpt-4o")
        base_url = os.getenv("OPENAI_BASE_URL", None)

    return LLMConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
    )


class LLMClient:
    """
    LLM 调用统一客户端。

    未来实现：
    - chat(): 同步调用，返回完整响应
    - chat_stream(): 异步流式调用，返回 AsyncIterator[str]
    - chat_with_tools(): 带 tool use 的调用

    V1 占位：返回占位文本。
    """

    def __init__(self, config: LLMConfig | None = None):
        self.config = config or _load_config_from_env()

    def chat(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """
        同步 LLM 调用。

        TODO (V2): 根据 self.config.provider 分发到具体 API。
        当前返回占位响应。
        """
        # TODO: 实现真实 LLM 调用
        # if self.config.provider == LLMProvider.ANTHROPIC:
        #     return self._chat_anthropic(prompt, system, max_tokens, temperature)
        # elif self.config.provider == LLMProvider.DEEPSEEK:
        #     return self._chat_deepseek(prompt, system, max_tokens, temperature)
        # ...
        return self._placeholder_response(prompt)

    async def chat_stream(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """
        异步流式 LLM 调用（用于 SSE 推送）。

        TODO (V2): 实现真实流式调用。
        """
        # 占位：直接返回完整响应
        yield self._placeholder_response(prompt)

    def _placeholder_response(self, prompt: str) -> str:
        """V1 占位响应"""
        return f"[LLM 占位响应] 问题：{prompt[:100]}...（接入 LLM 后将返回真实回答）"


def create_llm_client() -> LLMClient:
    """
    工厂函数：创建 LLM 客户端实例。
    从 .env 自动读取配置。
    """
    config = _load_config_from_env()
    return LLMClient(config)
