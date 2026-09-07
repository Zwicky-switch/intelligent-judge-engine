"""从评阅模型请求"强制 JSON"输出, 并稳健解析.

设计约束: LLM 只做解释/判点, 分值必须回到量规上由引擎重算 ——
引擎不信任模型返回的数值, 只采纳其分类/证据/评语。
"""
from __future__ import annotations

import json
import logging
import re

from app.llm.base import ChatModel
from app.llm.providers import LLMError

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> str:
    text = text.strip()
    # 去掉 ```json ... ``` 围栏
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S)
    if fence:
        text = fence.group(1).strip()
    # 从首个 { 到末尾 } 截取最外层对象
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]
    return text


def request_json(model: ChatModel, system: str, user: str, *, retries: int = 2) -> dict:
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            raw = model.complete(system, user)
            return json.loads(_extract_json(raw))
        except (LLMError, ValueError, json.JSONDecodeError) as e:
            last_err = e
            logger.warning("请求模型 JSON 失败(第 %d 次): %s", attempt + 1, e)
            continue
    raise LLMError(f"模型未能返回合法 JSON: {last_err}")
