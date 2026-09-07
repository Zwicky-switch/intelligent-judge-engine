# 智评 · Insight — 架构说明

本文描述 V1 系统(对应《工程方案》第一阶段的完整闭环：客观/主观/口语评阅 + 复核仲裁 + 能力诊断)。目录：

1. [核心设计原则](#1-核心设计原则)
2. [模块职责与调用链](#2-模块职责与调用链)
3. [评阅管线(证据优先)](#3-评阅管线)
4. [数据模型](#4-数据模型)
5. [诊断：Q 矩阵 → 掌握度 → 建议](#5-诊断)
6. [复核/双评/仲裁/审计](#6-复核双评仲裁审计)
7. [API 与角色界面映射](#7-api-与角色界面映射)
8. [能力扩展点(后续规划)](#8-能力扩展点后续规划)

---

## 1. 核心设计原则

1. **证据优先** —— 每个得分点必须能回溯到答案原文片段(文本字符区间)或音频时间戳；拿不出证据的点标记 `无法判断` 转人工，绝不静默扣分。
2. **量规约束 + 模型可替换** —— 评阅引擎以题目 `rubric`(得分点：分值/描述/关键词)与 `answer_config`(标准答案)为唯一分源；大模型只做"解释、判点复核、评语"，输出被二次夹取，不能改分。
3. **人机协同** —— 教师保留终审权，`accept / adjust / arbitrate / return_model` 全部落库；`AuditLog` 不可删除。
4. **置信度路由** —— `confidence`、质量门控、证据完整度决定放行/复核档位：`none`(自动放行)、`sample`(抽样复核)、`forced`(强制复核)。
5. **如实上报** —— 未观测的能力维度、未接入的评测模态(发音/实操视频识别)在报告中如实标注"无数据"，前端与指标均不产生无效评分。

---

## 2. 模块职责与调用链

```
frontend(Vue3 + Element Plus + ECharts 多角色)
   │  /v1 (REST + JWT, axios 拦截器 401→登录)
backend FastAPI
   ├─ app/core        security(JWT/pbkdf2) · deps(角色守卫)
   ├─ app/parsers     normalize_text / quality_gate_text(空·超长·低质→拒评转人工,客观题同样适用)
   │                              ▲ 音频侧车转录(.txt)/ASR 适配(时间轴)/上传录音契约
   ├─ app/llm         get_model()=deepseek|qwen|zhipu|openai_compat|builtin(内置本地引擎)
   │                     request_json() 强制 JSON + 量规约束提示词(subjective/中文评语)
   ├─ app/engines     objective(确定性) · numeric(单位/容差/有效数字) · symbolic(公式·符号/数值抽样等价)
   │                     subjective(级联) · spoken(四层) · video_stub(实操·接口预留)
   ├─ app/orchestrator runner.grade_answer() → EngineOutcome → Score/Evidence/Audit(含 latency/extra)
   │                     review.apply_review() → 复核·双评(pass1/pass2)·仲裁审计   jobs → 批量任务
   ├─ app/diagnostics qmatrix → mastery(node/ability/dimension/theta·60维全录)
   │                     bkt(时序掌握) · calibration(分数段校准/温度) · irt(2PL) → recommender
   │                     profile_match(画像-作答匹配度测量)
   └─ app/seeds/demo  课程/章节/知识节点/60维能力体系/题目(8题型含公式与双评)/Q矩阵/强中弱学生答卷/grader2
```

**调用链(单题即时评阅)**：`POST /answers` → `quality_gate` → `runner.grade_answer(item, content, llm)` → 对应引擎产出 `EngineOutcome{total, point_results, hits/evidence, confidence, review_level}` → 落 `Score/Evidence/ReviewRecord(none)/AuditLog` → 前端按 `status/review_level` 展示。

---

## 3. 评阅管线

### 3.1 客观题(`engines/objective.py` · 确定性·幂等)
- 单选/判断：字母/对错规范化精确比对。
- 多选：`full` 全对得分；`partial` 按 `(选对-选错)/正确答案数` 部分得分。
- 填空：`|；;，,、` 分空；每空支持多候选/正则 `pattern`；`order_matters` 控制顺序敏感性；超答按前 N 空截断。
- 数值(`engines/numeric.py`)：量纲族表做单位换算(如 `m/s²`、`km/h`)，`tolerance_abs/rel`、缺单位保留分 `unit_credit`、有效数字校验。
- 输出 `Evidence`(判定原因)+ 满分置信度 → 通常 `auto_release`(默认开启，可由 `scoring_policy` 覆盖)。
- **质量门控对客观同样生效**：空答/无法解析不再 `auto_passed` 静默得 0，而是照算 0 分并置 `forced`/`needs_review` 交由教师复核(M2)。

### 3.2 文本主观题(`engines/subjective.py` · 级联)
1. 量规拆得分点 → 关键词/正则召回答案片段；
2. 逐点判 `satisfied/partial/unsatisfied/unknown`(覆盖率阈值)，产出带**字符偏移**的证据；
3. 分数公式：`S = Σ score_i·(满足?1:0.5?) `，罚分仅采纳 `scoring_policy.penalties` 显式项，结果夹在 `[0,max]`；
4. 可选大模型复核判点 + 中文评语(JSON 结构化，二次夹取量规约束)；
5. 质量门控不通过/疑似"引图作答"→ 不改判 0 分，强制人工复核。

### 3.3 口语题(`engines/spoken.py` · 四层)
- `pronunciation/fluency` 依赖 ASR 词级时间戳(`ASRAdapter` 接口)；无 ASR 时该层标记**无数据**(`nodata`)不计分，如实呈现。
- `expression` 走课程术语库与语法启发式；`content` 层按量规要点匹配(可 LLM 复核)。
- 作答支持「文本转写(视为人工誊抄)」与「可选上传录音(multipart，扩展名白名单)」；转写文本照常判分，录音落盘为 `content_uri` 供后续接入真实 ASR 回放(装 faster-whisper 则可自动转录)。
- 判分产出四层 `layers{pronunciation/fluency/expression/content}` 持久化于 `Score.extra.layers`；含人工侧车词级时间戳的样本会在 `fluency` 层真实计算一次语速。
- 初始化样本含"人工誊抄转写(侧车)"答案，用于展示四层报告与时间戳证据结构。

### 3.4 实操视频题(`engines/video_stub.py` · 接口预留)
- 实现引擎接口但明确需姿态/动作识别能力支持；步骤置为 `证据不足` 交由教师按量规人工评阅，**不推断学生未完成**。

### 3.5 公式题(`engines/symbolic.py` · 确定性·幂等)
- `answer_config = {formula:{expected, variables:[{name,min,max}]}}`；作答为学生填写的表达式字符串。
- 等价判定两级：优先 `sympy` 解析化简后判 `==`；未安装 sympy 时退化到**变量域内确定性数值抽样**(默认 12 个采样点、变量较多时按 4×变量数+4 提升；两表达式逐点相对误差 <1e-6 判等价)，两条路径均有测试覆盖。
- 输出证据 `reason` 注明等价依据(解析式/抽样点集)，空答经 M2 门控转人工；公式题不参与客观题重放守门。

---

## 4. 数据模型

| 实体 | 要点 |
|---|---|
| Course / Chapter / KnowledgeNode | 章节含先修关系 `prereq_codes` |
| SkillDomain / SkillDimension | 6 一级域 × 10 二级维 = 60；维度代码 = 域前缀+序号 |
| Item / ItemVersion | 题型/题干/`answer_config`/`rubric`(得分点)/`knowledge_nodes`/`q_matrix`(节点→维度+权重)/难度 a、区分度 b/`scoring_policy`(review_mode=single\|double、require_double_publish、容差)/发布即固化为版本快照 |
| AnswerObject | student_token / item / modality / content / quality / trace_id / content_uri(录音) |
| Evidence | point_id / label / kind / 文本区间或时间戳 / snippet / confidence / created_by |
| Score | point_scores / total_score / final_score / confidence / status / review_level / review_round / `extra`(JSON：elapsed_ms、engine 元数据、口语 `layers`、双评 `double` 状态机) |
| ReviewRecord | 每次教师 action 一行：旧分→新分/原因/操作人(双评每次独立分也各一行，by 记录操作者) |
| AuditLog | 不可删除的审计 |
| AssessmentJob | 批量评阅任务(后台线程)与状态统计 |
| Diagnosis | 学生-课程诊断画像快照(node_mastery 含 BKT/ability/theta/recommendations/confidence) |
| RubricTemplate | 量规模板(name/subject/rubric JSON)，供命题教师一键套用 |
| PublishApproval | 发布复核登记(item_id/reviewer_id/comment)；`require_double_publish` 题目需 ≥2 个不同账号 |
| CourseDimensionToggle | 按课程停用能力维度(course_id/dimension_code/enabled，absent=启用) |

发布(锁定量规)后题目不可改，再次发布生成新版本；历史成绩按作答当时的 `item_version + model_version` 记录，不回写。

---

## 5. 诊断

- **Q 矩阵映射**：`Item.q_matrix = { node_code: {dimension, weight} }`(每节点映射到唯一能力维度)。按课程停用维度(`CourseDimensionToggle`)在聚合时被过滤，启用维权重重归一(M11)。
- **默认算法**（`diagnostics/mastery.py`）：
  - 节点掌握度 = 按 Q 权重加权的终评分比例，做正则收缩(λ=0.6)防小样本震荡；
  - 能力域 = 由二级维度按区分度加权聚合，输出 6 域 `ability{score,confidence,observed}`；
  - **维度全景 = 完整 60 维目录**，每维 `{code,label,domain_code,domain_label,enabled,score,observed}`：未观测维 `score=null` 且前端如实灰显"未观测"；
  - IRT 辅助：2PL 分数化拟然 MLE 估计 θ(题目参数用题目配置 a/b，如实标注为启发式)。
- **BKT 时序掌握**（`diagnostics/bkt.py`）：对 (学生,节点) 取按作答时间排序的序列；≥2 次观测时网格搜索极大化序列对数拟然拟合 `{pL0,pT,pG,pS}` 并回代末次后验 `mastery_after`；1 次观测退化为单轮规则并在报告注明 BKT 激活条件。属轻量本地估计，非大规模训练。
- **画像-作答匹配度**（`profile_match`）：对已终审作答，用当前 θ 与 IRT 预测各题对/错概率，与实得分算一致率/平均绝对差，得到实测的"能力画像对作答的解释程度"。
- **置信度合成**：观测数、各能力域 confidence、证据完整度 → `compute_overall_confidence`。
- **推荐**（`recommender.py`）：弱节点(<70%) → 先修节点补习(high)、微课(high)、巩固练习(medium)，输出对方案 §5.3 的 JSON。
- 报告页如实说明算法层级（`algorithm_detail`）。

---

## 6. 复核/双评/仲裁/审计

- 路由：客观 `review_level=none` → 自动放行(`status=auto_passed`)；非客观按引擎 `review_level`：`sample` 抽审 / `forced` 强制；空答客观同样转 `needs_review`。
- 教师工作台：evidence 高亮原文 → 逐得分点/证据明细 → 操作：
  - 单评模式：`accept` 接受模型分，`adjust` 改分终审，`arbitrate` 仲裁终审(需在 [0,max] 内)，`return_model` 删分退回重评。
  - **双评模式**(item `scoring_policy.review_mode=double`)：同一题由 **≥2 位不同教师**背靠背操作(按角色去重拦截 409)。题进入队列即带初始态 `await_pass1`(待第 1 评)；第一笔独立分记 `passes[0]` 后状态转 `await_pass2`；第二笔与第一笔分差 ≤ 容差(±1 分或 ±10%)→ 自动以均值终审 `done`；超差 → 状态 `await_arbitrate`，第三位教师 `arbitrate` 定案。动作流在后端 `apply_review` 内按状态机内部展开为 `double_pass1/double_pass2`，不再需要前端手选。
- **双人复核发布**(item `require_double_publish=true`)：`POST /items/{id}/publish` 先登记一次 `PublishApproval`，需 ≥2 个不同账号复核(通常教师+管理员)才真正 `published=True` 并生成版本快照；未达人数返回 `publish_pending` 与进度。普通题仍单账号发布(默认兼容)。
- 每次操作生成 `ReviewRecord` 与不可删 `AuditLog`；前端展示复核轨迹时间线。
- 管理端 `/audit`(admin) 可查全量动作。
- **质量指标实测**(`/metrics/quality`，口径见 API 文档与看板 note)：
  - `latency_ms`：由 `Score.extra.elapsed_ms` 聚合 avg/p95/max/n；
  - `objective_accuracy_guard`：对所有已终审客观分**重放确定性判分**并与存量总分比对，不一致计入 misgraded → accuracy = 1 − misgraded/n(运行时守门，无外部金标准依赖)；
  - `consistency`：engine 初评 vs 教师终审(真值)的每题型平均绝对差 + ±1 分容差一致率；
  - `calibration`：分数段 teacher−engine 偏移、温度最小二乘拟合 final≈a·engine+b(R²、n)、|offset| 超阈的分数段自动提示转人工；
  - `teacher_consistency`：双评完成对里两位教师 ±1 容差一致率与平均绝对差。

---

## 7. API 与角色界面映射

| 角色 | 界面 | 主要 API |
|---|---|---|
| 命题教师 | 题库管理 / 题目编辑器(量规模板·双评·双人发布)/ 知识图谱·维度·课程维度开关 | `/items*` `/rubric-templates` `/courses` `/dimensions` `/courses/{id}/dimensions` |
| 阅卷教师(A/B) | 复核中心(含双评阶段)/ 评阅工作台 | `/reviews/queue` `/reviews/{id}` `/scores/{id}` |
| 教务管理员 | 质量看板(延迟/守门/一致率/校准)/ 审计日志 | `/metrics/quality` `/audit`(另具命题/复核权) |
| 学生 | 我的成绩 / 自主练习(主观·公式·口语转写+录音)/ 诊断报告(60维·BKT·热力·匹配度) | `/scores/overview/{token}` `/practice/items` `/answers` `/diagnosis/mine/current` |

OpenAPI 交互文档：启动后端后访问 `http://127.0.0.1:8000/docs`。

---

## 8. 能力扩展点(后续规划)

| 扩展点 | 当前版本 | 后续规划 |
|---|---|---|
| 实操视频识别 | `video_stub` 接口预留，教师按步骤量规人工评阅 | 接入姿态/动作识别模型；帧证据入 `Evidence` |
| 实时发音 ASR | `ASRAdapter` 接口；可接 Whisper/侧车转录；口语作答支持"文本转写+录音证据"契约 | 音素级发音置信度；逐词时间戳入 `Evidence` 并回放 |
| IRT/BKT | 题目启发式参数(a/b)；已观测序列(≥2)上的 BKT 网格拟合与后验 | 真实题库参数标定 + 大规模跨轮时序训练 |
| OCR 富文本坐标 | 填空/主观文本偏移 | 版面解析 + 坐标级证据 |
| 数据库 | SQLite(默认轻量) | PostgreSQL(生产) |
| 私有化部署 | `.env` 可替换模型 | 部署脚手架/容器化 |
| 多模态证据展示 | 文本高亮 + 音频侧车 | 音/视频回放组件 |

**如实边界**：报告与指标只呈现已实测的层；无数据层不评分、不产生无效分数（口语发音/流畅层、实操视频层均如此）。
