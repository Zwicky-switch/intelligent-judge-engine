# 智评·Insight 生产部署指南

> 版本：v1.0 | 更新：2026-09-13
> 适用：单机部署（Docker 或裸机），支持 Windows / Linux

---

## 一、部署架构

```
                    ┌─────────────┐
   用户浏览器 ─────► │   nginx     │ ──► 前端静态文件 (Vue3 dist)
                    │  (80/443)   │
                    └──────┬──────┘
                           │ /v1/*
                    ┌──────▼──────┐
                    │  FastAPI    │ ──► SQLite (WAL模式)
                    │  uvicorn    │ ──► 上传文件 (音频/视频/图片)
                    │  N workers  │ ──► ASR (faster-whisper)
                    └─────────────┘ ──► OCR (智谱API / rapidocr离线)
```

---

## 二、方式一：Docker Compose（推荐）

### 2.1 前置条件

- Docker 20.10+ / Docker Compose v2
- 至少 4GB 内存（ASR 模型加载约 1.5GB）
- 磁盘空间：镜像约 2GB + 数据 + 上传文件

### 2.2 部署步骤

```bash
# 1. 克隆/上传项目到服务器
cd intelligent-judge-engine

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env, 填写 SECRET_KEY、OCR_LLM_API_KEY 等

# 3. 构建前端
cd frontend
npm install
npm run build
cd ..

# 4. 启动服务
docker compose up -d --build

# 5. 查看日志
docker compose logs -f backend

# 6. 健康检查
curl http://localhost/health
```

### 2.3 数据持久化

| 挂载路径 | 用途 |
|---|---|
| `./backend/data` | SQLite 数据库（app.db） |
| `./backend/uploads` | 学生作答媒体文件 |
| `./backend/models` | ASR 模型缓存（首次启动自动下载） |

### 2.4 HTTPS 配置

1. 将证书放入 `deploy/certs/`（`fullchain.pem` + `privkey.pem`）
2. 编辑 `deploy/nginx.conf`，取消 HTTPS server 块注释
3. `docker-compose.yml` 中取消 443 端口映射
4. `docker compose restart nginx`

---

## 三、方式二：裸机部署（无 Docker）

### 3.1 后端

```bash
cd backend

# 创建虚拟环境
python -m venv .venv

# 安装依赖
.venv/bin/pip install -r requirements.txt
# 可选: ASR + 离线OCR
.venv/bin/pip install faster-whisper==1.2.1 av==18.1.0 ctranslate2==4.8.2 rapidocr-onnxruntime==1.4.4

# 配置环境
cp ../.env.example .env
# 编辑 .env

# 启动（Linux/macOS）
chmod +x start_prod.sh
./start_prod.sh

# 启动（Windows）
start_prod.bat
```

### 3.2 前端

```bash
cd frontend
npm install
npm run build
# dist/ 目录即为静态产物, 由 nginx 托管
```

### 3.3 nginx 配置

将 `deploy/nginx.conf` 复制到 nginx 配置目录，修改 `upstream` 地址为实际后端地址：

```nginx
upstream insight_backend {
    server 127.0.0.1:8000;  # 裸机部署时后端在本机
    keepalive 32;
}
```

---

## 四、性能配置

### 4.1 Worker 数

- **文本/客观题为主**：worker 数 = CPU 逻辑核数
- **ASR/OCR 密集**：worker 数 ≤ 物理核数（避免 CPU 过载）
- 默认脚本自动取 `min(逻辑核数, 8)`

### 4.2 SQLite WAL

已在 `app/db.py` 中默认启用：
- `journal_mode=WAL`：读写不阻塞
- `synchronous=NORMAL`：性能与安全平衡
- `cache_size=20MB`：页缓存

### 4.3 大文件上传

- nginx `client_max_body_size 350m`
- 后端音频上限 60MB / 视频上限 300MB
- ASR 转写超时 nginx 300s

---

## 五、监控与运维

### 5.1 响应时间

- 每个 API 响应头含 `X-Response-Time-ms`（端到端耗时）
- 慢请求（>1s）自动记录到后端日志
- 引擎内部耗时记录在 `score.extra.elapsed_ms`

### 5.2 健康检查

```bash
# Docker
docker compose ps
docker compose logs backend --tail 100

# API
curl http://localhost/health
curl http://localhost/v1/meta  # 需登录
```

### 5.3 数据备份

```bash
# 备份数据库
cp backend/data/app.db backend/data/app.db.$(date +%Y%m%d).bak

# 备份上传文件
tar czf uploads_$(date +%Y%m%d).tar.gz backend/uploads/
```

---

## 六、常见问题

| 问题 | 解决方案 |
|---|---|
| ASR 首次启动慢 | 首次需下载模型(~500MB), 后续使用缓存 |
| OCR 返回 401 | 智谱 API Key 过期, 更新 `.env` 中 `OCR_LLM_API_KEY` |
| 视频上传 413 | nginx `client_max_body_size` 不足, 调大到 350m+ |
| 并发提交卡顿 | 减少 worker 数或升级 CPU; ASR 为 CPU 密集型 |
| 数据库锁 | 确认 WAL 已启用(`PRAGMA journal_mode`); 避免长事务 |

---

## 七、安全清单

- [ ] `.env` 中 `SECRET_KEY` 已替换为随机强密钥（≥32字节）
- [ ] `.env` 已加入 `.gitignore`，不提交到代码仓库
- [ ] nginx 已配置 HTTPS（生产环境必须）
- [ ] CORS `allow_origins` 已收敛为前端域名（非 `*`）
- [ ] 数据库定期备份
- [ ] 上传目录已限制大小并定期清理
