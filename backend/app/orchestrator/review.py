"""教师复核 / 仲裁 / 退回 / 双评, 以及不可删除审计."""
from __future__ import annotations

import threading
from datetime import datetime, timezone

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.constants import (
    ACT_ACCEPT, ACT_ADJUST, ACT_ARBITRATE, ACT_DOUBLE_PASS1, ACT_DOUBLE_PASS2,
    ACT_RETURN,
    ST_AUTO_PASSED, ST_NEEDS_REVIEW, ST_REVIEWED,
)
from app.models import Answer, AuditLog, Evidence, Item, ReviewRecord, Score


def _audit(db: Session, actor: str, actor_id: int | None, action: str,
           target_type: str, target_id: int | str, detail: dict | None = None):
    db.add(AuditLog(actor=actor, actor_id=actor_id, action=action,
                    target_type=target_type, target_id=str(target_id),
                    detail=detail or {}))


def _double_tolerance(max_score: float) -> float:
    """双评容差: ±1 分与 ±10% 满分 取较严者."""
    return round(min(1.0, 0.1 * float(max_score)), 2)


# ---- 每分卷进程内锁: 串行化双评的"读-改-写", 防并发下两笔第 1 评互相覆盖 ----
_SCORE_LOCK_GUARD = threading.Lock()
_SCORE_LOCKS: dict[int, threading.Lock] = {}


def _score_lock(score_id: int) -> threading.Lock:
    with _SCORE_LOCK_GUARD:
        lock = _SCORE_LOCKS.get(score_id)
        if lock is None:
            lock = _SCORE_LOCKS[score_id] = threading.Lock()
        return lock


class DoubleReviewError(ValueError):
    """双评流程冲突(如: 同一位教师重复评同一卷, 而非两位不同教师独立评)."""


def _apply_double(db: Session, score: Score, action: str, teacher_username: str,
                  teacher_id: int | None, new_score: float | None,
                  comment: str) -> Score:
    """双评/三评流程(最小真实):

    1) 第一位教师独立评(accept/adjust) -> double_pass1, 卷仍待评(等待第二评);
    2) 第二位不同教师独立评 -> double_pass2:
       - 分差 <= 容差 -> 均值自动终审(double_finalize);
       - 分差 > 容差 -> 卷进入"需仲裁", 仍待第三位教师;
    3) 第三位不同教师 arbitrate(new_score) -> 终审。
    阶段状态写入 score.extra["double"], 供阅卷台展示(第几评/独立分)。
    """
    from app.constants import ACT_DOUBLE_PASS1, ACT_DOUBLE_PASS2

    passes = (db.query(ReviewRecord)
              .filter(ReviewRecord.score_id == score.id,
                      ReviewRecord.action.in_([ACT_DOUBLE_PASS1, ACT_DOUBLE_PASS2]))
              .order_by(ReviewRecord.id).all())
    done_by = [r.reviewed_by for r in passes if r.reviewed_by]
    if teacher_id is not None and teacher_id in done_by:
        raise DoubleReviewError("本卷已完成您的独立评阅, 双评需另一位教师独立完成")

    ext = dict(score.extra or {})
    double = dict(ext.get("double") or
                  {"mode": "double", "passes": [], "state": "await_pass1"})
    passes_vals = [p["score"] for p in double.get("passes", [])]
    detail = {"item_version": score.item_version, "model_version": score.model_version,
              "review_mode": "double"}
    now = datetime.now(timezone.utc)

    # 状态机前置校验: 只有两评齐且超差(await_arbitrate)才可由第三位教师仲裁;
    # 已进入待仲裁的卷不再接受新的独立改分(防止被误记为 double_pass2 覆盖终局)。
    state = double.get("state", "await_pass1")
    if action == ACT_ARBITRATE and state != "await_arbitrate":
        raise DoubleReviewError(
            "仲裁仅在两教师分差超容差进入待仲裁后, 由第三位教师执行终审")
    if action != ACT_ARBITRATE and state == "await_arbitrate":
        raise DoubleReviewError(
            "该卷两评已超容差进入待仲裁, 需第三位教师仲裁终审, 不再接受独立改分")

    # 已有两笔独立分 -> 第三位教师仲裁终审
    if action == ACT_ARBITRATE and len(passes_vals) >= 2:
        if new_score is None:
            raise ValueError("仲裁需提供 new_score")
        final = max(0.0, min(score.max_score, float(new_score)))
        old_final = score.final_score if score.final_score is not None else score.total_score
        score.final_score = round(final, 2)
        score.status = ST_REVIEWED
        score.review_round = (score.review_round or 0) + 1
        score.reviewed_by = teacher_id
        score.reviewed_at = now
        if comment:
            score.comment = comment
        double.update({"state": "done", "final_method": "arbitrate",
                       "arbitrated_by": teacher_username,
                       "message": f"双评分差超容差, 第三位教师仲裁终审 {score.final_score}"})
        ext["double"] = double
        score.extra = ext
        db.add(ReviewRecord(score_id=score.id, action=ACT_ARBITRATE,
                            old_score=old_final, new_score=score.final_score,
                            comment=comment, reviewed_by=teacher_id))
        _audit(db, teacher_username, teacher_id, "review.arbitrate", "score", score.id,
               {**detail, "old": old_final, "new": score.final_score, "double": double})
        db.commit()
        return score

    # 独立评(accept=引擎分作本人独立分; adjust=本人改分)
    val = score.total_score if new_score is None else float(new_score)
    val = max(0.0, min(score.max_score, val))
    val = round(val, 2)
    pass_no = len(passes_vals) + 1
    pass_action = ACT_DOUBLE_PASS1 if pass_no == 1 else ACT_DOUBLE_PASS2
    double.setdefault("passes", []).append({
        "score": val, "by": teacher_username,
        "at": now.isoformat(timespec="seconds")})
    double["by_ids"] = done_by + ([teacher_id] if teacher_id else [])
    ext["double"] = double
    score.extra = ext
    db.add(ReviewRecord(score_id=score.id, action=pass_action,
                        old_score=score.total_score, new_score=val,
                        comment=comment, reviewed_by=teacher_id))
    _audit(db, teacher_username, teacher_id, f"review.{pass_action}", "score", score.id,
           {**detail, "pass_no": pass_no, "value": val})

    if pass_no == 1:
        double["state"] = "await_pass2"
        double["message"] = "第一评已记录(独立)。等待第二位教师复核后取均值/仲裁。"
        ext["double"] = double
        score.extra = ext
        db.commit()
        return score

    # 第二评: 判差
    v1, v2 = passes_vals[0], val
    diff = round(abs(v1 - v2), 2)
    tol = _double_tolerance(score.max_score)
    if diff <= tol:
        final = round((v1 + v2) / 2, 2)
        old_final = score.final_score if score.final_score is not None else score.total_score
        score.final_score = final
        score.status = ST_REVIEWED
        score.review_round = (score.review_round or 0) + 1
        score.reviewed_by = teacher_id
        score.reviewed_at = now
        double.update({"state": "done", "final_method": "avg", "diff": diff, "tolerance": tol,
                       "message": f"双评一致(分差 {diff} ≤ 容差 {tol}), 终审取均值 {final}"})
        ext["double"] = double
        score.extra = ext
        db.add(ReviewRecord(score_id=score.id, action=ACT_ACCEPT,
                            old_score=old_final, new_score=final,
                            comment=f"双评取均值(v1={v1}, v2={val})", reviewed_by=teacher_id))
        _audit(db, teacher_username, teacher_id, "review.double_finalize", "score", score.id,
               {**detail, "v1": v1, "v2": val, "final": final, "method": "avg"})
        db.commit()
        return score

    double.update({"state": "await_arbitrate", "diff": diff, "tolerance": tol,
                   "message": f"两教师分差 {diff} > 容差 {tol}, 需第三位教师仲裁。"})
    ext["double"] = double
    score.extra = ext
    db.commit()
    return score


def apply_review(db: Session, score_id: int, action: str, teacher_username: str,
                 teacher_id: int | None, new_score: float | None = None,
                 comment: str = "") -> Score | None:
    """执行一次复核操作. 返回更新后的 Score; return_model 后返回 None.

    全程持有该分卷的进程内锁: 并发(如两位教师同时点同一卷)时串行化"读-改-写",
    并在锁内回滚锁前会话的快照、以 populate_existing 重读, 保证看到最新已提交状态,
    避免双评的两次第 1 评互相覆盖或仲裁前置条件读到旧状态。
    """
    with _score_lock(score_id):
        db.rollback()  # 丢弃锁外读到的旧快照(如 API 层预校验的读取), 锁内重读最新
        score = db.query(Score).filter(Score.id == score_id) \
            .populate_existing().one_or_none()
        if score is None:
            raise ValueError("Score 不存在")
        answer = db.get(Answer, score.answer_id)
        detail = {"item_version": score.item_version, "model_version": score.model_version}

        # 双评题: 待评状态下的 accept/adjust/arbitrate 进入双评流程(改分范围校验在 API 层)
        item = db.get(Item, score.item_id)
        is_double = (item is not None
                     and (item.scoring_policy or {}).get("review_mode") == "double"
                     and score.status == ST_NEEDS_REVIEW
                     and action != ACT_RETURN)
        if is_double:
            return _apply_double(db, score, action, teacher_username, teacher_id,
                                 new_score, comment)

        if action == ACT_RETURN:
            # 退回模型重评: 清空当前成绩、复核轨迹与证据, 答案回到待评状态。
            # Score 一并删除, 故其上的 ReviewRecord(含双评/终审记录)必须同步删除,
            # 否则留悬空引用并污染一致性等指标。退回动作本身记入不可删除审计。
            _audit(db, teacher_username, teacher_id, "review.return_model",
                   "score", score_id, {**detail, "comment": comment})
            db.execute(delete(ReviewRecord).where(ReviewRecord.score_id == score.id))
            db.execute(delete(Evidence).where(Evidence.score_id == score.id))
            if answer:
                answer.graded = False
                answer.error = "教师退回模型重评"
            db.delete(score)
            db.commit()
            return None

        if action not in (ACT_ACCEPT, ACT_ADJUST, ACT_ARBITRATE):
            raise ValueError(f"未知复核动作: {action}")

        old_final = score.final_score if score.final_score is not None else score.total_score
        if action == ACT_ACCEPT:
            final = score.total_score
        elif action in (ACT_ADJUST, ACT_ARBITRATE):
            final = score.total_score if new_score is None else new_score

        score.final_score = round(float(final), 2)
        score.status = ST_REVIEWED
        score.review_round = (score.review_round or 0) + 1
        score.reviewed_by = teacher_id
        score.reviewed_at = datetime.now(timezone.utc)
        if comment:
            score.comment = comment

        db.add(ReviewRecord(score_id=score.id, action=action,
                            old_score=old_final, new_score=score.final_score,
                            comment=comment, reviewed_by=teacher_id))
        _audit(db, teacher_username, teacher_id, f"review.{action}", "score", score.id,
               {**detail, "old": old_final, "new": score.final_score})
        db.commit()
        return score


def list_review_queue(db: Session, review_level: str | None = None,
                      item_type: str | None = None):
    q = db.query(Score, Answer, Item).join(Answer, Answer.id == Score.answer_id) \
        .join(Item, Item.id == Score.item_id) \
        .filter(Score.status == ST_NEEDS_REVIEW)
    if review_level:
        q = q.filter(Score.review_level == review_level)
    if item_type:
        q = q.filter(Item.type == item_type)
    return q.order_by(Score.created_at.asc()).all()


def list_recent(db: Session, limit: int = 50):
    q = db.query(Score, Answer, Item).join(Answer, Answer.id == Score.answer_id) \
        .join(Item, Item.id == Score.item_id)
    return q.order_by(Score.created_at.desc()).limit(limit).all()
