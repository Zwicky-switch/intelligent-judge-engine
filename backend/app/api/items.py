"""题库: 题目草稿/详情/发布/停用(命题教师与教务), 删除(仅教务管理员)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.constants import (
    ALL_ITEM_TYPES, ROLE_ADMIN, ROLE_PROP_TEACHER, OBJECTIVE_TYPES,
)
from app.core.deps import CurrentUser, require_roles
from app.db import get_db
from app.models import (
    Answer, AuditLog, Course, Evidence, Item, ItemVersion, PublishApproval,
    ReviewRecord, Score, User,
)
from app.models.base import utcnow

from app.api.serializers import item_dict

router = APIRouter(prefix="/items", tags=["题库"])
STAFF = (ROLE_ADMIN, ROLE_PROP_TEACHER)


def _parse_dt(s: str | None) -> datetime | None:
    """解析 ISO 时间串(前端 el-date-picker value-format), 非法抛 422."""
    if s is None or not str(s).strip():
        return None
    try:
        return datetime.fromisoformat(str(s).strip().replace("Z", "+00:00"))
    except ValueError as e:
        raise HTTPException(422, f"时间格式非法(需 YYYY-MM-DDTHH:mm:ss): {s}") from e


def _delete_upload(uri: str) -> None:
    """删除答卷关联的上传文件(音频/图片/视频), 仅限 UPLOAD_DIR 内防越界."""
    if not uri:
        return
    try:
        p = Path(uri).resolve()
        base = Path(settings.UPLOAD_DIR).resolve()
        if p.is_relative_to(base) and p.is_file():
            p.unlink(missing_ok=True)
    except Exception:
        pass


class ItemBody(BaseModel):
    code: str | None = None
    type: str
    title: str
    course_id: int
    chapter_id: int | None = None
    max_score: float = Field(default=10.0, gt=0)
    cognitive_level: str = "apply"
    answer_config: dict = Field(default_factory=dict)
    rubric: list = Field(default_factory=list)
    reference_answer: str = ""
    knowledge_nodes: list = Field(default_factory=list)
    q_matrix: dict = Field(default_factory=dict)
    scoring_policy: dict = Field(default_factory=dict)
    difficulty: float = 0.0
    discrimination: float = 1.0
    # 提交截止时间(ISO 串, 空=不限时); 发布时间 published_at 由发布动作自动写入, 不可手填
    submit_deadline: str | None = None


@router.get("")
def list_items(
    type: str | None = None,
    chapter_id: int | None = None,
    published: bool | None = None,
    course_id: int | None = None,
    cur: CurrentUser = Depends(require_roles(*STAFF)),
    db: Session = Depends(get_db),
):
    q = db.query(Item)
    if type:
        q = q.filter(Item.type == type)
    if chapter_id is not None:
        q = q.filter(Item.chapter_id == chapter_id)
    if published is not None:
        q = q.filter(Item.published == published)
    if course_id is not None:
        q = q.filter(Item.course_id == course_id)
    rows = q.order_by(Item.code).all()
    return {"items": [item_dict(i) for i in rows], "total": len(rows)}


@router.get("/types")
def item_types(cur: CurrentUser = Depends(require_roles(*STAFF))):
    from app.constants import ITEM_TYPE_LABELS, MODALITY_TEXT, ITEM_MODALITY
    return {"types": [
        {"value": t, "label": ITEM_TYPE_LABELS[t],
         "objective": t in OBJECTIVE_TYPES, "modality": ITEM_MODALITY[t]}
        for t in sorted(ALL_ITEM_TYPES)]}


@router.get("/{item_id}")
def get_item(item_id: int, cur: CurrentUser = Depends(require_roles(*STAFF)),
             db: Session = Depends(get_db)):
    it = db.get(Item, item_id)
    if it is None:
        raise HTTPException(404, "题目不存在")
    d = item_dict(it)
    d["answer_count"] = db.query(Answer).filter(Answer.item_id == item_id).count()
    return d


@router.post("")
def create_item(body: ItemBody, cur: CurrentUser = Depends(require_roles(*STAFF)),
                db: Session = Depends(get_db)):
    if body.type not in ALL_ITEM_TYPES:
        raise HTTPException(422, f"不支持题型 {body.type}")
    if db.get(Course, body.course_id) is None:
        raise HTTPException(404, "课程不存在")
    code = (body.code or "").strip() or f"auto-{body.course_id}"
    if db.query(Item).filter(Item.code == code).first():
        raise HTTPException(409, f"题目编号 {code} 已存在")
    it = Item(code=code, type=body.type, course_id=body.course_id,
              chapter_id=body.chapter_id, title=body.title, max_score=body.max_score,
              cognitive_level=body.cognitive_level,
              answer_config=body.answer_config, rubric=body.rubric,
              reference_answer=body.reference_answer,
              knowledge_nodes=body.knowledge_nodes, q_matrix=body.q_matrix,
              scoring_policy=body.scoring_policy,
              difficulty=body.difficulty, discrimination=body.discrimination,
              submit_deadline=_parse_dt(body.submit_deadline),
              published=False, created_by=cur.id)
    db.add(it)
    db.commit()
    return item_dict(it)


@router.put("/{item_id}")
def update_item(item_id: int, body: ItemBody,
                cur: CurrentUser = Depends(require_roles(*STAFF)),
                db: Session = Depends(get_db)):
    it = db.get(Item, item_id)
    if it is None:
        raise HTTPException(404, "题目不存在")
    # 已发布题目允许修订: 内容可直接更新, 历史成绩绑定旧版本快照不回写;
    # 更新后再次"发布/修订发布"即固化新版本快照(版本+1)。
    it.type = body.type
    it.title = body.title
    it.course_id = body.course_id
    it.chapter_id = body.chapter_id
    it.max_score = body.max_score
    it.cognitive_level = body.cognitive_level
    it.answer_config = body.answer_config
    it.rubric = body.rubric
    it.reference_answer = body.reference_answer
    it.knowledge_nodes = body.knowledge_nodes
    it.q_matrix = body.q_matrix
    it.scoring_policy = body.scoring_policy
    it.difficulty = body.difficulty
    it.discrimination = body.discrimination
    it.submit_deadline = _parse_dt(body.submit_deadline)
    db.commit()
    return item_dict(it)


def _needed_approvals(it: Item) -> int:
    return 2 if (it.scoring_policy or {}).get("require_double_publish") else 1


@router.post("/{item_id}/publish")
def publish_item(item_id: int, comment: str = "",
                 cur: CurrentUser = Depends(require_roles(*STAFF)),
                 db: Session = Depends(get_db)):
    """发布(双人复核: scoring_policy.require_double_publish=true 需 ≥2 个不同账号复核).

    复核账足 -> 固化 ItemVersion 快照并置 published=True; 不足 -> 记录复核并保持草稿。
    """
    it = db.get(Item, item_id)
    if it is None:
        raise HTTPException(404, "题目不存在")
    need = _needed_approvals(it)
    db.add(PublishApproval(item_id=it.id, reviewer_id=cur.id, comment=comment))
    db.flush()
    approver_ids = {r.reviewer_id for r in db.query(PublishApproval)
                    .filter(PublishApproval.item_id == it.id).all()}
    if len(approver_ids) < need:
        db.commit()
        out = item_dict(it)
        out.update({"publish_pending": True, "approvals_needed": need,
                    "approvals_received": len(approver_ids),
                    "message": (f"双人复核发布: 已登记复核 {len(approver_ids)}/{need} 个账号, "
                                "还需不同账号复核后才真正发布。" if need > 1 else
                                "复核已登记。")})
        return out
    # 复核账足: 固化本次快照并发布(首次发布=版本1; 修订发布=版本+1)
    it.current_version = (it.current_version or 1) + (1 if it.published else 0)
    db.add(ItemVersion(item_id=it.id, version=it.current_version,
                       rubric=it.rubric, answer_config=it.answer_config,
                       reference_answer=it.reference_answer,
                       knowledge_nodes=it.knowledge_nodes, q_matrix=it.q_matrix,
                       max_score=it.max_score, scoring_policy=it.scoring_policy,
                       published_by=cur.id))
    it.published = True
    it.published_at = utcnow()   # 发布时间 = 最近一次真正发布/修订发布的时刻
    db.commit()
    out = item_dict(it)
    out.update({"publish_pending": False, "approvals_needed": need,
                "approvals_received": len(approver_ids),
                "message": f"已发布并固化版本快照(v{it.current_version})，历史成绩不回写。"})
    return out


@router.post("/{item_id}/toggle")
def toggle_item(item_id: int, enabled: bool = Query(...),
                cur: CurrentUser = Depends(require_roles(*STAFF)),
                db: Session = Depends(get_db)):
    it = db.get(Item, item_id)
    if it is None:
        raise HTTPException(404, "题目不存在")
    it.enabled = enabled
    db.commit()
    return item_dict(it)


@router.delete("/{item_id}")
def delete_item(item_id: int,
                cur: CurrentUser = Depends(require_roles(ROLE_ADMIN)),
                db: Session = Depends(get_db)):
    """删除题目及该题全部数据(仅教务管理员): 版本快照/发布复核/答卷/成绩/证据/复核记录/上传文件."""
    it = db.get(Item, item_id)
    if it is None:
        raise HTTPException(404, "题目不存在")
    score_ids = [s.id for s in db.query(Score).filter(Score.item_id == item_id).all()]
    answer_ids = [a.id for a in db.query(Answer).filter(Answer.item_id == item_id).all()]
    # 1) 上传文件(仅 UPLOAD_DIR 内)
    for (uri,) in db.query(Answer.content_uri).filter(Answer.item_id == item_id).all():
        _delete_upload(uri)
    # 2) 教师复核/仲裁记录(经 score 关联)
    if score_ids:
        db.query(ReviewRecord).filter(ReviewRecord.score_id.in_(score_ids)).delete(
            synchronize_session=False)
    # 3) 评分证据(按 answer/score/item 关联)
    db.query(Evidence).filter(
        (Evidence.item_id == item_id)
        | ((Evidence.answer_id.isnot(None)) & (Evidence.answer_id.in_(answer_ids)))
        | ((Evidence.score_id.isnot(None)) & (Evidence.score_id.in_(score_ids)))
    ).delete(synchronize_session=False)
    # 4) 成绩
    if score_ids:
        db.query(Score).filter(Score.id.in_(score_ids)).delete(synchronize_session=False)
    # 5) 答卷
    if answer_ids:
        db.query(Answer).filter(Answer.id.in_(answer_ids)).delete(synchronize_session=False)
    # 6) 发布双人复核登记 / 版本快照
    db.query(PublishApproval).filter(PublishApproval.item_id == item_id).delete(
        synchronize_session=False)
    n_versions = db.query(ItemVersion).filter(ItemVersion.item_id == item_id).delete(
        synchronize_session=False)
    # 7) 审计留痕(审计记录本身不可删除)
    db.add(AuditLog(actor=cur.username, actor_id=cur.id, action="item.delete",
                    target_type="item", target_id=str(item_id),
                    detail={"code": it.code, "title": it.title,
                            "answers": len(answer_ids), "scores": len(score_ids)}))
    db.delete(it)
    db.commit()
    return {"ok": True, "deleted": {
        "item_id": item_id, "code": it.code,
        "versions": n_versions, "answers": len(answer_ids), "scores": len(score_ids)}}


# ---------------- 版本快照 / 比较 / 发布复核状态 ----------------

@router.get("/{item_id}/versions")
def list_versions(item_id: int,
                  cur: CurrentUser = Depends(require_roles(*STAFF)),
                  db: Session = Depends(get_db)):
    it = db.get(Item, item_id)
    if it is None:
        raise HTTPException(404, "题目不存在")
    rows = (db.query(ItemVersion).filter(ItemVersion.item_id == item_id)
            .order_by(ItemVersion.version.asc()).all())
    names = {u.id: u.username for u in db.query(User).all()}
    return {"item_id": item_id, "current_version": it.current_version,
            "items": [_version_dict(v, names) for v in rows]}


@router.get("/{item_id}/versions/compare")
def compare_versions(item_id: int, v1: int = Query(...), v2: int = Query(...),
                     cur: CurrentUser = Depends(require_roles(*STAFF)),
                     db: Session = Depends(get_db)):
    a = _get_version(db, item_id, v1)
    b = _get_version(db, item_id, v2)
    changes = []
    for f in ("rubric", "answer_config", "reference_answer", "knowledge_nodes",
              "q_matrix", "scoring_policy", "max_score"):
        d = _field_diff(f, getattr(a, f), getattr(b, f))
        if d:
            changes.append(d)
    return {"item_id": item_id, "v1": v1, "v2": v2, "changes": changes}


@router.get("/{item_id}/versions/{version}")
def get_version(item_id: int, version: int,
                cur: CurrentUser = Depends(require_roles(*STAFF)),
                db: Session = Depends(get_db)):
    v = _get_version(db, item_id, version)
    names = {u.id: u.username for u in db.query(User).all()}
    return _version_dict(v, names)


@router.get("/{item_id}/publish-status")
def publish_status(item_id: int,
                   cur: CurrentUser = Depends(require_roles(*STAFF)),
                   db: Session = Depends(get_db)):
    it = db.get(Item, item_id)
    if it is None:
        raise HTTPException(404, "题目不存在")
    rows = (db.query(PublishApproval).filter(PublishApproval.item_id == item_id)
            .order_by(PublishApproval.id.asc()).all())
    need = _needed_approvals(it)
    ids = [r.reviewer_id for r in rows]
    names = {u.id: u.username for u in db.query(User)
             .filter(User.id.in_([i for i in ids if i])).all()}
    approvals = [{"reviewer_id": r.reviewer_id,
                  "reviewer_name": names.get(r.reviewer_id, f"#{r.reviewer_id}"),
                  "comment": r.comment or "",
                  "created_at": r.created_at.isoformat() if r.created_at else None}
                 for r in rows]
    return {**item_dict(it),
            "publish_pending": bool(it.published is False),
            "approvals_needed": need,
            "approvals_received": len({i for i in ids if i}),
            "approvals": approvals,
            "can_publish": len({i for i in ids if i}) >= need}


def _get_version(db: Session, item_id: int, version: int) -> ItemVersion:
    v = (db.query(ItemVersion).filter(ItemVersion.item_id == item_id,
                                      ItemVersion.version == version).first())
    if v is None:
        raise HTTPException(404, f"版本 {version} 不存在")
    return v


def _version_dict(v: ItemVersion, names: dict) -> dict:
    return {
        "item_id": v.item_id, "version": v.version,
        "rubric": v.rubric or [], "answer_config": v.answer_config or {},
        "reference_answer": v.reference_answer or "",
        "knowledge_nodes": v.knowledge_nodes or [], "q_matrix": v.q_matrix or {},
        "scoring_policy": v.scoring_policy or {}, "max_score": v.max_score,
        "published_by": v.published_by,
        "published_by_name": names.get(v.published_by, ""),
        "published_at": v.published_at.isoformat() if v.published_at else None,
    }


def _preview(value) -> str:
    s = str(value)
    return s if len(s) <= 120 else s[:117] + "..."


def _field_diff(field: str, a, b) -> dict | None:
    """浅比较两版本某字段: 相等 None; dict 级比较键的增/删/改; 其余给出前后预览."""
    if a == b:
        return None
    if isinstance(a, dict) and isinstance(b, dict):
        added = sorted(k for k in b if k not in a)
        removed = sorted(k for k in a if k not in b)
        changed = sorted(k for k in set(a) & set(b) if a[k] != b[k])
        return {"field": field, "kind": "changed",
                "detail": {"added": added, "removed": removed, "changed": changed},
                "before": _preview(a), "after": _preview(b)}
    return {"field": field, "kind": "changed",
            "before": _preview(a), "after": _preview(b)}
