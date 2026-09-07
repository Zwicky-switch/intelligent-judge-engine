"""OpenAI 兼容 chat completions 实现(httpx 同步)."""
from __future__ import annotations

import httpx

from app.llm.base import ChatModel


class LLMError(RuntimeError):
    pass


class OpenAICompatModel(ChatModel):
    def __init__(self, base_url: str, api_key: str, model: str, provider: str = "openai_compat"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model
        self.provider = provider

    def complete(self, system: str, user: str, *, temperature: float | None = None,
                 max_tokens: int = 2048) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.0 if temperature is None else temperature,
            "max_tokens": max_tokens,
        }
        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as e:
            raise LLMError(f"调用 {self.provider} 失败: {e}") from e
        if resp.status_code >= 400:
            raise LLMError(f"{self.provider} 返回 {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"{self.provider} 响应结构异常: {resp.text[:300]}") from e
