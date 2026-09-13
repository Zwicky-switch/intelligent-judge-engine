# 智评 · Insight — 多题型智能评阅与能力诊断引擎

面向《多题型智能评阅与能力诊断引擎工程方案》的可交付实现：**证据优先的规则/模型协同评阅 + 教师复核仲裁(含双评/仲裁) + Q 矩阵能力诊断与个性化建议**。

覆盖 9 类题型：单选 / 多选 / 判断 / 填空 / 数值 / 文本主观 / **公式(符号与数值抽样等价判定)** / 口语 / **实操视频(音轨转写内容判分, 基础版)**。客观题与公式题为 100% 确定性判分(金标准守护)，空答不静默给分、自动转人工复核；文本主观题 / 口语题由内置本地引擎完成评阅，开箱即用；配置 DeepSeek / 通义 / 智谱的 API Key 后自动切换为「规则定分 + 大模型判点复核与评语」的协同模式。**双评题**由两位独立教师背靠背评分、超差进入仲裁；**发布双人复核**保证量规与答案的变更需两个不同账号确认后才正式生效。多媒体作答已接入：口语/视频上传由 **faster-whisper** 服务端自动转写（口语流畅层真算、实操视频基础版按音轨内容判分），图片作答经**视觉模型 OCR（智谱 glm-4v-flash，2026-09-13 已实测：4 张真实手写图加权 CER 24.06%，失败自动回退本地 RapidOCR）**转文字后复用主观题判分；学生提交的原图/原录音/原视频全程留存，教师复评可回放核验。

---

## 1. 快速启动(Windows)

需要：Python 3.12/3.13、Node.js ≥ 20。

```bash
# ---- 后端(默认 127.0.0.1:8000) ----
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
# 可选: 安装 faster-whisper 启用服务端 ASR 自动转写(口语题录音无需前端誊抄文本, 流畅层按词级时间戳真算)
#   首次运行会自动下载 Whisper small 模型(~460MB), 国内网络需先设镜像: set HF_ENDPOINT=https://hf-mirror.com
.venv\Scripts\python -m pip install faster-whisper
.venv\Scripts\python run.py
# 首次启动: 自动建表并注入初始化示例数据(大学物理课程/题目/答卷并完成评阅)

# ---- 前端(另开终端, 默认 http://127.0.0.1:5173) ----
cd frontend
npm install
npm run dev
```

也可双击根目录 `scripts/` 下的 `start_all.bat`(**一次启动前后端, 就绪后自动打开浏览器**)；或分别双击 `start_backend.bat` / `start_frontend.bat`。

> ⚠️ **请通过浏览器访问 http://127.0.0.1:5173, 不要直接双击 `frontend/index.html`**。该页面依赖 Vite 开发服务器加载模块(源码为绝对路径 `/src/main.js`)，以 `file://` 方式打开会白屏——请以开发服务器方式访问。

### 初始化示例数据

后端目录 `data/app.db` 若不存在，会在启动时自动生成初始化示例数据(强/中/弱三档学生答卷已完成评阅；覆盖 8 类题型；复核队列中保留一份双评题，供 `grader` 与 `grader2` 两位阅卷教师走完整独立双评与仲裁流程)。重置为初始化状态(会删除并重建当前库)：`cd backend && .venv\Scripts\python -m app.seeds.demo --reset`，或删除 `backend/data/app.db` 后重启后端。

### 预置账号

| 角色 | 用户名 | 密码 |
|---|---|---|
| 教务管理员 | `admin` | `admin123` |
| 命题教师 | `prop_teacher` | `teacher123` |
| 阅卷教师 A(复核/仲裁) | `grader` | `teacher123` |
| 阅卷教师 B(双评独立第 2 评) | `grader2` | `teacher123` |
| 学生(强) | `student_li`(李雪) | `stu123` |
| 学生(中) | `student_wang`(王哲) | `stu123` |
| 学生(弱) | `student_zhao`(赵晨) | `stu123` |

登录页为常用账号提供快捷标签，其余账号可直接输入用户名与密码。双评流程请分别以 `grader`(阅卷教师 A)与 `grader2`(阅卷教师 B)登录，对复核中心中的同一道双评题完成第 1 评与第 2 评。

---

## 2. 核心设计

| 设计点 | 实现 |
|---|---|
| 证据优先 | 每个得分点绑定 `Evidence`：文本字符区间 / 关键词命中片段 / 音频侧车，作答原文可高亮回溯 |
| 量规约束 | 大模型**只复核判点、不绕过量规给分**；分值一律按量规权重确定性结算并二次夹取 |
| 人机协同 / 全程审计 | 教师保留 接受/改分/仲裁/退回 全权；每次操作写入 `audit_logs` 与 `review_records`，不可删除 |
| 置信度路由 | 无法判断/证据冲突/低置信度 → 强制复核；抽样档可由教师接收；高分高信度主观题可按策略自动放行 |
| 如实上报 | 口语发音层在未接入音素级对齐时如实标「无数据」；流畅层已接入 faster-whisper 词级时间戳真算；实操视频为基础版(音轨转写内容判分, 动作/时序步骤证据不足转人工)，不产生无效评分 |
| 客观题确定判分 | 单选/多选(部分得分)/判断/填空/数值(单位换算·容差·有效数字)，金标准表 47 例全绿；空答/低质不静默给 0、转人工复核 |
| 双评/仲裁 | 双评题两位教师背靠背独立评分，分差 ≤ 容差自动取均值终审，超差强制 `arbitrate` 由第三位教师仲裁 |
| 发布质量门 | 发布(锁定量规)可设双人复核(需 ≥2 个不同账号)；已发布题可直接「重新发布」(版本+1、刷新发布时间，无需重新编辑)；历史版本快照 + 逐字段差异比较；量规模板一键套用 |
| 题目生命周期 | 题目新增**发布时间**(发布动作自动写入)与**提交截止时间**(教师可配置/清空，学生端截止后禁用提交)；教务管理员可**删除题目并级联清理**全部答卷/成绩/版本/复核/上传文件(审计留痕)；已发布且已作答的题目修订再发布后，**重新出现在学生端题目列表**(学生按作答版本与当前版本比对) |
| 媒体证据回放 | 教师复评/复核可回放学生**原图/原录音/原视频**(`GET /answers/{id}/media`，教师任意卷、学生限本人、目录越界防护)；历史旧路径 `content_uri` 迁移已完成(一次性脚本已归档至 `new-chat/_archive_judge_engine/`) |
| 提交互斥 | 学生端同一时刻仅允许一道题提交判分，进行中的其他提交按钮全部禁用、函数级兜底拦截，**不可打断** |
| 公式题 | 符号等价判定优先 `sympy`，无该依赖时以变量域数值抽样(相对误差 <1e-6)兜底，结果幂等 |
| 能力诊断 | 60 维能力全景(支持按课程停用维度)、知识节点 BKT 时序掌握度、画像-作答匹配度 `profile_match` |
| 质量指标 | 引擎内部时延(p50/p95/max)、存量分数重放一致率、engine↔已终审一致率(演示数据)、分数段校准(演示数据)、双评教师间一致性 |
| 可插拔模型 | 默认内置本地引擎(无需外部 Key)；`GRADE_LLM_PROVIDER` 配置外部模型即启用大模型判点复核与评语 |

---

## 3. 角色与工作台(前端)

- **命题教师**：题库管理(新建/编辑/发布/停用/删除，量规与答案编辑器；公式题可编辑期望式与变量域)、量规模板套用、发布历史版本比较、双人复核发布进度跟踪、知识图谱与 6×10 能力维度体系 + 按课程停用维度开关；已发布题可点「重新发布」直接再发布(版本+1)，题目可单独配置提交截止时间。
- **阅卷教师**：复核中心(待复核队列按 强制/抽样 两档，双评题按「待第 1 评 / 待第 2 评 / 待仲裁」阶段分组并展示已收独立分；新增「已评阅」页签可只读回看全部已终审卷)、评阅工作台(作答原文证据高亮、**直接回放学生原图/原录音/原视频**、逐得分点判定、接受/改分/仲裁/退回；双评题按「第 1 评 / 第 2 评 / 仲裁」分阶段操作并展示另一方独立分；已终审卷只读、不再显示改分操作)。
- **教务管理员**：质量看板(自动放行率/教师终审率/得分率分布/班级六域画像/题目表现 + 存量分数重放一致率、engine↔已终审一致率(演示数据)、引擎内部时延、分数段校准(演示数据)、双评教师间一致性)、审计日志、题目删除(级联清理该题全部数据)。
- **学生**：我的成绩(逐题得分 + 证据展开；口语题四层表现)、题目(客观题即时反馈 + 主观文本/公式送复核 + 口语文本转写并可选附录音证据 + 图片/视频作答；题目可设提交截止时间，截止后禁用提交；**同一时刻只允许一道题提交判分，不可打断**)、能力诊断报告(六域雷达 + 知识节点掌握度/BKT 时序 + 知识热力图 + 60 维能力全景 + 短板 Top3 + 先修/微课/练习建议 + 画像-作答匹配度)。
- **全角色共享**：侧边栏「引擎技术导览」(`/engine`)一页讲清 提交→门控→量规协同评阅→证据→双评复核仲裁→能力诊断 的处理闭环，并按登录角色给出数据入口；顶栏「技术铭牌」实时显示当前评阅模型与引擎版本(`GET /v1/meta`)。

---

## 4. 工程结构

```
intelligent-judge-engine/
├── backend/
│   ├── run.py                    # uvicorn 启动入口
│   ├── app/
│   │   ├── config.py             # .env 集中配置
│   │   ├── models/               # User/Course/Chapter/KnowledgeNode/SkillDomain/SkillDimension
│   │   │                         # Item/ItemVersion/Answer/Evidence/Score/ReviewRecord/AuditLog/Diagnosis/AssessmentJob
│   │   │                         # RubricTemplate/PublishApproval/CourseDimensionToggle
│   │   ├── engines/              # objective / numeric / subjective / spoken / symbolic(公式) / video(实操, 基础版: 音轨转写内容判分)
│   │   ├── parsers/              # 答案质量门控 / ASR 适配(口语+视频音轨) / 图片 OCR(视觉模型+RapidOCR 兜底) / 音频上传
│   │   ├── llm/                  # 外部模型适配(deepseek/qwen/zhipu) + 内置引擎 + 强制 JSON + 量规约束提示词
│   │   ├── orchestrator/         # runner(编排+置信度路由) / review(复核·双评仲裁·审计) / jobs(批量任务)
│   │   ├── diagnostics/          # qmatrix / mastery(掌握度·能力向量·置信度) / bkt(时序掌握) / calibration(校准) / irt(2PL) / recommender
│   │   ├── api/                  # auth/courses/knowledge/items/rubric-templates/answers/scores/reviews/
│   │   │                         #   assessment/diagnosis/metrics/audit/practice/meta
│   │   └── seeds/                # 初始化示例数据脚本(app.seeds.demo 可 --reset 重置)
│   ├── tests/                    # 91 例: 客观题金标准 + 双评仲裁 + 公式等价 + BKT/校准 + 全链路
│   └── data/                     # app.db(SQLite, 已 gitignore)
├── frontend/
│   ├── src/{router,stores,api,components,views}   # Vue3 + Element Plus + ECharts 多角色工作台
│   └── vite.config.js            # 开发代理 /v1 → 127.0.0.1:8000
├── docs/architecture.md          # 架构、模块职责、模型替换 / ASR / 能力扩展点
├── docs/交付阅读与观看方案.md    # 📖 交付导读：按 5 分钟/30 分钟/2 小时三档阅读路线 + 九屏演示顺序 + 验收清单
├── docs/交付版_文件清单与修正说明.md  # 交付版清单、密钥清理确认、模型选择/算法实现、组长问题解决方案、修正记录
├── docs/项目总结_经验与技术_20260913.md  # 项目经验/坑/先进技术/算法总结(配全景图)
├── scripts/                      # start_backend.bat / start_frontend.bat / start_all.bat
└── .env.example
```

---

## 5. 接入外部大模型(可插拔)

复制 `.env.example` 为根目录 `.env`(或 `backend/.env`)：

```
GRADE_LLM_PROVIDER=deepseek        # 或 qwen / zhipu(OpenAI 兼容)
GRADE_LLM_API_KEY=sk-xxxxxxxx
GRADE_LLM_BASE_URL=https://api.deepseek.com/v1   # 各厂商 OpenAI 兼容端点
GRADE_LLM_MODEL=deepseek-chat
```

重启后端即生效，无需改代码。评阅引擎会：
1. 本地规则先对量规逐点判定 `满足/部分/不满足/无法判断` 并召回原文证据；
2. 大模型在**量规分数约束内**复核判点类别、给出罚分建议与中文评语(JSON 结构化输出，返回后按量规二次夹取)；
3. 置信度取本地与模型混合值，仍走统一复核路由。

### 图片作答(识图转文字 OCR)

主观题支持上传手写/截图作答：`POST /answers/image`(multipart: item_id + image) → 服务端提取图片文字 → 复用主观题判分引擎打分，原图留存为证据。识别链路**视觉模型优先、本地 OCR 兜底**：

- 视觉模型（已配智谱 glm-4v-flash，免费额度）：手写/截图识别效果好；可切换通义 qwen-vl-plus 或自定义 OpenAI 兼容视觉模型
- 视觉模型未配置或调用失败 → 自动回退本地 **RapidOCR**（`pip install rapidocr-onnxruntime`，离线可用，印刷体效果好）
- 两者都不可用才返回 422 并给出配置指引，不静默降级

```
# .env(配置智谱视觉 Key 时填入; 留空则回退本地 RapidOCR)
OCR_LLM_PROVIDER=zhipu            # 或 qwen
OCR_LLM_API_KEY=
OCR_LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
OCR_LLM_MODEL=glm-4v-flash
```

### 视频作答(实操视频题, 基础版)

`POST /answers/video`(multipart: item_id + video, 支持 mp4/mov/webm 等) → 服务端用 faster-whisper **直接转写视频音轨**(PyAV 解码, 无需 ffmpeg) → 按步骤量规关键词对"内容覆盖"维度自动判分。

- 量规中**配置了 keywords** 的步骤按转写文本判 满足/部分/不满足 并给分；
- **未配置 keywords** 的动作/时序步骤标记"证据不足"，不自动扣分，整卷转人工按视频补齐评定(强制复核兜底)；
- 无音轨转写(静音视频)同样转人工，不自动给 0 分。

基础版不含姿态估计/动作识别/时序对齐(属后续规划)，动作类步骤最终分以教师人工评定为准。

未配置外部模型 Key 时，主观题/口语题由内置本地引擎完成启发式判点与评语，公式题/客观题始终由确定性引擎判分——系统在任何配置下均可完整运行。

---

## 6. API 一览(均挂 /v1, 详见 http://127.0.0.1:8000/docs)

- 认证：`POST /auth/login`、`GET /auth/me`
- 课程/图谱：`GET /courses`、`GET /courses/{id}/knowledge`、`GET /dimensions`、`GET /ability-domains`、`GET/PUT /courses/{id}/dimensions`(按课程停用能力维度)
- 题库：`GET/POST /items`、`GET /items/types`、`GET/PUT /items/{id}`、`DELETE /items/{id}`(仅教务管理员，级联删除该题全部数据)、`POST /items/{id}/publish|toggle`；`GET/POST/PUT/DELETE /rubric-templates`(量规模板)；`GET /items/{id}/versions`、`GET /items/{id}/versions/compare?v1=&v2=`(版本快照与差异)
- 答卷与评阅：`POST /answers`(提交即评)、`POST /answers/audio`(口语录音, faster-whisper 自动转写)、`POST /answers/image`(图片作答, 视觉模型+RapidOCR)、`POST /answers/video`(实操视频, 音轨转写判分)、`GET /answers/{id}/media`(媒体证据回放)、`GET /practice/items`(学生题目列表：客观/主观/公式/口语/视频，含作答版本与当前版本、提交截止)、`POST /assessments/run` + `GET /assessments/{job_id}`
- 成绩/复核：`GET /scores`、`GET /scores/overview/{token}`、`GET /scores/{id}`、`GET /reviews/queue?status=needs_review|reviewed`(待复核队列与已评阅卷，含双评阶段分组)、`POST /reviews/{score_id}`(accept/adjust/arbitrate/return_model，双评按状态机流转)
- 诊断/指标/审计：`GET /diagnosis/{student_token}`、`GET /diagnosis/mine/current`(60 维全景/profile_match/BKT)、`GET /metrics/quality`(引擎内部时延/存量分数重放一致率/一致率/校准/双评一致性)、`GET /audit`
- 引擎信息：`GET /meta` —— `model_version / llm_provider / llm_model / review_threshold / auto_release_objective / note`（`has_api_key` 字段已于 2026-09-13 移除，避免暴露密钥配置状态）

---

## 7. 验证(自检清单)

```bash
cd backend
.venv\Scripts\python -m pytest -q          # 91 passed(客观金标准 + 双评仲裁 + 公式等价 + BKT/校准 + 全链路)
cd ../frontend
npm run build                               # 构建通过
```

- 按 5 类角色走通：命题(含双人复核发布)→发布→学生自主练习(主观/口语/公式)与查分→双评题由 `grader`+`grader2` 背靠背打分→(超差)仲裁→学生 60 维/BKT 报告→教务看板(引擎内部时延/存量分数重放一致率/一致率/校准)。
- 评阅与诊断口径、数据对象、模型版本说明可在 `/docs`(OpenAPI)、看板 note 与报告 `algorithm_detail` 中交叉核对。

---

## 8. 版本路线图(后续规划能力)

以下能力已按最新状态如实标注（未接入的部分不产生无效判定）：

- 实操视频**姿态识别/动作时序对齐**：当前为基础版(音轨转写内容判分)，姿态识别待接入；实时**音素级发音评测**：当前流畅层已接 faster-whisper 词级时间戳真算，发音层需音素对齐后启用；大规模真实题库的 IRT/BKT 参数标定与训练(当前为题目启发式参数 + 已观测作答序列上的 BKT 拟合)；OCR 富文本坐标级识别(当前为整图文本提取)。
- 详见 `docs/architecture.md` 的「能力扩展点」一节。

---

## 9. 组长问题与解决方案（2026-09-11 核实包 → 2026-09-13 交付版）

> 完整版（含密钥扫描方法、模型选择依据、算法实现位置、修正记录）见 `docs/交付版_文件清单与修正说明.md`。

| # | 组长问题 | 状态 | 解决方案 |
|---|---|---|---|
| 1 | `.env` 敏感密钥清理（与并发平台模块同优先级） | ✅ 已解决 | 真实智谱 Key 已移除为占位模板；全盘扫描（含隐藏文件/git 历史/backend.zip）确认无残留；`.gitignore` 已覆盖 `.env`；SECRET_KEY 生产部署须环境变量注入 |
| 2 | OCR 真实效果验证（旧 Key 过期 HTTP 401） | ✅ 已解决 | 新 Key 实测：glm-4.7 纯文本 HTTP 200（但**无视觉**，不支持图片输入）；OCR 改用 **glm-4v-flash**，4 张真实手写图加权 CER 24.06%，脚本/真值/报告见 `scripts/ocr_eval/` |
| 3 | ASR 人工真值集（依赖版本已锁定） | ▲ 部分解决 | 依赖版本/模型 revision/权重哈希已锁定；已用"AI 校对代理真值"量化：5 段真实素材 **WER 16.95% / CER 7.29%**（脚本见 `scripts/asr_eval/`）；**真实人工抽检校准 ≥10% 待安排** |
| 4a | 教师盲评（需协调任课教师） | ⚠️ 待办 | 实验方案已提交；责任人待定（需项目负责人协调）；当前有模拟教师二审基线（语义槽 v2 一致率 100%） |
| 4b | 能力诊断信效度验证 | ⚠️ 待办 | 实验方案已提交；责任人待定 |
| 4c | Q 矩阵标注一致性（Kappa） | ⚠️ 待办 | 实验方案已提交；需两位独立标注者 |
| 4d | IRT/BKT 大样本标定 | ⚠️ 待办 | 实验方案已提交；责任人待定 |
| 5 | 前端依赖漏洞（1 高危 + 2 中危） | ✅ 已评估 | 2026-09-11 团队决定暂缓升级（vite 5→8、echarts 5→6 破坏性变更，交付阶段风险>收益），已附风险说明 |

**核心算法优化（对应问题 2/3 的衍生修复）**：
- **语义槽评分算法 v2**：主观题关键字从"字符面覆盖率"升级为"语义槽覆盖率"（同义变体分组、命中任一即槽覆盖），消除"同义变体膨胀分母"缺陷——同一教师基准下一致率 **11.1% → 100%**，平均分差 2.56 → 0.33，91 项测试无回归。
- **公式等价判定**：sympy 符号化简优先，离线以变量域数值抽样（固定种子、相对误差 <1e-6、AST 白名单安全求值）兜底，结果幂等、沙箱无代码执行。

### 真人评测替代方案（无人力时如何量化验证）

> 真实教师盲评/人工听写尚未到位时，以下三套替代方案已落地并量化，**可作为真实评测前的基线**；正式交付仍需真实教师/人工抽检校准（见各方案"局限"）。

| 替代项 | 方案 | 方法 | 结果 | 局限 |
|---|---|---|---|---|
| 教师盲评 → **模拟教师二审** | 标准答案 + 关键字对照法 | 编写 3 道基础低开放性题（牛顿第二定律/惯性/动能定理）× 强/中/弱三档 = **9 份答卷**；引擎判分 vs 关键字对照模拟教师二审（阈值略宽模拟人工宽松度） | v1 一致率 88.9% → **v2 语义槽优化后 100%（9/9）**，平均分差 0.33 | 仅适用于基础低开放性题目；**非真实教师盲评**；高开放性题目仍需真实教师验证；脚本见 `scripts/teacher_sim/` |
| ASR 人工真值 → **"AI 充当人力"代理真值** | 交叉转写 + AI 语境校对 | 保留学生原口语句式，只修正同音字/术语错误（测力计→侧力剂等），建立 5 段真实素材逐字真值 | **WER 16.95% / CER 7.29%** | 代理真值非真人听写；**正式交付需人工抽检 ≥10% 校准**；公式符号误识别（EK→1K）已实证影响判分；真值模板见 `scripts/asr_eval/` |
| OCR 人工真值 → **逐字校对** | 人工逐字转写 4 张真实手写图 | 对照学生原图建立逐字真值，计算字符错误率 | 加权 **CER 24.06%**（正文良好、公式域符号误差为主） | 样本量小（4 张）；公式域可经提示词优化/公式裁剪继续降；真值见 `scripts/ocr_eval/ground_truth/` |

**统一口径**：三套方案均为"替代真值/替代评分"，数字只代表对应替代基准下的指标，**不替代**真实教师盲评与人工听写的正式结论；真实评测到位后需重算并以真实结果为准。
