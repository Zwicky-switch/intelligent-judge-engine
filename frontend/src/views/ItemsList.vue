<template>
  <div class="page">
    <div class="card">
      <div class="toolbar">
        <h3>题库管理</h3>
        <el-select v-model="filters.course_id" placeholder="课程" clearable style="width:180px" @change="loadItems">
          <el-option v-for="c in courses" :key="c.id" :label="c.name" :value="c.id" />
        </el-select>
        <el-select v-model="filters.type" placeholder="题型" clearable style="width:160px" @change="loadItems">
          <el-option v-for="t in types" :key="t.value" :label="t.label" :value="t.value" />
        </el-select>
        <el-select v-model="filters.published" placeholder="发布状态" clearable style="width:150px" @change="loadItems">
          <el-option label="已发布" :value="true" />
          <el-option label="草稿" :value="false" />
        </el-select>
        <div class="spacer" />
        <el-button type="primary" :icon="Plus" @click="$router.push('/items/new')">新建题目</el-button>
      </div>

      <el-table :data="items" v-loading="loading" border size="default" style="width:100%">
        <el-table-column prop="code" label="编号" width="130">
          <template #default="{ row }"><span class="mono">{{ row.code }}</span></template>
        </el-table-column>
        <el-table-column label="题型" width="104">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" :type="tagType(row.type)">{{ row.type_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="title" label="题干" min-width="200" show-overflow-tooltip />
        <el-table-column label="满分" width="66">
          <template #default="{ row }">{{ row.max_score.toFixed(1) }}</template>
        </el-table-column>
        <el-table-column label="发布策略" width="104">
          <template #default="{ row }">
            <el-tag v-if="row.scoring_policy?.review_mode === 'double'" type="warning" size="small">双评</el-tag>
            <el-tag v-if="row.scoring_policy?.require_double_publish" type="danger" size="small" effect="plain">双人复核发布</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="版本" width="64" prop="current_version" />
        <el-table-column label="发布时间/截止" width="150">
          <template #default="{ row }">
            <div class="small-text" style="line-height:1.6">
              <div><span class="muted">发布</span> {{ fmtTime(row.published_at) }}</div>
              <div><span class="muted">截止</span> {{ row.submit_deadline ? fmtTime(row.submit_deadline) : '不限' }}</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="发布" width="86">
          <template #default="{ row }">
            <el-tag :type="row.published ? 'success' : 'info'" size="small">{{ row.published ? '已发布' : '草稿' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="70">
          <template #default="{ row }">
            <el-switch :model-value="!!row.enabled" @change="(v) => onToggle(row, v)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" :icon="EditPen" @click="$router.push(`/items/${row.id}`)">编辑</el-button>
            <el-button link type="info" :icon="Clock" @click="openVersions(row)">历史</el-button>
            <el-button v-if="!row.published" link type="success" :icon="Position" @click="onPublish(row)">发布</el-button>
            <el-button v-else link type="warning" :icon="RefreshRight" @click="onPublish(row)">重新发布</el-button>
            <el-button v-if="isAdmin" link type="danger" :icon="Delete" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <p class="muted note">发布后量规与答案将固化为版本快照(历史成绩不回写)；已发布的题可点"重新发布"直接再发布(版本+1)，无需重新编辑；双人复核发布需 2 个不同账号复核后才真正发布。</p>
    </div>

    <!-- 版本历史 / 比较 -->
    <el-dialog v-model="verDialog" :title="`版本历史 — ${verItem?.code || ''}`" width="720px">
      <div v-if="versions.length" class="ver-head">
        <span class="muted small-text">比较：</span>
        <el-select v-model="cmpV1" size="small" style="width:110px">
          <el-option v-for="v in versions" :key="v.version" :label="`v${v.version}`" :value="v.version" />
        </el-select>
        <span class="muted"> ↔ </span>
        <el-select v-model="cmpV2" size="small" style="width:110px">
          <el-option v-for="v in versions" :key="v.version" :label="`v${v.version}`" :value="v.version" />
        </el-select>
        <el-button size="small" type="primary" :disabled="!cmpV1 || !cmpV2 || cmpV1 === cmpV2" @click="compare">比较差异</el-button>
      </div>

      <el-table :data="versions" size="small" border style="width:100%">
        <el-table-column prop="version" label="版本" width="70">
          <template #default="{ row }"><b>v{{ row.version }}</b></template>
        </el-table-column>
        <el-table-column label="发布于" min-width="150">
          <template #default="{ row }">{{ row.published_by_name || '—' }} · {{ fmtTime(row.published_at) }}</template>
        </el-table-column>
        <el-table-column label="量规要点" min-width="200">
          <template #default="{ row }">
            <span class="muted">{{ pointBrief(row.rubric) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="满分" width="70" prop="max_score" />
      </el-table>

      <div v-if="cmpChanges" class="cmp">
        <div class="cmp-title">v{{ cmpV1 }} → v{{ cmpV2 }} 差异</div>
        <el-empty v-if="!cmpChanges.length" :image-size="50" description="两个版本内容一致" />
        <div v-for="(c, i) in cmpChanges" :key="i" class="cmp-item">
          <div class="cmp-field"><el-tag size="small" type="warning">changed</el-tag> <b>{{ c.field }}</b></div>
          <template v-if="c.detail">
            <div class="muted small-text" v-if="c.detail.added?.length">新增键: {{ c.detail.added.join(', ') }}</div>
            <div class="muted small-text" v-if="c.detail.removed?.length">删除键: {{ c.detail.removed.join(', ') }}</div>
            <div class="muted small-text" v-if="c.detail.changed?.length">变更键: {{ c.detail.changed.join(', ') }}</div>
          </template>
          <pre v-else class="cmp-pre"><span class="old">- {{ c.before }}</span><span class="new">+ {{ c.after }}</span></pre>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, EditPen, Position, RefreshRight, Clock, Delete } from '@element-plus/icons-vue'
import { listItems, itemTypes, listCourses, publishItem, toggleItem, deleteItem, itemVersions, compareVersions } from '@/api'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const isAdmin = computed(() => auth.role === 'admin')

const items = ref([])
const types = ref([])
const courses = ref([])
const loading = ref(false)
const filters = reactive({ course_id: undefined, type: '', published: undefined })

const verDialog = ref(false)
const verItem = ref(null)
const versions = ref([])
const cmpV1 = ref(null)
const cmpV2 = ref(null)
const cmpChanges = ref(null)

const OBJ_TYPES = ['single_choice', 'multiple_choice', 'true_false', 'fill_blank', 'numeric']
function tagType(t) {
  return OBJ_TYPES.includes(t) ? 'primary' : (t === 'subjective_text' ? 'success' : (t === 'spoken' ? 'warning' : 'danger'))
}
function fmtTime(s) { return s ? s.replace('T', ' ').slice(0, 19) : '—' }
function pointBrief(rubric) {
  const arr = rubric || []
  return arr.length ? `${arr.length} 个得分点 (${arr.map((p) => (p.description || '').slice(0, 12)).join(' / ')})` : '—'
}

async function loadItems() {
  loading.value = true
  try {
    const res = await listItems({
      course_id: filters.course_id, type: filters.type || undefined,
      published: filters.published,
    })
    items.value = res.items || []
  } finally { loading.value = false }
}

async function openVersions(row) {
  verItem.value = row
  cmpChanges.value = null
  cmpV1.value = cmpV2.value = null
  const res = await itemVersions(row.id)
  versions.value = res.items || []
  if (versions.value.length >= 2) {
    cmpV1.value = versions.value[0].version
    cmpV2.value = versions.value[versions.value.length - 1].version
  }
  verDialog.value = true
}

async function compare() {
  const res = await compareVersions(verItem.value.id, cmpV1.value, cmpV2.value)
  cmpChanges.value = res.changes || []
}

async function onPublish(row) {
  const doublePub = row.scoring_policy?.require_double_publish
  await ElMessageBox.confirm(
    row.published
      ? `不修改题目内容，直接重新发布并固化版本快照(v${(row.current_version || 1) + 1})${doublePub ? '(双人复核发布：需 2 个不同账号复核)' : ''}，确认？`
      : `发布并固化量规/答案${doublePub ? '(双人复核发布：需 2 个不同账号复核后才真正发布)' : ''}，确认？`,
    row.published ? '重新发布题目' : '发布题目', { type: 'warning' })
  const res = await publishItem(row.id, '')
  if (res.publish_pending) {
    ElMessage.warning(res.message || `已登记复核 ${res.approvals_received}/${res.approvals_needed}，还需其他账号复核`)
  } else {
    ElMessage.success(res.message || '重新发布成功')
  }
  loadItems()
}

async function onToggle(row, v) {
  try {
    await toggleItem(row.id, v)
    row.enabled = v
    ElMessage.success(v ? '已启用' : '已停用')
  } catch (e) { /* 拦截器已提示 */ }
}

async function onDelete(row) {
  const ok = await ElMessageBox.confirm(
    `删除题目 ${row.code} 将连带删除该题全部答卷、成绩、版本快照、发布复核记录与上传文件，且不可恢复。确认删除？`,
    '删除题目', { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' },
  ).catch(() => null)
  if (!ok) return
  try {
    const res = await deleteItem(row.id)
    ElMessage.success(`已删除 ${res.deleted.code}（答卷 ${res.deleted.answers} 条、成绩 ${res.deleted.scores} 条、版本 ${res.deleted.versions} 个）`)
    await loadItems()
  } catch (e) { /* 拦截器已提示 */ }
}

onMounted(async () => {
  const [it, cs] = await Promise.all([itemTypes(), listCourses()])
  types.value = it.types || []
  courses.value = cs.items || []
  loadItems()
})
</script>

<style scoped>
.toolbar { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 14px; }
.toolbar h3 { margin: 0 auto 0 0; }
.spacer { flex: 1; }
.mono { font-family: Consolas, Menlo, monospace; }
.note { font-size: 12px; margin: 12px 0 0; }
.ver-head { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.small-text { font-size: 12px; }
.cmp { margin-top: 14px; border-top: 1px dashed #dcdfe6; padding-top: 10px; }
.cmp-title { font-weight: 600; margin-bottom: 8px; }
.cmp-item { border: 1px solid #ebeef5; border-radius: 6px; padding: 8px 10px; margin-bottom: 8px; background: #fafbfc; }
.cmp-field { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.cmp-pre { margin: 4px 0 0; display: flex; flex-direction: column; gap: 2px; font-size: 12px; }
.cmp-pre .old { color: #f56c6c; }
.cmp-pre .new { color: #18a058; }
</style>
