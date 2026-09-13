<template>
  <div class="page engine-page">
    <!-- 顶部: 引擎横幅 + 实时技术铭牌 -->
    <div class="hero card">
      <div class="hero-left">
        <div class="kicker">ENGINE INSIDE</div>
        <h2>评阅闭环，一图看懂</h2>
        <p class="muted">从「学生作答」到「能力诊断与学习建议」的一条流水线：客观题走确定性规则，主观 / 口语题由国产大模型在<b>量规约束</b>下协同评阅，全程把证据与置信度留给教师复核仲裁。</p>
        <div class="hero-tags">
          <span class="h-tag" :class="{ off: !isLive }">
            <span class="h-dot"></span>{{ providerLabel }}
          </span>
          <span class="h-tag">{{ meta?.model_version || '—' }}</span>
          <span class="h-tag">低信度阈值 {{ fmtTh(meta?.review_threshold) }}</span>
          <span class="h-tag">{{ meta?.auto_release_objective ? '客观题自动放行' : '客观题人工放行' }}</span>
        </div>
        <p class="note muted">{{ meta?.note }}</p>
      </div>
    </div>

    <!-- 流水线: 6 个环节 -->
    <div class="card">
      <div class="block-title">处理流水线（提交 → 诊断）</div>
      <el-row :gutter="14">
        <el-col v-for="(s, i) in STAGES" :key="s.key" :xs="24" :sm="12" :lg="8">
          <div class="stage" :class="'st-' + s.tone">
            <div class="st-head">
              <span class="st-no">{{ i + 1 }}</span>
              <span class="st-tag">{{ s.tag }}</span>
            </div>
            <div class="st-title">{{ s.title }}</div>
            <ul class="st-body">
              <li v-for="d in s.desc" :key="d">{{ d }}</li>
            </ul>
            <div class="st-link">
              <el-link v-for="l in linksFor(s.key)" :key="l.to" type="primary" :underline="'never'" @click="router.push(l.to)">
                <el-icon><component :is="l.icon" /></el-icon>&nbsp;{{ l.label }} →
              </el-link>
              <span v-if="!linksFor(s.key).length" class="muted st-empty">此环节在你的角色端自动执行，无独立页面</span>
            </div>
          </div>
        </el-col>
      </el-row>
    </div>

    <!-- 边界说明: 如实交代后续规划能力(已接口预留、不产生无效判定) -->
    <div class="card">
      <el-alert type="info" :closable="false" show-icon>
        <template #title><b>能力范围说明</b></template>
        <div class="boundary">
          <p>当前版本已支持并通过真实作答数据验证：客观题全题型与公式题（符号 / 数值抽样判等价）确定性判分、文本主观题「量规 → 证据 → 判点 → 大模型评语」协同、口语题四层表现报告（faster-whisper 接入后流畅层按词级时间戳真算；发音层未接入音素对齐时如实标「无数据」）、<b>图片作答 OCR</b>（视觉模型优先，失败回退本地 RapidOCR，转文字后按主观题判分）、<b>实操视频基础版</b>（服务端转写音轨，按步骤量规关键词判内容覆盖，动作/时序步骤证据不足转人工）、质量门控「空答不静默给分、转人工复核」、教师复核 / <b>双评（两位教师背靠背独立评分，超差进入仲裁）</b> / 发布双人复核 / 全程审计、Q 矩阵与 60 维能力诊断 + BKT 时序掌握 + 画像-作答匹配度，以及含延迟、存量分数重放一致率、engine↔教师一致率、分数段校准的质量看板。评阅默认由<b>内置本地引擎</b>完成，开箱即用；在服务配置（<code>.env</code>）中填入 DeepSeek / 通义 / 智谱的 API Key 后自动启用外部大模型做判点复核与评语生成。</p>
          <p>以下能力属于<span class="phase2">后续版本规划</span>，当前版本不产生无效判定：实操视频<b>姿态识别 / 动作时序对齐</b>（当前基础版只判音轨内容）、实时<b>音素级发音评测</b>（当前流畅层已真算，发音层待音素对齐）、大规模真实题库的 IRT / BKT 参数标定与训练。</p>
        </div>
      </el-alert>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { DataAnalysis, Files, Grid, Histogram, Lock, Monitor, Document } from '@element-plus/icons-vue'
import { engineMeta } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { PROVIDER_LABEL_OF, isExternalProvider } from '@/utils/const'

const router = useRouter()
const auth = useAuthStore()
const role = computed(() => auth.role)

const meta = ref(null)
const isLive = computed(() => !!meta.value && isExternalProvider(meta.value.llm_provider))
const providerLabel = computed(() =>
  (meta.value && PROVIDER_LABEL_OF(meta.value.llm_provider)) || '内置本地引擎')
const fmtTh = (v) => (v === null || v === undefined ? '—' : Number(v).toFixed(2))

onMounted(async () => {
  try { meta.value = await engineMeta() } catch { meta.value = null }
})

// 流水线环节说明(静态文案)
const STAGES = [
  {
    key: 'submit', tag: '提交', tone: 'blue', title: '① 多题型作答提交',
    desc: ['支持单选 / 多选 / 判断 / 填空 / 数值 / 公式 / 文本主观题 / 口语题', '口语支持文本转写 + 可选上传录音(multipart 契约)', '内容统一进 parser 做规范化与质量门控，作答带原文与 URI'],
  },
  {
    key: 'gate', tag: '门控', tone: 'cyan', title: '② 质量门控与规范化',
    desc: ['空卷 / 超长 / 内容不符一律不自动给分', '宁可转人工，也不静默猜一个分数(客观空答同样转人工)', '文本保留字符级偏移，便于证据回溯'],
  },
  {
    key: 'grade', tag: '评阅', tone: 'indigo', title: '③ 量规约束下协同评阅',
    desc: ['客观 / 数值 / 公式题：确定性判分，可解释、可重放', '公式题符号/数值抽样判等价，结果唯一幂等', '主观 / 口语题：规则召回要点 → 大模型判点补强并写评语(LLM 不绕量规)'],
  },
  {
    key: 'evidence', tag: '证据', tone: 'green', title: '④ 证据优先落库',
    desc: ['每个得分点关联原文片段 / 音频时间戳', '判分同时记录置信度与理由，供教师核对', '“只给结论不给证据”的坏味道被结构上消除'],
  },
  {
    key: 'review', tag: '复核', tone: 'amber', title: '⑤ 置信度路由 + 双评/复核仲裁',
    desc: ['低置信度 / 证据冲突 / 质量不足 → 强制转人工', '双评题两位教师背靠背独立分，超差进入仲裁', '发布可设双人复核门；动作全程进不可删审计'],
  },
  {
    key: 'diagnosis', tag: '诊断', tone: 'purple', title: '⑥ Q 矩阵 → 能力诊断 → 建议',
    desc: ['题↔知识点↔能力维度的显式映射', '节点掌握度 + BKT 时序 / 60 维全景 / 热力图', '输出个性化学习建议与画像-作答匹配度'],
  },
]

// 各角色“去看看”的真实入口(只指向本角色可见的页面)
function linksFor(key) {
  const r = role.value
  const map = {
    submit: {
      prop_teacher: { to: '/items', label: '去题库看题型覆盖', icon: Files },
      grader: { to: '/review', label: '去复核队列看待评', icon: Document },
      admin: { to: '/items', label: '去题库看题型覆盖', icon: Files },
      student: { to: '/my/scores', label: '看我的作答与得分', icon: DataAnalysis },
    },
    gate: {
      prop_teacher: { to: '/items', label: '去题目设置与样例', icon: Files },
      grader: { to: '/review', label: '去复核中心', icon: Document },
      admin: { to: '/dashboard', label: '去看质量看板', icon: Monitor },
      student: { to: '/my/scores', label: '看我的成绩单', icon: DataAnalysis },
    },
    grade: {
      prop_teacher: { to: '/knowledge', label: '去知识图谱与能力维度', icon: Grid },
      grader: { to: '/review', label: '去复核中心', icon: Document },
      admin: { to: '/dashboard', label: '去看判分与放行指标', icon: Monitor },
      student: { to: '/my/scores', label: '看逐题判点与评语', icon: DataAnalysis },
    },
    evidence: {
      prop_teacher: { to: '/knowledge', label: '去看知识点映射', icon: Grid },
      grader: { to: '/review', label: '去复核证据与理由', icon: Document },
      admin: { to: '/audit', label: '去审计复核记录', icon: Lock },
      student: { to: '/my/scores', label: '看原文证据高亮', icon: DataAnalysis },
    },
    review: {
      grader: { to: '/review', label: '去复核仲裁', icon: Document },
      admin: { to: '/review', label: '去复核仲裁', icon: Document },
      student: { to: '/my/report', label: '看我的能力报告', icon: Histogram },
    },
    diagnosis: {
      prop_teacher: { to: '/knowledge', label: '去看能力维度', icon: Grid },
      grader: { to: '/dashboard', label: '看班级能力画像', icon: Monitor },
      admin: { to: '/dashboard', label: '看班级能力画像', icon: Monitor },
      student: { to: '/my/report', label: '看六域诊断报告', icon: Histogram },
    },
  }
  const hit = map[key] && map[key][r]
  return hit ? [hit] : []
}
</script>

<style scoped>
.engine-page .card { border-radius: 14px; }
.hero {
  position: relative; overflow: hidden;
  background:
    radial-gradient(520px 260px at 96% -20%, rgba(85, 164, 255, .16), transparent 70%),
    linear-gradient(120deg, #0c2340, #123861 55%, #18518f);
  color: #eef3f9; border: none;
}
.hero-left { max-width: 920px; }
.kicker { font-size: 12px; letter-spacing: 3px; color: #7fb2e8; font-weight: 700; margin-bottom: 8px; }
.hero h2 { margin: 0 0 10px; color: #fff; font-size: 22px; }
.hero p.muted { color: #b9c9db; line-height: 1.8; margin: 0 0 16px; }
.hero p.muted b { color: #dcebfb; }
.hero-tags { display: flex; flex-wrap: wrap; gap: 8px; }
.h-tag {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 4px 12px; border-radius: 20px; font-size: 12px;
  background: rgba(255, 255, 255, .08); border: 1px solid rgba(255, 255, 255, .14); color: #dbe7f5;
  font-family: Consolas, Menlo, monospace;
}
.h-dot { width: 7px; height: 7px; border-radius: 50%; background: #23a55a; box-shadow: 0 0 0 3px rgba(35, 165, 90, .2); }
.h-tag.off .h-dot { background: #c9a227; box-shadow: 0 0 0 3px rgba(201, 162, 39, .18); }
.note { font-size: 12px; line-height: 1.6; margin: 12px 0 0; }

.block-title { font-weight: 600; margin-bottom: 14px; }
.stage {
  height: 100%;
  border: 1px solid var(--border-soft); border-top: 3px solid #409eff;
  border-radius: 12px; padding: 14px 16px; margin-bottom: 14px;
  background: linear-gradient(180deg, #fff, #fbfcfe);
  transition: transform .18s ease, box-shadow .18s ease;
}
.stage:hover { transform: translateY(-2px); box-shadow: 0 6px 18px -12px rgba(47, 124, 214, .35); }
.st-cyan { border-top-color: #33c3c0; }
.st-indigo { border-top-color: #6f6ce0; }
.st-green { border-top-color: #34b57d; }
.st-amber { border-top-color: #e6a23c; }
.st-purple { border-top-color: #9a6be0; }
.st-head { display: flex; align-items: center; justify-content: space-between; }
.st-no {
  width: 24px; height: 24px; line-height: 24px; text-align: center; border-radius: 7px;
  background: linear-gradient(135deg, #2f7cd6, #55b0ff); color: #fff; font-weight: 700; font-size: 13px;
}
.st-tag { font-size: 11px; color: var(--muted); letter-spacing: 1px; }
.st-title { font-weight: 700; margin: 10px 0 8px; font-size: 15px; color: #2a3340; }
.st-body { list-style: none; margin: 0 0 12px; padding: 0; font-size: 13px; line-height: 1.7; color: #5a6472; }
.st-body li { position: relative; padding-left: 14px; }
.st-body li::before { content: ''; position: absolute; left: 2px; top: 9px; width: 5px; height: 5px; border-radius: 50%; background: #b9cfec; }
.st-link { min-height: 22px; }
.st-empty { font-size: 12px; }
.el-link { font-size: 13px; }

.boundary { font-size: 13px; line-height: 1.85; }
.boundary p { margin: 0 0 6px; }
.boundary code { background: #f0f4f9; border-radius: 4px; padding: 1px 5px; font-size: 12px; }
.boundary .phase2 { color: var(--muted); cursor: not-allowed; }
@media (max-width: 640px) {
  .hero h2 { font-size: 18px; }
}
</style>
