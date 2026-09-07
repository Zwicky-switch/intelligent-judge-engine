<template>
  <div class="page">
    <el-tabs v-model="tab">
      <el-tab-pane label="我的作答记录" name="mine">
        <div class="card" v-loading="loading">
          <div class="stat-grid" v-if="attempts.length">
            <div class="stat-card"><div class="lbl">已作答题目</div><div class="num">{{ attempts.length }}</div></div>
            <div class="stat-card"><div class="lbl">平均得分率</div><div class="num">{{ fmtPct(avgRatio) }}</div></div>
            <div class="stat-card"><div class="lbl">待教师复核</div><div class="num" style="color:#f0a020">{{ needReview }}</div></div>
          </div>
          <el-empty v-else :image-size="80" description="还没有作答记录，去「自主练习」做一题吧" />

          <el-collapse v-if="attempts.length" v-model="openIds" class="attempts">
            <el-collapse-item v-for="at in attempts" :key="at.score.id" :name="at.score.id">
              <template #title>
                <div class="at-title">
                  <span class="mono code">{{ at.item.code }}</span>
                  <span class="muted">{{ at.item.type_label }}</span>
                  <b class="stem">{{ at.item.title }}</b>
                  <el-tag :type="STATUS_TAG[at.score.status]" size="small">{{ STATUS_LABELS[at.score.status] }}</el-tag>
                  <span class="score">得分 <b>{{ fmtScore(at.score.final_score ?? at.score.total_score) }}</b>/{{ fmtScore(at.score.max_score) }}</span>
                </div>
              </template>
              <div class="collapse-body">
                <el-descriptions :column="3" size="small" border class="mini-desc">
                  <el-descriptions-item label="我的作答">
                    {{ answerTextOf(at) || '—' }}
                  </el-descriptions-item>
                  <el-descriptions-item label="模型版本">{{ at.score.model_version }}</el-descriptions-item>
                  <el-descriptions-item label="置信度">{{ fmtPct(at.score.confidence) }}</el-descriptions-item>
                </el-descriptions>
                <ScoreBreakdown :answer-text="answerTextOf(at)" :score="at.score" />
              </div>
            </el-collapse-item>
          </el-collapse>
        </div>
      </el-tab-pane>

      <el-tab-pane label="自主练习" name="practice">
        <div class="card" v-loading="pLoading">
          <div class="sub-head">
            <b>自主练习</b>
            <span class="muted">客观题即时判定；主观/口语/公式题送教师复核后给出终审成绩</span>
          </div>
          <div v-for="it in practiceList" :key="it.id" class="practice-card">
            <div class="pc-head">
              <span class="mono code">{{ it.code }}</span>
              <el-tag size="small" effect="plain">{{ it.type_label }}</el-tag>
              <span class="muted">满分 {{ fmtScore(it.max_score) }} · {{ it.chapter_name }}</span>
              <span class="spacer" />
              <el-tag v-if="it.answered" size="small" type="success">已作答</el-tag>
            </div>
            <pre class="stem-text">{{ it.title }}</pre>

            <!-- 选择/判断 -->
            <div v-if="choices(it).length" class="choices">
              <el-radio-group v-if="it.type === 'single_choice'" v-model="answers[it.id]">
                <el-radio v-for="c in choices(it)" :key="c.letter" :value="c.letter" class="choice">{{ c.letter }}. {{ c.text }}</el-radio>
              </el-radio-group>
              <el-checkbox-group v-else-if="it.type === 'multiple_choice'" v-model="answers[it.id]">
                <el-checkbox v-for="c in choices(it)" :key="c.letter" :value="c.letter" class="choice">{{ c.letter }}. {{ c.text }}</el-checkbox>
              </el-checkbox-group>
              <el-radio-group v-else-if="it.type === 'true_false'" v-model="answers[it.id]">
                <el-radio value="T">正确</el-radio><el-radio value="F">错误</el-radio>
              </el-radio-group>
            </div>
            <!-- 数值 / 填空 -->
            <el-input v-else-if="it.type === 'numeric'" v-model="answers[it.id]" placeholder="输入数值(可带单位，如 5 m/s^2)" style="max-width:340px" />
            <el-input v-else-if="it.type === 'fill_blank'" v-model="answers[it.id]" placeholder="多个空用 | 分隔，如: ma|N|惯性" style="max-width:380px" />
            <!-- 文本主观题 -->
            <el-input v-else-if="it.type === 'subjective_text'" v-model="answers[it.id]" type="textarea" :rows="5"
                      placeholder="分点写出你的推导/说理过程(越长越完整，判分依据关键词与逻辑)" />
            <!-- 公式符号化题 -->
            <el-input v-else-if="it.type === 'formula'" v-model="answers[it.id]"
                      placeholder="输入字母表达式，如 F/m、a=(x+y)^2(用 * / ^ 或 ×÷)" style="max-width:420px" />
            <!-- 口语题: 转写文本 + 可选录音 -->
            <div v-else-if="it.type === 'spoken'" class="spoken-box">
              <el-input v-model="answers[it.id]" type="textarea" :rows="4"
                        placeholder="用文本誊写你的口头陈述(相当于录音转写)，内容逻辑/表达层会据此判分" />
              <div class="audio-row">
                <el-button size="small" @click="pickAudio(it)">选择录音(可选)</el-button>
                <span class="muted small" v-if="audioNames[it.id]">已选：{{ audioNames[it.id] }}</span>
                <span v-else class="muted small">未接入自动语音评测时，系统仍按上方转写文本评分；上传的录音将作为评测证据留存</span>
                <input :ref="(el) => setAudioInput(it.id, el)" type="file" accept="audio/*" style="display:none" @change="(e) => onPickAudio(it, e)" />
              </div>
            </div>
            <el-input v-else v-model="answers[it.id]" placeholder="输入作答" style="max-width:380px" />

            <div class="pc-actions">
              <el-button type="primary" size="small" :disabled="!answers[it.id]" :loading="submittingId === it.id"
                         @click="submit(it)">{{ canSubmitText(it) ? '提交' : '提交判分' }}</el-button>
              <span v-if="lastResult && lastResult.item_id === it.id" class="result">
                <el-tag :type="scoreTag" size="small">{{ scoreLabel }}</el-tag>
                <span class="muted">{{ lastResult.message }}</span>
                <span v-if="spokenSummary" class="muted small">· {{ spokenSummary }}</span>
              </span>
            </div>
          </div>
          <el-empty v-if="!practiceList.length" :image-size="70" description="暂无可练习的题目" />
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { studentOverview, practiceItems, submitAnswer, submitAnswerAudio } from '@/api'
import { useAuthStore } from '@/stores/auth'
import ScoreBreakdown from '@/components/ScoreBreakdown.vue'
import { STATUS_LABELS, STATUS_TAG, SPOKEN_LAYER_LABELS, fmtScore, fmtPct } from '@/utils/const'

const auth = useAuthStore()
const tab = ref('mine')

const loading = ref(false)
const attempts = ref([])
const openIds = ref([])
const needReview = ref(0)
const avgRatio = ref(null)

const practiceList = ref([])
const pLoading = ref(false)
const answers = reactive({})
const audioFiles = reactive({})
const audioNames = reactive({})
const audioInputs = {}
const submittingId = ref(null)
const lastResult = ref(null)

const answerTextOf = (at) => {
  const a = at.answer
  return a ? (a.raw_response || a.content || '') : ''
}

async function loadMine() {
  loading.value = true
  try {
    const res = await studentOverview(auth.user.student_token)
    attempts.value = res.attempts || []
    const done = attempts.value.filter((at) => ['auto_passed', 'reviewed'].includes(at.score.status))
    const ratios = done.map((at) => {
      const s = at.score
      const fin = s.final_score ?? s.total_score
      return s.max_score ? fin / s.max_score : 0
    })
    avgRatio.value = ratios.length ? ratios.reduce((a, b) => a + b, 0) / ratios.length : null
    needReview.value = attempts.value.filter((at) => at.score.status === 'needs_review').length
  } finally { loading.value = false }
}

const LETTERS = 'ABCDEFGHIJ'
function choices(it) {
  const opts = (it.public_config && it.public_config.options) || []
  if (opts.length) return opts.map((o, i) => ({ letter: LETTERS[i], text: o }))
  const out = []
  for (const line of (it.title || '').split('\n')) {
    const m = line.trim().match(/^([A-H])[\.、．:：)]\s*(.+)$/)
    if (m) out.push({ letter: m[1], text: m[2] })
  }
  return out
}

function canSubmitText(it) {
  return ['subjective_text', 'spoken', 'formula'].includes(it.type)
}

function setAudioInput(id, el) {
  if (el) audioInputs[id] = el
}
function pickAudio(it) {
  const input = audioInputs[it.id]
  if (input) input.click()
}
function onPickAudio(it, e) {
  const file = e.target.files && e.target.files[0]
  if (!file) return
  audioFiles[it.id] = file
  audioNames[it.id] = file.name
  e.target.value = ''   // 允许重复选择同一文件
}

function answerPayload(it) {
  let v = answers[it.id]
  if (it.type === 'multiple_choice') v = (v || []).join(',')
  return { item_id: it.id, content: (v || '').trim() }
}

const scoreTag = computed(() => {
  const s = lastResult.value?.score
  return s ? STATUS_TAG[s.status] : 'info'
})
const scoreLabel = computed(() => {
  const s = lastResult.value?.score
  if (!s) return ''
  return `${STATUS_LABELS[s.status]} · 引擎分 ${fmtScore(s.total_score)}/${fmtScore(s.max_score)}`
})
const spokenSummary = computed(() => {
  const layers = lastResult.value?.score?.extra?.layers
  if (!layers) return ''
  const parts = []
  for (const code of ['content', 'expression', 'fluency', 'pronunciation']) {
    const l = layers[code]
    if (!l) continue
    if (l.status === 'ok' && typeof l.score === 'number') parts.push(`${SPOKEN_LAYER_LABELS[code]} ${Math.round(l.score * 100)}%`)
    else parts.push(`${SPOKEN_LAYER_LABELS[code]} 无数据`)
  }
  return `四层：${parts.join(' / ')}`
})

async function submit(it) {
  submittingId.value = it.id
  try {
    let res
    if (it.type === 'spoken' && audioFiles[it.id]) {
      // 口语录音契约: 转写文本 + 录音文件(存证据)
      const fd = new FormData()
      fd.append('item_id', it.id)
      fd.append('content', (answers[it.id] || '').trim())
      fd.append('asr_note', 'manual_transcript')
      fd.append('audio', audioFiles[it.id])
      res = await submitAnswerAudio(fd)
    } else {
      res = await submitAnswer(answerPayload(it))
    }
    lastResult.value = { ...res, item_id: it.id }
    ElMessage.success(res.message || '判分完成')
    await loadMine()
    await loadPractice()   // 移除已作答题目
  } finally {
    submittingId.value = null
  }
}

async function loadPractice() {
  pLoading.value = true
  try {
    const res = await practiceItems()
    practiceList.value = (res.items || []).filter((it) => !it.answered)
    res.items.forEach((it) => {
      if (it.type === 'multiple_choice') answers[it.id] = answers[it.id] || []
    })
  } finally { pLoading.value = false }
}

onMounted(() => {
  loadMine()
  loadPractice()
})
</script>

<style scoped>
.sub-head { display: flex; align-items: baseline; gap: 12px; margin-bottom: 8px; }
.at-title { display: flex; align-items: center; gap: 8px; flex: 1; min-width: 0; width: 100%; }
.at-title .stem { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; font-weight: 500; }
.at-title .score { margin-left: auto; color: #606266; }
.collapse-body { padding: 4px 8px 8px; }
.mini-desc { margin-bottom: 14px; }
.mono { font-family: Consolas, Menlo, monospace; }
.code { font-size: 12px; color: #606266; }
.small { font-size: 12px; }
.practice-card { border: 1px solid #ebeef5; border-radius: 8px; padding: 14px 16px; margin-bottom: 14px; background: #fafbfc; }
.pc-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.spacer { flex: 1; }
.stem-text { white-space: pre-wrap; line-height: 1.7; font-family: inherit; margin: 8px 0 10px; font-size: 14px; }
.choices { display: flex; flex-direction: column; gap: 6px; margin-bottom: 10px; }
.choice { margin-right: 16px; }
.spoken-box { display: flex; flex-direction: column; gap: 8px; max-width: 640px; }
.audio-row { display: flex; align-items: center; gap: 10px; }
.pc-actions { display: flex; align-items: center; gap: 12px; margin-top: 8px; }
.result { display: inline-flex; align-items: center; gap: 8px; flex-wrap: wrap; }
</style>
