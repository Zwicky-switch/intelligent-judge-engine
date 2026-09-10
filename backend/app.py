"""
媒体评分后端
- 上传图片/语音/视频 → 立即重新打分 → 返回最新结果
- 全局变量保存最新打分，无需重启后端
- 接口：
    POST /api/analyze   上传文件并重新打分（核心）
    GET  /api/score     获取最近一次打分结果（不上传也能查）
    GET  /api/health    健康检查
"""
import os
import math
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_IMAGE = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
ALLOWED_AUDIO = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
ALLOWED_VIDEO = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flac"}

# ============================================================
# 全局状态：保存最近一次打分结果
# 每次上传成功后更新，不需要重启后端
# ============================================================
latest_result = {
    "a": 0, "b": 0, "c": 0, "d": 0, "e": 0, "score": 0,
    "files": {"image_bytes": 0, "audio_bytes": 0, "video_bytes": 0},
}


def ext_of(filename: str) -> str:
    return os.path.splitext(filename or "")[1].lower()


def save_file(file_storage, allowed_exts):
    """保存上传文件，返回 (saved_path, size_bytes)；不合法返回 (None, 0)"""
    if not file_storage or not file_storage.filename:
        return None, 0
    ext = ext_of(file_storage.filename)
    if ext not in allowed_exts:
        return None, 0
    safe_name = secure_filename(file_storage.filename)
    save_path = os.path.join(UPLOAD_DIR, safe_name)
    file_storage.save(save_path)
    return save_path, os.path.getsize(save_path)


def analyze(image_size, audio_size, video_size):
    """
    打分函数：每次调用都会重新计算。
    演示逻辑：基于文件大小归一化映射到 a~e。
    接入真实模型时，在这里读取 uploads/ 下的文件并运行你的算法。
    """
    def norm(size):
        return min(1.0, math.log10(size + 1) / 7.0) if size > 0 else 0.0

    ni, na, nv = norm(image_size), norm(audio_size), norm(video_size)

    a = round(40 + 60 * (0.6 * ni + 0.4 * nv), 1)
    b = round(40 + 60 * (0.7 * na + 0.3 * nv), 1)
    c = round(40 + 60 * nv, 1)
    d = round(30 + 70 * (0.4 * ni + 0.3 * na + 0.3 * nv), 1)
    e = round(35 + 65 * (ni + na + nv) / 3, 1)
    score = round((a + b + c + d + e) / 5, 1)

    return {"a": a, "b": b, "c": c, "d": d, "e": e, "score": score}


# ============================================================
# 核心接口：上传文件 → 保存 → 重新打分 → 更新全局 → 返回结果
# 每次调用都会重新打分，不需要重启后端
# ============================================================
@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    global latest_result

    image = request.files.get("image")
    audio = request.files.get("audio")
    video = request.files.get("video")

    if not any([image, audio, video]):
        return jsonify({"error": "至少上传一个文件（image / audio / video）"}), 400

    # 1. 保存新上传的文件到磁盘
    _, img_size = save_file(image, ALLOWED_IMAGE)
    _, aud_size = save_file(audio, ALLOWED_AUDIO)
    _, vid_size = save_file(video, ALLOWED_VIDEO)

    if image and img_size == 0:
        return jsonify({"error": f"图片格式不支持: {image.filename}"}), 400
    if audio and aud_size == 0:
        return jsonify({"error": f"音频格式不支持: {audio.filename}"}), 400
    if video and vid_size == 0:
        return jsonify({"error": f"视频格式不支持: {video.filename}"}), 400

    # 2. 关键：上传完成后立即重新打分（每次都重新算，不依赖重启）
    result = analyze(img_size, aud_size, vid_size)
    result["files"] = {
        "image_bytes": img_size,
        "audio_bytes": aud_size,
        "video_bytes": vid_size,
    }

    # 3. 更新全局状态，后续 /api/score 可以直接查到最新结果
    latest_result = result

    # 4. 把最新打分直接返回给前端
    return jsonify(result)


# ============================================================
# 查询接口：获取最近一次打分结果，不需要重新上传
# ============================================================
@app.route("/api/score", methods=["GET"])
def api_score():
    return jsonify(latest_result)


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    # debug=True 会自动检测代码变更并重启，开发时方便
    # 但注意：debug 模式下全局变量会因自动重启而重置，属于正常现象
    app.run(host="0.0.0.0", port=5000, debug=True)
