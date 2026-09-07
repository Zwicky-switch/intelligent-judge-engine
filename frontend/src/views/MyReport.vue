<template>
  <div class="page" v-loading="loading">
    <div class="card" v-if="report">
      <div class="head">
        <div>
          <h3>{{ report.course_name }} · 能力诊断报告</h3>
          <p class="muted small-text">
            学生：{{ report.student_name }} · 观测题目 {{ report.observed }} · 全局置信度 {{ fmtPct(report.confidence) }}
            · IRT θ {{ report.theta === null || report.theta === undefined ? '—' : report.theta.toFixed(2) }}
          </p>
          <div class="meta-tags">
            <el-tag v-if="pm" size="small" type="success" effect="light">画像-作答匹配度 {{ fmtPct(pm.value) }} <span class="mono tag-sub">n={{ pm.n }}</span></el-tag>
            <el-tag size="small" effect="plain">能力维度观测 {{ observedDimCount }}/60</el-tag>
            <el-tag v-if="activeBktCount" size="small" type="warning" effect="plain">BKT 激活 {{ activeBktCount }} 节点</el-tag>
            <span class="muted small-text">算法口径：{{ report.algorithm_detail || report.model_version }}</span>
          </div>
        </div>
        <el-button :icon="Refresh" circle @click="load" />
      </div>
    </div>

    <el-row :gutter="16" v-if="report">
      <el-col :xs="24" :md="11">
        <div class="card">
          <div class="block-title">六大能力域画像</div>
          <EChart :option="radarOpt" height="320px" />
          <p class="muted small-text">未观测到的能力域不参与评分(如实标注)，数据越多画像越可靠。</p>
        </div>
      </el-col>
      <el-col :xs="24" :md="13">
        <div class="card">
          <div class="block-title">掌握度短板 Top3</div>
          <div v-if="weakNodes.length" class="weak-list">
            <div v-for="w in weakNodes" :key="w.code" class="weak-item">
              <div class="weak-name">
                <el-tag type="danger" size="small">弱</el-tag>
                <b>{{ w.name }}</b>
                <span class="muted mono">{{ w.code }}</span>
              </div>
              <el-progress :percentage="Math.round(w.mastery * 100)" :stroke-width="14"
                           :color="w.mastery < 0.45 ? '#f56c6c' : '#e6a23c'" />
            </div>
          </div>
          <el-empty v-else :image-size="60" description="暂无显著短板，保持当前学习节奏" />

          <div class="block-title mt">建议与学习任务</div>
          <div v-if="(report.recommendations || []).length" class="rec-list">
            <div v-for="(r, i) in report.recommendations" :key="i" class="rec-item">
              <el-tag size="small" :type="recTag(r.type)" effect="dark">{{ recLabel(r.type) }}</el-tag>
              <div class="rec-body">
                <div class="rec-title">{{ r.title }}</div>
                <div class="muted small-text">{{ r.reason }}</div>
              </div>
              <el-tag size="small" :type="r.priority === 'high' ? 'danger' : 'warning'" effect="plain">{{ r.priority === 'high' ? '优先' : '建议' }}</el-tag>
            </div>
          </div>
          <el-empty v-else :image-size="60" description="暂无推荐任务" />
        </div>
      </el-col>
    </el-row>

    <!-- 知识节点掌握度热力图 -->
    <div class="card" v-if="report">
      <div class="block-title">知识节点掌握度热力图</div>
      <EChart v-if="heatCells.length" :option="heatOpt" height="340px" />
      <el-empty v-else :image-size="60" description="尚无已观测知识节点，先完成几道题即可点亮热力" />
      <p class="muted small-text">横轴为知识点、纵轴为章节；颜色越绿掌握度越高。尚未被观测的节点不填色，见下方节点表与 60 维全景。</p>
    </div>

    <!-- 60 维能力维度全景 -->
    <div class="card" v-if="report">
      <div class="block-title">能力维度全景(本轮已观测 {{ observedDimCount }}/60)</div>
      <div v-for="dom in DOMAIN_ORDER" :key="dom" class="dom-block">
        <div class="dom-head">
          <span class="dot" :style="{ background: DOMAIN_COLORS[dom] }" />
          <b>{{ dimGroupName(dom) }}</b>
          <span class="muted small-text">{{ dimsOf(dom).filter((d) => d.observed > 0).length }}/{{ dimsOf(dom).length }} 已观测</span>
        </div>
        <div class="dim-grid">
          <div v-for="d in dimsOf(dom)" :key="d.code" class="dim-cell" :class="{ off: !d.enabled, unseen: d.observed === 0 }">
            <div class="dim-top">
              <span class="dim-name" :title="`${d.code} · ${d.label}`">{{ d.label }}</span>
              <el-tag v-if="!d.enabled" type="info" size="small">课程停用</el-tag>
            </div>
            <template v-if="d.observed > 0 && d.enabled">
              <el-progress :percentage="Math.round(d.score * 100)" :stroke-width="8" :show-text="false"
                           :color="d.score < 0.45 ? '#f56c6c' : d.score < 0.7 ? '#e6a23c' : '#67c23a'" />
              <div class="dim-val">{{ (d.score * 100).toFixed(0) }}<span class="muted">/100</span></div>
            </template>
            <div v-else-if="d.observed === 0" class="dim-val muted">未观测</div>
          </div>
        </div>
      </div>
    </div>

    <div class="card" v-if="report">
      <div class="block-title">知识节点掌握度明细</div>
      <el-table :data="nodeRows" size="small" border style="width:100%">
        <el-table-column prop="chapter" label="章节" width="130" />
        <el-table-column label="知识节点" width="200">
          <template #default="{ row }"><span class="mono">{{ row.code }}</span> {{ row.name }}</template>
        </el-table-column>
        <el-table-column label="掌握度" min-width="190">
          <template #default="{ row }">
            <el-progress :percentage="Math.round(row.mastery * 100)" :stroke-width="16"
                         :color="row.mastery < 0.45 ? '#f56c6c' : row.mastery < 0.7 ? '#e6a23c' : '#67c23a'"
                         :format="() => `${(row.mastery * 100).toFixed(0)}%`" />
          </template>
        </el-table-column>
        <el-table-column label="BKT 掌握度" width="180">
          <template #default="{ row }">
            <template v-if="row.bkt && row.bkt.active && typeof row.bkt.mastery_after === 'number'">
              <div class="bkt-val">
                <b :style="{ color: row.bkt.mastery_after < 0.45 ? '#f56c6c' : row.bkt.mastery_after < 0.7 ? '#e6a23c' : '#67c23a' }">
                  {{ (row.bkt.mastery_after * 100).toFixed(0) }}%</b>
                <el-tag size="small" type="success">BKT 时序</el-tag>
              </div>
            </template>
            <span v-else class="muted small-text">{{ (row.bkt && row.bkt.n) ? `仅 ${row.bkt.n} 次观测, BKT 未激活` : '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="原始比例" width="80">
          <template #default="{ row }">{{ fmtPct(row.raw) }}</template>
        </el-table-column>
        <el-table-column label="置信度" width="80">
          <template #default="{ row }">{{ fmtPct(row.confidence) }}</template>
        </el-table-column>
        <el-table-column label="观测" width="70">
          <template #default="{ row }">{{ row.observed }}</template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { myDiagnosis, courseKnowledge } from '@/api'
import EChart from '@/components/EChart.vue'
import { DOMAIN_LABELS, DOMAIN_COLORS, fmtPct } from '@/utils/const'

const loading = ref(false)
const report = ref(null)
const knowledge = ref(null)

const DOMAIN_ORDER = ['domain_knowledge', 'domain_problem', 'domain_practice', 'domain_expression', 'domain_critical', 'domain_transfer']

const radarOpt = computed(() => {
  const ab = report.value?.ability || {}
  const observed = DOMAIN_ORDER.filter((c) => ab[c] && ab[c].observed > 0).length
  const colors = observed === DOMAIN_ORDER.length ? '#2f7cd6' : '#a0aec0'
  return {
    tooltip: {},
    radar: {
      indicator: DOMAIN_ORDER.map((c) => ({ name: ab[c]?.label || DOMAIN_LABELS[c], min: 0, max: 100 })),
      radius: '60%',
    },
    series: [{
      type: 'radar',
      symbolSize: 5,
      data: [{
        name: '能力得分', value: DOMAIN_ORDER.map((c) => Math.round((ab[c]?.score ?? 0) * 100)),
        areaStyle: { opacity: .22 }, lineStyle: { width: 2, color: colors }, itemStyle: { color: colors },
      }],
    }],
  }
})

// 维度全景
const dimList = computed(() => Object.values(report.value?.dimensions || {}))
const dimsOf = (dom) => dimList.value.filter((d) => d.domain_code === dom)
const dimGroupName = (dom) => {
  const one = dimsOf(dom)[0]
  return one?.domain_label || DOMAIN_LABELS[dom] || dom
}
const observedDimCount = computed(() => dimList.value.filter((d) => d.observed > 0).length)

// 热力图: 行=章节, 列=该章节已观测到的知识节点
const chapters = computed(() => (knowledge.value?.chapters || []).filter((c) => (c.nodes || []).length))
const codeName = computed(() => {
  const m = {}
  for (const ch of chapters.value) for (const n of ch.nodes || []) m[n.code] = { name: n.name, chapter: ch.name }
  return m
})

const heatCells = computed(() => {
  const cells = []
  let yi = 0
  for (const ch of chapters.value) {
    let rowHas = false
    for (const n of ch.nodes || []) {
      const m = report.value?.node_mastery?.[n.code]
      if (m && typeof m.mastery === 'number' && m.observed > 0) {
        rowHas = true
        cells.push({ code: n.code, yi, mastery: m.mastery })
      }
    }
    if (rowHas) yi += 1
  }
  return cells
})
const heatX = computed(() => {
  // 只保留已观测节点作为列
  const seen = []
  for (const ch of chapters.value) {
    for (const n of ch.nodes || []) {
      const m = report.value?.node_mastery?.[n.code]
      if (m && typeof m.mastery === 'number' && m.observed > 0 && !seen.includes(n.code)) seen.push(n.code)
    }
  }
  return seen
})
const heatY = computed(() => {
  const rows = []
  for (const ch of chapters.value) {
    const any = (ch.nodes || []).some((n) => {
      const m = report.value?.node_mastery?.[n.code]
      return m && typeof m.mastery === 'number' && m.observed > 0
    })
    if (any) rows.push(ch.name)
  }
  return rows
})
const heatOpt = computed(() => {
  const x = heatX.value
  const y = heatY.value
  const data = heatCells.value.map((c) => ({ value: [x.indexOf(c.code), c.yi, +(c.mastery * 100).toFixed(1)] }))
  return {
    tooltip: {
      formatter: (p) => {
        const code = x[p.value[0]]
        const ch = y[p.value[1]]
        const meta = codeName.value[code] || {}
        return `${ch} · ${meta.name || code}<br/>掌握度 <b>${p.value[2].toFixed(0)}%</b> (${code})`
      },
    },
    grid: { left: 150, right: 20, top: 10, bottom: 70 },
    xAxis: { type: 'category', data: x, axisLabel: { fontSize: 10, rotate: 45, interval: 0 }, splitArea: { show: true } },
    yAxis: { type: 'category', data: y, axisLabel: { fontSize: 11 }, splitArea: { show: true } },
    visualMap: {
      min: 0, max: 100, calculable: true, orient: 'horizontal', left: 'center', bottom: 4,
      inRange: { color: ['#f56c6c', '#e6a23c', '#cde6a0', '#67c23a'] },
      textStyle: { fontSize: 11 },
    },
    series: [{
      type: 'heatmap', data,
      label: { show: false },
      itemStyle: { borderColor: '#fff', borderWidth: 1 },
      emphasis: { itemStyle: { shadowBlur: 6, shadowColor: 'rgba(0,0,0,.25)' } },
    }],
  }
})

const nodeRows = computed(() => {
  const nm = report.value?.node_mastery || {}
  const map = codeName.value
  return Object.keys(nm).map((code) => ({ code, name: map[code]?.name || code, chapter: map[code]?.chapter || '', ...nm[code] }))
    .sort((a, b) => a.mastery - b.mastery)
})

const weakNodes = computed(() => nodeRows.value.filter((n) => typeof n.mastery === 'number' && n.mastery < 0.7).slice(0, 3))
const activeBktCount = computed(() => nodeRows.value.filter((n) => n.bkt && n.bkt.active).length)
const pm = computed(() => report.value?.profile_match || null)

const recLabel = (t) => ({ prereq: '先修补习', micro_lesson: '微课学习', practice: '巩固练习' }[t] || t)
const recTag = (t) => ({ prereq: 'danger', micro_lesson: 'warning', practice: 'success' }[t] || 'info')

async function load() {
  loading.value = true
  try {
    const res = await myDiagnosis()
    report.value = res
    if (res.course_id) {
      knowledge.value = await courseKnowledge(res.course_id)
    }
  } finally { loading.value = false }
}
onMounted(load)
</script>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: flex-start; }
.head h3 { margin: 0 0 4px; }
.small-text { font-size: 12px; line-height: 1.6; }
.block-title { font-weight: 600; margin-bottom: 12px; }
.mt { margin-top: 18px; }
.weak-list { display: flex; flex-direction: column; gap: 14px; }
.weak-name { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.mono { font-family: Consolas, Menlo, monospace; font-size: 12px; }
.rec-list { display: flex; flex-direction: column; }
.rec-item { display: flex; gap: 10px; align-items: flex-start; padding: 10px 4px; border-bottom: 1px dashed #ebeef5; }
.rec-body { flex: 1; }
.rec-title { font-weight: 600; }
.meta-tags { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 4px; }
.tag-sub { font-size: 11px; margin-left: 4px; }
.dom-block { margin-bottom: 16px; }
.dom-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.dim-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 8px; }
.dim-cell { border: 1px solid #ebeef5; border-radius: 6px; padding: 8px 10px; background: #fafbfc; }
.dim-cell.unseen { background: #f7f8fa; opacity: .85; }
.dim-cell.off { background: #fbfbfb; }
.dim-top { display: flex; justify-content: space-between; align-items: center; gap: 4px; margin-bottom: 6px; }
.dim-name { font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dim-val { font-size: 12px; margin-top: 2px; }
.bkt-val { display: flex; align-items: center; gap: 6px; }
</style>
