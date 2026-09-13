"""教务看板质量指标: 评阅分布/复核负载/班级能力画像/题目表现."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.constants import (
    ABILITY_DOMAINS, ACT_DOUBLE_PASS1, ACT_DOUBLE_PASS2,
    ITEM_TYPE_LABELS, MODEL_VERSION, OBJECTIVE_TYPES,
    ROLE_ADMIN, ROLE_GRADER, ST_AUTO_PASSED, ST_NEEDS_REVIEW, ST_REVIEWED,
)
from app.config import settings
from app.core.deps import CurrentUser, require_roles
from app.db import get_db
from app.diagnostics.calibration import (
    compute_calibration, compute_engine_teacher_consistency, percentile,
)
from app.diagnostics.mastery import compute_mastery
from app.llm.base import normalize_provider
from app.engines.objective import grade_objective
from app.models import Answer, Course, Item, ReviewRecord, Score, User

router = APIRouter(prefix="/metrics", tags=["教务指标"])
VIEWERS = (ROLE_ADMIN, ROLE_GRADER)


def _ratio(sc: Score) -> float | None:
    if sc.max_score > 0:
        return (sc.final_score if sc.final_score is not None else sc.total_score) / sc.max_score
    return None


def _double_teacher_consistency(drecs: list[ReviewRecord]) -> dict:
    """双评教师间一致性: 按 reviewed_by 区分教师, 覆盖三类边界.

    - 同分: 两位不同教师给同分 -> 正常计入一致(diff=0 ≤ 容差);
    - 同一教师重复操作: 同 reviewer 只取首次, 不把同一教师两次当两位独立分;
    - 单题超过两次评阅: 只取前两位不同教师各自的首次独立分, 多余记录忽略。
    """
    per_score: dict[int, list[tuple[int | None, float]]] = {}
    for rec in drecs:
        if rec.new_score is None or rec.reviewed_by is None:
            continue
        per_score.setdefault(rec.score_id, []).append(
            (rec.reviewed_by, float(rec.new_score)))
    pairs = within1 = 0
    diffs: list[float] = []
    for recs in per_score.values():
        chosen: list[tuple[int | None, float]] = []
        seen: set[int | None] = set()
        for tid, val in recs:          # 记录按 id 升序 = 按发生时间
            if tid not in seen:
                seen.add(tid)
                chosen.append((tid, val))
            if len(chosen) == 2:
                break
        if len(chosen) < 2:
            continue                   # 需两位不同教师
        v1, v2 = chosen[0][1], chosen[1][1]
        pairs += 1
        d = abs(v1 - v2)
        diffs.append(d)
        if d <= 1.0:
            within1 += 1
    return {
        "pairs": pairs,
        "within_1pt_rate": round(within1 / pairs, 3) if pairs else None,
        "mean_abs_diff": round(sum(diffs) / pairs, 3) if pairs else None,
        "method": "双评完成对: 按 reviewed_by 区分两位不同教师各自首次独立分, ±1 分容差一致率",
        "note": "覆盖边界: 同分计入一致; 同一教师重复操作只取首次; 单题超两次只取前两位教师。未开启双评或尚无完成对时 pairs=0(如实上报)。",
    }


@router.get("/quality")
def quality_metrics(course_id: int | None = Query(default=None),
                    cur: CurrentUser = Depends(require_roles(*VIEWERS)),
                    db: Session = Depends(get_db)):
    sq = db.query(Score)
    if course_id is not None:
        sq = sq.join(Item, Item.id == Score.item_id).filter(Item.course_id == course_id)

    scores = sq.all()
    total = len(scores)
    auto = sum(1 for s in scores if s.status == ST_AUTO_PASSED)
    review = sum(1 for s in scores if s.status == ST_NEEDS_REVIEW)
    reviewed = sum(1 for s in scores if s.status == ST_REVIEWED)
    forced = sum(1 for s in scores if s.review_level == "forced")
    ratios = [_ratio(s) for s in scores if s.status in (ST_AUTO_PASSED, ST_REVIEWED)]
    ratios = [r for r in ratios if r is not None]

    # 每题表现: 平均得分率只统计已终审/自动放行的卷(finalized),
    # 与 totals.avg_ratio 同一口径(待复核卷尚无终评分, 不计入均值);
    # answers 仍为含待复核在内的作答总量, 便于教师看负载。
    item_rows: dict[int, dict] = {}
    for s in scores:
        m = item_rows.setdefault(s.item_id,
                                 {"n": 0, "ratio_sum": 0.0, "ratio_n": 0,
                                  "needs_review": 0})
        m["n"] += 1
        if s.status == ST_NEEDS_REVIEW:
            m["needs_review"] += 1
            continue
        r = _ratio(s)
        if r is not None:
            m["ratio_sum"] += r
            m["ratio_n"] += 1
    items = {i.id: i for i in db.query(Item).all()}
    by_item = []
    for iid, m in item_rows.items():
        it = items.get(iid)
        by_item.append({
            "item_id": iid, "code": it.code if it else "", "type": it.type if it else "",
            "type_label": ITEM_TYPE_LABELS.get(it.type, it.type) if it else "",
            "title": (it.title[:24] + "…") if it and len(it.title) > 24 else (it.title if it else ""),
            "answers": m["n"],
            "finalized": m["ratio_n"],
            "avg_ratio": round(m["ratio_sum"] / m["ratio_n"], 3) if m["ratio_n"] else None,
            "needs_review": m["needs_review"],
        })
    by_item.sort(key=lambda x: x["answers"], reverse=True)

    # 班级能力画像(对每个学生实时计算一次)
    domain_agg: dict[str, dict] = {}
    course = db.query(Course).first() if course_id is None else db.get(Course, course_id)
    for code, _name in ABILITY_DOMAINS:
        domain_agg[code] = {"label": _name, "scores": [], "observed": 0}
    stu_users = db.query(User).filter(User.role == "student").all()
    ccid = course_id or (course.id if course else 0)
    for u in stu_users:
        try:
            m = compute_mastery(db, u.student_token, ccid)
        except Exception:
            continue
        for code, _name in ABILITY_DOMAINS:
            v = m.get("ability", {}).get(code)
            if v:
                domain_agg[code]["scores"].append(v["score"])
                domain_agg[code]["observed"] += 1
    class_ability = {
        code: (round(sum(v["scores"]) / len(v["scores"]), 3) if v["scores"] else None)
        for code, v in domain_agg.items()
    }

    # 得分率分布(0-1 五档)
    bins = [0, 0.2, 0.4, 0.6, 0.8, 1.0001]
    dist = [{"bin": f"{bins[i] * 100:.0f}-{min(bins[i + 1], 1) * 100:.0f}%", "count": 0}
            for i in range(len(bins) - 1)]
    for r in ratios:
        for i in range(len(bins) - 1):
            if bins[i] <= r < bins[i + 1]:
                dist[i]["count"] += 1
                break

    finalized = auto + reviewed

    # ---- 评阅延迟(score.extra.elapsed_ms) ----
    latency = sorted([float(s.extra.get("elapsed_ms")) for s in scores
                      if s.extra and isinstance(s.extra.get("elapsed_ms"), (int, float))])
    latency_stats = {
        "avg": round(sum(latency) / len(latency), 2) if latency else None,
        "p95": round(percentile(latency, 0.95), 2) if latency else None,
        "max": round(latency[-1], 2) if latency else None,
        "n": len(latency),
    }

    # ---- 客观题确定性守门: 重放判定与存量自动放行分对账 ----
    items = {i.id: i for i in db.query(Item).all()}  # 已有局部变量 items; 此处统一为 map
    ans_map = {a.id: a for a in db.query(Answer).filter(
        Answer.id.in_([s.answer_id for s in scores])).all()}
    checked = misgraded = 0
    for s in scores:
        if s.status != ST_AUTO_PASSED or s.item_id not in items:
            continue
        it = items[s.item_id]
        if it.type not in OBJECTIVE_TYPES:
            continue
        a = ans_map.get(s.answer_id)
        raw = (a.raw_response or a.content or "") if a else ""
        replay = grade_objective(it.type, it.answer_config or {}, raw,
                                 it.max_score, it.scoring_policy or {})
        checked += 1
        if abs(float(replay.total) - float(s.total_score or 0.0)) > 0.001:
            misgraded += 1
    objective_accuracy_guard = {
        "checked": checked, "misgraded": misgraded,
        "accuracy": round(1 - misgraded / checked, 4) if checked else None,
        "method": "objective_replay",
        "note": "对全部自动放行客观分用当前引擎重放判定并核对总分; 不一致计入 misgraded。",
    }

    # ---- engine vs 教师终审 一致性 + 分数段校准 ----
    teacher_rows = [s for s in scores if s.status == ST_REVIEWED]
    item_info = {iid: {"type": it.type if it else "",
                       "type_label": ITEM_TYPE_LABELS.get(it.type, it.type) if it else ""}
                 for iid, it in items.items()}
    consistency = compute_engine_teacher_consistency(teacher_rows, item_info)
    calibration = compute_calibration(teacher_rows,
                                      {iid: (it.max_score if it else s.max_score)
                                       for iid, it in items.items()})

    # ---- 双评教师间一致性(按 reviewed_by 区分教师, 覆盖三类边界) ----
    drecs = db.query(ReviewRecord).filter(
        ReviewRecord.action.in_([ACT_DOUBLE_PASS1, ACT_DOUBLE_PASS2])
    ).order_by(ReviewRecord.id).all()
    teacher_consistency = _double_teacher_consistency(drecs)

    finalized = auto + reviewed
    return {
        "course_id": ccid or None,
        "totals": {"answers": total, "auto_passed": auto, "needs_review": review,
                   "reviewed": reviewed, "forced": forced},
        "review_rate": round(reviewed / finalized, 3) if finalized else 0.0,
        "auto_release_rate": round(auto / finalized, 3) if finalized else 0.0,
        "avg_ratio": round(sum(ratios) / len(ratios), 3) if ratios else None,
        "distribution": dist,
        "by_item": by_item,
        "class_ability": class_ability,
        "latency_ms": latency_stats,
        "objective_accuracy_guard": objective_accuracy_guard,
        "consistency": consistency,
        "calibration": calibration,
        "teacher_consistency": teacher_consistency,
        "model_version": MODEL_VERSION,
        "llm_provider": normalize_provider(),
        "note": "review_rate=教师已终审占比; auto_release_rate=自动放行占比(客观题); "
                "口语发音/流畅层在未接入 ASR 时不计分并标注无数据。",
    }
