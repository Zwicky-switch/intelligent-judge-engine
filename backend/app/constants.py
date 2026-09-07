"""领域常量与枚举(字符串常量, 便于序列化)."""
from __future__ import annotations

# ---------- 用户角色 ----------
ROLE_ADMIN = "admin"              # 教务管理员
ROLE_PROP_TEACHER = "prop_teacher"  # 命题教师
ROLE_GRADER = "grader"            # 阅卷教师 / 仲裁专家
ROLE_STUDENT = "student"          # 学生
ROLES = [ROLE_ADMIN, ROLE_PROP_TEACHER, ROLE_GRADER, ROLE_STUDENT]

ROLE_LABELS = {
    ROLE_ADMIN: "教务管理员",
    ROLE_PROP_TEACHER: "命题教师",
    ROLE_GRADER: "阅卷教师",
    ROLE_STUDENT: "学生",
}

# ---------- 题型 ----------
T_SINGLE_CHOICE = "single_choice"
T_MULTIPLE_CHOICE = "multiple_choice"
T_TRUE_FALSE = "true_false"
T_FILL_BLANK = "fill_blank"
T_NUMERIC = "numeric"
T_SUBJECTIVE_TEXT = "subjective_text"
T_SPOKEN = "spoken"
T_VIDEO = "practical_video"
T_FORMULA = "formula"         # 公式符号化题(字母表达式等价判定)

OBJECTIVE_TYPES = {
    T_SINGLE_CHOICE, T_MULTIPLE_CHOICE, T_TRUE_FALSE, T_FILL_BLANK, T_NUMERIC,
}
ALL_ITEM_TYPES = OBJECTIVE_TYPES | {
    T_SUBJECTIVE_TEXT, T_SPOKEN, T_VIDEO, T_FORMULA,
}

ITEM_TYPE_LABELS = {
    T_SINGLE_CHOICE: "单选题",
    T_MULTIPLE_CHOICE: "多选题",
    T_TRUE_FALSE: "判断题",
    T_FILL_BLANK: "填空题",
    T_NUMERIC: "数值题",
    T_SUBJECTIVE_TEXT: "文本主观题",
    T_SPOKEN: "口语题",
    T_VIDEO: "实操视频题",
    T_FORMULA: "公式符号化题",
}

# 题型 -> 答案模态
MODALITY_TEXT = "text"
MODALITY_AUDIO = "audio"
MODALITY_VIDEO = "video"
ITEM_MODALITY = {
    T_SINGLE_CHOICE: MODALITY_TEXT,
    T_MULTIPLE_CHOICE: MODALITY_TEXT,
    T_TRUE_FALSE: MODALITY_TEXT,
    T_FILL_BLANK: MODALITY_TEXT,
    T_NUMERIC: MODALITY_TEXT,
    T_SUBJECTIVE_TEXT: MODALITY_TEXT,
    T_SPOKEN: MODALITY_AUDIO,
    T_VIDEO: MODALITY_VIDEO,
    T_FORMULA: MODALITY_TEXT,
}

# ---------- 得分点判定状态 ----------
V_SATISFIED = "satisfied"    # 明确满足
V_PARTIAL = "partial"        # 部分满足
V_UNSATISFIED = "unsatisfied"  # 不满足
V_UNKNOWN = "unknown"        # 无法判断 -> 强制人工
VERDICT_LABELS = {
    V_SATISFIED: "满足",
    V_PARTIAL: "部分满足",
    V_UNSATISFIED: "不满足",
    V_UNKNOWN: "无法判断",
}

# ---------- 评分结果状态与复核档位 ----------
ST_PENDING = "pending"       # 已提交未评
ST_AUTO_PASSED = "auto_passed"   # 自动通过(客观题 / 高信度放行), 仍可被教师复核改
ST_NEEDS_REVIEW = "needs_review"  # 需人工复核(按档位)
ST_REVIEWED = "reviewed"     # 教师已终审(accept/adjust/arbitrate)

LVL_NONE = "none"       # 自动通过
LVL_SAMPLE = "sample"   # 抽样复核
LVL_FORCED = "forced"   # 强制复核
REVIEW_LEVELS = [LVL_NONE, LVL_SAMPLE, LVL_FORCED]

# 复核动作
ACT_ACCEPT = "accept"         # 接受模型分(双评下=本人独立分取引擎分)
ACT_ADJUST = "adjust"         # 修改分值(双评下=本人独立分)
ACT_ARBITRATE = "arbitrate"   # 仲裁终审(双评超差时第三位教师终审)
ACT_RETURN = "return_model"   # 退回模型重新评阅

# 双评/三评动作(记入 ReviewRecord.action, 供一致性与阶段展示)
ACT_DOUBLE_PASS1 = "double_pass1"   # 第 1 位教师独立评阅
ACT_DOUBLE_PASS2 = "double_pass2"   # 第 2 位教师独立评阅

# ---------- 能力域(一级) ----------
ABILITY_DOMAINS = [
    ("domain_knowledge", "知识理解"),
    ("domain_problem", "问题解决"),
    ("domain_practice", "实践操作"),
    ("domain_expression", "表达沟通"),
    ("domain_critical", "批判与创新"),
    ("domain_transfer", "学习迁移"),
]

# ---------- 口语四层指标 ----------
LAYER_PRON = "pronunciation"
LAYER_FLUENCY = "fluency"
LAYER_EXPRESSION = "expression"
LAYER_CONTENT = "content"
SPOKEN_LAYERS = [LAYER_PRON, LAYER_FLUENCY, LAYER_EXPRESSION, LAYER_CONTENT]
SPOKEN_LAYER_LABELS = {
    LAYER_PRON: "发音准确度",
    LAYER_FLUENCY: "语流流畅度",
    LAYER_EXPRESSION: "语言表达",
    LAYER_CONTENT: "内容逻辑性",
}

MODEL_VERSION = "insight-judge-v0.1"  # 当前模型版本号(模型可替换: 换模型升版本)
