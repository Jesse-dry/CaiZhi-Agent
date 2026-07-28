"""
LLM 客户端封装

统一封装 Anthropic / DeepSeek / OpenAI 的调用接口。
支持同步和流式调用（SSE 推送准备）。

用法:
    client = create_llm_client()            # 从 .env 读取配置
    answer = client.chat(prompt, system="...")
    async for chunk in client.chat_stream(prompt):
        yield chunk
"""

import logging
import os
import time
from dataclasses import dataclass
from enum import Enum
from typing import AsyncIterator

from dotenv import load_dotenv
load_dotenv()  # 确保 .env 中的 API key 等配置已加载

logger = logging.getLogger(__name__)


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

    支持三种 provider：
    - Anthropic (Claude) — 通过 anthropic SDK
    - DeepSeek — 通过 OpenAI 兼容接口
    - OpenAI — 通过 openai SDK

    包含指数退避重试，处理超时/限流/连接错误。
    """

    def __init__(self, config: LLMConfig | None = None):
        self.config = config or _load_config_from_env()
        logger.info(f"LLMClient initialized: provider={self.config.provider.value}, model={self.config.model}")

    def chat(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """
        同步 LLM 调用。

        Args:
            prompt: 用户消息
            system: 系统提示词
            max_tokens: 最大输出 token（None 用默认值）
            temperature: 采样温度（None 用默认值）

        Returns:
            LLM 返回的文本
        """
        if self.config.provider == LLMProvider.ANTHROPIC:
            return self._chat_anthropic(prompt, system, max_tokens, temperature)
        elif self.config.provider in (LLMProvider.DEEPSEEK, LLMProvider.OPENAI):
            return self._chat_openai_compatible(prompt, system, max_tokens, temperature)
        else:
            raise ValueError(f"Unknown provider: {self.config.provider}")

    async def chat_stream(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        """
        异步流式 LLM 调用（用于 SSE 推送）。

        每 yield 一个文本片段。
        """
        if self.config.provider == LLMProvider.ANTHROPIC:
            async for chunk in self._chat_anthropic_stream(prompt, system, max_tokens, temperature):
                yield chunk
        elif self.config.provider in (LLMProvider.DEEPSEEK, LLMProvider.OPENAI):
            async for chunk in self._chat_openai_compatible_stream(prompt, system, max_tokens, temperature):
                yield chunk
        else:
            raise ValueError(f"Unknown provider: {self.config.provider}")

    # ── OpenAI-Compatible (DeepSeek + OpenAI) ──────────────────────

    def _chat_openai_compatible(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """
        通过 OpenAI 兼容接口调用（同时服务 DeepSeek 和 OpenAI）。

        参考项目已有模式：rag/image_captioner.py lines 98-128、
        rag/dashscope_embedder.py lines 60-65。
        """
        from openai import APIError, APIConnectionError, APITimeoutError, OpenAI, RateLimitError

        client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
        )

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        actual_max_tokens = max_tokens or self.config.max_tokens
        actual_temperature = temperature if temperature is not None else self.config.temperature

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = client.chat.completions.create(
                    model=self.config.model,
                    messages=messages,
                    max_tokens=actual_max_tokens,
                    temperature=actual_temperature,
                )
                content = response.choices[0].message.content
                return content if content else ""

            except (APITimeoutError, RateLimitError, APIConnectionError) as e:
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    logger.warning(
                        f"API error (attempt {attempt+1}/{max_retries}): {type(e).__name__}: {e}, "
                        f"retrying in {wait}s"
                    )
                    time.sleep(wait)
                else:
                    raise RuntimeError(
                        f"LLM API call failed after {max_retries} attempts: {type(e).__name__}: {e}"
                    ) from e

            except APIError as e:
                raise RuntimeError(f"LLM API error: {type(e).__name__}: {e}") from e

    async def _chat_openai_compatible_stream(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        """流式版本 — 用 asyncio.to_thread 包装同步 streaming 调用。"""
        import asyncio

        from openai import APIError, APIConnectionError, APITimeoutError, OpenAI, RateLimitError

        client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
        )

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        actual_max_tokens = max_tokens or self.config.max_tokens
        actual_temperature = temperature if temperature is not None else self.config.temperature

        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            try:
                # OpenAI streaming 是同步 blocking generator，
                # 用 to_thread 避免阻塞事件循环
                def _stream():
                    stream = client.chat.completions.create(
                        model=self.config.model,
                        messages=messages,
                        max_tokens=actual_max_tokens,
                        temperature=actual_temperature,
                        stream=True,
                    )
                    for chunk in stream:
                        delta = chunk.choices[0].delta
                        if delta.content:
                            yield delta.content

                gen = _stream()
                while True:
                    try:
                        chunk = await asyncio.to_thread(next, gen)
                        yield chunk
                    except StopIteration:
                        return

            except (APITimeoutError, RateLimitError, APIConnectionError) as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    logger.warning(
                        f"Stream API error (attempt {attempt+1}/{max_retries}): "
                        f"{type(e).__name__}: {e}, retrying in {wait}s"
                    )
                    time.sleep(wait)
                else:
                    raise RuntimeError(
                        f"LLM stream API call failed after {max_retries} attempts: "
                        f"{type(e).__name__}: {e}"
                    ) from e

            except APIError as e:
                raise RuntimeError(f"LLM stream API error: {type(e).__name__}: {e}") from e

    # ── Anthropic (stub for V2) ──────────────────────────────────

    def _chat_anthropic(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """
        Anthropic Claude 调用（V2 实现）。

        当前回退到 OpenAI 兼容模式 — 如果 base_url 指向兼容端点则可用。
        否则抛出 NotImplementedError。
        """
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=self.config.api_key)
            actual_max_tokens = max_tokens or self.config.max_tokens

            kwargs = {"model": self.config.model, "max_tokens": actual_max_tokens, "messages": [{"role": "user", "content": prompt}]}
            if system:
                kwargs["system"] = system
            if temperature is not None:
                kwargs["temperature"] = temperature

            response = client.messages.create(**kwargs)
            # Anthropic 返回 ContentBlock 列表，取第一个 text block
            for block in response.content:
                if block.type == "text":
                    return block.text
            return response.content[0].text if response.content else ""

        except ImportError:
            raise NotImplementedError(
                "Anthropic SDK not available. Install with: pip install anthropic"
            )
        except Exception as e:
            raise RuntimeError(f"Anthropic API error: {type(e).__name__}: {e}") from e

    async def _chat_anthropic_stream(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        """Anthropic 流式调用（V2 实现）。"""
        import asyncio

        try:
            import anthropic

            client = anthropic.Anthropic(api_key=self.config.api_key)
            actual_max_tokens = max_tokens or self.config.max_tokens

            kwargs = {"model": self.config.model, "max_tokens": actual_max_tokens, "messages": [{"role": "user", "content": prompt}]}
            if system:
                kwargs["system"] = system
            if temperature is not None:
                kwargs["temperature"] = temperature

            def _stream():
                with client.messages.stream(**kwargs) as stream:
                    for text in stream.text_stream:
                        yield text

            gen = _stream()
            while True:
                try:
                    chunk = await asyncio.to_thread(next, gen)
                    yield chunk
                except StopIteration:
                    return

        except ImportError:
            raise NotImplementedError(
                "Anthropic SDK not available. Install with: pip install anthropic"
            )
        except Exception as e:
            raise RuntimeError(f"Anthropic stream API error: {type(e).__name__}: {e}") from e


def create_llm_client() -> LLMClient:
    """
    工厂函数：创建 LLM 客户端实例。
    从 .env 自动读取配置。
    """
    config = _load_config_from_env()
    return LLMClient(config)
