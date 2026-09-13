# ============================================================
# 智评·Insight 后端生产 Dockerfile
# ============================================================
# 多阶段构建: 基础运行时 + 可选 ASR/OCR 依赖
# 构建: docker build -t insight-judge-backend ./backend
# 运行: docker run -p 8000:8000 --env-file .env insight-judge-backend
# ============================================================

FROM python:3.11-slim AS base

# 系统依赖: libgomp (onnxruntime/ctranslate2 需要), libgl1 (opencv/rapidocr)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖(利用 Docker 层缓存)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 可选依赖: ASR (faster-whisper) + 离线 OCR (rapidocr)
# 若不需要可注释掉以减小镜像体积
RUN pip install --no-cache-dir \
    faster-whisper==1.2.1 \
    av==18.1.0 \
    ctranslate2==4.8.2 \
    rapidocr-onnxruntime==1.4.4

# 复制应用代码
COPY . .

# 数据与上传目录(volume 挂载)
RUN mkdir -p /app/data /app/uploads

EXPOSE 8000

# 生产启动: uvicorn 多 worker
# worker 数 = CPU 核数;  ASR/OCR 为 CPU 密集型, 建议 worker 数 <= 物理核数
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "4", \
     "--limit-concurrency", "50", \
     "--timeout-keep-alive", "30"]
