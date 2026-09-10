"""图片识图转文字(OCR): 视觉大模型优先 + 本地 RapidOCR 兜底.

- OCR_LLM_*(视觉模型)与评阅判分模型(GRADE_LLM_*)解耦:
  判分模型可能是纯文本的 deepseek(不能看图), 而 OCR 必须用多模态视觉模型。
  推荐: 智谱 glm-4v-flash(有免费额度) / 通义 qwen-vl-plus; 也可自定义 OpenAI 兼容视觉模型。
- 未配置视觉模型或调用失败时, 回退本地 RapidOCR(pip install rapidocr-onnxruntime,
  离线可用): 印刷体/截图效果好, 手写识别一般 —— 因此低质量识别会经质量门控/强制复核兜底。
- 两者都不可用才抛 OCRConfigError(接口层转 422), 不静默返回空文本。
- 识别结果只提取图片中的文字原文, 不解释、不总结。
"""
from __future__ import annotations

import base64
import logging
from pathlib import Path

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# 图片上传大小上限(10MB, base64 后约 13.4MB, 多模态接口可接受)
MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

# ---- 本地 OCR 兜底(RapidOCR, 离线可选依赖) ----
_LOCAL_OCR_CHECKED = None          # None=未探测 / True·False
_local_engine = None


def _local_ocr_available() -> bool:
    global _LOCAL_OCR_CHECKED, _LOCAL_OCR_AVAILABLE
    if _LOCAL_OCR_CHECKED is None:
        try:
            import rapidocr_onnxruntime  # noqa: F401
            _LOCAL_OCR_AVAILABLE = True
        except Exception:
            _LOCAL_OCR_AVAILABLE = False
        _LOCAL_OCR_CHECKED = True
    return _LOCAL_OCR_AVAILABLE


def _get_local_engine():
    global _local_engine
    if _local_engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _local_engine = RapidOCR()
    return _local_engine


def _ocr_local(path: Path) -> tuple[str, str]:
    """本地 RapidOCR 识别, 返回 (逐行拼接文本, provider)."""
    if not _local_ocr_available():
        raise OCRConfigError(
            "未配置 OCR 视觉模型且未安装本地 RapidOCR: 请配置 OCR_LLM_* "
            "(推荐 zhipu + glm-4v-flash) 或 `pip install rapidocr-onnxruntime` 走离线本地识别"
        )
    try:
        result, _ = _get_local_engine()(str(path))
    except Exception as e:  # noqa: BLE001
        raise OCRError(f"本地 OCR 识别失败: {e}") from e
    lines = []
    for item in (result or []):
        txt = item[1] if len(item) > 1 else ""
        if isinstance(txt, str) and txt.strip():
            lines.append(txt.strip())
    return "\n".join(lines), "rapidocr"

# 视觉模型默认映射(OpenAI 兼容 /chat/completions)
_OCR_PROVIDER_DEFAULTS = {
    "zhipu": {
        "base": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4v-flash",          # 智谱免费视觉模型
    },
    "qwen": {
        "base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-vl-plus",
    },
}

_OCR_PROMPT = (
    "你是试卷识别助手。请提取图片中的全部文字(包括手写体), 逐行输出原文。\n"
    "只返回图片里的文字本身, 不要解释、不要总结、不要添加任何额外内容。\n"
    "如果图片里没有可辨认的文字, 只返回一个空字符串。"
)


class OCRConfigError(RuntimeError):
    """未配置可用的视觉 OCR 模型."""


class OCRError(RuntimeError):
    """视觉模型调用失败."""


def _mime_of(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }.get(ext, "image/png")


def _resolve_vision_model() -> tuple[str, str, str]:
    """返回 (base_url, api_key, model); 未配置时抛 OCRConfigError."""
    provider = (settings.OCR_LLM_PROVIDER or "").strip().lower()
    api_key = (settings.OCR_LLM_API_KEY or "").strip()
    if not provider:
        raise OCRConfigError(
            "未配置 OCR 视觉模型: 请设置 OCR_LLM_PROVIDER/OCR_LLM_API_KEY "
            "(推荐 zhipu + glm-4v-flash, 有免费额度; 或 qwen + qwen-vl-plus)"
        )
    defaults = _OCR_PROVIDER_DEFAULTS.get(provider)
    if defaults is None:
        base = (settings.OCR_LLM_BASE_URL or "").strip()
        model = (settings.OCR_LLM_MODEL or "").strip()
        if not base or not model:
            raise OCRConfigError(
                f"未知 OCR provider={provider}; 自定义 provider 需同时配置 "
                "OCR_LLM_BASE_URL 与 OCR_LLM_MODEL"
            )
        return base.rstrip("/"), api_key, model
    if not api_key:
        raise OCRConfigError(f"OCR provider={provider} 但未配置 OCR_LLM_API_KEY")
    base = (settings.OCR_LLM_BASE_URL.strip() or defaults["base"]).rstrip("/")
    model = settings.OCR_LLM_MODEL.strip() or defaults["model"]
    return base, api_key, model


def ocr_image(path: Path) -> tuple[str, str]:
    """识别图片中的文字: 视觉模型优先, 未配置时回退本地 RapidOCR.

    返回 (识别文本, provider: zhipu/... 或 rapidocr)。调用失败抛 OCRError;
    视觉模型与本地 OCR 都不可用抛 OCRConfigError(接口层转 422)。
    """
    if not path.exists() or path.stat().st_size == 0:
        raise OCRError("图片文件为空或不存在")
    if path.stat().st_size > MAX_IMAGE_BYTES:
        raise OCRError(f"图片过大(>{MAX_IMAGE_BYTES // (1024 * 1024)}MB), 请压缩后重试")

    try:
        base_url, api_key, model = _resolve_vision_model()
    except OCRConfigError:
        # 未配置视觉模型 -> 本地 RapidOCR 兜底(离线也能跑)
        return _ocr_local(path)
    b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
    data_url = f"data:{_mime_of(path)};base64,{b64}"

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _OCR_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "temperature": 0.0,
        "max_tokens": 1024,   # 智谱 glm-4v-flash 限制 [1,1024], 超限返回 400
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
    except httpx.HTTPError as e:  # noqa: BLE001
        raise OCRError(f"OCR 视觉模型调用失败({base_url}): {e}") from e
    if resp.status_code >= 400:
        raise OCRError(f"OCR 视觉模型返回 {resp.status_code}: {resp.text[:300]}")
    try:
        text = resp.json()["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as e:  # noqa: BLE001
        raise OCRError(f"OCR 视觉模型响应结构异常: {resp.text[:300]}") from e
    return text, (settings.OCR_LLM_PROVIDER or "").strip().lower()
