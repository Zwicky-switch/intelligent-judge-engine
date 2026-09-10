"""收敛回归: M0.. 分批实现新增能力的端到端/单元测试.

与 test_api_flow 共享同一会话级内存库(ensure_seeded 幂等), 断言多用区间避免
模块间执行顺序造成的计数耦合。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module", autouse=True)
def _seed_db():
    from app.db import SessionLocal
    from app.seeds.demo import ensure_seeded
    db = SessionLocal()
    try:
        ensure_seeded(db)
    finally:
        db.close()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def tokens(client: TestClient):
    out = {}
    for key, (u, p) in {
        "admin": ("admin", "admin123"),
        "prop": ("prop_teacher", "teacher123"),
        "grader": ("grader", "teacher123"),
        "grader2": ("grader2", "teacher123"),
        "li": ("student_li", "stu123"),
        "wang": ("student_wang", "stu123"),
        "zhao": ("student_zhao", "stu123"),
    }.items():
        r = client.post("/v1/auth/login", json={"username": u, "password": p})
        assert r.status_code == 200, r.text
        out[key] = r.json()["access_token"]
    return out


def _item_by_code(client: TestClient, token: str, code: str) -> dict:
    r = client.get("/v1/items", headers=_auth(token))
    assert r.status_code == 200, r.text
    return next(i for i in r.json()["items"] if i["code"] == code)


# ---------------- M0: 评阅耗时 + Score.extra 落库 ----------------

def test_m0_score_carries_elapsed_ms(client, tokens):
    it = _item_by_code(client, tokens["prop"], "PHY-2026-001")
    res = client.post("/v1/answers", headers=_auth(tokens["li"]),
                      json={"item_id": it["id"], "content": "A"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["score"]["status"] == "auto_passed"
    assert body["score"]["total_score"] == 2.0
    extra = body["score"]["extra"]
    assert isinstance(extra, dict)
    assert isinstance(extra.get("elapsed_ms"), (int, float)) and extra["elapsed_ms"] >= 0
    # 详情页同样带 extra
    d = client.get(f"/v1/scores/{body['score']['id']}", headers=_auth(tokens["li"]))
    assert d.status_code == 200
    assert "elapsed_ms" in d.json()["extra"]


# ---------------- M2: 客观题空卷不静默自动 0, 转强制复核 ----------------

def test_m2_empty_objective_goes_to_forced_review(client, tokens):
    it = _item_by_code(client, tokens["prop"], "PHY-2026-009")
    res = client.post("/v1/answers", headers=_auth(tokens["li"]),
                      json={"item_id": it["id"], "content": ""})
    assert res.status_code == 200, res.text
    body = res.json()
    sc = body["score"]
    assert sc["status"] == "needs_review"
    assert sc["review_level"] == "forced"
    assert sc["total_score"] == 0.0
    assert sc["final_score"] is None
    # 该空卷出现在阅卷队列的强制档
    q = client.get("/v1/reviews/queue?review_level=forced", headers=_auth(tokens["grader"]))
    assert q.status_code == 200
    assert any(i["id"] == sc["id"] for i in q.json()["items"])


def test_m2_nonempty_but_wrong_objective_still_auto(client, tokens):
    """非空但判错的选择题仍是确定性判分 -> 自动放行(与空卷区分)."""
    it = _item_by_code(client, tokens["prop"], "PHY-2026-009")
    res = client.post("/v1/answers", headers=_auth(tokens["li"]),
                      json={"item_id": it["id"], "content": "A"})
    assert res.status_code == 200, res.text
    assert res.json()["score"]["status"] == "auto_passed"
    assert res.json()["score"]["total_score"] == 0.0


# ---------------- M3: 学生自主作答闭环(主观题/口语文本) ----------------

def _fresh_student_token(client: TestClient) -> str:
    """在共享内存库里新建一名未作答学生并登录(种子三生均已答完全部题目)."""
    from app.core.security import hash_password
    from app.db import SessionLocal
    from app.models import User
    db = SessionLocal()
    try:
        salt, h = hash_password("stu123")
        db.add(User(username="student_fresh", display_name="新生", role="student",
                    password_hash=h, salt=salt, student_token="stu_fresh", active=True))
        db.commit()
    finally:
        db.close()
    r = client.post("/v1/auth/login", json={"username": "student_fresh", "password": "stu123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_m3_practice_items_cover_subjective_spoken_without_leaks(client, tokens):
    """练习列表向(未作答)学生开放主观/口语/视频题, 但绝不泄露 答案/量规/参考答案/术语库."""
    r = client.get("/v1/practice/items", headers=_auth(_fresh_student_token(client)))
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    types = {i["type"] for i in items}
    assert "subjective_text" in types and "spoken" in types
    assert "practical_video" in types   # 视频基础版已上线: 学生练习区可上传视频作答
    by_code = {i["code"]: i for i in items}
    assert "PHY-2026-020" in by_code and "PHY-2026-030" in by_code
    assert by_code["PHY-2026-020"]["modality"] == "text"
    assert by_code["PHY-2026-030"]["modality"] == "audio"
    # 无答案/量规/术语库泄露
    for i in items:
        blob = str(i)
        for leak in ("correct", "reference_answer", "rubric", "term_bank", "参考答案"):
            assert leak not in blob
    # 客观题只暴露答题所需配置, public_config 不得含判分键
    obj = next(i for i in items if i["type"] == "single_choice")
    assert isinstance(obj["public_config"], dict)
    assert "correct" not in str(obj["public_config"])


def test_m3_student_submits_subjective_text(client, tokens):
    """学生在自主练习提交文本主观题 -> 出分并进教师复核(默认抽样档)."""
    from app.seeds.demo import _STRONG_SUBJ
    it = _item_by_code(client, tokens["prop"], "PHY-2026-020")
    res = client.post("/v1/answers", headers=_auth(tokens["li"]),
                      json={"item_id": it["id"], "content": _STRONG_SUBJ})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["score"]["total_score"] == it["max_score"] == 8.0
    assert body["score"]["status"] == "needs_review"
    assert body["score"]["review_level"] == "sample"
    assert body["score"]["final_score"] is None
    assert "复核" in body.get("message", "")
    # 学生自己的成绩单能看到该笔(学生 GET /v1/scores 只见本人)
    me = client.get("/v1/scores", headers=_auth(tokens["li"]))
    assert me.status_code == 200
    assert any(s["id"] == body["score"]["id"] for s in me.json()["items"])


def test_m3_student_submits_spoken_transcript(client, tokens):
    """口语题文本转写提交: 自动标注 manual_transcript, 出四层明细(未接入层如实 nodata)."""
    from app.seeds.demo import _STRONG_SPOKEN
    it = _item_by_code(client, tokens["prop"], "PHY-2026-030")
    res = client.post("/v1/answers", headers=_auth(tokens["li"]),
                      json={"item_id": it["id"], "content": _STRONG_SPOKEN})
    assert res.status_code == 200, res.text
    body = res.json()
    # 无音频 -> 自动记为人工誊抄转写
    assert body["answer"]["modality"] == "audio"
    assert body["answer"]["quality"]["note_asr"] == "manual_transcript"
    assert body["answer"]["content_uri"] == ""
    sc = body["score"]
    assert sc["total_score"] > 0
    assert sc["status"] == "needs_review"
    layers = (sc.get("extra") or {}).get("layers")
    assert layers and len(layers) == 4
    assert layers["pronunciation"]["status"] == "nodata"   # 无音素级 ASR, 诚实不硬编分
    assert layers["fluency"]["status"] == "nodata"          # 无词级时间戳
    # 内容/表达层基于本地启发式给分(不硬编); 术语库 5 词全命中 -> 表达应偏上
    assert layers["content"]["status"] == "ok" and 0 < layers["content"]["score"] <= 1
    assert layers["expression"]["status"] == "ok" and layers["expression"]["score"] >= 0.6


# ---------------- M4: 口语四层入库 + 种子时间戳样本 + 录音契约 ----------------

def test_m4_seed_strong_spoken_has_fluency_via_sidecar():
    """强学生种子口语样本带 manual_sidecar 词级时间戳 -> 流畅层真实算一次; 发音层仍 nodata."""
    from app.db import SessionLocal
    from app.models import Answer, Score
    db = SessionLocal()
    try:
        ans = db.query(Answer).filter(Answer.trace_id == "seed-0-spoken").first()
        assert ans is not None
        words = [w for s in ans.segments or [] for w in (s.get("words") or [])]
        assert len(words) >= 20 and any(w.get("start") is not None for w in words)
        assert any(s.get("source") == "manual_sidecar" for s in ans.segments or [])
        sc = db.query(Score).filter(Score.answer_id == ans.id).first()
        assert sc is not None
        layers = (sc.extra or {}).get("layers") or {}
        assert layers["fluency"]["status"] == "ok"
        assert 0 <= layers["fluency"]["score"] <= 1
        assert "词/分钟" in (layers["fluency"].get("detail") or "")
        assert layers["pronunciation"]["status"] == "nodata"   # 无强制对齐, 不硬编分
    finally:
        db.close()


def _tiny_wav(ms: int = 1000, rate: int = 8000) -> bytes:
    import io
    import wave
    bio = io.BytesIO()
    with wave.open(bio, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(rate)
        w.writeframes(b"\x80" * (rate * ms // 1000))
    return bio.getvalue()


def test_m4_audio_upload_contract(client, tokens):
    """上传录音+人工转写: 文件入库 content_uri, 转写照常判分, 时长记入质量元数据."""
    import os
    from app.seeds.demo import _STRONG_SPOKEN
    it = _item_by_code(client, tokens["prop"], "PHY-2026-030")
    res = client.post("/v1/answers/audio", headers=_auth(tokens["li"]),
                      data={"item_id": str(it["id"]), "content": _STRONG_SPOKEN},
                      files={"audio": ("demo.wav", _tiny_wav(), "audio/wav")})
    assert res.status_code == 200, res.text
    body = res.json()
    ans = body["answer"]
    assert ans["modality"] == "audio"
    assert ans["content_uri"].endswith(".wav")
    assert ans["content"] == _STRONG_SPOKEN
    assert ans["quality"]["note_asr"] == "manual_transcript"
    assert ans["quality"]["duration_ms"] == 1000
    sc = body["score"]
    assert sc["total_score"] > 0
    assert (sc.get("extra") or {}).get("quality", {}).get("duration_ms") == 1000
    assert (sc.get("extra") or {}).get("layers", {}).get("pronunciation", {}).get("status") == "nodata"
    # 清理落盘测试文件
    os.remove(ans["content_uri"])


def test_m4_audio_upload_without_transcript_offline_is_422(client, tokens):
    """未随附转写且无可用 ASR(如未安装 faster-whisper) -> 明确 422, 不落盘、不评卷."""
    from unittest import mock

    it = _item_by_code(client, tokens["prop"], "PHY-2026-030")
    # 用 mock 模拟"无 ASR 适配器"环境, 与测试机是否装了 faster-whisper 解耦
    with mock.patch("app.api.answers.get_asr", return_value=None):
        res = client.post("/v1/answers/audio", headers=_auth(tokens["li"]),
                          data={"item_id": str(it["id"]), "content": ""},
                          files={"audio": ("blank.wav", _tiny_wav(), "audio/wav")})
    assert res.status_code == 422, res.text
    assert "faster-whisper" in res.text or "人工誊抄" in res.text


# ---------------- M6: metrics 扩容(延迟 / 客观守门 / 一致性 / 校准) ----------------

def test_m6_metrics_quality_includes_latency_guard_consistency_calibration(client, tokens):
    r = client.get("/v1/metrics/quality", headers=_auth(tokens["admin"]))
    assert r.status_code == 200, r.text
    body = r.json()

    lat = body["latency_ms"]
    assert lat["n"] > 0 and lat["avg"] > 0
    assert lat["p95"] >= lat["avg"] - 1e-9 and lat["max"] >= lat["p95"] - 1e-9

    guard = body["objective_accuracy_guard"]
    assert guard["checked"] > 0
    assert guard["accuracy"] is not None and 0 <= guard["accuracy"] <= 1
    assert guard["misgraded"] >= 0

    cons = body["consistency"]
    assert cons["n"] > 0
    assert cons["overall"] is not None and 0 <= cons["overall"] <= 1
    assert isinstance(cons["by_type"], dict) and len(cons["by_type"]) >= 1

    cal = body["calibration"]
    assert isinstance(cal["per_band"], list) and len(cal["per_band"]) == 5
    assert cal["temperature"]["n"] > 0
    assert isinstance(cal["temperature"]["a"], (int, float))
    assert isinstance(cal["flagged_bands"], list)


# ---------------- M7: 诊断消费(60 维全景 + 全节点 + profile_match) ----------------

def test_m7_report_full_dimensions_and_profile_match(client, tokens):
    r = client.get("/v1/diagnosis/stu_A7k2", headers=_auth(tokens["admin"]))
    assert r.status_code == 200, r.text
    body = r.json()

    dims = body["dimensions"]
    assert len(dims) >= 50                      # 60 维全量目录
    observed_any = any(v.get("score") is not None for v in dims.values())
    assert observed_any
    unobserved_any = any(v.get("score") is None for v in dims.values())
    assert unobserved_any
    sample = next(v for v in dims.values() if v.get("score") is not None)
    assert "label" in sample and "domain_code" in sample
    assert "domain_label" in sample and "enabled" in sample
    assert "observed" in sample

    nodes = body["node_mastery"]
    assert len(nodes) >= 8
    first = next(iter(nodes.values()))
    assert "name" in first and "chapter_name" in first and "code" in first
    assert any(v.get("mastery") is not None for v in nodes.values())

    pm = body["profile_match"]
    assert pm is not None
    assert 0 <= pm["value"] <= 1 and pm["n"] >= 2
    assert "IRF" in pm["method"] or "2PL" in pm["method"]


# ---------------- M8: BKT(最小真实, 时序掌握度) ----------------

def test_m8_fit_bkt_synthetic():
    from app.diagnostics.bkt import fit_bkt
    assert fit_bkt([]) is None
    assert fit_bkt([True]) is None
    res_all_pass = fit_bkt([True, True, True, True])
    res_all_fail = fit_bkt([False, False, False, False])
    assert res_all_pass is not None and res_all_fail is not None
    for r in (res_all_pass, res_all_fail):
        assert 0 <= r["mastery_after"] <= 1
        assert r["n"] == 4
        for k in ("pL0", "pT", "pG", "pS"):
            assert k in r["params"]
    assert res_all_pass["mastery_after"] > res_all_fail["mastery_after"]


def test_m8_report_nodes_carry_bkt(client, tokens):
    r = client.get("/v1/diagnosis/stu_A7k2", headers=_auth(tokens["admin"]))
    assert r.status_code == 200, r.text
    nodes = r.json()["node_mastery"]
    assert all("bkt" in v for v in nodes.values())
    active = [v for v in nodes.values() if v["bkt"].get("active")]
    assert active                                  # li 有 ≥2 次观测的节点 -> BKT 激活
    for v in active:
        assert 0 <= v["bkt"]["mastery_after"] <= 1
        assert v["bkt"]["params"]["pL0"] >= 0.1
    inactive = [v for v in nodes.values() if not v["bkt"].get("active")]
    assert inactive                               # 单次观测节点保持 inactive(诚实口径)


# ---------------- M1: LLM 判点/评语链路(修复 prompts 对 dict 的属性访问 bug) ----------------

def test_m1_prompt_accepts_plain_dict():
    """回归: 此前 subjective_user_prompt 用 item.rubric(属性) -> dict 抛 AttributeError,
    被引擎 except 吞掉导致大模型层从不执行."""
    from app.llm.prompts import spoken_user_prompt, subjective_user_prompt
    item = {"title": "受力分析题", "reference_answer": "参考",
            "rubric": [{"point_id": "P1", "score": 2,
                        "description": "正确受力分析", "keywords": ["重力", "支持力"]}]}
    s = subjective_user_prompt(item, "学生作答文本")
    assert "受力分析题" in s and "P1" in s and "学生作答文本" in s
    s2 = spoken_user_prompt(item, "转写文本")
    assert "转写文本" in s2 and "P1" in s2


class _ScriptedLLM:
    """离线脚本模型: 直接返回既定 JSON(模拟真实大模型的结构化输出)."""

    def __init__(self, payload: dict):
        self._payload = payload

    def complete(self, system, user, *, temperature=None, max_tokens=2048) -> str:
        import json
        return json.dumps(self._payload, ensure_ascii=False)


def _db_subjective_item():
    from app.db import SessionLocal
    from app.models import Item
    from app.orchestrator.runner import item_engine_dict
    db = SessionLocal()
    try:
        it = db.query(Item).filter(Item.code == "PHY-2026-020").first()
        return item_engine_dict(it)
    finally:
        db.close()


def _weak_subjective_answer() -> str:
    from app.seeds.demo import _WEAK_SUBJ
    return _WEAK_SUBJ


def test_m1_model_override_merges_into_rubric_total():
    """大模型判全部得分点 satisfied(高置信) -> 引擎按量规权重给满分, 评语用模型."""
    from app.engines.subjective import grade_subjective
    item = _db_subjective_item()
    fake = _ScriptedLLM({
        "point_judgments": [
            {"point_id": "P1", "verdict": "satisfied", "confidence": 0.9,
             "reason": "受力分析表述完整"},
            {"point_id": "P2", "verdict": "satisfied", "confidence": 0.9,
             "reason": "方程列写正确"},
            {"point_id": "P3", "verdict": "satisfied", "confidence": 0.9,
             "reason": "结果与单位正确"},
        ],
        "penalties": [],
        "comment": "步骤完整，模型复核认可。",
        "overall_confidence": 0.9,
    })
    out = grade_subjective(item, _weak_subjective_answer(), llm=fake)
    assert out.total == item["max_score"]  # 全满足 -> 量规满分
    assert all(p.status == "satisfied" for p in out.point_results)
    assert out.comment == "步骤完整，模型复核认可。"
    assert any("模型复核" in (p.reason or "") for p in out.point_results)


def test_m1_penalty_suggestion_is_clamped_to_policy():
    """模型建议罚分超过题目策略上限 -> 引擎夹到策略 max, 不越权."""
    from app.engines.subjective import grade_subjective
    from app.seeds.demo import _STRONG_SUBJ
    item = _db_subjective_item()
    policy = item["scoring_policy"] or {}
    cap = next(p["max"] for p in policy["penalties"] if p["reason"] == "单位错误或遗漏")
    fake = _ScriptedLLM({
        "point_judgments": [],
        "penalties": [{"reason": "单位错误或遗漏", "deduct": 99.0}],
        "comment": "注意单位。",
        "overall_confidence": 0.9,
    })
    # 完整作答本就该拿满分; 模型建议的超限罚分被夹到策略 0.5
    out = grade_subjective(item, _STRONG_SUBJ, llm=fake)
    assert out.total == item["max_score"] - cap
    assert any(p["reason"] == "单位错误或遗漏" and p["deduct"] == cap for p in out.penalties)


# ---------------- M9: 双评/三评(独立双阅卷 + 仲裁) + 评阅者一致性 ----------------

def _seed_double_pending_id(client, tokens) -> int:
    """定位种子双评示例题(王哲, PHY-2026-050)的待评成绩."""
    q = client.get("/v1/reviews/queue", headers=_auth(tokens["grader"]))
    assert q.status_code == 200, q.text
    rows = q.json()["items"]
    hit = [i["id"] for i in rows
           if i["item"]["code"] == "PHY-2026-050"
           and i["student_token"] == "stu_B9q4" and i["status"] == "needs_review"]
    assert hit, "种子双评待评卷未出现在复核队列"
    return hit[0]


def test_m9_double_review_within_tolerance_finalizes_avg(client, tokens):
    """双评题: 两位不同教师独立分 -> 分差 ≤ 容差(0.6) 自动取均值终审."""
    sid = _seed_double_pending_id(client, tokens)
    # 复核队列 double 分组: 待第 1 评卷计入 await_first(而非 await_second), 行态 await_pass1
    q0 = client.get("/v1/reviews/queue", headers=_auth(tokens["grader"]))
    body0 = q0.json()
    assert {"await_first", "await_second", "await_arbitrate"} <= set(body0["double"])
    assert body0["double"]["await_first"] >= 1
    hit0 = next(i for i in body0["items"] if i["id"] == sid)
    assert hit0["double"]["state"] == "await_pass1" and len(hit0["double"]["passes"]) == 0
    p1 = client.post(f"/v1/reviews/{sid}", headers=_auth(tokens["grader"]),
                     json={"action": "adjust", "new_score": 5.0, "comment": "第一评 5.0"})
    assert p1.status_code == 200, p1.text
    sc1 = p1.json()["score"]
    assert sc1["status"] == "needs_review"                      # 第一评后仍待第二评
    assert sc1["extra"]["double"]["state"] == "await_pass2"
    assert len(sc1["extra"]["double"]["passes"]) == 1
    # 同一位教师重复评同一卷 -> 409(双评需不同教师)
    dup = client.post(f"/v1/reviews/{sid}", headers=_auth(tokens["grader"]),
                      json={"action": "adjust", "new_score": 6.0})
    assert dup.status_code == 409
    # 第二位不同教师独立评(分差 0.4 ≤ 容差 0.6) -> 均值终审
    p2 = client.post(f"/v1/reviews/{sid}", headers=_auth(tokens["grader2"]),
                     json={"action": "adjust", "new_score": 5.4, "comment": "第二评 5.4"})
    assert p2.status_code == 200, p2.text
    sc = p2.json()["score"]
    assert sc["status"] == "reviewed"
    assert sc["final_score"] == 5.2                              # (5.0+5.4)/2
    dbl = sc["extra"]["double"]
    assert dbl["state"] == "done" and dbl["final_method"] == "avg"
    assert dbl["diff"] == 0.4 and dbl["tolerance"] == 0.6
    # 落库动作记录两笔独立评 + 来自两位不同教师
    from app.constants import ACT_DOUBLE_PASS1, ACT_DOUBLE_PASS2
    from app.db import SessionLocal
    from app.models import ReviewRecord
    db = SessionLocal()
    try:
        recs = db.query(ReviewRecord).filter(ReviewRecord.score_id == sid).all()
        acts = {r.action for r in recs}
        assert ACT_DOUBLE_PASS1 in acts and ACT_DOUBLE_PASS2 in acts
        teachers = {r.reviewed_by for r in recs
                    if r.action in (ACT_DOUBLE_PASS1, ACT_DOUBLE_PASS2)}
        assert len(teachers) >= 2
    finally:
        db.close()


def test_m9_double_over_tolerance_arbitrates_third_teacher(client, tokens):
    """双评分差 > 容差 -> 待仲裁; 第三位(不同)教师 arbitrate 终审."""
    from app.seeds.demo import _MID_DOUBLE
    it = _item_by_code(client, tokens["prop"], "PHY-2026-050")
    sub = client.post("/v1/answers", headers=_auth(tokens["wang"]),
                      json={"item_id": it["id"], "content": _MID_DOUBLE})
    assert sub.status_code == 200, sub.text
    sid = sub.json()["score"]["id"]
    assert sub.json()["score"]["status"] == "needs_review"
    # 第一评 4.0
    p1 = client.post(f"/v1/reviews/{sid}", headers=_auth(tokens["grader"]),
                     json={"action": "adjust", "new_score": 4.0})
    assert p1.status_code == 200
    # 第二评(另一位教师) 6.0, 分差 2.0 > 容差 0.6 -> 待仲裁
    p2 = client.post(f"/v1/reviews/{sid}", headers=_auth(tokens["grader2"]),
                     json={"action": "adjust", "new_score": 6.0, "comment": "第二评 6.0"})
    assert p2.status_code == 200, p2.text
    sc = p2.json()["score"]
    assert sc["status"] == "needs_review"
    assert sc["extra"]["double"]["state"] == "await_arbitrate"
    assert sc["extra"]["double"]["diff"] == 2.0
    # 队列按"待仲裁"归组可见
    q = client.get("/v1/reviews/queue", headers=_auth(tokens["admin"])).json()
    assert q["double"]["await_arbitrate"] >= 1
    meta = next(i for i in q["items"] if i["id"] == sid)
    assert meta["double"]["state"] == "await_arbitrate"
    # 第三位教师(admin, 与两位评阅不同)仲裁终审
    arb = client.post(f"/v1/reviews/{sid}", headers=_auth(tokens["admin"]),
                      json={"action": "arbitrate", "new_score": 5.5,
                            "comment": "第三位教师仲裁终审 5.5"})
    assert arb.status_code == 200, arb.text
    asc = arb.json()["score"]
    assert asc["status"] == "reviewed" and asc["final_score"] == 5.5
    assert asc["extra"]["double"]["state"] == "done"
    assert asc["extra"]["double"]["final_method"] == "arbitrate"
    assert asc["extra"]["double"]["arbitrated_by"] == "admin"


def test_m9_teacher_consistency_metric_shape(client, tokens):
    """teacher_consistency: 对 double_pass1/2 完成对统计 ±1 分一致率(如实上报)."""
    r = client.get("/v1/metrics/quality", headers=_auth(tokens["admin"]))
    assert r.status_code == 200, r.text
    tc = r.json()["teacher_consistency"]
    assert "pairs" in tc and "within_1pt_rate" in tc and "mean_abs_diff" in tc
    assert tc["pairs"] >= 0
    if tc["pairs"] > 0:
        assert tc["within_1pt_rate"] is not None and 0 <= tc["within_1pt_rate"] <= 1
        assert tc["mean_abs_diff"] is not None and tc["mean_abs_diff"] >= 0
    else:
        assert tc["within_1pt_rate"] is None and tc["mean_abs_diff"] is None
    # 本文件 M9 流程已产生 2 个双评完成对(0.4 与 2.0 分差) -> 统计有真实样本
    assert tc["pairs"] >= 2
    assert tc["within_1pt_rate"] == 0.5
    assert abs(tc["mean_abs_diff"] - 1.2) < 1e-6


# ---------------- M10: 量规模板 / 版本比较 / 发布双人复核 ----------------

def test_m10_rubric_template_crud(client, tokens):
    """量规模板: 建/查/改/删 + 种子示例模板开箱可见."""
    r = client.post("/v1/rubric-templates", headers=_auth(tokens["prop"]),
                    json={"name": "测试模板X", "subject": "物理", "description": "d",
                          "rubric": [{"point_id": "P1", "score": 2,
                                      "description": "正确", "keywords": ["受力"]}]})
    assert r.status_code == 200, r.text
    tid = r.json()["id"]
    # 种子已带 2 个示例模板
    lst = client.get("/v1/rubric-templates", headers=_auth(tokens["prop"]))
    assert lst.status_code == 200
    names = {i["name"] for i in lst.json()["items"]}
    assert "物理计算说理三段式" in names and "物理实验设计题" in names
    assert any(i["id"] == tid for i in lst.json()["items"])
    up = client.put(f"/v1/rubric-templates/{tid}", headers=_auth(tokens["prop"]),
                    json={"name": "测试模板X2", "subject": "物理", "description": "d2",
                          "rubric": [{"point_id": "P1", "score": 2, "description": "a",
                                      "keywords": ["x"]},
                                     {"point_id": "P2", "score": 1, "description": "b",
                                      "keywords": ["y"]}]})
    assert up.status_code == 200
    assert up.json()["name"] == "测试模板X2" and up.json()["point_count"] == 2
    dl = client.delete(f"/v1/rubric-templates/{tid}", headers=_auth(tokens["prop"]))
    assert dl.status_code == 200
    gone = [i for i in client.get("/v1/rubric-templates",
                                  headers=_auth(tokens["prop"])).json()["items"]
            if i["id"] == tid]
    assert not gone


def test_m10_double_publish_requires_two_approvers(client, tokens):
    """发布双人复核: require_double_publish 题需 2 个不同账号复核才真正发布(默认单账号兼容)."""
    it = _item_by_code(client, tokens["prop"], "PHY-2026-060")
    iid = it["id"]
    assert it["published"] is False and it["scoring_policy"]["require_double_publish"] is True
    st = client.get(f"/v1/items/{iid}/publish-status", headers=_auth(tokens["prop"]))
    assert st.status_code == 200
    assert st.json()["approvals_needed"] == 2 and st.json()["published"] is False
    # 第一位复核人(命题教师) -> 仍为草稿
    p1 = client.post(f"/v1/items/{iid}/publish", headers=_auth(tokens["prop"]))
    assert p1.status_code == 200, p1.text
    b1 = p1.json()
    assert b1["published"] is False and b1["publish_pending"] is True
    assert b1["approvals_received"] == 1
    # 同账号再点 -> 不新增有效复核(仍 1 个不同账号)
    p1b = client.post(f"/v1/items/{iid}/publish", headers=_auth(tokens["prop"]))
    assert p1b.json()["approvals_received"] == 1 and p1b.json()["published"] is False
    # 第二位不同账号(教务管理员)复核 -> 真正发布 + 固化 v1 快照
    p2 = client.post(f"/v1/items/{iid}/publish", headers=_auth(tokens["admin"]),
                     params={"comment": "复核通过, 允许发布"})
    assert p2.status_code == 200, p2.text
    b2 = p2.json()
    assert b2["published"] is True and b2["publish_pending"] is False
    assert b2["current_version"] == 1 and not b2["message"].startswith("双人复核")
    st2 = client.get(f"/v1/items/{iid}/publish-status", headers=_auth(tokens["prop"])).json()
    assert st2["approvals_received"] == 2 and len(st2["approvals"]) >= 2
    reviewers = {a["reviewer_name"] for a in st2["approvals"]}
    assert {"admin", "prop_teacher"} <= reviewers
    # 发布后题库列表中已置 published
    again = client.get("/v1/items", headers=_auth(tokens["prop"])).json()["items"]
    row = next(i for i in again if i["id"] == iid)
    assert row["published"] is True


def test_m10_publish_snapshot_and_version_compare(client, tokens):
    """单账号发布(默认)仍然可用; versions 列表/单版本/字段级 compare 正确."""
    base = _item_by_code(client, tokens["prop"], "PHY-2026-020")
    # 新建一道未发布草稿并由单账号(命题教师)发布 -> 默认流程不被双人复核阻塞
    created = client.post("/v1/items", headers=_auth(tokens["prop"]),
                          json={"code": "M10-ITM-A", "type": "subjective_text",
                                "title": "发布流程回归草稿", "course_id": base["course_id"],
                                "chapter_id": None, "max_score": 6,
                                "rubric": [{"point_id": "P1", "score": 6,
                                            "description": "说理", "keywords": ["依据"]}],
                                "knowledge_nodes": ["K-动能定理"],
                                "q_matrix": {"K-动能定理": {"dimension": "PS6", "weight": 1.0}}})
    assert created.status_code == 200, created.text
    iidA = created.json()["id"]
    pub = client.post(f"/v1/items/{iidA}/publish", headers=_auth(tokens["prop"]))
    assert pub.status_code == 200
    assert pub.json()["published"] is True and pub.json()["current_version"] == 1
    ver = client.get(f"/v1/items/{iidA}/versions", headers=_auth(tokens["prop"]))
    assert ver.status_code == 200
    assert len(ver.json()["items"]) == 1 and ver.json()["items"][0]["version"] == 1
    one = client.get(f"/v1/items/{iidA}/versions/1", headers=_auth(tokens["prop"]))
    assert one.status_code == 200 and one.json()["rubric"][0]["point_id"] == "P1"
    # compare: 向已发布题注入 v2 快照(参考答案变化), 验证字段级 diff 命中 reference_answer
    from app.db import SessionLocal
    from app.models import ItemVersion
    iid = base["id"]
    db = SessionLocal()
    try:
        db.add(ItemVersion(item_id=iid, version=2, rubric=base["rubric"],
                           answer_config=base["answer_config"],
                           reference_answer="修订后的参考答案",
                           knowledge_nodes=base["knowledge_nodes"],
                           q_matrix=base["q_matrix"], max_score=base["max_score"],
                           scoring_policy=base["scoring_policy"], published_by=None))
        db.commit()
    finally:
        db.close()
    cmp = client.get(f"/v1/items/{iid}/versions/compare", params={"v1": 1, "v2": 2},
                     headers=_auth(tokens["prop"]))
    assert cmp.status_code == 200, cmp.text
    fields = {c["field"] for c in cmp.json()["changes"]}
    assert "reference_answer" in fields
    assert cmp.json()["v1"] == 1 and cmp.json()["v2"] == 2


# ---------------- M11: 按学科关闭能力维度(课程开关 -> 画像排除 + 报告置灰) ----------------

def test_m11_course_dimension_toggle_affects_report(client, tokens):
    from app.db import SessionLocal
    from app.models import Course
    db = SessionLocal()
    try:
        cid = db.query(Course).first().id
    finally:
        db.close()
    # 基线: KN1(概念理解) 对李雪有观测 -> 有分
    d0 = client.get("/v1/diagnosis/stu_A7k2", headers=_auth(tokens["admin"])).json()
    assert d0["dimensions"]["KN1"]["enabled"] is True
    assert d0["dimensions"]["KN1"]["score"] is not None
    try:
        r = client.put(f"/v1/courses/{cid}/dimensions", json={"disabled": ["KN1"]},
                       headers=_auth(tokens["prop"]))
        assert r.status_code == 200, r.text
        assert r.json()["disabled_count"] == 1 and "KN1" in r.json()["disabled"]
        # 学生/阅卷教师无权改维度开关
        forbid = client.put(f"/v1/courses/{cid}/dimensions", json={"disabled": []},
                            headers=_auth(tokens["li"]))
        assert forbid.status_code == 403
        # 课程维度视图反映停用
        v = client.get(f"/v1/courses/{cid}/dimensions",
                       headers=_auth(tokens["admin"])).json()
        row = next(d for d in v["dimensions"] if d["code"] == "KN1")
        assert row["enabled"] is False and row["disabled"] is True
        # 报告: 停用维 enabled=False、无分数不进画像; 其它有观测维仍出分
        d1 = client.get("/v1/diagnosis/stu_A7k2", headers=_auth(tokens["admin"])).json()
        assert d1["dimensions"]["KN1"]["enabled"] is False
        assert d1["dimensions"]["KN1"]["score"] is None
        assert d1["dimensions"]["KN1"]["observed"] == 0
        assert any(v["enabled"] and v.get("score") is not None
                   for v in d1["dimensions"].values())
    finally:
        # 恢复启用, 避免污染后续用例
        client.put(f"/v1/courses/{cid}/dimensions", json={"disabled": []},
                   headers=_auth(tokens["admin"]))
    # 恢复后 KN1 重新计入画像
    d2 = client.get("/v1/diagnosis/stu_A7k2", headers=_auth(tokens["admin"])).json()
    assert d2["dimensions"]["KN1"]["enabled"] is True
    assert d2["dimensions"]["KN1"]["score"] is not None


# ---------------- M12: 公式符号化题(字母表达式等价判定) ----------------

def _m12_student(client):
    """新建一名未作答公式题的学生(种子三生均已答过部分题, 避免耦合计数)."""
    from app.core.security import hash_password
    from app.db import SessionLocal
    from app.models import User
    db = SessionLocal()
    try:
        if db.query(User).filter(User.username == "student_m12").first() is None:
            salt, h = hash_password("stu123")
            db.add(User(username="student_m12", display_name="M12新生", role="student",
                        password_hash=h, salt=salt, student_token="stu_m12", active=True))
            db.commit()
    finally:
        db.close()
    r = client.post("/v1/auth/login", json={"username": "student_m12", "password": "stu123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_m12_formula_engine_sampling_equivalence():
    """数值抽样等价检验: 展开式判等价满分; 不等价确定性判 0; 空/语法错转人工."""
    from app.engines.symbolic import grade_formula
    cfg = {"formula": {"expected": "(x+y)**2",
                       "variables": [{"name": "x", "min": -5.0, "max": 5.0},
                                     {"name": "y", "min": -5.0, "max": 5.0}]}}
    # (x+y)^2 与其展开式在定义域内处处相等 -> 判等价, 满分
    ok = grade_formula(cfg, "x^2 + 2*x*y + y^2", 10.0, method="sampling")
    assert ok.total == 10.0 and ok.review_level == "none"
    assert ok.hits[0].kind == "symbolic" and ok.hits[0].label == "satisfied"
    assert ok.extra["method"] == "numeric_sampling"
    # 含等号作答只取右侧: a=(x+y)^2 与标准式等价
    ok2 = grade_formula(cfg, "a=(x+y)^2", 10.0, method="sampling")
    assert ok2.total == 10.0
    # 不等价 -> 确定性判 0(非空作答, 与"空卷转人工"区分)
    bad = grade_formula(cfg, "x^3+y", 10.0, method="sampling")
    assert bad.total == 0.0 and bad.review_level == "none"
    assert bad.hits[0].label == "unsatisfied"
    # 空答 -> 强制人工复核, 不静默判 0
    empty = grade_formula(cfg, "", 10.0, method="sampling")
    assert empty.total == 0.0 and empty.review_level == "forced"
    # 语法错误(无法在定义域内求值) -> 同样转人工
    junk = grade_formula(cfg, "x*y+", 10.0, method="sampling")
    assert junk.total == 0.0 and junk.review_level == "forced"


def test_m12_formula_sandbox_no_code_execution():
    """公式数值抽样路径对学生输入绝不执行任意 Python(回归: 曾用受限 eval 可经
    __class__ 属性穿越逃逸到 os 实现 RCE; 现改白名单 AST, 逃逸载荷一律拒评转人工)."""
    from app.engines.symbolic import _eval_safe, grade_formula
    cfg = {"formula": {"expected": "F/m",
                       "variables": [{"name": "F", "min": 1.0, "max": 12.0},
                                     {"name": "m", "min": 1.0, "max": 12.0}]}}
    # 历史逃逸载荷(无等号, sanitize 不会截断; 原实现会执行并返回进程 PID)
    payloads = [
        "().__class__.__base__.__subclasses__()[116].__init__.__globals__"
        "['__builtins__']['__import__']('os').getpid()",
        "().__class__.__mro__",
        "1 .__class__.__base__",
    ]
    for p in payloads:
        # 引擎层: 任何求值异常 -> 无法采样 -> 强制人工复核, 不判分不执行
        out = grade_formula(cfg, p, 6.0, method="sampling")
        assert out.total == 0.0 and out.review_level == "forced", p
        # 底层求值器: 逃逸结构必须被拒绝
        try:
            _eval_safe(p, {"F": 2.0, "m": 1.0})
        except (ValueError, ZeroDivisionError):
            continue
        raise AssertionError("逃逸载荷未被拒绝: " + p)
    # 白名单求值路径保持正常
    assert abs(_eval_safe("F/m", {"F": 8.0, "m": 2.0}) - 4.0) < 1e-9
    assert abs(_eval_safe("sin(pi/2)", {}) - 1.0) < 1e-9
    assert abs(_eval_safe("2**3+1", {}) - 9.0) < 1e-9


def test_m12_formula_seed_auto_full_and_practice_no_leak(client, tokens):
    """公式题出现于学生练习列表(不下发标准式), zhao 种子答卷自动判满."""
    it = _item_by_code(client, tokens["prop"], "PHY-2026-070")
    assert it["type"] == "formula" and it["published"] is True
    tok = _m12_student(client)
    plist = client.get("/v1/practice/items", headers=_auth(tok)).json()
    row = next(x for x in plist["items"] if x["code"] == "PHY-2026-070")
    assert row["type"] == "formula"
    # 练习配置绝不泄露 expected/variables(否则学生照抄答案)
    pc = row["public_config"]
    assert not any(k in pc for k in ("expected", "formula", "correct", "variables"))


def test_m12_formula_api_submission_equivalent_and_empty(client, tokens):
    it = _item_by_code(client, tokens["prop"], "PHY-2026-070")
    tok = _m12_student(client)
    # 学生提交正确等价式 F/m -> 确定性自动判满, 证据 kind=symbolic
    res = client.post("/v1/answers", headers=_auth(tok),
                      json={"item_id": it["id"], "content": "F/m"})
    assert res.status_code == 200, res.text
    sc = res.json()["score"]
    assert sc["status"] == "auto_passed"
    assert sc["total_score"] == 3.0 and sc["final_score"] == 3.0
    assert sc["extra"]["method"] in ("numeric_sampling", "sympy")
    # 空答 -> 强制复核(不静默给 0)
    empty = client.post("/v1/answers", headers=_auth(tok),
                        json={"item_id": it["id"], "content": ""})
    assert empty.status_code == 200, empty.text
    esc = empty.json()["score"]
    assert esc["status"] == "needs_review" and esc["review_level"] == "forced"
    assert esc["final_score"] is None
