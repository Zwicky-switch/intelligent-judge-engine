<template>
  <div class="page">
    <div class="card">
      <div class="toolbar">
        <h3>审计日志(不可删除)</h3>
        <el-input v-model="action" placeholder="按动作筛选" clearable style="width:220px" @change="load" />
        <el-button type="primary" :icon="Search" @click="load">查询</el-button>
      </div>
      <el-table :data="items" size="small" border v-loading="loading" style="width:100%">
        <el-table-column label="时间" width="180">
          <template #default="{ row }"><span class="mono">{{ fmtTime(row.created_at) }}</span></template>
        </el-table-column>
        <el-table-column prop="actor" label="操作人" width="120" />
        <el-table-column prop="action" label="动作" width="150">
          <template #default="{ row }"><el-tag size="small" effect="plain">{{ row.action }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="target_type" label="对象" width="120" />
        <el-table-column prop="target_id" label="对象ID" width="100" />
        <el-table-column label="详情" min-width="260">
          <template #default="{ row }">
            <span v-if="row.detail && Object.keys(row.detail).length" class="mono">{{ JSON.stringify(row.detail) }}</span>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { auditList } from '@/api'

const items = ref([])
const loading = ref(false)
const action = ref('')

function fmtTime(s) {
  return s ? s.replace('T', ' ').slice(0, 19) : '—'
}

async function load() {
  loading.value = true
  try {
    const res = await auditList({ action: action.value || undefined })
    items.value = res.items || []
  } finally {
    loading.value = false
  }
}
onMounted(load)
</script>

<style scoped>
.toolbar { display: flex; gap: 12px; align-items: center; margin-bottom: 14px; }
.toolbar h3 { margin: 0 auto 0 0; }
.mono { font-family: Consolas, Menlo, monospace; font-size: 12px; }
</style>
