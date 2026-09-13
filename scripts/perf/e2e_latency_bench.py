"""端到端响应时间压测脚本.

测量文本主观题提交的端到端 HTTP 延迟(含网络/序列化/DB/引擎),
与引擎内部 elapsed_ms 对比, 定位真实用户感知延迟的瓶颈。

用法:
    cd backend
    .venv\\Scripts\\python ..\\scripts\\perf\\e2e_latency_bench.py
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

# 确保 backend 在 import 路径
BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import Item  # noqa: E402

CLIENT = TestClient(app)


def login(username: str, password: str) -> str:
    r = CLIENT.post("/v1/auth/login", json={"username": username, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def find_subjective_item() -> int | None:
    db = SessionLocal()
    try:
        item = db.query(Item).filter(
            Item.type == "subjective_text",
            Item.published == True,  # noqa: E712
            Item.enabled == True,    # noqa: E712
        ).first()
        return item.id if item else None
    finally:
        db.close()


def bench_submit(token: str, item_id: int, answers: list[str], n: int = 20) -> dict:
    """提交 n 次文本主观题, 测量端到端延迟和引擎内部延迟."""
    headers = {"Authorization": f"Bearer {token}"}
    e2e_ms: list[float] = []
    engine_ms: list[float] = []
    for i in range(n):
        content = answers[i % len(answers)]
        t0 = time.perf_counter()
        r = CLIENT.post(
            "/v1/answers",
            json={"item_id": item_id, "content": content},
            headers=headers,
        )
        elapsed = (time.perf_counter() - t0) * 1000
        e2e_ms.append(elapsed)
        if r.status_code == 200:
            data = r.json()
            eng = (data.get("score") or {}).get("extra") or {}
            if isinstance(eng, str):
                try:
                    eng = json.loads(eng)
                except Exception:
                    eng = {}
            if "elapsed_ms" in eng:
                engine_ms.append(float(eng["elapsed_ms"]))
        else:
            print(f"  [{i}] HTTP {r.status_code}: {r.text[:200]}")
    return {
        "e2e_avg": statistics.mean(e2e_ms),
        "e2e_p50": statistics.median(e2e_ms),
        "e2e_p95": sorted(e2e_ms)[int(len(e2e_ms) * 0.95)] if e2e_ms else 0,
        "e2e_max": max(e2e_ms),
        "e2e_min": min(e2e_ms),
        "engine_avg": statistics.mean(engine_ms) if engine_ms else 0,
        "engine_p95": sorted(engine_ms)[int(len(engine_ms) * 0.95)] if engine_ms else 0,
        "engine_max": max(engine_ms) if engine_ms else 0,
        "n": n,
        "overhead_avg": statistics.mean(e2e_ms) - (statistics.mean(engine_ms) if engine_ms else 0),
    }


def main():
    print("=" * 70)
    print("端到端响应时间压测: 文本主观题提交")
    print("=" * 70)

    token = login("student_li", "stu123")
    item_id = find_subjective_item()
    if item_id is None:
        print("未找到已发布的主观题, 跳过")
        return

    print(f"题目 ID: {item_id}")
    print(f"压测次数: 20\n")

    answers = [
        "根据牛顿第二定律，物体的加速度与合外力成正比，与质量成反比。公式为F=ma。",
        "惯性是物体保持原来运动状态不变的性质，质量越大惯性越大。",
        "动能定理：合外力对物体做的总功等于物体动能的变化量。W=ΔEk。",
    ]

    # 预热 3 次
    print("预热中...")
    bench_submit(token, item_id, answers, n=3)

    print("\n正式压测...")
    result = bench_submit(token, item_id, answers, n=20)

    print("\n" + "=" * 70)
    print("结果")
    print("=" * 70)
    print(f"  端到端延迟 (含HTTP/DB/序列化/引擎):")
    print(f"    avg  = {result['e2e_avg']:.2f} ms")
    print(f"    p50  = {result['e2e_p50']:.2f} ms")
    print(f"    p95  = {result['e2e_p95']:.2f} ms")
    print(f"    max  = {result['e2e_max']:.2f} ms")
    print(f"    min  = {result['e2e_min']:.2f} ms")
    print(f"  引擎内部延迟 (仅判分逻辑):")
    print(f"    avg  = {result['engine_avg']:.2f} ms")
    print(f"    p95  = {result['engine_p95']:.2f} ms")
    print(f"    max  = {result['engine_max']:.2f} ms")
    print(f"  框架/DB/序列化开销 (端到端 - 引擎):")
    print(f"    avg  = {result['overhead_avg']:.2f} ms")
    print(f"  引擎占比: {result['engine_avg'] / result['e2e_avg'] * 100:.1f}%")

    out = Path(__file__).parent / "e2e_latency_report.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告已写入: {out}")


if __name__ == "__main__":
    main()
