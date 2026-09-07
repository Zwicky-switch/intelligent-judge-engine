"""评阅大模型适配层: 统一协议 + 工厂.

模型可替换 —— 同一协议接入 deepseek / 通义 qwen / 智谱 glm / 自定义兼容端点;
provider 保持内置引擎默认值或未配置 Key 时返回 None, 引擎自动降级到本地确定性判点。
"""
from app.llm.base import ChatModel, get_model

__all__ = ["ChatModel", "get_model"]
