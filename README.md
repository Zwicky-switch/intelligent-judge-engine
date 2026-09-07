# 智评 · Insight — 多题型智能评阅与能力诊断引擎

面向《多题型智能评阅与能力诊断引擎工程方案》的可交付实现：**证据优先的规则/模型协同评阅 + 教师复核仲裁(含双评/仲裁) + Q 矩阵能力诊断与个性化建议**。

覆盖 8 类题型：单选 / 多选 / 判断 / 填空 / 数值 / 文本主观 / **公式(符号与数值抽样等价判定)** / 口语。客观题与公式题为 100% 确定性判分(金标准守护)，空答不静默给分、自动转人工复核；文本主观题 / 口语题由内置本地引擎完成评阅，开箱即用；配置 DeepSeek / 通义 / 智谱的 API Key 后自动切换为「规则定分 + 大模型判点复核与评语」的协同模式。**双评题**由两位独立教师背靠背评分、超差进入仲裁；**发布双人复核**保证量规与答案的变更需两个不同账号确认后才正式生效。

---

## 1. 快速启动(Windows)

需要：Python 3.12/3.13、Node.js ≥ 20。

```bash
# ---- 后端(默认 127.0.0.1:8000) ----
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
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
| 如实上报 | 未接入 ASR 评测源时，口语发音/流畅层如实标「无数据」，不产生无效评分；实操视频为接口预留、由人工按步骤量规评阅 |
| 客观题确定判分 | 单选/多选(部分得分)/判断/填空/数值(单位换算·容差·有效数字)，金标准表 47 例全绿；空答/低质不静默给 0、转人工复核 |
| 双评/仲裁 | 双评题两位教师背靠背独立评分，分差 ≤ 容差自动取均值终审，超差强制 `arbitrate` 由第三位教师仲裁 |
| 发布质量门 | 发布(锁定量规)可设双人复核(需 ≥2 个不同账号)；历史版本快照 + 逐字段差异比较；量规模板一键套用 |
| 公式题 | 符号等价判定优先 `sympy`，无该依赖时以变量域数值抽样(相对误差 <1e-6)兜底，结果幂等 |
| 能力诊断 | 60 维能力全景(支持按课程停用维度)、知识节点 BKT 时序掌握度、画像-作答匹配度 `profile_match` |
| 质量指标 | 延迟(p50/p95/max)、客观题守门准确率、engine↔教师终审一致率、分数段校准与温度拟合、双评教师间一致性 |
| 可插拔模型 | 默认内置本地引擎(无需外部 Key)；`GRADE_LLM_PROVIDER` 配置外部模型即启用大模型判点复核与评语 |

---

## 3. 角色与工作台(前端)

- **命题教师**：题库管理(新建/编辑/发布/停用，量规与答案编辑器；公式题可编辑期望式与变量域)、量规模板套用、发布历史版本比较、双人复核发布进度跟踪、知识图谱与 6×10 能力维度体系 + 按课程停用维度开关。
- **阅卷教师**：复核中心(强制/抽样两档队列；双评题按「待第 1 评 / 待第 2 评 / 待仲裁」阶段分组并展示已收独立分)、评阅工作台(作答原文证据高亮、逐得分点判定、接受/改分/仲裁/退回；双评题按「第 1 评 / 第 2 评 / 仲裁」分阶段操作并展示另一方独立分)。
- **教务管理员**：质量看板(自动放行率/教师终审率/得分率分布/班级六域画像/题目表现 + 客观守门准确率、engine↔教师一致率、延迟、分数段校准与温度拟合、双评教师间一致性)、审计日志。
- **学生**：我的成绩(逐题得分 + 证据展开；口语题四层表现)、自主练习(客观题即时反馈 + 主观文本/公式送复核 + 口语文本转写并可选附录音证据)、能力诊断报告(六域雷达 + 知识节点掌握度/BKT 时序 + 知识热力图 + 60 维能力全景 + 短板 Top3 + 先修/微课/练习建议 + 画像-作答匹配度)。
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
│   │   ├── engines/              # objective / numeric / subjective / spoken / symbolic(公式) / video(实操, 接口预留)
│   │   ├── parsers/              # 答案质量门控 / ASR 适配 / 音频上传
│   │   ├── llm/                  # 外部模型适配(deepseek/qwen/zhipu) + 内置引擎 + 强制 JSON + 量规约束提示词
│   │   ├── orchestrator/         # runner(编排+置信度路由) / review(复核·双评仲裁·审计) / jobs(批量任务)
│   │   ├── diagnostics/          # qmatrix / mastery(掌握度·能力向量·置信度) / bkt(时序掌握) / calibration(校准) / irt(2PL) / recommender
│   │   ├── api/                  # auth/courses/knowledge/items/rubric-templates/answers/scores/reviews/
│   │   │                         #   assessment/diagnosis/metrics/audit/practice/meta
│   │   └── seeds/                # 初始化示例数据脚本(app.seeds.demo 可 --reset 重置)
│   ├── tests/                    # 87 例: 客观题金标准 + 双评仲裁 + 公式等价 + BKT/校准 + 全链路
│   └── data/                     # app.db(SQLite, 已 gitignore)
├── frontend/
│   ├── src/{router,stores,api,components,views}   # Vue3 + Element Plus + ECharts 多角色工作台
│   └── vite.config.js            # 开发代理 /v1 → 127.0.0.1:8000
├── docs/architecture.md          # 架构、模块职责、模型替换 / ASR / 能力扩展点
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

未配置外部模型 Key 时，主观题/口语题由内置本地引擎完成启发式判点与评语，公式题/客观题始终由确定性引擎判分——系统在任何配置下均可完整运行。

---

## 6. API 一览(均挂 /v1, 详见 http://127.0.0.1:8000/docs)

- 认证：`POST /auth/login`、`GET /auth/me`
- 课程/图谱：`GET /courses`、`GET /courses/{id}/knowledge`、`GET /dimensions`、`GET /ability-domains`、`GET/PUT /courses/{id}/dimensions`(按课程停用能力维度)
- 题库：`GET/POST /items`、`GET /items/types`、`GET/PUT /items/{id}`、`POST /items/{id}/publish|toggle`；`GET/POST/PUT/DELETE /rubric-templates`(量规模板)；`GET /items/{id}/versions`、`GET /items/{id}/versions/compare?v1=&v2=`(版本快照与差异)
- 答卷与评阅：`POST /answers`(提交即评，支持 multipart 附录音)、`GET /practice/items`(学生练习：客观/主观/公式/口语转写)、`POST /assessments/run` + `GET /assessments/{job_id}`
- 成绩/复核：`GET /scores`、`GET /scores/overview/{token}`、`GET /scores/{id}`、`GET /reviews/queue|recent`(含双评阶段分组)、`POST /reviews/{score_id}`(accept/adjust/arbitrate/return_model，双评按状态机流转)
- 诊断/指标/审计：`GET /diagnosis/{student_token}`、`GET /diagnosis/mine/current`(60 维全景/profile_match/BKT)、`GET /metrics/quality`(延迟/守门准确率/一致率/校准/双评一致性)、`GET /audit`
- 引擎信息：`GET /meta` —— `model_version / llm_provider / llm_model / has_api_key / review_threshold / auto_release_objective / note`

---

## 7. 验证(自检清单)

```bash
cd backend
.venv\Scripts\python -m pytest -q          # 87 passed(客观金标准 + 双评仲裁 + 公式等价 + BKT/校准 + 全链路)
cd ../frontend
npm run build                               # 构建通过
```

- 按 5 类角色走通：命题(含双人复核发布)→发布→学生自主练习(主观/口语/公式)与查分→双评题由 `grader`+`grader2` 背靠背打分→(超差)仲裁→学生 60 维/BKT 报告→教务看板(延迟/守门准确率/一致率/校准)。
- 评阅与诊断口径、数据对象、模型版本说明可在 `/docs`(OpenAPI)、看板 note 与报告 `algorithm_detail` 中交叉核对。

---

## 8. 版本路线图(后续规划能力)

以下能力已完成接口预留并如实标注，不产生无效判定：

- 实操视频姿态识别(当前由教师按步骤量规人工评阅)、实时音素级发音评测 ASR(口语作答支持「文本转写 + 录音证据」契约，录音可回放)、大规模真实题库的 IRT/BKT 参数标定与训练(当前为题目启发式参数 + 已观测作答序列上的 BKT 拟合)、OCR 富文本坐标级识别。
- 详见 `docs/architecture.md` 的「能力扩展点」一节。
