<template>
  <div class="page" v-loading="loading">
    <div class="card">
      <div class="topbar">
        <div class="back" @click="$router.push('/items')"><el-icon><ArrowLeft /></el-icon> 返回题库</div>
        <div class="title-line">
          <h3>{{ isNew ? '新建题目' : `题目 ${form.code}` }}</h3>
          <el-tag v-if="!isNew" size="small" :type="published ? 'success' : 'info'">{{ published ? '已发布' : '草稿' }}</el-tag>
          <el-tag v-if="form.type" size="small" effect="plain">{{ typeLabel }}</el-tag>
        </div>
        <div class="actions">
          <el-button v-if="!published" type="primary" :loading="saving" @click="save(false)">保存</el-button>
          <el-button v-if="!published" type="success" :loading="publishing" @click="save(true)">保存并发布</el-button>
          <el-button v-else type="warning" :loading="publishing" @click="save(true)">修订发布(升版本)</el-button>
        </div>
      </div>
      <el-alert v-if="published" type="warning" :closable="false" show-icon class="pub-alert"
                title="题目已发布：量规与答案已固化，内容锁定不可改。需修订请再次“修订发布”以生成新版本(历史成绩不回写)。" />
    </div>

    <!-- 评分与发布策略(M9 双评 / M10 双人复核发布) -->
    <div class="card">
      <div class="block-title">评分与发布策略</div>
      <el-form label-width="150px" label-position="left" :disabled="published">
        <el-form-item v-if="hasRubric" label="双评模式(review_mode)">
          <el-radio-group v-model="policy.review_mode">
            <el-radio value="single">单评（默认）</el-radio>
            <el-radio value="double">双评（≥2 位不同教师独立评分，超容差转仲裁）</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="发布双人复核">
          <el-switch v-model="policy.require_double_publish"
                     active-text="需 2 个不同账号复核通过后才真正发布(固化为版本)" inactive-text="单个账号即可发布" />
        </el-form-item>
        <el-form-item v-if="!isNew" label="版本快照">
          <span class="muted small-text">当前 v{{ form.current_version || 1 }} · {{ published ? '已发布(内容锁定, 修订发布会升版本)' : '草稿(未发布)' }}</span>
          <span class="muted small-text" style="margin-left:10px">历史版本与差异比较可在题库列表的「历史」中查看。</span>
        </el-form-item>
      </el-form>
    </div>

    <div class="card">
      <div class="form-grid">
        <el-form label-width="92px" label-position="left" :disabled="published">
          <el-row :gutter="16">
            <el-col :span="6">
              <el-form-item label="题目编号"><el-input v-model="form.code" placeholder="如 PHY-2026-050(留空自动)" /></el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="所属课程">
                <el-select v-model="form.course_id" style="width:100%" @change="onCourseChange">
                  <el-option v-for="c in courses" :key="c.id" :label="c.name" :value="c.id" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="5">
              <el-form-item label="章节">
                <el-select v-model="form.chapter_id" clearable style="width:100%">
                  <el-option v-for="ch in chapters" :key="ch.id" :label="ch.name" :value="ch.id" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="5">
              <el-form-item label="题型">
                <el-select v-model="form.type" :disabled="!isNew" style="width:100%" @change="onTypeChange">
                  <el-option v-for="t in types" :key="t.value" :label="t.label" :value="t.value" />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="6"><el-form-item label="满分"><el-input-number v-model="form.max_score" :min="0.5" :max="100" :precision="1" style="width:100%" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="认知层级">
              <el-select v-model="form.cognitive_level" style="width:100%">
                <el-option v-for="(l,k) in COGNITIVE_LABELS" :key="k" :label="l" :value="k" />
              </el-select>
            </el-form-item></el-col>
            <el-col :span="5"><el-form-item label="难度(a)"><el-input-number v-model="form.difficulty" :min="-3" :max="3" :step="0.1" style="width:100%" /></el-form-item></el-col>
            <el-col :span="5"><el-form-item label="区分度"><el-input-number v-model="form.discrimination" :min="0.2" :max="3" :step="0.1" style="width:100%" /></el-form-item></el-col>
          </el-row>
          <el-form-item label="题干/场景">
            <el-input v-model="form.title" type="textarea" :rows="3" placeholder="选择题可将选项写在题干内；主观题写出完整问题情境" />
          </el-form-item>
        </el-form>
      </div>
    </div>

    <!-- 答案与判分配置 -->
    <div class="card" v-if="form.type">
      <div class="block-title">答案与判分配置</div>
      <div v-if="published" class="readonly-json mono">{{ JSON.stringify(formAC, null, 2) }}</div>

      <div v-else>
        <!-- 单选题 -->
        <el-form v-if="form.type === 'single_choice'" label-width="120px" label-position="left">
          <el-form-item label="选项(每行一个)">
            <el-input v-model="ui.optionsText" type="textarea" :rows="5" placeholder="A. 速度&#10;B. 时间&#10;C. 温度&#10;D. 路程" />
          </el-form-item>
          <el-form-item label="正确答案">
            <el-select v-model="ui.correctLetter" style="width:120px">
              <el-option v-for="L in 'ABCDEFGH'.split('')" :key="L" :label="L" :value="L" />
            </el-select>
          </el-form-item>
        </el-form>

        <!-- 多选题 -->
        <el-form v-else-if="form.type === 'multiple_choice'" label-width="120px" label-position="left">
          <el-form-item label="选项(每行一个)">
            <el-input v-model="ui.optionsText" type="textarea" :rows="5" placeholder="A. xxx&#10;B. xxx" />
          </el-form-item>
          <el-form-item label="正确答案(多选)">
            <el-checkbox-group v-model="ui.correctLetters">
              <el-checkbox v-for="L in 'ABCDEFGH'.split('')" :key="L" :value="L">{{ L }}</el-checkbox>
            </el-checkbox-group>
          </el-form-item>
          <el-form-item label="计分模式">
            <el-radio-group v-model="ui.scoringMode">
              <el-radio value="partial">部分得分(漏选/误选按比例)</el-radio>
              <el-radio value="full">全对才得分</el-radio>
            </el-radio-group>
          </el-form-item>
        </el-form>

        <!-- 判断题 -->
        <el-form v-else-if="form.type === 'true_false'" label-width="120px" label-position="left">
          <el-form-item label="正确答案">
            <el-radio-group v-model="ui.tf">
              <el-radio :value="true">正确</el-radio>
              <el-radio :value="false">错误</el-radio>
            </el-radio-group>
          </el-form-item>
        </el-form>

        <!-- 填空题 -->
        <el-form v-else-if="form.type === 'fill_blank'" label-width="120px" label-position="left">
          <el-form-item label="填空配置">
            <p class="hint">每行一个空；同一空可用“|”分隔多个可接受答案，如 <span class="mono">ma|m*a|m·a</span></p>
            <el-input v-model="ui.blankLines" type="textarea" :rows="4" />
          </el-form-item>
          <el-form-item label="顺序">
            <el-switch v-model="ui.order" active-text="顺序敏感" inactive-text="顺序无关" />
          </el-form-item>
        </el-form>

        <!-- 数值题 -->
        <el-form v-else-if="form.type === 'numeric'" label-width="120px" label-position="left" class="grid-form">
          <el-form-item label="标准值"><el-input-number v-model="ui.value" :precision="3" /></el-form-item>
          <el-form-item label="绝对容差"><el-input-number v-model="ui.tolAbs" :min="0" :precision="3" /></el-form-item>
          <el-form-item label="单位"><el-input v-model="ui.unit" style="width:150px" placeholder="如 m/s^2, J, N" /></el-form-item>
          <el-form-item label="缺单位保留"><el-input-number v-model="ui.unitCredit" :min="0" :max="1" :step="0.1" /></el-form-item>
          <el-form-item label="有效数字"><el-input-number v-model="ui.sig" :min="1" :max="9" /></el-form-item>
          <el-form-item label="相对容差"><el-input-number v-model="ui.tolRel" :min="0" :precision="3" /></el-form-item>
          <p class="hint full">单位缺省时将进行纯数值比对；单位可识别时会做量纲换算(见引擎单位族)。</p>
        </el-form>

        <!-- 口语题: 术语库 -->
        <el-form v-else-if="form.type === 'spoken'" label-width="120px" label-position="left">
          <el-form-item label="课程术语库">
            <p class="hint">表达层术语词典(逗号分隔)。示例：加速度, 合外力, 成正比, 惯性</p>
            <el-input v-model="ui.termText" type="textarea" :rows="3" />
          </el-form-item>
        </el-form>

        <!-- 公式符号化题(M12) -->
        <el-form v-else-if="form.type === 'formula'" label-width="120px" label-position="left">
          <el-form-item label="标准公式">
            <el-input v-model="ui.formulaExpected" style="width:380px" placeholder="如 F/m、a=(x+y)^2/m"
                      @change="(v) => (ui.formulaExpected = (v || '').replace(/[×·]/g, '*').replace(/÷/g, '/'))" />
            <p class="hint">学生作答将做“符号化简等价 / 数值抽样等价”判定：支持 + - * / ^、×·÷、上标；等价给满分，不等价不给分，空答转人工。</p>
          </el-form-item>
          <el-form-item label="变量数值域">
            <el-input v-model="ui.formulaVarsText" type="textarea" :rows="4" placeholder="每行：字母|min|max&#10;F|1|12&#10;m|1|12"
                      style="width:380px" />
            <p class="hint">抽样判分按该域取随机点。未列出的自由字母自动取默认 [-10,10]；无需变量(常数式)可留空。</p>
          </el-form-item>
        </el-form>
      </div>
    </div>

    <!-- 参考答案(主观/口语) -->
    <div class="card" v-if="['subjective_text', 'spoken'].includes(form.type)">
      <div class="block-title">参考答案(供判点与模型提示)</div>
      <el-input v-model="form.reference_answer" type="textarea" :rows="4" :disabled="published"
                placeholder="写出完整/规范的参考答案" />
    </div>

    <!-- 得分点量规(主观/口语/视频) -->
    <div class="card" v-if="['subjective_text', 'spoken', 'practical_video'].includes(form.type)">
      <div class="block-title">得分点量规</div>
      <div v-if="templates.length" class="tpl-row">
        <el-select v-model="templateSel" placeholder="从量规模板套用(覆盖当前列表)" clearable size="small"
                   style="width:320px" :disabled="published" @change="applyTemplate">
          <el-option v-for="t in templates" :key="t.id" :label="`${t.name}（${t.point_count} 点 / ${t.total_score} 分）`" :value="t.id" />
        </el-select>
        <span class="muted small-text">套用后会按模板填充得分点，可继续手动编辑。</span>
      </div>
      <div class="rubric-head row">
        <span class="col w60">编号</span><span class="col flex">得分点描述</span>
        <span class="col w90">分值</span><span class="col flex2">关键词(逗号分隔，用于证据召回)</span>
        <span class="col w40"></span>
      </div>
      <div v-for="(r, i) in rubricRows" :key="i" class="row rubric-row">
        <span class="col w60 mono">P{{ i + 1 }}</span>
        <el-input v-model="r.description" class="col flex" placeholder="该得分点的判定标准" :disabled="published" />
        <el-input-number v-model="r.score" class="col w90" :min="0" :precision="1" :disabled="published" />
        <el-input v-model="r.keywords" class="col flex2" placeholder="如: 受力分析, 摩擦力" :disabled="published" />
        <el-button class="col w40" link type="danger" :disabled="published" @click="rubricRows.splice(i, 1)">删</el-button>
      </div>
      <el-button text type="primary" :disabled="published" @click="rubricRows.push({ description: '', score: 1, keywords: '' })">
        + 增加得分点
      </el-button>
    </div>

    <!-- 评分策略 -->
    <div class="card" v-if="['subjective_text', 'spoken', 'practical_video'].includes(form.type)">
      <div class="block-title">评分策略</div>
      <el-form label-width="140px" label-position="left" :disabled="published">
        <el-form-item label="复核阈值(置信度)">
          <el-input-number v-model="policy.review_threshold" :min="0" :max="1" :step="0.01" />
          <span class="hint inline">低于该置信度转强制复核</span>
        </el-form-item>
        <el-form-item v-if="form.type === 'subjective_text'" label="自动放行">
          <el-switch v-model="policy.auto_release" active-text="高置信度自动放行" />
        </el-form-item>
        <el-form-item v-if="form.type === 'subjective_text'" label="罚分项">
          <p class="hint">每行一条：“原因|最大扣分”，例如 单位错误|0.5</p>
          <el-input v-model="policy.penaltyText" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
    </div>

    <!-- 知识节点与 Q 矩阵 -->
    <div class="card">
      <div class="block-title">知识节点与能力维度映射(Q 矩阵)</div>
      <el-form label-width="120px" label-position="left" :disabled="published">
        <el-form-item label="考查知识节点">
          <el-select v-model="form.knowledge_nodes" multiple filterable style="width:100%">
            <el-option-group v-for="ch in chapterTree" :key="ch.id" :label="ch.name">
              <el-option v-for="n in ch.nodes" :key="n.code" :label="`${n.code} ${n.name}`" :value="n.code" />
            </el-option-group>
          </el-select>
        </el-form-item>
      </el-form>
      <el-table :data="nodeRows" size="small" border style="width:100%" v-if="nodeRows.length">
        <el-table-column label="知识节点" prop="code" width="200" />
        <el-table-column label="能力维度(二级)" min-width="260">
          <template #default="{ row }">
            <el-select v-model="row.dimension" filterable placeholder="选择能力维度" style="width:100%">
              <el-option-group v-for="d in dimDomains" :key="d.code" :label="`${d.name} (${d.code})`">
                <el-option v-for="m in d.dimensions" :key="m.code" :label="`${m.code} · ${m.name}`" :value="m.code" />
              </el-option-group>
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="权重" width="130">
          <template #default="{ row }">
            <el-input-number v-model="row.weight" :min="0.1" :step="0.1" :precision="1" size="small" />
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'
import { getItem, createItem, updateItem, publishItem, itemTypes, listCourses, courseKnowledge, listDimensions, listRubricTemplates } from '@/api'
import { COGNITIVE_LABELS, ITEM_TYPE_LABELS } from '@/utils/const'

const route = useRoute()
const router = useRouter()
const isNew = route.params.id === 'new' || route.name === 'item-new'
const itemId = isNew ? null : Number(route.params.id)

const loading = ref(false)
const saving = ref(false)
const publishing = ref(false)
const types = ref([])
const courses = ref([])
const chapters = ref([])
const chapterTree = ref([])
const dimDomains = ref([])
const templates = ref([])
const templateSel = ref(null)
const published = ref(false)

const form = reactive({
  code: '', type: '', course_id: null, chapter_id: null, title: '', max_score: 10,
  cognitive_level: 'apply', difficulty: 0, discrimination: 1,
  reference_answer: '', knowledge_nodes: [], current_version: 1,
})
// 题型相关
const ui = reactive({
  optionsText: '', correctLetter: 'A', correctLetters: [], scoringMode: 'full', tf: true,
  blankLines: '', order: true, value: 5, tolAbs: 0.1, tolRel: null, unit: 'm/s^2',
  unitCredit: 0.3, sig: null, termText: '',
  formulaExpected: '', formulaVarsText: '',
})
const rubricRows = ref([])
const RUBRIC_TYPES = ['subjective_text', 'spoken', 'practical_video']
const hasRubric = computed(() => RUBRIC_TYPES.includes(form.type))
const policy = reactive({ review_threshold: 0.72, auto_release: false, penaltyText: '',
                          review_mode: 'single', require_double_publish: false })
const nodeRows = ref([])

const typeLabel = computed(() => ITEM_TYPE_LABELS[form.type] || form.type)

function blankAC(type) {
  const m = {
    single_choice: { correct: 'A', options: [] },
    multiple_choice: { correct: ['A'], scoring_mode: 'full', options: [] },
    true_false: { correct: true },
    fill_blank: { blanks: [], order_matters: true },
    numeric: { answer: { value: 0, tolerance_abs: 0.1, unit: 'm/s^2', unit_credit: 0.3 } },
    spoken: { term_bank: [] },
    formula: { formula: { expected: '', variables: [] } },
    subjective_text: {}, practical_video: {},
  }
  return JSON.parse(JSON.stringify(m[type] || {}))
}
function fillUiFromAC(ac, type) {
  Object.assign(ui, {
    optionsText: '', correctLetter: 'A', correctLetters: [], scoringMode: 'full', tf: true,
    blankLines: '', order: true, value: 5, tolAbs: 0.1, tolRel: null, unit: 'm/s^2',
    unitCredit: 0.3, sig: null, termText: '', formulaExpected: '', formulaVarsText: '',
  })
  if (!ac) return
  if (type === 'single_choice') {
    ui.correctLetter = (ac.correct || 'A').toString().toUpperCase()
    ui.optionsText = (ac.options || []).join('\n')
  } else if (type === 'multiple_choice') {
    ui.correctLetters = (ac.correct || []).map(String).map((s) => s.toUpperCase())
    ui.scoringMode = ac.scoring_mode || 'full'
    ui.optionsText = (ac.options || []).join('\n')
  } else if (type === 'true_false') {
    ui.tf = !!ac.correct
  } else if (type === 'fill_blank') {
    ui.order = ac.order_matters !== false
    ui.blankLines = (ac.blanks || []).map((b) => (Array.isArray(b.value) ? b.value.join('|') : (b.value || ''))).join('\n')
  } else if (type === 'numeric') {
    const a = ac.answer || {}
    ui.value = a.value ?? 0
    ui.tolAbs = a.tolerance_abs ?? null
    ui.tolRel = a.tolerance_rel ?? null
    ui.unit = a.unit || ''
    ui.unitCredit = a.unit_credit ?? 0.3
    ui.sig = a.significant_digits ?? null
  } else if (type === 'spoken') {
    ui.termText = (ac.term_bank || []).join(', ')
  } else if (type === 'formula') {
    const f = (ac.formula || {})
    ui.formulaExpected = f.expected || ''
    ui.formulaVarsText = (f.variables || []).map((v) => `${v.name}|${v.min}|${v.max}`).join('\n')
  }
}
function buildAC() {
  const t = form.type
  if (t === 'single_choice') return { correct: ui.correctLetter, options: splitLines(ui.optionsText) }
  if (t === 'multiple_choice') return { correct: ui.correctLetters, scoring_mode: ui.scoringMode, options: splitLines(ui.optionsText) }
  if (t === 'true_false') return { correct: ui.tf }
  if (t === 'fill_blank') {
    const blanks = ui.blankLines.split('\n').filter((s) => s.trim() !== '').map((s) => {
      const parts = s.split('|').map((x) => x.trim()).filter(Boolean)
      return { value: parts.length === 1 ? parts[0] : parts }
    })
    return { blanks, order_matters: ui.order }
  }
  if (t === 'numeric') {
    const a = { value: ui.value }
    if (ui.tolAbs !== null && ui.tolAbs !== undefined) a.tolerance_abs = ui.tolAbs
    if (ui.tolRel !== null && ui.tolRel !== undefined) a.tolerance_rel = ui.tolRel
    if (ui.unit) a.unit = ui.unit
    a.unit_credit = ui.unitCredit
    if (ui.sig) a.significant_digits = ui.sig
    return { answer: a }
  }
  if (t === 'spoken') {
    return { term_bank: splitTerms(ui.termText) }
  }
  if (t === 'formula') {
    const variables = splitLines(ui.formulaVarsText).map((line) => {
      const p = line.split('|').map((x) => x.trim())
      const name = (p[0] || '').trim()
      if (!name) return null
      const lo = p[1] === undefined || p[1] === '' ? null : Number(p[1])
      const hi = p[2] === undefined || p[2] === '' ? null : Number(p[2])
      return { name, min: (lo === null || Number.isNaN(lo)) ? -10 : lo, max: (hi === null || Number.isNaN(hi)) ? 10 : hi }
    }).filter(Boolean)
    return { formula: { expected: ui.formulaExpected.trim(), variables } }
  }
  return {}
}
// 已发布只读展示由 formAC 提供; 未发布时保存使用 buildAC()
const formAC = ref({})

function splitLines(s) {
  return (s || '').split('\n').map((x) => x.trim()).filter(Boolean)
}
function splitTerms(s) {
  return (s || '').split(/[,，、;；]/).map((x) => x.trim()).filter(Boolean)
}
function parsePenalties(text) {
  const out = []
  for (const line of (text || '').split('\n')) {
    const s = line.trim()
    if (!s) continue
    const m = s.split('|')
    const reason = (m[0] || '').trim()
    const max = parseFloat(m[1])
    if (reason && !Number.isNaN(max)) out.push({ reason, max })
  }
  return out
}

watch(() => [...form.knowledge_nodes], (codes) => {
  const existing = new Map(nodeRows.value.map((r) => [r.code, r]))
  nodeRows.value = codes.map((c) => existing.get(c) || { code: c, dimension: '', weight: 1 })
})

function buildPayload() {
  const qm = {}
  const qmArr = nodeRows.value.filter((r) => r.code && r.dimension)
  for (const r of qmArr) qm[r.code] = { dimension: r.dimension, weight: Number(r.weight) || 1 }

  let ac = {}
  if (isNew) ac = buildAC()
  else {
    // 已发布原样保留; 未发布按 UI 重建
    ac = published.value ? (formAC.value || {}) : buildAC()
  }

  const rubric = rubricRows.value
    .filter((r) => (r.description || '').trim())
    .map((r, i) => ({
      point_id: `P${i + 1}`,
      description: r.description.trim(),
      score: Number(r.score) || 0,
      keywords: splitTerms(r.keywords),
    }))

  const penalties = policy.penaltyText ? parsePenalties(policy.penaltyText) : []
  const sp = {
    review_threshold: Number(policy.review_threshold) || 0.7,
  }
  if (penalties.length) sp.penalties = penalties
  if (form.type === 'subjective_text' && policy.auto_release) sp.auto_release = true
  if (hasRubric.value && policy.review_mode === 'double') sp.review_mode = 'double'
  if (policy.require_double_publish) sp.require_double_publish = true

  return {
    code: form.code.trim() || null, type: form.type, title: form.title,
    course_id: form.course_id, chapter_id: form.chapter_id || null,
    max_score: Number(form.max_score) || 1, cognitive_level: form.cognitive_level,
    answer_config: ac, rubric, reference_answer: form.reference_answer,
    knowledge_nodes: [...form.knowledge_nodes], q_matrix: qm,
    scoring_policy: sp, difficulty: form.difficulty, discrimination: form.discrimination,
  }
}

async function save(doPublish) {
  const payload = buildPayload()
  if (!payload.type || !payload.title.trim()) {
    ElMessage.warning('请选择题型并填写题干')
    return
  }
  if (payload.course_id == null) {
    ElMessage.warning('请选择所属课程')
    return
  }
  if (payload.type === 'practical_video' && payload.rubric.length === 0) {
    ElMessage.warning('实操视频题需先按步骤填写量规，供人工评阅')
    return
  }
  saving.value = true
  try {
    let row
    if (isNew) row = await createItem(payload)
    else if (!published.value) row = await updateItem(itemId, payload)
    if (doPublish) {
      publishing.value = true
      // 已发布内容锁定: 直接“修订发布”固化新快照(升版本, 历史成绩不回写)
      if (!isNew && published.value) row = await publishItem(itemId)
      else row = await publishItem(row.id)
      if (row.publish_pending) {
        ElMessage.warning(row.message || `待复核：已登记 ${row.approvals_received}/${row.approvals_needed} 个账号，需另一账号复核后发布`)
      } else {
        ElMessage.success(row.message || '已发布并固化为版本快照')
      }
    } else {
      ElMessage.success('已保存')
    }
    router.replace(`/items/${row.id}`)
    await load()
  } catch (e) { /* 拦截器提示 */ } finally {
    saving.value = false
    publishing.value = false
  }
}

async function loadTemplates(cid) {
  const res = await listRubricTemplates({ course_id: cid || undefined })
  templates.value = (res.items || []).filter((t) => t.enabled)
}
function applyTemplate(id) {
  if (!id) return
  const t = templates.value.find((x) => x.id === id)
  if (!t || !t.rubric?.length) return
  rubricRows.value = t.rubric
    .filter((p) => (p.description || '').trim())
    .map((p) => ({ description: p.description.trim(), score: Number(p.score ?? p.max ?? 1),
                   keywords: (p.keywords || []).map(String).join(', ') }))
  ElMessage.success(`已套用模板「${t.name}」(${rubricRows.value.length} 个得分点)`)
  templateSel.value = null
}
function onCourseChange(cid) {
  form.chapter_id = null
  if (!cid) { chapters.value = []; chapterTree.value = [] }
  loadKnowledge(cid)
  loadTemplates(cid)
}
function onTypeChange(t) {
  fillUiFromAC(blankAC(t), t)
  rubricRows.value = [{ description: '', score: 1, keywords: '' }]
  const hasRubric = ['subjective_text', 'spoken', 'practical_video'].includes(t)
  if (!hasRubric) rubricRows.value = []
}
async function loadKnowledge(cid) {
  if (!cid) return
  const res = await courseKnowledge(cid)
  chapters.value = res.chapters || []
  chapterTree.value = res.chapters || []
}

async function load() {
  loading.value = true
  try {
    const cs = await listCourses()
    courses.value = cs.items || []
    const it = await itemTypes()
    types.value = it.types || []
    const dims = await listDimensions()
    dimDomains.value = dims.domains || []
    if (isNew) {
      if (courses.value.length) {
        form.course_id = courses.value[0].id
        await loadKnowledge(form.course_id)
      }
      form.type = 'single_choice'
      policy.review_mode = 'single'
      policy.require_double_publish = false
      onTypeChange('single_choice')
      if (form.course_id) await loadTemplates(form.course_id)
      return
    }
    const row = await getItem(itemId)
    published.value = row.published
    Object.assign(form, {
      code: row.code, type: row.type, course_id: row.course_id, chapter_id: row.chapter_id,
      title: row.title, max_score: row.max_score, cognitive_level: row.cognitive_level,
      difficulty: row.difficulty, discrimination: row.discrimination,
      reference_answer: row.reference_answer, knowledge_nodes: row.knowledge_nodes || [],
      current_version: row.current_version || 1,
    })
    formAC.value = row.answer_config || {}
    // 读入各编辑模型
    fillUiFromAC(row.answer_config || {}, row.type)
    rubricRows.value = (row.rubric || []).map((p) => ({
      description: p.description || '', score: p.score || p.max || 1,
      keywords: (p.keywords || []).join(', '),
    }))
    const sp = row.scoring_policy || {}
    policy.review_threshold = sp.review_threshold ?? 0.72
    policy.auto_release = !!sp.auto_release
    policy.penaltyText = (sp.penalties || []).map((p) => `${p.reason}|${p.max}`).join('\n')
    policy.review_mode = sp.review_mode || 'single'
    policy.require_double_publish = !!sp.require_double_publish
    await loadTemplates(row.course_id)
    // 章节与知识树
    await loadKnowledge(row.course_id)
  } finally {
    loading.value = false
  }
}
onMounted(load)
</script>

<style scoped>
.topbar { display: flex; align-items: center; }
.back { cursor: pointer; color: #409eff; margin-right: 18px; display: inline-flex; align-items: center; font-size: 14px; }
.title-line { display: flex; gap: 8px; align-items: center; margin-right: auto; }
.title-line h3 { margin: 0; }
.actions { display: flex; gap: 6px; }
.pub-alert { margin-top: 12px; }
.block-title { font-weight: 600; margin: 0 0 12px; }
.form-grid { max-width: 1100px; }
.row { display: flex; align-items: center; gap: 8px; }
.rubric-head { font-size: 12px; color: #909399; padding: 0 2px 6px; }
.rubric-row { margin-bottom: 8px; }
.col.flex { flex: 1.2; } .col.flex2 { flex: 1.6; }
.col.w60 { width: 60px; flex: none; } .col.w40 { width: 40px; flex: none; }
.col.w90 { width: 90px; flex: none; }
.hint { font-size: 12px; color: #909399; margin: 2px 0; width: 100%; }
.hint.inline { margin-left: 10px; }
.hint.full { width: 100%; }
.readonly-json { background: #f6f8fa; padding: 10px; border-radius: 6px; }
.mono { font-family: Consolas, Menlo, monospace; font-size: 12px; }
.tpl-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 10px; }
.small-text { font-size: 12px; }
</style>
