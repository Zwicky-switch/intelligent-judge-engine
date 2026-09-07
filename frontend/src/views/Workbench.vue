<template>
  <div class="page" v-loading="loading">
    <el-card v-if="score">
      <div class="top">
        <el-button :icon="Back" @click="$router.push('/review')">返回队列</el-button>
        <div class="subject">
          <span class="mono code">{{ score.item?.code }}</span>
          <span class="muted">{{ score.item?.type_label }}</span>
          <b class="title">{{ score.item?.title }}</b>
        </div>
        <el-tag :type="LEVEL_TAG[score.review_level]" size="small">{{ LEVEL_LABELS[score.review_level] }}</el-tag>
        <el-tag :type="STATUS_TAG[score.status]" size="small">{{ STATUS_LABELS[score.status] }}</el-tag>
        <el-tag v-if="isDouble" :type="dbl.state === 'await_arbitrate' ? 'danger' : 'warning'" size="small">
          双评 · {{ DOUBLE_STATE_LABELS[dbl.state] }}
        </el-tag>
      </div>

      <el-descriptions :column="4" border size="small" class="desc">
        <el-descriptions-item label="学生">{{ score.student_name }}</el-descriptions-item>
        <el-descriptions-item label="引擎得分">{{ fmtScore(score.total_score) }} / {{ fmtScore(score.max_score) }}</el-descriptions-item>
        <el-descriptions-item label="终审分">{{ fmtScore(score.final_score ?? score.total_score) }}</el-descriptions-item>
        <el-descriptions-item label="模型置信度">{{ fmtPct(score.confidence) }}</el-descriptions-item>
        <el-descriptions-item label="模型版本">{{ score.model_version }}</el-descriptions-item>
        <el-descriptions-item label="复核轮次">第 {{ score.review_round }} 轮</el-descriptions-item>
        <el-descriptions-item label="质量门控">
          <el-tag v-if="answer?.quality" size="small" :type="answer.quality.pass ? 'success' : 'warning'">
            {{ answer.quality.pass ? '通过' : '未通过' }}
          </el-tag>
          <span v-else class="muted">—</span>
        </el-descriptions-item>
        <el-descriptions-item label="作答模态">{{ answer?.modality }}</el-descriptions-item>
      </el-descriptions>

      <!-- 双评/仲裁进度横幅 -->
      <div v-if="isDouble" class="double-banner" :class="{ arb: dbl.state === 'await_arbitrate' }">
        <div class="db-row">
          <b class="db-title">双评进度</b>
          <el-tag size="small" :type="dbl.state === 'await_arbitrate' ? 'danger' : 'warning'">
            {{ DOUBLE_STATE_LABELS[dbl.state] }}
          </el-tag>
          <span class="muted small-text">容差 = min(1 分, 满分 10%) = {{ dbl.tolerance ?? '—' }}</span>
          <span class="spacer" />
          <el-tag v-if="reviewedByMe" type="success" effect="light" size="small">您已完成本卷独立评，需另一位教师操作</el-tag>
        </div>
        <div class="db-passes">
          <div v-for="(p, i) in dbl.passes || []" :key="i" class="db-pass">
            第 {{ i + 1 }} 评 <b>{{ fmtScore(p.score) }}</b> 分 · {{ p.by }} · {{ fmtTime(p.at) }}
          </div>
          <span v-if="!(dbl.passes || []).length" class="muted small-text">尚无教师独立分 —— 您将是第 1 位评阅教师。</span>
        </div>
        <div v-if="dbl.diff !== undefined" class="muted small-text">
          已得分差 <b>{{ dbl.diff }}</b>（容差 {{ dbl.tolerance }}）→
          {{ dbl.diff <= dbl.tolerance ? '可自动取均值终审' : '超容差，需第三位教师仲裁终审' }}
        </div>
        <div class="muted small-text db-msg">{{ dbl.message }}</div>
      </div>

      <ScoreBreakdown :answer-text="answerText" :score="scoreWithEvidence" />
    </el-card>

    <!-- 教师操作条 -->
    <div v-if="score" class="review-bar card">
      <div class="bar-left">
        <b>{{ opTitle }}</b>
        <span class="muted small-text">{{ opHint }}</span>
      </div>
      <div class="bar-right">
        <el-input-number v-model="adjustScore" :min="0" :max="score.max_score" :precision="1"
                         :step="0.5" :disabled="!score" style="width:150px" />
        <el-input v-model="comment" placeholder="复核意见(选填)" style="width:260px" />
        <el-button type="primary" :disabled="!canScore || isArbStage" @click="act('accept')">
          {{ btnText('accept') }}
        </el-button>
        <el-button type="warning" :disabled="!canScore || isArbStage" @click="act('adjust')">
          {{ btnText('adjust') }}
        </el-button>
        <el-button type="danger" plain :disabled="!canScore || !isArbStage" @click="act('arbitrate')">
          {{ btnText('arbitrate') }}
        </el-button>
        <el-button @click="act('return_model')">退回模型重评</el-button>
      </div>
    </div>

    <div class="card" v-if="reviewRecords.length">
      <div class="block-title">复核轨迹</div>
      <el-timeline>
        <el-timeline-item v-for="r in reviewRecords" :key="r.id" :timestamp="fmtTime(r.created_at)" placement="top">
          <el-tag size="small" effect="plain">{{ ACTION_LABELS[r.action] }}</el-tag>
          <span class="tl"> 由 {{ r.reviewed_by || '—' }} 操作</span>
          <div class="muted tl">
            原分 {{ fmtScore(r.old_score) }} → 新分 {{ fmtScore(r.new_score) }}
            <span v-if="r.comment"> · {{ r.comment }}</span>
          </div>
        </el-timeline-item>
      </el-timeline>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Back } from '@element-plus/icons-vue'
import { getScore, doReview } from '@/api'
import ScoreBreakdown from '@/components/ScoreBreakdown.vue'
import { useAuthStore } from '@/stores/auth'
import {
  LEVEL_LABELS, LEVEL_TAG, STATUS_LABELS, STATUS_TAG, ACTION_LABELS,
  DOUBLE_STATE_LABELS, fmtScore, fmtPct,
} from '@/utils/const'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const scoreId = Number(route.params.scoreId)

const loading = ref(false)
const score = ref(null)
const answer = ref(null)
const reviewRecords = ref([])
const adjustScore = ref(0)
const comment = ref('')

const answerText = computed(() => {
  const a = answer.value
  if (!a) return ''
  return a.raw_response || a.content || ''
})
const scoreWithEvidence = computed(() => (score.value || {}))

const dbl = computed(() => (score.value?.extra?.double) || null)
// 双评卷判定: 有双评骨架, 或题目显式配置了 double 复核模式(兼容首评前尚无骨架的旧卷)
const isDouble = computed(() => {
  if (score.value?.status !== 'needs_review') return false
  if (!!dbl.value) return true
  return score.value?.item?.scoring_policy?.review_mode === 'double'
})
const passCount = computed(() => (dbl.value?.passes || []).length)
const isArbStage = computed(() => !!isDouble.value && passCount.value >= 2 && dbl.value?.state === 'await_arbitrate')
const reviewedByMe = computed(() => {
  if (!isDouble.value) return false
  const me = auth.user?.username
  return !!me && (dbl.value?.passes || []).some((p) => p.by === me)
})
const canScore = computed(() => !isDouble.value || !reviewedByMe.value)

const opTitle = computed(() => {
  if (!isDouble.value) return '教师复核操作'
  if (isArbStage.value) return '仲裁终审（第 3 评 · 分差超容差）'
  if (reviewedByMe.value) return '等待另一位教师独立评'
  return `第 ${passCount.value === 0 ? 1 : 2} 评独立评分`
})
const opHint = computed(() => {
  if (!isDouble.value) return '所有操作将写入不可删除的审计日志，并生成一条复核记录。'
  if (reviewedByMe.value) return '双评要求两位不同教师独立评分，本卷您的独立分已记录。'
  if (isArbStage.value) return '两教师分差超容差，请以仲裁身份给出终审分数并提交。'
  return '双评题：每位教师独立评分互不沟通；第二评落定后系统自动按容差取均值终审或转仲裁。'
})
const btnText = (a) => {
  if (!isDouble.value) {
    return { accept: '接受模型分', adjust: '改分并终审', arbitrate: '仲裁终审' }[a]
  }
  if (isArbStage.value) return '仲裁终审(独立终局分)'
  if (a === 'accept') return '接受引擎分作为本人独立分'
  if (a === 'adjust') return '本人独立给分(用上方分数)'
  return '仲裁终审'
}

function fmtTime(s) { return s ? s.replace('T', ' ').slice(0, 19) : '—' }

async function load() {
  loading.value = true
  try {
    const d = await getScore(scoreId)
    score.value = d
    answer.value = d.answer || null
    reviewRecords.value = d.review_records || []
    adjustScore.value = d.final_score ?? d.total_score
  } finally { loading.value = false }
}

function confirmFor(action) {
  if (action === 'return_model') {
    const extra = isDouble.value && passCount.value > 0 ? ' 并将清除已记录的双评进度' : ''
    return [`退回后当前成绩与证据将被清除并重新评阅${extra}，确认？`, '退回模型']
  }
  if (isDouble.value && reviewedByMe.value) {
    return ['您已完成本卷独立评，双评需另一位教师独立操作。', '不可重复评阅']
  }
  if (isArbStage.value) {
    return ['两教师分差超容差，确认以仲裁身份提交该终审分数？', '仲裁终审']
  }
  if (isDouble.value) {
    return [`确认将该分记录为您的${passCount.value === 0 ? '第 1 评' : '第 2 评'}独立分？提交后不可撤回。`, '提交独立分']
  }
  const map = {
    accept: ['确认接受引擎评分作为终审成绩？', '接受评分'],
    adjust: ['确认将成绩改为该分并终审？', '教师改分'],
    arbitrate: ['确认以仲裁身份给出终审分数？', '仲裁终审'],
  }
  return map[action] || ['确认该操作？', '确认']
}

async function act(action) {
  const payload = { action, comment: comment.value }
  if (action === 'adjust' || action === 'arbitrate') {
    payload.new_score = Number(adjustScore.value)
  }
  const [text, title] = confirmFor(action)
  await ElMessageBox.confirm(text, title, { type: action === 'return_model' ? 'warning' : 'info' })
  loading.value = true
  try {
    const res = await doReview(scoreId, payload)
    ElMessage.success(res.message || '已记录复核结果')
    if (res.action === 'return_model') {
      router.push('/review')
      return
    }
    await load()   // 双评推进后刷新页面状态(供下一位/同一位查看新阶段)
  } catch (e) {
    loading.value = false
    const detail = e?.response?.data?.detail
    if (detail) ElMessage.error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
}
onMounted(load)
</script>

<style scoped>
.top { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; flex-wrap: wrap; }
.subject { display: flex; align-items: center; gap: 8px; flex: 1; min-width: 0; }
.subject .code { font-size: 13px; }
.subject .title { margin-left: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.desc { margin-bottom: 0; }
.review-bar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.bar-left { flex: 1; display: flex; flex-direction: column; gap: 2px; min-width: 220px; }
.bar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.block-title { font-weight: 600; margin-bottom: 10px; }
.tl { font-size: 12px; }
.small-text { font-size: 12px; line-height: 1.6; }
.spacer { flex: 1; }
.double-banner { border: 1px solid #ffe58f; background: #fffbe6; border-radius: 8px; padding: 12px 14px; margin-top: 14px; }
.double-banner.arb { border-color: #ffa39e; background: #fff1f0; }
.db-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 6px; }
.db-title { font-size: 13px; }
.db-passes { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 4px; }
.db-pass { background: #fff; border: 1px solid #e6e8eb; border-radius: 6px; padding: 4px 10px; font-size: 12px; }
.db-msg { margin-top: 2px; }
</style>
