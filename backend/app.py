"""
媒体评分后端
- 接收图片 / 语音 / 视频（multipart/form-data，字段名分别为 image / audio / video，均可选）
- 返回 a, b, c, d, e, score 六个变量
- 这里用文件大小/类型做一个可复现的演示评分；接入真实模型时替换 analyze() 即可
"""
import os
import math
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)  # 开发期允许跨域；生产请收紧

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_IMAGE = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
ALLOWED_AUDIO = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
ALLOWED_VIDEO = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv"}


def ext_of(filename: str) -> str:
    return os.path.splitext(filename or "")[1].lower()


def save_file(file_storage, allowed_exts):
    """保存上传文件并返回 (saved_path, size_bytes)；不合法返回 (None, 0)"""
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
    演示评分逻辑：基于文件大小做归一化，映射到 a~e 五个维度。
    真实业务中应在这里调用你的模型 / 算法，返回 0~100 的五个维度分。
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


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    image = request.files.get("image")
    audio = request.files.get("audio")
    video = request.files.get("video")

    if not any([image, audio, video]):
        return jsonify({"error": "至少上传一个文件（image / audio / video）"}), 400

    _, img_size = save_file(image, ALLOWED_IMAGE)
    _, aud_size = save_file(audio, ALLOWED_AUDIO)
    _, vid_size = save_file(video, ALLOWED_VIDEO)

    if image and img_size == 0:
        return jsonify({"error": f"图片格式不支持: {image.filename}"}), 400
    if audio and aud_size == 0:
        return jsonify({"error": f"音频格式不支持: {audio.filename}"}), 400
    if video and vid_size == 0:
        return jsonify({"error": f"视频格式不支持: {video.filename}"}), 400

    result = analyze(img_size, aud_size, vid_size)
    result["files"] = {
        "image_bytes": img_size,
        "audio_bytes": aud_size,
        "video_bytes": vid_size,
    }
    return jsonify(result)


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
