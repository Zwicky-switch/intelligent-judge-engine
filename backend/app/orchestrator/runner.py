"""评分编排器: 选引擎 -> 评阅 -> 落 Score + Evidence -> 置信度路由.

幂等: 同一答案已终审则跳过重评; 反复调用不产生重复计分。
"""
from __future__ import annotations

import logging
import time

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import settings
from app.constants import (
    ALL_ITEM_TYPES, T_VIDEO, T_FORMULA, MODALITY_TEXT,
    OBJECTIVE_TYPES, ST_AUTO_PASSED, ST_NEEDS_REVIEW, LVL_NONE, LVL_SAMPLE,
    LVL_FORCED, MODEL_VERSION,
)
from app.engines.objective import grade_objective
from app.engines.subjective import grade_subjective
from app.engines.spoken import grade_spoken
from app.engines.symbolic import grade_formula
from app.engines.video_stub import grade_video
from app.llm import get_model
from app.models import Answer, Evidence, Item, Score

logger = logging.getLogger(__name__)


def item_engine_dict(item: Item) -> dict:
    return {
        "title": item.title,
        "rubric": item.rubric or [],
        "reference_answer": item.reference_answer or "",
        "max_score": item.max_score,
        "scoring_policy": item.scoring_policy or {},
        "answer_config": item.answer_config or {},
        "knowledge_nodes": item.knowledge_nodes or [],
        "q_matrix": item.q_matrix or {},
    }


def _route_status(item_type: str, outcome) -> tuple[str, str]:
    """路由: 返回 (status, review_level)."""
    if item_type in OBJECTIVE_TYPES:
        return ST_AUTO_PASSED, LVL_NONE
    # 非客观题: 高信度自动放行(none) / 抽样 / 强制, 其余进复核队列
    lvl = outcome.review_level or LVL_SAMPLE
    if lvl == LVL_NONE:
        return ST_AUTO_PASSED, LVL_NONE
    return ST_NEEDS_REVIEW, lvl


def grade_answer(db: Session, answer: Answer, llm=None, model_version: str = MODEL_VERSION) -> Score | None:
    """对单个已通过质量门控的答案执行评阅并落库. 返回 Score."""
    item = db.get(Item, answer.item_id)
    if item is None:
        return None
    # 幂等: 已有终审分则跳过
    existing = db.query(Score).filter(Score.answer_id == answer.id).first()
    if existing is not None:
        if existing.status in (ST_AUTO_PASSED, ST_NEEDS_REVIEW, "reviewed"):
            # 允许把"待复核"重新评阅? 不: 保持一次评阅一致性
            if existing.status == ST_NEEDS_REVIEW:
                pass
            else:
                return existing
        # 重新评阅: 清理旧记录
        db.execute(delete(Evidence).where(Evidence.score_id == existing.id))
        db.delete(existing)
        db.flush()

    item_dict = item_engine_dict(item)
    itype = item.type
    llm = llm if itype not in OBJECTIVE_TYPES else None
    _t0 = time.perf_counter()
    if itype in OBJECTIVE_TYPES:
        outcome = grade_objective(itype, item.answer_config or {}, answer.raw_response or answer.content,
                                  item.max_score, item.scoring_policy)
    elif itype == "subjective_text":
        outcome = grade_subjective(item_dict, answer.content or "", llm=llm,
                                   quality=answer.quality)
    elif itype == "spoken":
        outcome = grade_spoken(item_dict, answer.content or "", segments=answer.segments or [],
                               llm=llm, quality=answer.quality)
    elif itype == T_VIDEO:
        outcome = grade_video(item_dict, answer.content or "", answer.segments or [])
    elif itype == T_FORMULA:
        # 公式符号化题: 确定性等价判定(如 F=ma 与 a=F/m); 空/解析失败在引擎内转人工
        outcome = grade_formula(item.answer_config or {}, answer.content or "",
                                item.max_score, item.scoring_policy)
    else:
        logger.warning("未支持题型 %s (answer %s)", itype, answer.id)
        return None

    status, review_level = _route_status(itype, outcome)
    # 客观题/公式题空卷或质量门控未过: 不静默自动 0, 转人工复核(口径: 宁转人工不静默给 0)
    if (itype in OBJECTIVE_TYPES or itype == T_FORMULA) and not bool((answer.quality or {}).get("pass", True)):
        status, review_level = ST_NEEDS_REVIEW, LVL_FORCED
    final_score = outcome.total if status == ST_AUTO_PASSED else None

    # 引擎元数据落库: 口语 extra.layers(四层)、质量门控、评阅耗时(供延迟指标)
    extra = dict(outcome.extra or {})
    extra["elapsed_ms"] = round((time.perf_counter() - _t0) * 1000.0, 2)
    # 双评题(独立双阅卷): 生成成绩时预置双评骨架, 让复核队列/阅卷台在首评前
    # 即可识别该卷需两位教师独立复核, 并能看到当前所处阶段(await_pass2)。
    if ((item.scoring_policy or {}).get("review_mode") == "double"
            and status == ST_NEEDS_REVIEW):
        extra.setdefault("double", {
            "mode": "double", "passes": [], "by_ids": [], "state": "await_pass1",
            "message": "该卷需两位教师独立复核: 您将是第 1 位评阅教师; 分差在容差内取均值终审, 超差转第三位教师仲裁。"})

    score = Score(
        answer_id=answer.id, item_id=item.id, student_token=answer.student_token,
        item_version=item.current_version, model_version=model_version,
        max_score=item.max_score, total_score=round(outcome.total, 2),
        final_score=round(final_score, 2) if final_score is not None else None,
        point_scores=[{"point_id": p.point_id, "description": p.description, "max": p.max,
                       "status": p.status, "earned": p.earned, "reason": p.reason,
                       "confidence": p.confidence} for p in outcome.point_results],
        penalties=outcome.penalties,
        confidence=round(outcome.confidence, 3),
        status=status, review_level=review_level,
        comment=outcome.comment, reasoning=outcome.reasoning,
        error=outcome.error,
        extra=extra,
    )
    db.add(score)
    db.flush()

    for h in outcome.hits:
        db.add(Evidence(
            answer_id=answer.id, score_id=score.id, item_id=item.id,
            point_id=h.point_id, source_type=h.source_type,
            ref_start=h.ref_start, ref_end=h.ref_end,
            label=h.label, kind=h.kind, text_snippet=(h.snippet or "")[:400],
            confidence=h.confidence, created_by="engine",
        ))
    answer.graded = True
    if outcome.error:
        answer.error = outcome.error
    db.flush()
    return score


def grade_answers_batch(db: Session, answer_ids: list[int], llm=None) -> dict:
    stats = {"attempted": 0, "ok": 0, "error": 0, "auto": 0, "review": 0}
    for aid in answer_ids:
        ans = db.get(Answer, aid)
        if ans is None or ans.graded:
            continue
        stats["attempted"] += 1
        try:
            sc = grade_answer(db, ans, llm=llm)
            if sc is None:
                stats["error"] += 1
                continue
            stats["ok"] += 1
            if sc.status == ST_AUTO_PASSED:
                stats["auto"] += 1
            else:
                stats["review"] += 1
        except Exception as e:  # noqa: BLE001
            logger.exception("评阅失败 answer=%s", aid)
            stats["error"] += 1
            ans.error = str(e)[:400]
    db.commit()
    return stats


def default_llm():
    try:
        return get_model()
    except Exception as e:  # noqa: BLE001
        logger.warning("评阅模型不可用: %s; 使用本地确定性判点", e)
        return None
