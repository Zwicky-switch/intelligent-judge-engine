// 领域常量与中文标签(与 backend/app/constants.py 对齐)

export const ROLES = {
  ADMIN: 'admin',
  PROP_TEACHER: 'prop_teacher',
  GRADER: 'grader',
  STUDENT: 'student',
}
export const ROLE_LABELS = {
  admin: '教务管理员',
  prop_teacher: '命题教师',
  grader: '阅卷教师',
  student: '学生',
}

export const ITEM_TYPE_LABELS = {
  single_choice: '单选题',
  multiple_choice: '多选题',
  true_false: '判断题',
  fill_blank: '填空题',
  numeric: '数值题',
  subjective_text: '文本主观题',
  spoken: '口语题',
  practical_video: '实操视频题',
  formula: '公式符号化题',
}

export const VERDICT_LABELS = {
  satisfied: '满足',
  partial: '部分满足',
  unsatisfied: '不满足',
  unknown: '无法判断',
}
// verdict -> Element Plus tag 类型
export const VERDICT_TAG = {
  satisfied: 'success',
  partial: 'warning',
  unsatisfied: 'info',
  unknown: 'danger',
}

export const STATUS_LABELS = {
  pending: '待评',
  auto_passed: '自动通过',
  needs_review: '待复核',
  reviewed: '已终审',
}
export const STATUS_TAG = {
  pending: 'info',
  auto_passed: 'success',
  needs_review: 'warning',
  reviewed: 'primary',
}

export const LEVEL_LABELS = {
  none: '自动放行',
  sample: '抽样复核',
  forced: '强制复核',
}
export const LEVEL_TAG = {
  none: 'info',
  sample: 'warning',
  forced: 'danger',
}

export const ACTION_LABELS = {
  accept: '接受模型分',
  adjust: '教师改分',
  arbitrate: '仲裁终审',
  return_model: '退回模型重评',
  double_pass1: '第 1 评独立分',
  double_pass2: '第 2 评独立分',
}

export const DOUBLE_STATE_LABELS = {
  await_pass1: '待第 1 评',
  await_pass2: '待第 2 评',
  await_arbitrate: '待仲裁(超容差)',
  done: '双评完成',
}

export const SPOKEN_LAYER_LABELS = {
  pronunciation: '发音准确度',
  fluency: '语流流畅度',
  expression: '语言表达',
  content: '内容逻辑性',
}
// 口语四层 -> Element 标签颜色 / 无数据提示
export const SPOKEN_LAYER_TAG = { pronunciation: 'danger', fluency: 'success', expression: 'primary', content: 'warning' }
export const SPOKEN_LAYER_NODATA = {
  pronunciation: '需接入音素级 ASR/强制对齐',
  fluency: '需词级时间戳(ASR/侧车)',
  expression: '',
  content: '',
}

export const DOMAIN_LABELS = {
  domain_knowledge: '知识理解',
  domain_problem: '问题解决',
  domain_practice: '实践操作',
  domain_expression: '表达沟通',
  domain_critical: '批判与创新',
  domain_transfer: '学习迁移',
}
// 6 能力域雷达配色(按固定顺序)
export const DOMAIN_COLORS = {
  domain_knowledge: '#5470c6',
  domain_problem: '#91cc75',
  domain_practice: '#fac858',
  domain_expression: '#ee6666',
  domain_critical: '#73c0de',
  domain_transfer: '#3ba272',
}

export const COGNITIVE_LABELS = {
  remember: '识记',
  understand: '理解',
  apply: '应用',
  analyze: '分析',
  evaluate: '评价',
  create: '创造',
}

// 评阅引擎 provider 显示名与判定(与 backend llm/base.py normalize_provider 对齐)。
// 后端把内置引擎(含历史内部值)统一归并为 builtin, 前端无需感知其它本地别名。
export const PROVIDER_LABELS = {
  builtin: '内置本地引擎',
  deepseek: 'DeepSeek 大模型',
  qwen: '通义千问大模型',
  zhipu: '智谱 GLM 大模型',
  openai: 'OpenAI 兼容大模型',
  openai_compat: 'OpenAI 兼容大模型',
}
export const PROVIDER_LABEL_OF = (code) =>
  (code && PROVIDER_LABELS[code]) || code || '内置本地引擎'
// 是否外部模型在驱动: 内置引擎视为本地, 其余需配合 has_api_key 判定在线。
export const isExternalProvider = (code) => !!code && code !== 'builtin'

export const fmtScore = (v) => (v === null || v === undefined ? '—' : Number(v).toFixed(1))
export const fmtPct = (v) => (v === null || v === undefined ? '—' : `${Math.round(Number(v) * 100)}%`)
