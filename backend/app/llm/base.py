"""ChatModel 协议与工厂."""
from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger(__name__)

# 内置引擎 provider 别名(含历史值 mock): 对外一律归并为 builtin, 不把 mock 当产品名呈现
_BUILTIN_PROVIDERS = {"", "mock", "none", "builtin", "local", "offline"}


def normalize_provider() -> str:
    """评阅引擎 provider 的对外规范码: 内置引擎(未配置外部模型)统一归并为
    'builtin', UI/文档/指标据此展示为『内置本地引擎』, 不向外暴露 mock 等内部值。"""
    prov = (settings.GRADE_LLM_PROVIDER or "").strip().lower()
    return "builtin" if prov in _BUILTIN_PROVIDERS else prov


class ChatModel:
    """统一评阅模型接口(OpenAI 兼容 chat completions)."""

    provider: str = "openai_compat"
    model_name: str = ""
    temperature_default: float = 0.0

    def complete(self, system: str, user: str, *, temperature: float | None = None,
                 max_tokens: int = 2048) -> str:
        """返回模型文本输出; 失败抛 LLMError."""
        raise NotImplementedError


_PROVIDER_DEFAULTS = {
    "deepseek": {
        "base": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
    "qwen": {
        "base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
    },
    "zhipu": {
        "base": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-air",
    },
}


def get_model() -> ChatModel | None:
    """按配置返回评阅模型; 未配置(或 provider=mock)返回 None -> 本地确定性降级."""
    from app.llm.providers import OpenAICompatModel  # 延迟导入避免与 providers 的循环依赖

    provider = (settings.GRADE_LLM_PROVIDER or "builtin").strip().lower()
    if provider in _BUILTIN_PROVIDERS:
        return None
    if provider == "openai":
        provider = "openai_compat"
    defaults = _PROVIDER_DEFAULTS.get(provider)
    if defaults is None:
        # 支持自定义: base_url 必须显式给出
        base = (settings.GRADE_LLM_BASE_URL or "").strip()
        model = settings.GRADE_LLM_MODEL.strip()
        if not base or not model:
            raise ValueError(f"未知评阅 provider={provider}; 需要同时配置 GRADE_LLM_BASE_URL/GRADE_LLM_MODEL")
        return OpenAICompatModel(base_url=base.rstrip("/"), api_key=settings.GRADE_LLM_API_KEY,
                                 model=model, provider=provider)
    api_key = settings.GRADE_LLM_API_KEY.strip()
    if not api_key:
        logger.warning("评阅 provider=%s 但未配置 GRADE_LLM_API_KEY; 降级为本地确定性判点", provider)
        return None
    base = (settings.GRADE_LLM_BASE_URL.strip() or defaults["base"]).rstrip("/")
    model = settings.GRADE_LLM_MODEL.strip() or defaults["model"]
    return OpenAICompatModel(base_url=base, api_key=api_key, model=model, provider=provider)
