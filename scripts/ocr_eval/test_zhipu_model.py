"""智谱 API Key + glm-4.7 模型连通性测试.

用法:
    cd backend
    .venv\\Scripts\\python ..\\scripts\\ocr_eval\\test_zhipu_model.py [图片路径]
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

# 确保 backend 在 import 路径
BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

import httpx  # noqa: E402

# 从 .env 读取配置
from app.config import settings  # noqa: E402

API_KEY = settings.OCR_LLM_API_KEY
BASE_URL = (settings.OCR_LLM_BASE_URL or "https://open.bigmodel.cn/api/paas/v4").rstrip("/")
MODEL = settings.OCR_LLM_MODEL or "glm-4.7"


def chat_text():
    """纯文本调用测试."""
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "回复OK两个字"}],
        "temperature": 0.0,
        "max_tokens": 32,
    }
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(f"{BASE_URL}/chat/completions", headers=headers, json=payload)
    print(f"  HTTP {resp.status_code}")
    if resp.status_code >= 400:
        print(f"  body: {resp.text[:500]}")
        return False
    try:
        content = resp.json()["choices"][0]["message"]["content"]
    except Exception as e:  # noqa: BLE001
        print(f"  解析失败: {e}; body={resp.text[:300]}")
        return False
    print(f"  响应: {content[:100]!r}")
    return True


def chat_image(img_path: Path):
    """图片输入调用测试(OCR 场景)."""
    b64 = base64.b64encode(img_path.read_bytes()).decode("utf-8")
    ext = img_path.suffix.lower().lstrip(".")
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "webp": "image/webp", "bmp": "image/bmp"}.get(ext, "image/png")
    data_url = f"data:{mime};base64,{b64}"
    payload = {
        "model": MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": "提取图片中的全部文字, 逐行输出原文, 不要解释。"},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }],
        "temperature": 0.0,
        "max_tokens": 1024,
    }
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(f"{BASE_URL}/chat/completions", headers=headers, json=payload)
    except httpx.HTTPError as e:  # noqa: BLE001
        print(f"  调用失败: {e}")
        return False
    print(f"  HTTP {resp.status_code}")
    if resp.status_code >= 400:
        print(f"  body: {resp.text[:800]}")
        return False
    try:
        content = resp.json()["choices"][0]["message"]["content"]
    except Exception as e:  # noqa: BLE001
        print(f"  解析失败: {e}; body={resp.text[:500]}")
        return False
    print(f"  OCR 结果({len(content)}字):")
    print("  " + content.replace("\n", "\n  "))
    return True


def main():
    print("=" * 70)
    print("智谱 API Key + 模型连通性测试")
    print("=" * 70)
    print(f"  base_url: {BASE_URL}")
    print(f"  model   : {MODEL}")
    print(f"  api_key : {API_KEY[:12]}...{API_KEY[-6:] if len(API_KEY) > 18 else ''}")
    print()

    print("[1/2] 纯文本调用测试...")
    ok_text = chat_text()
    print()

    print("[2/2] 图片输入测试...")
    if len(sys.argv) > 1:
        img = Path(sys.argv[1])
    else:
        # 默认用同学1的图片
        img = Path(r"C:\Users\刘奕飞\Desktop\作答资料\同学1（70分\1.png")
    if not img.exists():
        print(f"  图片不存在: {img}")
        ok_img = False
    else:
        ok_img = chat_image(img)
    print()

    print("=" * 70)
    print(f"文本调用: {'✓ 通过' if ok_text else '✗ 失败'}")
    print(f"图片调用: {'✓ 通过' if ok_img else '✗ 失败'}")
    if not (ok_text and ok_img):
        print("提示: 若模型不支持视觉输入, 可改用 glm-4v-flash(视觉) 或 glm-4.7(文本).")
    print("=" * 70)
    return 0 if (ok_text and ok_img) else 1


if __name__ == "__main__":
    sys.exit(main())
