<template>
  <div class="page">
    <div class="card">
      <div class="toolbar">
        <h3>复核中心</h3>
        <div class="spacer" />
        <div class="counts">
          <el-tag type="info" effect="plain" size="small">双评待第 1 评：{{ dbl.await_first }}</el-tag>
          <el-tag type="warning" effect="plain" size="small">双评待第 2 评：{{ dbl.await_second }}</el-tag>
          <el-tag type="danger" effect="plain" size="small">双评待仲裁：{{ dbl.await_arbitrate }}</el-tag>
        </div>
        <el-radio-group v-model="scope" size="default" @change="load">
          <el-radio-button value="todo">待复核({{ total }})</el-radio-button>
          <el-radio-button value="reviewed">已评阅</el-radio-button>
        </el-radio-group>
        <el-radio-group v-if="scope === 'todo'" v-model="level" size="default" @change="load">
          <el-radio-button value="">全部</el-radio-button>
          <el-radio-button value="forced">强制复核({{ counts.forced }})</el-radio-button>
          <el-radio-button value="sample">抽样复核({{ counts.sample }})</el-radio-button>
        </el-radio-group>
        <el-button :icon="Refresh" circle @click="load" />
      </div>

      <el-table :data="items" v-loading="loading" border size="default" style="width:100%">
        <el-table-column label="学生" width="96">
          <template #default="{ row }">{{ row.student_name }}</template>
        </el-table-column>
        <el-table-column label="题目" min-width="200">
          <template #default="{ row }">
            <div><span class="mono">{{ row.item?.code }}</span> · {{ row.item?.type_label }}</div>
            <div class="muted ellip">{{ row.item?.title }}</div>
          </template>
        </el-table-column>
        <el-table-column label="复核档位" width="96">
          <template #default="{ row }">
            <el-tag :type="LEVEL_TAG[row.review_level]" size="small">{{ LEVEL_LABELS[row.review_level] }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="双评阶段" width="120">
          <template #default="{ row }">
            <template v-if="row.double && row.double.state">
              <el-tag :type="row.double.state === 'await_arbitrate' ? 'danger' : 'warning'" size="small">
                {{ DOUBLE_STATE_LABELS[row.double.state] }}
              </el-tag>
              <div class="muted small-text">{{ (row.double.passes || []).length }} 笔独立分</div>
            </template>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="引擎得分" width="88">
          <template #default="{ row }"><b>{{ fmtScore(row.total_score) }}</b></template>
        </el-table-column>
        <el-table-column label="满分" width="66">
          <template #default="{ row }">{{ fmtScore(row.max_score) }}</template>
        </el-table-column>
        <el-table-column label="置信度" width="86">
          <template #default="{ row }">{{ fmtPct(row.confidence) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="88">
          <template #default="{ row }">
            <el-tag :type="STATUS_TAG[row.status]" size="small">{{ STATUS_LABELS[row.status] }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="提交时间" width="160">
          <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="108" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" size="small" @click="$router.push(`/review/${row.id}`)">
              {{ scope === 'reviewed' ? '查看' : (row.double && row.double.state === 'await_arbitrate' ? '去仲裁' : (row.double ? '评/复核' : '评阅/复核')) }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { reviewQueue } from '@/api'
import { LEVEL_LABELS, LEVEL_TAG, STATUS_LABELS, STATUS_TAG, DOUBLE_STATE_LABELS, fmtScore, fmtPct } from '@/utils/const'

const items = ref([])
const loading = ref(false)
const scope = ref('todo')
const level = ref('')
const counts = reactive({ forced: 0, sample: 0 })
const dbl = reactive({ await_second: 0, await_arbitrate: 0 })
const total = ref(0)

function fmtTime(s) { return s ? s.replace('T', ' ').slice(0, 19) : '—' }

async function load() {
  loading.value = true
  try {
    if (scope.value === 'reviewed') {
      // 已评阅(终审)卷只读查看
      const res = await reviewQueue({ status: 'reviewed' })
      items.value = res.items || []
      total.value = res.total || 0
      return
    }
    const all = await reviewQueue({})
    total.value = all.total || 0
    counts.forced = all.levels?.forced || 0
    counts.sample = all.levels?.sample || 0
    dbl.await_second = all.double?.await_second || 0
    dbl.await_arbitrate = all.double?.await_arbitrate || 0
    // 重新按当前档位拉取(服务端也会过滤)
    const res = level.value ? await reviewQueue({ review_level: level.value }) : all
    items.value = res.items || []
  } finally { loading.value = false }
}
onMounted(load)
</script>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 14px; }
.toolbar h3 { margin: 0; }
.spacer { flex: 1; }
.counts { display: flex; align-items: center; gap: 6px; }
.small-text { font-size: 12px; }
.mono { font-family: Consolas, Menlo, monospace; font-size: 12px; }
.ellip { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 320px; font-size: 12px; }
</style>
