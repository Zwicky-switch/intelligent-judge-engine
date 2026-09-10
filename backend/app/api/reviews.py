"""阅卷复核: 复核队列(带学生名/证据) 与 教师操作(接受/改分/仲裁/退回)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.constants import (
    ACT_ACCEPT, ACT_ADJUST, ACT_ARBITRATE, ACT_DOUBLE_PASS1, ACT_DOUBLE_PASS2,
    ACT_RETURN, ROLE_ADMIN, ROLE_GRADER,
)
from app.core.deps import CurrentUser, require_roles
from app.db import get_db
from app.models import Answer, Evidence, Item, ReviewRecord, Score
from app.orchestrator.review import (
    DoubleReviewError, apply_review, list_review_queue, list_recent,
)

from app.api.scores import _student_name
from app.api.serializers import evidence_dict, score_dict

router = APIRouter(prefix="/reviews", tags=["阅卷复核"])
REVIEWERS = (ROLE_ADMIN, ROLE_GRADER)


def _item_meta(db: Session, score: Score, answer: Answer,
               viewer_id: int | None = None) -> dict:
    item = db.get(Item, score.item_id)
    name_row = _student_name(db, score.student_token)
    d = score_dict(score, answer=answer, item=item, include_answer=True,
                   include_evidence=(db.query(Evidence)
                                     .filter(Evidence.score_id == score.id)
                                     .order_by(Evidence.id).all()))
    d["student_name"] = name_row
    # 双评展示信息: 是否双评卷 + 阶段状态 + 已产生的独立分 + 当前教师是否已评。
    # 双评卷以题目 review_mode 判定(与状态机一致); 首评前的卷可能尚无 extra 骨架,
    # 在此归一化为待第二评状态, 供阅卷台首评前即提示"需两位教师独立复核"。
    is_double = bool(item and (item.scoring_policy or {}).get("review_mode") == "double")
    double = (score.extra or {}).get("double")
    if is_double and not isinstance(double, dict):
        double = {"mode": "double", "passes": [], "by_ids": [], "state": "await_pass1",
                  "message": "该卷需两位教师独立复核: 尚未有教师独立评; 分差在容差内取均值终审, 超差转第三位教师仲裁。"}
    d["double"] = double
    d["is_double"] = is_double
    d["double_reviewed_by_me"] = False
    if is_double and double and viewer_id is not None:
        d["double_reviewed_by_me"] = (
            viewer_id in (double.get("by_ids") or []))
    return d


@router.get("/queue")
def review_queue(review_level: str | None = Query(default=None),
                 item_type: str | None = None,
                 status: str | None = Query(default="needs_review"),
                 cur: CurrentUser = Depends(require_roles(*REVIEWERS)),
                 db: Session = Depends(get_db)):
    rows = list_review_queue(db, review_level=review_level, item_type=item_type,
                             status=status)
    double_first = sum(1 for sc, _, _ in rows
                       if (sc.extra or {}).get("double", {}).get("state") == "await_pass1")
    double_await = sum(1 for sc, _, _ in rows
                       if (sc.extra or {}).get("double", {}).get("state") == "await_pass2")
    arbitrate = sum(1 for sc, _, _ in rows
                    if (sc.extra or {}).get("double", {}).get("state") == "await_arbitrate")
    return {"items": [_item_meta(db, sc, ans, cur.id) for sc, ans, it in rows],
            "total": len(rows),
            "levels": {"sample": 0, "forced": 0} | {
                "sample": sum(1 for sc, _, _ in rows if sc.review_level == "sample"),
                "forced": sum(1 for sc, _, _ in rows if sc.review_level == "forced")},
            "double": {"await_first": double_first,
                       "await_second": double_await,
                       "await_arbitrate": arbitrate}}


@router.get("/recent")
def recent_scores(limit: int = 30, cur: CurrentUser = Depends(require_roles(*REVIEWERS)),
                  db: Session = Depends(get_db)):
    rows = list_recent(db, limit=limit)
    return {"items": [_item_meta(db, sc, ans, cur.id) for sc, ans, _ in rows], "total": len(rows)}


class ReviewAction(BaseModel):
    action: str                 # accept / adjust / arbitrate / return_model
    new_score: float | None = None
    comment: str = ""


@router.post("/{score_id}")
def do_review(score_id: int, body: ReviewAction,
              cur: CurrentUser = Depends(require_roles(*REVIEWERS)),
              db: Session = Depends(get_db)):
    if body.action not in (ACT_ACCEPT, ACT_ADJUST, ACT_ARBITRATE, ACT_RETURN):
        raise HTTPException(422, f"未知动作 {body.action}")
    if body.action in (ACT_ADJUST, ACT_ARBITRATE):
        sc = db.get(Score, score_id)
        if sc is None:
            raise HTTPException(404, "成绩不存在")
        if body.new_score is None:
            raise HTTPException(422, f"{body.action} 需要 new_score")
        lo, hi = 0.0, sc.max_score
        if not (lo <= body.new_score <= hi):
            raise HTTPException(422, f"改分需在 [0, {hi:g}] 内")
    try:
        result = apply_review(db, score_id, body.action, cur.username, cur.id,
                              new_score=body.new_score, comment=body.comment)
    except DoubleReviewError as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    if result is None:  # return_model: 已删除该成绩, 回到待评
        return {"ok": True, "action": body.action,
                "message": "已退回模型重评, 原成绩与证据已清除"}
    msg = ""
    dbl = (result.extra or {}).get("double")
    if dbl and dbl.get("state") == "await_pass2":
        msg = "第一评已记录。该卷进入双评待第二评, 需另一位教师独立复核。"
    elif dbl and dbl.get("state") == "await_arbitrate":
        msg = "两教师分差超容差, 已进入待仲裁, 需第三位教师终审。"
    elif dbl and dbl.get("state") == "done":
        msg = dbl.get("message", "双评/仲裁完成")
    out = {"ok": True, "action": body.action, "score": score_dict(result)}
    if msg:
        out["message"] = msg
    return out
