"""答卷: 提交(即时评阅) / 音频上传(口语) / 查询."""
from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.constants import (
    ITEM_MODALITY, MODALITY_TEXT, OBJECTIVE_TYPES, T_SPOKEN, T_SUBJECTIVE_TEXT, T_VIDEO,
    ROLE_ADMIN, ROLE_GRADER, ROLE_PROP_TEACHER, ROLE_STUDENT, ST_NEEDS_REVIEW,
)
from app.core.deps import CurrentUser, require_roles, get_current_user
from app.db import get_db
from app.models import Answer, Item
from app.parsers.audio import ALLOWED_AUDIO_EXT, basic_audio_check, get_asr
from app.parsers.image_ocr import (
    ALLOWED_IMAGE_EXT, MAX_IMAGE_BYTES, OCRConfigError, OCRError, ocr_image,
)
from app.parsers.text import quality_gate_text
from app.orchestrator.runner import default_llm, grade_answer

from app.api.serializers import answer_dict, item_dict, score_dict

router = APIRouter(prefix="/answers", tags=["答卷"])
STAFF = (ROLE_ADMIN, ROLE_PROP_TEACHER, ROLE_GRADER)


def _check_deadline(item: Item) -> None:
    """提交截止时间校验: 已过截止 -> 400(前端禁用按钮, 后端兜底).

    deadline 无时区按服务器本地时间解释(前端 el-date-picker 输出本地时间)。
    """
    dl = item.submit_deadline
    if dl is None:
        return
    now = datetime.now().astimezone()   # 本地 aware
    if dl.tzinfo is None:
        dl = dl.replace(tzinfo=now.tzinfo)   # 无时区按本地解释(前端 el-date-picker 输出本地时间)
    else:
        dl = dl.astimezone()
    if now > dl:
        raise HTTPException(
            400,
            f"已超过该题提交截止时间({dl.strftime('%Y-%m-%d %H:%M')}), 不能再提交",
        )

# 上传大小上限(图片见 MAX_IMAGE_BYTES; 音视频给更大但仍有界)
MAX_AUDIO_BYTES = 60 * 1024 * 1024      # 口语录音 60MB
MAX_VIDEO_BYTES = 300 * 1024 * 1024     # 实操视频 300MB
_CHUNK = 1024 * 1024


def _save_upload(src, dest: Path, max_bytes: int) -> None:
    """流式落盘 + 大小上限, 避免整包进内存/超大文件拖垮服务."""
    total = 0
    with open(dest, "wb") as out:
        while True:
            chunk = src.read(_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(
                    413, f"文件超过上限 {max_bytes // (1024 * 1024)}MB, 已拒绝")
            out.write(chunk)


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
    _check_deadline(item)

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
    _check_deadline(item)
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
        _save_upload(audio.file, dest, MAX_AUDIO_BYTES)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    except Exception as e:  # noqa: BLE001
        dest.unlink(missing_ok=True)
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


@router.post("/image")
def submit_image_answer(
    item_id: int = Form(...),
    student_token: str | None = Form(None),
    image: UploadFile | None = File(None),
    cur: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """图片作答(识图转文字)契约: 主观题可拍照/截图上传 -> OCR 提取文字 -> 按主观题判分.

    需配置视觉 OCR 模型(OCR_LLM_*, 推荐智谱 glm-4v-flash 免费额度);
    未配置时返回 422 并给出配置指引, 不静默降级。
    识别文本作为作答 content 落库, 原图存 content_uri 作为证据。
    """
    if image is None or not (image.filename or "").strip():
        raise HTTPException(422, "缺少图片文件(image)")
    item = db.get(Item, item_id)
    if item is None:
        raise HTTPException(404, "题目不存在")
    if not item.published or not item.enabled:
        raise HTTPException(409, "题目未发布或已停用, 暂不可作答")
    _check_deadline(item)
    if item.type != T_SUBJECTIVE_TEXT:
        raise HTTPException(422, "图片作答目前仅支持文本主观题")

    if cur.role == ROLE_STUDENT:
        token = cur.student_token
        if student_token not in (None, token):
            raise HTTPException(403, "学生只能提交本人答卷")
    else:
        token = (student_token or "").strip() or cur.student_token
        if not token:
            raise HTTPException(422, "请指定 student_token(或由学生本人提交)")

    ext = Path(image.filename).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXT:
        raise HTTPException(422, f"不支持的图片格式 {ext or '(无扩展名)'}, 支持: {sorted(ALLOWED_IMAGE_EXT)}")
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = settings.UPLOAD_DIR / f"{token}-img-{uuid.uuid4().hex[:10]}{ext}"
    try:
        _save_upload(image.file, dest, MAX_IMAGE_BYTES)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    except Exception as e:  # noqa: BLE001
        dest.unlink(missing_ok=True)
        raise HTTPException(500, f"保存图片失败: {e}") from e

    try:
        ocr_text, ocr_src = ocr_image(dest)
    except OCRConfigError as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(422, str(e)) from e
    except OCRError as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(502, f"OCR 识别失败: {e}") from e
    ocr_text = (ocr_text or "").strip()

    quality = quality_gate_text(ocr_text, item_type="subjective_text")
    quality["note_ocr"] = ocr_src

    ans = Answer(
        trace_id=f"{token}:{item.id}:{uuid.uuid4().hex[:10]}",
        student_token=token, item_id=item.id, modality="image",
        content=ocr_text, raw_response="",
        content_uri=str(dest.resolve()), segments=[], quality=quality,
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
        data["message"] = "已接收图片作答, 待批量评阅(异步)"
    return data


# 视频格式白名单(容器格式; faster-whisper 经 PyAV 直接解音轨, 无需 ffmpeg)
ALLOWED_VIDEO_EXT = {".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v"}


@router.post("/video")
def submit_video_answer(
    item_id: int = Form(...),
    student_token: str | None = Form(None),
    video: UploadFile | None = File(None),
    cur: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """视频作答(基础版)契约: 实操视频题上传过程视频 -> 服务端转写音轨 -> 按量规关键词判分.

    基础版只做"音轨转写内容覆盖"维度的自动判分; 未配置关键词的动作/时序步骤
    标记证据不足转人工评定(不自动扣分)。需安装 faster-whisper(可选依赖)。
    """
    if video is None or not (video.filename or "").strip():
        raise HTTPException(422, "缺少视频文件(video)")
    item = db.get(Item, item_id)
    if item is None:
        raise HTTPException(404, "题目不存在")
    if not item.published or not item.enabled:
        raise HTTPException(409, "题目未发布或已停用, 暂不可作答")
    _check_deadline(item)
    if item.type != T_VIDEO:
        raise HTTPException(422, "视频上传目前仅支持实操视频题")

    if cur.role == ROLE_STUDENT:
        token = cur.student_token
        if student_token not in (None, token):
            raise HTTPException(403, "学生只能提交本人答卷")
    else:
        token = (student_token or "").strip() or cur.student_token
        if not token:
            raise HTTPException(422, "请指定 student_token(或由学生本人提交)")

    ext = Path(video.filename).suffix.lower()
    if ext not in ALLOWED_VIDEO_EXT:
        raise HTTPException(422, f"不支持的视频格式 {ext or '(无扩展名)'}, 支持: {sorted(ALLOWED_VIDEO_EXT)}")
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = settings.UPLOAD_DIR / f"{token}-vid-{uuid.uuid4().hex[:10]}{ext}"
    try:
        _save_upload(video.file, dest, MAX_VIDEO_BYTES)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    except Exception as e:  # noqa: BLE001
        dest.unlink(missing_ok=True)
        raise HTTPException(500, f"保存视频失败: {e}") from e

    adapter = get_asr()
    if adapter is None:
        dest.unlink(missing_ok=True)
        raise HTTPException(422, "未安装 faster-whisper, 无法转写视频音轨: "
                                 "请 pip install faster-whisper 后重试(首次运行自动下载模型)")
    try:
        transcript, segments, src = adapter.transcribe(dest)
        transcript = (transcript or "").strip()
    except Exception as e:  # noqa: BLE001
        dest.unlink(missing_ok=True)
        raise HTTPException(500, f"音轨转写失败: {e}") from e

    quality = quality_gate_text(transcript, item_type="practical_video")
    quality["note_asr"] = "whisper"

    ans = Answer(
        trace_id=f"{token}:{item.id}:{uuid.uuid4().hex[:10]}",
        student_token=token, item_id=item.id, modality="video",
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
        data["message"] = ("已评阅, 部分步骤证据不足/低置信度, 需教师复核后终审"
                           if score.status == ST_NEEDS_REVIEW else "评阅完成")
    else:
        data["score"] = None
        data["message"] = "已接收视频作答, 待批量评阅(异步)"
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


@router.get("/{answer_id}/media")
def get_answer_media(answer_id: int, cur: CurrentUser = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    """回放/下载答卷的原始媒体证据(口语录音/实操视频/作答图片).

    教师与管理员可查看任意卷; 学生仅限本人卷。仅允许访问本服务写入上传目录内的文件。
    """
    ans = db.get(Answer, answer_id)
    if ans is None:
        raise HTTPException(404, "答卷不存在")
    if cur.role == ROLE_STUDENT and ans.student_token != cur.student_token:
        raise HTTPException(403, "无权查看他人答卷")
    # 仅按文件名在当前上传目录解析: 兼容历史绝对路径/相对路径库值,
    # 项目迁移到其他机器(路径变化)后媒体回放依然可用; 文件名由上传时随机后缀保证唯一。
    name = Path(ans.content_uri or "").name
    p = settings.UPLOAD_DIR / name
    if not p.is_file():
        raise HTTPException(404, "证据文件不存在或已被清理")
    resolved = p.resolve()
    # 越界防护: 防 content_uri 被篡改为任意本地路径读取
    if not resolved.is_relative_to(settings.UPLOAD_DIR.resolve()):
        raise HTTPException(403, "非法文件路径")
    return FileResponse(resolved)
