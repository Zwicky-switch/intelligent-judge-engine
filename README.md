# 媒体评分雷达图（前后端）

## 目录结构
```
media-radar-app/
├── backend/
│   ├── app.py            # Flask 后端
│   ├── requirements.txt
│   └── uploads/          # 上传文件保存目录（自动创建）
└── frontend/
    └── index.html        # 前端页面（Chart.js 雷达图）
```

## 启动后端
```bash
cd backend
pip install -r requirements.txt
python app.py
# 监听 http://0.0.0.0:5000
```

## 打开前端
直接用浏览器打开 `frontend/index.html` 即可。
（前端通过 fetch 调用 http://localhost:5000/api/analyze，已开启 CORS。）

## 接口说明
- POST /api/analyze，multipart/form-data
  - 字段：image（图片，可选）、audio（语音，可选）、video（视频，可选）
  - 至少传一个
- 返回 JSON：
```json
{
  "a": 72.3,
  "b": 65.1,
  "c": 58.0,
  "d": 70.5,
  "e": 68.2,
  "score": 66.8,
  "files": {"image_bytes": 12345, "audio_bytes": 0, "video_bytes": 0}
}
```

## 接入真实模型
后端 analyze(image_size, audio_size, video_size) 函数目前是基于文件大小的演示评分。
把你的模型/算法放进去，返回 {"a":.., "b":.., "c":.., "d":.., "e":.., "score":..} 即可，前端无需改动。
