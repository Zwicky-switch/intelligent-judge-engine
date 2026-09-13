# OCR CER 评估说明

## 目录结构

```
scripts/ocr_eval/
├── eval_ocr_cer.py      # CER 评估主脚本
├── README.md            # 本说明文件
├── samples/             # 学生原图(待识别图片)
│   ├── student_01.png
│   └── student_02.png
├── ground_truth/        # 人工逐字真值文本
│   ├── student_01.txt   # 与图片同名(不含扩展名)
│   └── student_02.txt
└── cer_report.json      # 运行后生成的评估报告
```

## 使用方法

### 1. 配置有效 OCR Key

在项目根目录 `.env` 中填入有效的智谱视觉模型 Key：

```
OCR_LLM_PROVIDER=zhipu
OCR_LLM_API_KEY=你的有效Key
OCR_LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
OCR_LLM_MODEL=glm-4v-flash
```

> 注意：**2026-09-13 已用有效 Key 实测完成**（4 张真实手写图，加权 CER 24.06%，报告见 `cer_report.json`）。交付版 `.env` 不含真实 Key，重跑评估前需填入有效 Key；未配置时脚本会提示 401 并失败，属预期行为。

### 2. 放置样本与真值

- 将学生原图放入 `samples/` 目录（支持 .png/.jpg/.jpeg/.webp/.bmp）
- 将人工逐字真值文本放入 `ground_truth/` 目录，文件名与图片同名（不含扩展名），后缀 `.txt`
- 真值文本应为图片中文字的**逐字准确转写**，包含换行

### 3. 运行评估

```bash
cd backend
.venv\Scripts\python ../scripts/ocr_eval/eval_ocr_cer.py
```

### 4. 查看结果

脚本会输出：
- 每张图片的识别文本、真值文本、CER（字符错误率）
- 汇总平均 CER 和加权 CER（按真值字符数加权）
- 详细报告写入 `cer_report.json`

## CER 计算公式

```
CER = (S + D + I) / N
```

- S = 替换字符数
- D = 删除字符数
- I = 插入字符数
- N = 真值文本总字符数

CER 越低越好，0 表示完全识别正确。

## 当前状态

- [x] 评估脚本已就绪
- [x] 目录结构已创建
- [x] **有效 OCR API Key + 4 张真实学生手写图**（2026-09-13 实测完成）
- [x] 人工逐字真值已放入 `ground_truth/`
- [x] **运行并计算 CER**：平均 21.91% / 加权 24.06%（见 `cer_report.json`）
- [ ] 公式域 CER 优化（提示词/公式区裁剪，属后续优化项）
