 <template>
  <div>
    <!-- 作答原文 + 证据高亮 -->
    <div class="card">
      <div class="block-title">作答原文与证据高亮</div>
      <el-empty v-if="!answerText" description="本题无文本作答内容(见下方证据/人工复核)" :image-size="60" />
      <template v-else>
        <EvidenceText :text="answerText" :markers="markers" :active-point="activePoint" />
      </template>
    </div>

    <!-- 口语四层表现(M4: extra.layers, ok=实时层分 / nodata=如实待接入) -->
    <div class="card" v-if="spokenLayers">
      <div class="block-title">口语四层表现</div>
      <div class="layer-grid">
        <div v-for="code in SPOKEN_ORDER" :key="code" class="layer-card" :class="{ nodata: layerStatus(code) === 'nodata' }">
          <div class="layer-head">
            <span class="layer-name">{{ SPOKEN_LAYER_LABELS[code] }}</span>
            <el-tag v-if="layerStatus(code) === 'nodata'" size="small" type="info">无数据</el-tag>
            <el-tag v-else size="small" :type="SPOKEN_LAYER_TAG[code]">{{ fmtPct(layerScore(code)) }}</el-tag>
          </div>
          <el-progress v-if="layerStatus(code) !== 'nodata'" :percentage="Math.round(layerScore(code) * 100)"
                       :stroke-width="10" :show-text="false"
                       :color="layerScore(code) < 0.6 ? '#e6a23c' : '#67c23a'" />
          <div class="layer-detail muted">
            {{ layerDetail(code) || (layerStatus(code) === 'nodata' ? (SPOKEN_LAYER_NODATA[code] || '暂无对应评测源') : '') }}
          </div>
        </div>
      </div>
    </div>

    <!-- 得分点明细 -->
    <div class="card">
      <div class="block-title">得分点明细</div>
      <el-table v-if="points.length" :data="points" size="small" border highlight-current-row
                @row-click="(r) => (activePoint = r.point_id)" style="width:100%">
        <el-table-column prop="point_id" label="得分点" width="110">
          <template #default="{ row }"><span class="mono">{{ row.point_id }}</span></template>
        </el-table-column>
        <el-table-column prop="description" label="量规描述" min-width="170" />
        <el-table-column label="判定" width="100">
          <template #default="{ row }">
            <el-tag :type="verdictTag(row.status)" size="small">{{ verdictLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="得分" width="110">
          <template #default="{ row }">
            <b>{{ row.earned.toFixed(1) }}</b> / {{ row.max.toFixed(1) }}
          </template>
        </el-table-column>
        <el-table-column prop="reason" label="评阅依据" min-width="220" show-overflow-tooltip />
      </el-table>
      <el-empty v-else description="本题无逐点拆解，判定结果见下方证据" :image-size="60" />

      <div v-if="penalties.length" class="penal">
        <div class="penal-title">罚分项</div>
        <div v-for="p in penalties" :key="p.reason" class="penal-item">
          扣 {{ Number(p.deduct).toFixed(1) }} 分 — {{ p.reason }}
        </div>
      </div>
    </div>

    <!-- 证据明细 -->
    <div class="card" v-if="evidence.length">
      <div class="block-title">证据明细(共 {{ evidence.length }} 条)</div>
      <el-table :data="evidence" size="small" border style="width:100%">
        <el-table-column label="所属得分点" width="110">
          <template #default="{ row }">
            <span class="mono">{{ row.point_id || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="判定" width="100">
          <template #default="{ row }">
            <el-tag :type="verdictTag(row.label)" size="small">{{ row.label_text }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="证据来源" width="110">
          <template #default="{ row }">{{ row.kind }}</template>
        </el-table-column>
        <el-table-column label="证据内容 / 定位" min-width="200">
          <template #default="{ row }">
            <span v-if="row.text_snippet" class="snippet">“{{ row.text_snippet }}”</span>
            <span v-else-if="typeof row.ref_start === 'number'" class="muted mono">区间 [{{ row.ref_start }}, {{ row.ref_end }}]</span>
            <span v-else class="muted">无原文片段(依据见得分点)</span>
          </template>
        </el-table-column>
        <el-table-column label="置信度" width="100">
          <template #default="{ row }">{{ fmtPct(row.confidence) }}</template>
        </el-table-column>
        <el-table-column label="产生方" width="110">
          <template #default="{ row }">{{ row.created_by || 'engine' }}</template>
        </el-table-column>
      </el-table>
    </div>

    <div v-if="comment || reasoning" class="card">
      <div v-if="comment"><div class="block-title">建议评语</div><p class="reason">{{ comment }}</p></div>
      <div v-if="reasoning"><div class="block-title">引擎解释</div><p class="reason muted">{{ reasoning }}</p></div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import EvidenceText from './EvidenceText.vue'
import {
  VERDICT_LABELS, VERDICT_TAG, SPOKEN_LAYER_LABELS, SPOKEN_LAYER_TAG,
  SPOKEN_LAYER_NODATA, fmtPct,
} from '@/utils/const'

const props = defineProps({
  answerText: { type: String, default: '' },
  score: { type: Object, default: () => ({}) },
})

const SPOKEN_ORDER = ['pronunciation', 'fluency', 'expression', 'content']
const activePoint = ref('')
const comment = computed(() => props.score.comment || '')
const reasoning = computed(() => props.score.reasoning || '')
const points = computed(() => (props.score.point_scores || []).map((p) => ({ ...p, max: Number(p.max ?? 0), earned: Number(p.earned ?? 0) })))
const penalties = computed(() => props.score.penalties || [])
const evidence = computed(() => props.score.evidence || [])
const markers = computed(() =>
  evidence.value
    .filter((e) => e && typeof e.ref_start === 'number' && typeof e.ref_end === 'number')
    .map((e) => ({ start: e.ref_start, end: e.ref_end, verdict: e.label, point_id: e.point_id })),
)
const verdictLabel = (v) => VERDICT_LABELS[v] || v || '—'
const verdictTag = (v) => VERDICT_TAG[v] || 'info'

// 口语四层: score.extra.layers = { code: {status:'ok'|'nodata', score(0-1), detail} }
const spokenLayers = computed(() => {
  const layers = props.score?.extra?.layers
  return layers && typeof layers === 'object' && Object.keys(layers).length ? layers : null
})
const layerStatus = (code) => (spokenLayers.value && spokenLayers.value[code]?.status) || 'nodata'
const layerScore = (code) => {
  const v = spokenLayers.value?.[code]?.score
  return typeof v === 'number' ? Math.max(0, Math.min(1, v)) : 0
}
const layerDetail = (code) => spokenLayers.value?.[code]?.detail || ''
</script>

<style scoped>
.block-title { font-weight: 600; margin-bottom: 12px; }
.layer-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
.layer-card { border: 1px solid #ebeef5; border-radius: 8px; padding: 12px 14px; background: #fafbfc; }
.layer-card.nodata { background: #f6f8fa; border-style: dashed; }
.layer-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.layer-name { font-weight: 600; }
.layer-detail { font-size: 12px; line-height: 1.6; margin-top: 6px; }
.penal { margin-top: 12px; border: 1px solid #ffccc7; background: #fff2f0; border-radius: 6px; padding: 10px 12px; }
.penal-title { font-weight: 600; color: #cf1322; margin-bottom: 6px; }
.penal-item { line-height: 1.8; color: #a8071a; }
.snippet { font-style: italic; color: #514; }
.reason { line-height: 1.8; white-space: pre-wrap; margin: 0; }
.mono { font-family: Consolas, Menlo, monospace; }
</style>
