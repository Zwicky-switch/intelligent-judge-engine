<template>
  <div class="page">
    <div class="card" v-loading="loading">
      <div class="dash-title">
        <div>
          <h3>评阅质量看板</h3>
          <p class="muted small-text">模型 {{ t.model_version || '—' }} · 评阅引擎：{{ PROVIDER_LABEL_OF(t.llm_provider) }}</p>
        </div>
        <el-button :icon="Refresh" circle @click="load" />
      </div>

      <div class="stat-grid">
        <div class="stat-card"><div class="lbl">答卷总数</div><div class="num">{{ t.totals?.answers ?? 0 }}</div></div>
        <div class="stat-card"><div class="lbl">自动放行(客观)</div><div class="num" style="color:#18a058">{{ t.totals?.auto_passed ?? 0 }}</div></div>
        <div class="stat-card"><div class="lbl">待人工复核</div><div class="num" style="color:#f0a020">{{ t.totals?.needs_review ?? 0 }}</div></div>
        <div class="stat-card"><div class="lbl">教师已终审</div><div class="num" style="color:#409eff">{{ t.totals?.reviewed ?? 0 }}</div></div>
        <div class="stat-card"><div class="lbl">自动放行率</div><div class="num">{{ fmtPct(t.auto_release_rate) }}</div></div>
        <div class="stat-card"><div class="lbl">教师终审率</div><div class="num">{{ fmtPct(t.review_rate) }}</div></div>
        <div class="stat-card"><div class="lbl">平均得分率</div><div class="num">{{ fmtPct(t.avg_ratio) }}</div></div>
      </div>
      <p class="muted note">{{ t.note }}</p>
      <div class="stat-grid health">
        <div class="stat-card"><div class="lbl">平均判分耗时</div><div class="num small-num">{{ fmtMs(lat.avg) }}</div></div>
        <div class="stat-card"><div class="lbl">P95 判分耗时</div><div class="num small-num">{{ fmtMs(lat.p95) }}</div></div>
        <div class="stat-card"><div class="lbl">存量分数重放一致率</div>
          <div class="num" :style="{ color: guardColor }">{{ fmtPct(guard.accuracy) }}</div>
          <div class="lbl" style="font-size:11px">重放样本 {{ guard.checked ?? 0 }} · 不一致 {{ guard.misgraded ?? 0 }}</div>
        </div>
        <div class="stat-card"><div class="lbl">引擎↔教师 ±1分一致率</div><div class="num" style="color:#18a058">{{ fmtPct(consistency.overall) }}</div>
          <div class="lbl" style="font-size:11px">样本 {{ consistency.n ?? 0 }}</div>
        </div>
        <div class="stat-card"><div class="lbl">双评教师一致率(±1分)</div><div class="num" style="color:#409eff">{{ fmtPct(t.teacher_consistency?.within_1pt_rate) }}</div>
          <div class="lbl" style="font-size:11px">完成对 {{ t.teacher_consistency?.pairs ?? 0 }} · 平均差 {{ fmtMs0(t.teacher_consistency?.mean_abs_diff) }} 分</div>
        </div>
      </div>
    </div>

    <el-row :gutter="16">
      <el-col :xs="24" :md="12">
        <div class="card"><div class="block-title">得分率分布</div>
          <EChart :option="distOpt" height="300px" /></div>
      </el-col>
      <el-col :xs="24" :md="12">
        <div class="card"><div class="block-title">班级能力画像(六域均值)</div>
          <EChart :option="radarOpt" height="300px" /></div>
      </el-col>
    </el-row>

    <div class="card">
      <div class="block-title">题目表现(按答题量)</div>
      <el-table :data="t.by_item || []" size="small" border style="width:100%">
        <el-table-column prop="code" label="题号" width="130" />
        <el-table-column prop="title" label="题干" min-width="180" show-overflow-tooltip />
        <el-table-column prop="type_label" label="题型" width="110" />
        <el-table-column label="作答数" width="90" prop="answers" />
        <el-table-column label="平均得分率" width="120">
          <template #default="{ row }">
            <el-progress :percentage="Math.round((row.avg_ratio ?? 0) * 100)" :stroke-width="12" />
          </template>
        </el-table-column>
        <el-table-column label="待复核" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.needs_review" type="warning" size="small">{{ row.needs_review }} 份</el-tag>
            <span v-else class="muted">0</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-row :gutter="16">
      <el-col :xs="24" :md="12">
        <div class="card">
          <div class="block-title">引擎↔教师一致性(已终审样本, ±1 分容差)</div>
          <el-table :data="consistencyRows" size="small" border style="width:100%">
            <el-table-column prop="type_label" label="题型" min-width="120" />
            <el-table-column prop="n" label="样本" width="80" />
            <el-table-column label="平均绝对差(分)" width="130">
              <template #default="{ row }">{{ row.mean_abs_diff ?? '—' }}</template>
            </el-table-column>
            <el-table-column label="±1 分一致率" width="130">
              <template #default="{ row }">
                <el-tag :type="(row.within_1pt_rate ?? 0) >= 0.8 ? 'success' : 'warning'" size="small">{{ fmtPct(row.within_1pt_rate) }}</el-tag>
              </template>
            </el-table-column>
          </el-table>
          <p class="muted note">{{ consistency.note }}</p>
          <div class="sub-block">
            <div class="block-title" style="margin:4px 0 8px">双评教师间一致性</div>
            <div v-if="(t.teacher_consistency?.pairs ?? 0) > 0">
              <el-tag type="success" size="small">±1 分一致率 {{ fmtPct(t.teacher_consistency.within_1pt_rate) }}</el-tag>
              <span class="muted" style="margin-left:10px">完成对 {{ t.teacher_consistency.pairs }} · 平均绝对差 {{ t.teacher_consistency.mean_abs_diff }} 分</span>
            </div>
            <div v-else class="muted small-text">{{ t.teacher_consistency?.note || '暂无双评完成对' }}</div>
          </div>
        </div>
      </el-col>
      <el-col :xs="24" :md="12">
        <div class="card">
          <div class="block-title">延迟与客观题存量重放</div>
          <el-descriptions :column="2" size="small" border>
            <el-descriptions-item label="平均耗时">{{ fmtMs(lat.avg) }}</el-descriptions-item>
            <el-descriptions-item label="P95">{{ fmtMs(lat.p95) }}</el-descriptions-item>
            <el-descriptions-item label="最大">{{ fmtMs(lat.max) }}</el-descriptions-item>
            <el-descriptions-item label="样本">{{ lat.n ?? 0 }}</el-descriptions-item>
          </el-descriptions>
          <div class="guard-box" :class="guardClass">
            <div class="guard-head">
              <span>客观题存量重放</span>
              <b :style="{ color: guardColor }">{{ fmtPct(guard.accuracy) }}</b>
            </div>
            <p class="small-text">已核对 <b>{{ guard.checked ?? 0 }}</b> 份自动放行客观分, 重放判分与存量总分不一致 <b>{{ guard.misgraded ?? 0 }}</b> 份。</p>
            <p class="small-text">{{ guard.note }}</p>
          </div>
        </div>
      </el-col>
    </el-row>

    <div class="card">
      <div class="block-title">分数段校准(教师终审 − 引擎分, 按引擎得分率分档)</div>
      <el-row :gutter="16">
        <el-col :xs="24" :md="14">
          <el-table :data="t.calibration?.per_band || []" size="small" border style="width:100%">
            <el-table-column prop="band" label="得分率段" width="110" />
            <el-table-column prop="n" label="样本" width="80" />
            <el-table-column label="平均偏移(分)" width="130">
              <template #default="{ row }">
                <span v-if="row.offset === null || row.offset === undefined" class="muted">—</span>
                <b v-else :style="{ color: row.offset > 0.05 ? '#18a058' : (row.offset < -0.05 ? '#f0a020' : '#909399') }">
                  {{ row.offset > 0 ? '+' : '' }}{{ row.offset }}
                </b>
              </template>
            </el-table-column>
            <el-table-column label="提示" min-width="120">
              <template #default="{ row }">
                <el-tag v-if="row.flag" type="danger" size="small">需人工校准</el-tag>
                <span v-else class="muted">正常</span>
              </template>
            </el-table-column>
          </el-table>
        </el-col>
        <el-col :xs="24" :md="10">
          <p class="small-text" style="line-height:1.9">
            温度拟合 <b>teacher ≈ {{ temp.a ?? '—' }} × engine {{ (temp.b ?? 0) >= 0 ? '+' : '−' }}{{ fmtMs0(Math.abs(temp.b ?? 0)) }}</b>
            <span class="muted">(R²={{ temp.r2 ?? '—' }}, n={{ temp.n ?? 0 }})</span>
          </p>
          <p class="small-text muted" style="line-height:1.7">{{ tempMeaning }}</p>
          <div v-if="(t.calibration?.flagged_bands || []).length" class="small-text" style="line-height:2">
            需关注段：
            <el-tag v-for="b in t.calibration.flagged_bands" :key="b" type="danger" size="small" style="margin-right:6px">{{ b }}</el-tag>
          </div>
          <div v-else class="small-text muted">所有分数段偏移在阈值内, 当前无需人工校准。</div>
          <p class="muted note">{{ t.calibration?.note }}</p>
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { qualityMetrics } from '@/api'
import EChart from '@/components/EChart.vue'
import { DOMAIN_LABELS, PROVIDER_LABEL_OF, fmtPct } from '@/utils/const'

const loading = ref(false)
const t = reactive({})

const DOMAIN_ORDER = ['domain_knowledge', 'domain_problem', 'domain_practice', 'domain_expression', 'domain_critical', 'domain_transfer']

const lat = computed(() => t.latency_ms || {})
const guard = computed(() => t.objective_accuracy_guard || {})
const consistency = computed(() => t.consistency || {})
const consistencyRows = computed(() => Object.values(consistency.value.by_type || {}))
const temp = computed(() => t.calibration?.temperature || {})
const guardColor = computed(() => {
  const a = guard.value.accuracy
  if (a === null || a === undefined) return '#909399'
  return a >= 0.98 ? '#18a058' : a >= 0.9 ? '#e6a23c' : '#f56c6c'
})
const guardClass = computed(() => guard.value.accuracy >= 0.98 ? 'ok' : (guard.value.accuracy >= 0.9 ? 'mid' : 'bad'))
const tempMeaning = computed(() => {
  const a = temp.value.a
  if (a === null || a === undefined) return '暂无足够终审样本拟合温度(至少 2 份已终审答卷)。'
  const slope = Math.abs(a - 1) < 0.05 ? '引擎与教师同量纲, 校准良好' : (a > 1 ? '教师给分整体高于引擎(引擎偏严)' : '引擎给分整体高于教师(引擎偏松)')
  const r2 = temp.value.r2
  const fit = (r2 ?? 0) >= 0.5 ? '线性拟合解释力较强(R² 较高)' : '拟合解释力有限, 受题型差异影响'
  return `${slope}; ${fit}。`
})
const fmtMs = (v) => (v === null || v === undefined ? '—' : `${Math.round(v)} ms`)
const fmtMs0 = (v) => (v === null || v === undefined ? '—' : Number(v).toFixed(2))

async function load() {
  loading.value = true
  try {
    const res = await qualityMetrics()
    Object.assign(t, res)
  } finally {
    loading.value = false
  }
}

const distOpt = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 40, right: 16, top: 24, bottom: 30 },
  xAxis: { type: 'category', data: (t.distribution || []).map((d) => d.bin), axisLabel: { fontSize: 11 } },
  yAxis: { type: 'value', minInterval: 1 },
  series: [{ type: 'bar', data: (t.distribution || []).map((d) => d.count), barWidth: 40,
    itemStyle: { color: '#409eff', borderRadius: [4, 4, 0, 0] },
    label: { show: true, position: 'top' } }],
}))

const radarOpt = computed(() => {
  const ca = t.class_ability || {}
  return {
    tooltip: {},
    radar: { indicator: DOMAIN_ORDER.map((c) => ({ name: DOMAIN_LABELS[c], min: 0, max: 100 })),
      radius: '62%' },
    series: [{
      type: 'radar',
      data: [{ value: DOMAIN_ORDER.map((c) => Math.round((ca[c] ?? 0) * 100)), name: '班级平均',
        areaStyle: { opacity: .25 }, lineStyle: { width: 2, color: '#2f7cd6' } }],
    }],
  }
})
onMounted(load)
</script>

<style scoped>
.dash-title { display: flex; justify-content: space-between; align-items: flex-start; }
.dash-title h3 { margin: 0 0 4px; }
.small-text { font-size: 12px; }
.block-title { font-weight: 600; margin-bottom: 12px; }
.note { font-size: 12px; line-height: 1.6; margin: 12px 0 0; }
.health { margin-top: 14px; }
.small-num { font-size: 22px; }
.guard-box { margin-top: 12px; border: 1px solid #ebeef5; border-radius: 6px; padding: 10px 12px; background: #f6f8fa; }
.guard-box.ok { border-color: #b7eb8f; background: #f6ffed; }
.guard-box.mid { border-color: #ffe58f; background: #fffbe6; }
.guard-box.bad { border-color: #ffa39e; background: #fff1f0; }
.guard-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.sub-block { margin-top: 14px; border-top: 1px dashed #e0e0e0; padding-top: 12px; }
</style>
