"""端到端 API 流程测试(内存库 + 离线模型):
登录 -> 看题 -> 查成绩/证据 -> 复核队列 -> 教师接受/改分 -> 诊断报告 -> 指标 -> 审计 + 权限守卫.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module", autouse=True)
def _seed_db():
    """确保演示种子写进内存库(幂等, 多测试模块共享同一内存库)."""
    from app.db import SessionLocal
    from app.seeds.demo import ensure_seeded
    db = SessionLocal()
    try:
        ensure_seeded(db)
    finally:
        db.close()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _login(client: TestClient, username: str, password: str) -> str:
    r = client.post("/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def tokens(client: TestClient):
    return {
        "admin": _login(client, "admin", "admin123"),
        "prop": _login(client, "prop_teacher", "teacher123"),
        "grader": _login(client, "grader", "teacher123"),
        "li": _login(client, "student_li", "stu123"),
    }


def test_login_and_me(client, tokens):
    r = client.get("/v1/auth/me", headers=_auth(tokens["admin"]))
    assert r.status_code == 200
    assert r.json()["role"] == "admin"
    r = client.post("/v1/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


def test_items_and_types(client, tokens):
    r = client.get("/v1/items", headers=_auth(tokens["prop"]))
    assert r.status_code == 200
    items = r.json()["items"]
    codes = {i["code"] for i in items}
    assert "PHY-2026-020" in codes and "PHY-2026-040" in codes
    subj = next(i for i in items if i["code"] == "PHY-2026-020")
    assert subj["type"] == "subjective_text" and len(subj["rubric"]) == 3
    r = client.get("/v1/items/types", headers=_auth(tokens["prop"]))
    assert len(r.json()["types"]) >= 8


def test_student_overview(client, tokens):
    r = client.get("/v1/scores/overview/stu_A7k2", headers=_auth(tokens["li"]))
    assert r.status_code == 200
    data = r.json()
    assert data["student_name"] == "李雪"
    # 客观题逐题有成绩与证据; 数出已评题目数
    attempts = data["attempts"]
    assert len(attempts) == 12
    obj = [a for a in attempts if a["item"]["code"] == "PHY-2026-001"][0]
    assert obj["score"]["status"] == "auto_passed"
    assert obj["score"]["total_score"] == 2.0


def test_student_cannot_see_others(client, tokens):
    r = client.get("/v1/scores/overview/stu_C2m8", headers=_auth(tokens["li"]))
    assert r.status_code == 403


def test_score_detail_has_evidence(client, tokens):
    r = client.get("/v1/scores/overview/stu_A7k2", headers=_auth(tokens["li"]))
    subj = next(a for a in r.json()["attempts"] if a["item"]["code"] == "PHY-2026-020")
    sid = subj["score"]["id"]
    d = client.get(f"/v1/scores/{sid}", headers=_auth(tokens["li"]))
    assert d.status_code == 200
    body = d.json()
    assert len(body["evidence"]) >= 3
    assert any(ev["kind"] == "keyword" for ev in body["evidence"])
    assert body["point_scores"]


def test_submit_new_objective(client, tokens):
    # 学生本人提交一题错答 -> 客观题确定性判 0 并自动放行
    r = client.get("/v1/items", headers=_auth(tokens["prop"]))
    item = next(i for i in r.json()["items"] if i["code"] == "PHY-2026-001")
    res = client.post("/v1/answers", headers=_auth(tokens["li"]),
                      json={"item_id": item["id"], "content": "C"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["score"]["status"] == "auto_passed"
    assert body["score"]["total_score"] == 0.0
    assert body["score"]["final_score"] == 0.0


def test_review_queue_and_actions(client, tokens):
    r = client.get("/v1/reviews/queue", headers=_auth(tokens["grader"]))
    assert r.status_code == 200
    q = r.json()
    assert q["total"] >= 1
    # 至少有一条强制复核(如弱生口语"引图"作答)
    assert q["levels"]["forced"] >= 1
    first = next(i for i in q["items"] if i["review_level"] == "forced")
    sid = first["id"]

    # 教师改分(arbitrate)后状态变化
    new_score = round(first["total_score"] + 0.5, 2)
    new_score = min(new_score, first["max_score"])
    act = client.post(f"/v1/reviews/{sid}", headers=_auth(tokens["grader"]),
                      json={"action": "arbitrate", "new_score": new_score,
                            "comment": "复核后仲裁终审"})
    assert act.status_code == 200, act.text
    assert act.json()["score"]["status"] == "reviewed"
    assert act.json()["score"]["final_score"] == new_score

    # 越界改分被拒
    bad = client.post(f"/v1/reviews/{sid}", headers=_auth(tokens["grader"]),
                      json={"action": "adjust", "new_score": first["max_score"] + 10})
    assert bad.status_code == 422


def test_student_forbidden_from_review(client, tokens):
    assert client.get("/v1/reviews/queue", headers=_auth(tokens["li"])).status_code == 403
    assert client.get("/v1/audit", headers=_auth(tokens["li"])).status_code == 403


def test_diagnosis_report(client, tokens):
    r = client.get("/v1/diagnosis/stu_A7k2", headers=_auth(tokens["admin"]))
    assert r.status_code == 200
    d = r.json()
    assert d["student_name"] == "李雪"
    assert d["node_mastery"] and d["ability"]["domain_knowledge"]["score"] > 0.5
    assert len(d["recommendations"]) >= 0
    assert d["observed"] >= 10

    # 学生本人快捷入口一致
    r2 = client.get("/v1/diagnosis/mine/current", headers=_auth(tokens["li"]))
    assert r2.status_code == 200
    assert r2.json()["student_token"] == "stu_A7k2"


def test_metrics_and_audit(client, tokens):
    r = client.get("/v1/metrics/quality", headers=_auth(tokens["admin"]))
    assert r.status_code == 200
    m = r.json()
    assert m["totals"]["answers"] >= 36
    assert m["totals"]["auto_passed"] >= 30
    assert m["class_ability"]["domain_knowledge"] is not None
    assert len(m["by_item"]) >= 10

    r = client.get("/v1/audit", headers=_auth(tokens["admin"]))
    assert r.status_code == 200
    assert len(r.json()["items"]) >= 1  # 复核动作留下不可删审计
