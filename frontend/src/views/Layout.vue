<template>
  <el-container class="layout">
    <el-aside width="220px" class="aside">
      <div class="logo">
        <span class="logo-mark">智评</span>
        <div class="logo-text">
          <b>Insight</b>
          <small>智能评阅诊断引擎</small>
        </div>
      </div>
      <el-menu :default-active="activePath" router class="menu">
        <el-menu-item v-for="m in menus" :key="m.path" :index="m.path"
                      :class="{ 'eng-item': m.engine }">
          <el-icon><component :is="m.icon" /></el-icon>
          <span>{{ m.title }}</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="header">
        <div class="crumb">{{ currentTitle }}</div>
        <div class="right">
          <div v-if="meta" class="tech-pill" :title="meta.note">
            <span class="dot" :class="{ online: isExternalProvider(meta.llm_provider) && meta.has_api_key }"></span>
            <span class="tp-name">{{ providerLabel }}</span>
            <span class="tp-model">{{ meta.model_version || '—' }}</span>
          </div>
          <el-tag size="small" effect="plain">{{ roleLabel }}</el-tag>
          <span class="uname">{{ user?.display_name || user?.username }}</span>
          <el-button text :icon="SwitchButton" @click="logout">退出</el-button>
        </div>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  DataAnalysis, Document, Files, Grid, Histogram, Lock, MagicStick, SwitchButton, User, Monitor, Cpu,
} from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { engineMeta } from '@/api'
import { PROVIDER_LABEL_OF, ROLE_LABELS, isExternalProvider } from '@/utils/const'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const user = computed(() => auth.user)
const role = computed(() => auth.role)
const roleLabel = computed(() => (user.value ? (user.value.role_label || ROLE_LABELS[role.value]) : ''))

// 技术铭牌: 引擎当前运行的评阅引擎 / 模型版本
const meta = ref(null)
const providerLabel = computed(() => {
  if (!meta.value) return ''
  return PROVIDER_LABEL_OF(meta.value.llm_provider)
})

const MENU_ALL = [
  { path: '/dashboard', title: '质量看板', icon: Monitor, roles: ['admin', 'grader'] },
  { path: '/review', title: '复核中心', icon: Document, roles: ['admin', 'grader'] },
  { path: '/items', title: '题库管理', icon: Files, roles: ['admin', 'prop_teacher'] },
  { path: '/knowledge', title: '知识图谱', icon: Grid, roles: ['admin', 'prop_teacher'] },
  { path: '/audit', title: '审计日志', icon: Lock, roles: ['admin'] },
  { path: '/my/scores', title: '我的成绩', icon: DataAnalysis, roles: ['student'] },
  { path: '/my/report', title: '诊断报告', icon: Histogram, roles: ['student'] },
  // 技术导览(全角色), 固定置底展示, 突出引擎本身的能力而不是某一个角色页面
  { path: '/engine', title: '引擎技术导览', icon: Cpu, roles: ['admin', 'grader', 'prop_teacher', 'student'] },
]

onMounted(async () => {
  try {
    meta.value = await engineMeta()
  } catch {
    meta.value = null
  }
})

const menus = computed(() => MENU_ALL.filter((m) => m.roles.includes(role.value)))
const activePath = computed(() => {
  const p = route.path
  for (const m of menus.value) {
    if (p === m.path || p.startsWith(m.path + '/')) return m.path
  }
  return p
})
const currentTitle = computed(() => route.meta.title || '智评 Insight')

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<style scoped>
.layout { height: 100vh; }
.aside {
  background:
    radial-gradient(320px 240px at 0% 0%, rgba(85, 164, 255, .18), transparent 70%),
    linear-gradient(180deg, #0c2340 0%, #10305a 60%, #0e2850 100%);
  color: #c8d4e2;
  display: flex; flex-direction: column;
  box-shadow: inset -1px 0 0 rgba(255, 255, 255, .05);
}
.logo { display: flex; align-items: center; gap: 10px; padding: 20px 18px 14px; color: #fff; }
.logo-mark {
  width: 40px; height: 40px; line-height: 40px; text-align: center; border-radius: 12px;
  background: linear-gradient(135deg, #2f7cd6, #55b0ff);
  box-shadow: 0 6px 14px -6px rgba(47, 124, 214, .75);
  font-weight: 800; color: #fff; flex: none; font-size: 15px; letter-spacing: .5px;
}
.logo-text { display: flex; flex-direction: column; line-height: 1.2; }
.logo-text b { font-size: 16px; letter-spacing: .3px; }
.logo-text small { color: #8ba3bd; font-size: 11px; margin-top: 3px; letter-spacing: .2px; }

.menu {
  flex: 1; min-height: 0;
  display: flex; flex-direction: column;
  border-right: none; background: transparent; padding: 4px 12px 14px;
  --el-menu-bg-color: transparent; --el-menu-text-color: #c6d3e0;
  --el-menu-hover-bg-color: rgba(255, 255, 255, .08); --el-menu-active-color: #fff;
}
.menu :deep(.el-menu-item) { height: 46px; border-radius: 10px; margin-bottom: 4px; padding-left: 16px !important; }
.menu :deep(.el-menu-item .el-icon) { color: inherit; font-size: 18px; margin-right: 6px; }
.menu :deep(.el-menu-item.is-active) {
  background: linear-gradient(90deg, #2f7cd6, #3f92e8);
  box-shadow: 0 6px 14px -8px rgba(47, 124, 214, .9);
  font-weight: 600;
}
.menu :deep(.el-menu-item:not(.is-active):hover) { color: #eef3f9; }

/* 引擎技术导览: 置底 + 分隔线, 与角色工作项区分开 */
.menu :deep(.eng-item) { margin-top: auto; position: relative; }
.menu :deep(.eng-item::before) {
  content: ''; position: absolute; left: 8px; right: 8px; top: -7px; height: 1px;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, .16), transparent);
  pointer-events: none;
}

.header {
  background: rgba(255, 255, 255, .86);
  backdrop-filter: blur(6px);
  border-bottom: 1px solid var(--border-soft, #e6ebf2);
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 24px; height: 58px;
  z-index: 5;
}
.crumb { display: flex; align-items: center; font-weight: 700; font-size: 15px; color: #2a3340; }
.crumb::before {
  content: ''; width: 10px; height: 10px; border-radius: 3px; margin-right: 10px;
  background: linear-gradient(135deg, #2f7cd6, #55b0ff);
  box-shadow: 0 0 0 4px rgba(47, 124, 214, .12);
}
.right { display: flex; align-items: center; gap: 14px; }
.tech-pill {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 4px 11px 4px 9px; border-radius: 20px;
  background: #f3f6fb; border: 1px solid #e3eaf3;
  font-size: 12px; color: #45505f; cursor: default;
}
.tech-pill .dot { width: 7px; height: 7px; border-radius: 50%; background: #c9a227; box-shadow: 0 0 0 3px rgba(201, 162, 39, .16); }
.tech-pill .dot.online { background: #23a55a; box-shadow: 0 0 0 3px rgba(35, 165, 90, .16); }
.tech-pill .tp-name { font-weight: 600; }
.tech-pill .tp-model { color: var(--muted, #9098a3); font-family: Consolas, Menlo, monospace; }
.uname { font-size: 14px; color: #3a4452; font-weight: 500; }
.main { background: transparent; overflow: auto; padding: 0; }
</style>
