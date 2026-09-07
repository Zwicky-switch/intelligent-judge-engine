import { createRouter, createWebHistory } from 'vue-router'

const TOKEN_KEY = 'insight_token'
const USER_KEY = 'insight_user'

function storedUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || 'null')
  } catch {
    return null
  }
}

export function homeByRole(role) {
  const map = {
    admin: '/dashboard',
    prop_teacher: '/items',
    grader: '/review',
    student: '/my/scores',
  }
  return map[role] || '/login'
}

const Login = () => import('@/views/Login.vue')
const Layout = () => import('@/views/Layout.vue')

const views = {
  Dashboard: () => import('@/views/Dashboard.vue'),
  Engine: () => import('@/views/Engine.vue'),
  Audit: () => import('@/views/Audit.vue'),
  ItemsList: () => import('@/views/ItemsList.vue'),
  ItemEdit: () => import('@/views/ItemEdit.vue'),
  Knowledge: () => import('@/views/Knowledge.vue'),
  ReviewQueue: () => import('@/views/ReviewQueue.vue'),
  Workbench: () => import('@/views/Workbench.vue'),
  MyScores: () => import('@/views/MyScores.vue'),
  MyReport: () => import('@/views/MyReport.vue'),
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: Login, meta: { public: true, title: '登录' } },
    {
      path: '/',
      component: Layout,
      redirect: () => homeByRole(storedUser()?.role),
      children: [
        { path: 'dashboard', name: 'dashboard', component: views.Dashboard, meta: { roles: ['admin', 'grader'], title: '质量看板' } },
        { path: 'audit', name: 'audit', component: views.Audit, meta: { roles: ['admin'], title: '审计日志' } },
        { path: 'items', name: 'items', component: views.ItemsList, meta: { roles: ['admin', 'prop_teacher'], title: '题库管理' } },
        { path: 'items/new', name: 'item-new', component: views.ItemEdit, meta: { roles: ['admin', 'prop_teacher'], title: '新建题目' } },
        { path: 'items/:id(\\d+)', name: 'item-edit', component: views.ItemEdit, meta: { roles: ['admin', 'prop_teacher'], title: '题目详情' } },
        { path: 'knowledge', name: 'knowledge', component: views.Knowledge, meta: { roles: ['admin', 'prop_teacher'], title: '知识图谱与能力维度' } },
        { path: 'review', name: 'review', component: views.ReviewQueue, meta: { roles: ['admin', 'grader'], title: '复核中心' } },
        { path: 'review/:scoreId(\\d+)', name: 'workbench', component: views.Workbench, meta: { roles: ['admin', 'grader'], title: '评阅工作台' } },
        { path: 'my/scores', name: 'my-scores', component: views.MyScores, meta: { roles: ['student'], title: '我的成绩' } },
        { path: 'my/report', name: 'my-report', component: views.MyReport, meta: { roles: ['student'], title: '能力诊断报告' } },
        // 技术导览: 全角色可见, 不参与角色守卫
        { path: 'engine', name: 'engine', component: views.Engine, meta: { title: '引擎技术导览' } },
      ],
    },
  ],
})

router.beforeEach((to) => {
  const token = localStorage.getItem(TOKEN_KEY)
  const user = storedUser()
  if (to.meta.public) {
    // 已登录访问登录页 -> 直接进工作台
    if (token && to.path === '/login') return homeByRole(user?.role)
    return true
  }
  if (!token) return { path: '/login', query: { redirect: to.fullPath } }
  const allowed = to.meta.roles
  if (allowed && !allowed.includes(user?.role)) return homeByRole(user?.role)
  return true
})

export default router
