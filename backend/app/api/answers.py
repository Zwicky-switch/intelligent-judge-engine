"""答卷: 提交(即时评阅) / 音频上传(口语) / 查询."""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.constants import (
    ITEM_MODALITY, MODALITY_TEXT, OBJECTIVE_TYPES, T_SPOKEN,
    ROLE_ADMIN, ROLE_GRADER, ROLE_PROP_TEACHER, ROLE_STUDENT, ST_NEEDS_REVIEW,
)
from app.core.deps import CurrentUser, require_roles, get_current_user
from app.db import get_db
from app.models import Answer, Item
from app.parsers.audio import ALLOWED_AUDIO_EXT, basic_audio_check, get_asr
from app.parsers.text import quality_gate_text
from app.orchestrator.runner import default_llm, grade_answer

from app.api.serializers import answer_dict, item_dict, score_dict

router = APIRouter(prefix="/answers", tags=["答卷"])
STAFF = (ROLE_ADMIN, ROLE_PROP_TEACHER, ROLE_GRADER)


class AnswerSubmit(BaseModel):
    item_id: int
    # 学生端可省略(用自己 token); 教师/管理员可为指定学生代录
    student_token: str | None = None
    # 文本模态: content=规范化作答; 客观题(选择/填空/数值)即为答题串(如 "A" / "5 m/s^2")
    content: str = ""
    # 客观题原文(可空; 与 content 一致)
    raw_response: str | None = None
    content_uri: str = ""
    modality: str | None = None
    # 口语: 若为人工誊抄或已完成 ASR 的转写文本, 用 content 传入并在此注明来源
    asr_note: str | None = None
    segments: list = Field(default_factory=list)


@router.post("")
def submit_answer(body: AnswerSubmit, cur: CurrentUser = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    item = db.get(Item, body.item_id)
    if item is None:
        raise HTTPException(404, "题目不存在")
    if not item.published or not item.enabled:
        raise HTTPException(409, "题目未发布或已停用, 暂不可作答")

    # 归属校验: 学生只能提交自己的答卷
    if cur.role == ROLE_STUDENT:
        token = cur.student_token
        if body.student_token not in (None, token):
            raise HTTPException(403, "学生只能提交本人答卷")
    else:
        token = (body.student_token or "").strip() or cur.student_token
        if not token:
            raise HTTPException(422, "请指定 student_token(或由学生本人提交)")

    modality = body.modality or ITEM_MODALITY.get(item.type, MODALITY_TEXT)
    content = (body.content or "").strip()
    raw = (body.raw_response if body.raw_response is not None else content).strip()

    # 质量门控(入库 quality = 门控结果; 主观题空/过短不会自动判零而是强制复核)
    if item.type in OBJECTIVE_TYPES:
        quality = quality_gate_text(raw, item_type=item.type)
    else:
        quality = quality_gate_text(content, item_type=item.type)
    if body.asr_note:
        quality["note_asr"] = body.asr_note
    elif item.type == T_SPOKEN and not (body.content_uri or "").strip() and not (body.segments or []):
        # 口语题仅提交文本(无音频文件/词级时间戳) -> 视作人工誊抄转写, 诚实标注证据来源
        quality["note_asr"] = "manual_transcript"

    ans = Answer(
        trace_id=f"{token}:{item.id}:{uuid.uuid4().hex[:10]}",
        student_token=token, item_id=item.id, modality=modality,
        content=content, raw_response=raw,
        content_uri=(body.content_uri or "").strip(),
        segments=body.segments or [], quality=quality,
    )
    db.add(ans)
    db.flush()

    # 即时评阅(离线无 Key 时自动用本地确定性引擎)
    try:
        score = grade_answer(db, ans, llm=default_llm())
    except Exception as e:  # noqa: BLE001
        ans.graded = False
        ans.error = str(e)[:400]
        db.commit()
        raise HTTPException(500, f"评阅过程异常: {e}") from e
    db.commit()

    data = {"answer": answer_dict(ans), "item": item_dict(item)}
    if score is not None:
        data["score"] = score_dict(score)
        if score.status == ST_NEEDS_REVIEW:
            data["message"] = "已评阅, 依据判定置信度该答卷需教师复核, 成绩以终审为准"
        else:
            data["message"] = "评阅完成"
    else:
        data["score"] = None
        data["message"] = "已接收答卷, 待批量评阅(异步)"
    return data


@router.post("/audio")
def submit_audio_answer(
    item_id: int = Form(...),
    content: str = Form(""),                       # 前端 ASR / 人工誊抄的转写文本(可空)
    student_token: str | None = Form(None),
    asr_note: str | None = Form(None),            # 转写来源说明(如前端 asr / manual_transcript)
    audio: UploadFile | None = File(None),
    cur: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """口语题录音上传契约: 存原始录音(content_uri)并按转写文本即时评阅.

    未装 faster-whisper 时要求随附转写文本(content); 装后(可选)可由本服务
    直接转写并产出词级时间戳 segments -> 流畅层/未来发音层才有依据。
    发音层在无强制对齐前仍如实标注"无数据"。
    """
    if audio is None or not (audio.filename or "").strip():
        raise HTTPException(422, "缺少录音文件(audio)")
    item = db.get(Item, item_id)
    if item is None:
        raise HTTPException(404, "题目不存在")
    if not item.published or not item.enabled:
        raise HTTPException(409, "题目未发布或已停用, 暂不可作答")
    if item.type != T_SPOKEN:
        raise HTTPException(422, "录音上传目前仅支持口语题")

    if cur.role == ROLE_STUDENT:
        token = cur.student_token
        if student_token not in (None, token):
            raise HTTPException(403, "学生只能提交本人答卷")
    else:
        token = (student_token or "").strip() or cur.student_token
        if not token:
            raise HTTPException(422, "请指定 student_token(或由学生本人提交)")

    transcript = (content or "").strip()
    # 无转写文本 -> 需要本服务 ASR; 离线未装 faster-whisper 时直接给出可执行建议
    adapter = get_asr(manual_transcript=transcript) if transcript else get_asr()
    if adapter is None and not transcript:
        raise HTTPException(422, "未提供转写文本且本服务未接入 ASR: "
                                 "请人工誊抄后把文本放到 content 字段, 或安装 faster-whisper 自动转写")

    ext = Path(audio.filename).suffix.lower()
    if ext not in ALLOWED_AUDIO_EXT:
        raise HTTPException(422, f"不支持的音频格式 {ext or '(无扩展名)'}")
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = settings.UPLOAD_DIR / f"{token}-{uuid.uuid4().hex[:10]}{ext}"
    try:
        dest.write_bytes(audio.file.read())
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"保存录音失败: {e}") from e
    acheck = basic_audio_check(dest)

    segments: list = []
    src = asr_note or "manual_transcript"
    if transcript:
        segments = []           # 人工誊抄侧车: 无词级对齐, 流畅层如实 nodata
    else:
        try:
            transcript, segments, src = adapter.transcribe(dest)
            transcript = (transcript or "").strip()
        except Exception as e:  # noqa: BLE001
            dest.unlink(missing_ok=True)
            raise HTTPException(500, f"ASR 转写失败: {e}") from e
        if not transcript:
            dest.unlink(missing_ok=True)
            raise HTTPException(422, "ASR 未能从录音中识别出有效文本")

    quality = quality_gate_text(transcript, item_type="spoken")
    quality["note_asr"] = "whisper" if src == "whisper" else "manual_transcript"
    if acheck.get("duration_ms") is not None:
        quality["duration_ms"] = acheck["duration_ms"]
    if acheck.get("flags"):
        quality["flags"] = sorted(set(quality.get("flags") or []) | set(acheck["flags"]))

    ans = Answer(
        trace_id=f"{token}:{item.id}:{uuid.uuid4().hex[:10]}",
        student_token=token, item_id=item.id, modality="audio",
        content=transcript, raw_response="",
        content_uri=str(dest.resolve()), segments=segments, quality=quality,
    )
    db.add(ans)
    db.flush()
    try:
        score = grade_answer(db, ans, llm=default_llm())
    except Exception as e:  # noqa: BLE001
        ans.graded = False
        ans.error = str(e)[:400]
        db.commit()
        dest.unlink(missing_ok=True)
        raise HTTPException(500, f"评阅过程异常: {e}") from e
    db.commit()

    data = {"answer": answer_dict(ans), "item": item_dict(item)}
    if score is not None:
        data["score"] = score_dict(score)
        data["message"] = ("已评阅, 依据判定置信度该答卷需教师复核, 成绩以终审为准"
                           if score.status == ST_NEEDS_REVIEW else "评阅完成")
    else:
        data["score"] = None
        data["message"] = "已接收录音, 待批量评阅(异步)"
    return data


@router.get("/{answer_id}")
def get_answer(answer_id: int, cur: CurrentUser = Depends(get_current_user),
               db: Session = Depends(get_db)):
    ans = db.get(Answer, answer_id)
    if ans is None:
        raise HTTPException(404, "答卷不存在")
    if cur.role == ROLE_STUDENT and ans.student_token != cur.student_token:
        raise HTTPException(403, "无权查看他人答卷")
    return answer_dict(ans)
