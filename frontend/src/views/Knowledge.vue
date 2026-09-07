<template>
  <div class="page">
    <div class="card" v-loading="loading">
      <div class="toolbar">
        <h3>课程知识图谱</h3>
        <el-select v-model="courseId" style="width:240px" @change="onCourse">
          <el-option v-for="c in courses" :key="c.id" :label="c.name" :value="c.id" />
        </el-select>
      </div>
      <el-empty v-if="!courseId" description="请选择课程" :image-size="70" />
      <el-tree v-else :data="treeData" :props="{ label: 'name', children: 'nodes' }" default-expand-all>
        <template #default="{ node, data }">
          <span class="tree-node">
            <span>{{ data.name }}</span>
            <span v-if="data.prereq_codes?.length" class="muted small3">
              先修: {{ data.prereq_codes.join('、') }}
            </span>
          </span>
        </template>
      </el-tree>
    </div>

    <!-- 课程能力维度开关(M11: 仅本课程诊断生效, absent=启用) -->
    <div class="card" v-if="courseId" v-loading="dimLoading">
      <div class="toggle-head">
        <div>
          <div class="block-title">课程能力维度开关</div>
          <p class="muted small3">停用后该维度不进入本课程的能力画像聚合与诊断报告；右侧显示已停用 {{ disabled.length }} 个。</p>
        </div>
        <div class="toggle-actions">
          <el-button size="small" :disabled="!dirty" @click="reloadDims">撤销</el-button>
          <el-button type="primary" size="small" :disabled="!dirty" :loading="saving" @click="save">保存生效</el-button>
        </div>
      </div>
      <div v-for="dom in DOMAIN_ORDER" :key="dom" class="domain-block">
        <div class="domain-title">{{ groupName(dom) }} <span class="muted small3">{{ groupLabel(dom) }}组</span></div>
        <el-checkbox-group v-model="disabledLocal" class="dim-checks">
          <el-checkbox v-for="d in dimsOf(dom)" :key="d.code" :value="d.code" class="dim-check">
            <span class="mono">{{ d.code }}</span> {{ d.name }}
          </el-checkbox>
        </el-checkbox-group>
      </div>
      <el-alert v-if="disabledLocal.length" type="warning" :closable="false" class="dim-alert">
        已停用 <b>{{ disabledLocal.length }}</b> 个维度（本课程不再统计，也不会出现在学生报告的 60 维全景中）。
      </el-alert>
    </div>

    <div class="card">
      <div class="block-title">能力域(一级) — 诊断雷达与看板使用</div>
      <el-tag v-for="d in abilityDomains" :key="d.code" class="dim-tag">{{ d.name }} <span class="muted">({{ d.code }})</span></el-tag>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { listCourses, courseKnowledge, abilityDomains as abilityDomainsApi, courseDimensions, setCourseDimensions } from '@/api'

const DOMAIN_ORDER = ['domain_knowledge', 'domain_problem', 'domain_practice', 'domain_expression', 'domain_critical', 'domain_transfer']
const DOMAIN_SHORT = { domain_knowledge: '知识', domain_problem: '问题解决', domain_practice: '实践', domain_expression: '表达', domain_critical: '批判创新', domain_transfer: '迁移' }

const courses = ref([])
const courseId = ref(null)
const treeData = ref([])
const abilityDomains = ref([])
const loading = ref(false)
const dimLoading = ref(false)
const saving = ref(false)

const dimRows = ref([])          // courseDimensions(...).dimensions
const disabledLocal = ref([])    // 待保存的停用全集
const disabled = computed(() => dimRows.value.filter((d) => d.disabled).map((d) => d.code))

const dirty = computed(() => {
  const base = disabled.value.slice().sort().join(',')
  const next = disabledLocal.value.slice().sort().join(',')
  return base !== next
})
const dimsOf = (dom) => dimRows.value.filter((d) => d.domain_code === dom)
const groupLabel = (dom) => DOMAIN_SHORT[dom] || dom
const groupName = (dom) => dimsOf(dom)[0]?.domain_label || groupLabel(dom)

async function load() {
  if (!courseId.value) return
  loading.value = true
  try {
    const res = await courseKnowledge(courseId.value)
    treeData.value = res.chapters || []
  } finally { loading.value = false }
}

async function reloadDims() {
  if (!courseId.value) return
  dimLoading.value = true
  try {
    const d = await courseDimensions(courseId.value)
    dimRows.value = d.dimensions || []
    disabledLocal.value = (d.disabled || []).slice()
  } finally { dimLoading.value = false }
}

async function save() {
  saving.value = true
  try {
    const d = await setCourseDimensions(courseId.value, disabledLocal.value)
    dimRows.value = d.dimensions || []
    disabledLocal.value = (d.disabled || []).slice()
    ElMessage.success(`已生效：停用 ${disabledLocal.value.length} 个能力维度`)
  } finally { saving.value = false }
}

function onCourse() {
  load()
  reloadDims()
}

onMounted(async () => {
  const [cs, ad] = await Promise.all([listCourses(), abilityDomainsApi()])
  courses.value = cs.items || []
  abilityDomains.value = ad.domains || []
  if (courses.value.length) {
    courseId.value = courses.value[0].id
    load()
    reloadDims()
  }
})
</script>

<style scoped>
.toolbar { display: flex; gap: 12px; align-items: center; margin-bottom: 12px; }
.toolbar h3 { margin: 0 auto 0 0; }
.tree-node { display: flex; gap: 8px; align-items: center; }
.small3 { font-size: 12px; }
.block-title { font-weight: 600; margin-bottom: 12px; }
.toggle-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; flex-wrap: wrap; }
.toggle-head .block-title { margin-bottom: 4px; }
.toggle-actions { display: flex; gap: 8px; }
.domain-block { margin-bottom: 14px; }
.domain-title { font-weight: 600; margin-bottom: 6px; }
.dim-checks { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 2px 8px; }
.dim-check { margin-right: 0; }
.dim-alert { margin-top: 4px; }
.dim-tag { margin: 2px 4px 2px 0; }
.mono { font-family: Consolas, Menlo, monospace; font-size: 12px; }
</style>
