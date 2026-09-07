<template>
  <div class="login-wrap">
    <div class="login-bg"></div>
    <el-card class="login-card">
      <div class="brand">
        <div class="brand-icon">智评</div>
        <h1>智评 · Insight</h1>
        <p class="muted">多题型智能评阅与能力诊断引擎</p>
      </div>

      <el-form :model="form" size="large" @submit.prevent="doLogin">
        <el-form-item>
          <el-input v-model="form.username" placeholder="用户名" :prefix-icon="User" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="form.password" type="password" show-password placeholder="密码"
                    :prefix-icon="Lock" @keyup.enter="doLogin" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" class="w100" :loading="loading" @click="doLogin">登 录</el-button>
        </el-form-item>
      </el-form>

      <el-divider content-position="left"><span class="muted small">预置账号（点击填充）</span></el-divider>
      <div class="demos">
        <el-tag v-for="a in demos" :key="a.username" class="demo-tag" effect="plain"
                @click="fill(a)">{{ a.label }}</el-tag>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import { login } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { homeByRole } from '@/router'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const loading = ref(false)

const form = reactive({ username: 'admin', password: 'admin123' })
const demos = [
  { label: '教务管理员', username: 'admin', password: 'admin123' },
  { label: '命题教师', username: 'prop_teacher', password: 'teacher123' },
  { label: '阅卷教师 A', username: 'grader', password: 'teacher123' },
  { label: '阅卷教师 B(双评)', username: 'grader2', password: 'teacher123' },
  { label: '学生·李雪', username: 'student_li', password: 'stu123' },
]

function fill(a) {
  form.username = a.username
  form.password = a.password
}

async function doLogin() {
  if (!form.username || !form.password) return
  loading.value = true
  try {
    const res = await login({ username: form.username, password: form.password })
    auth.setSession(res.access_token, res.user)
    ElMessage.success(`欢迎，${res.user.display_name || res.user.username}`)
    const target = route.query.redirect || homeByRole(res.user.role)
    router.push(target)
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || err.message || '登录失败，请检查用户名与密码')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrap { position: relative; height: 100vh; display: flex; align-items: center; justify-content: center;
  background:
    radial-gradient(560px 360px at 82% 12%, rgba(85, 164, 255, .28), transparent 70%),
    radial-gradient(640px 420px at 8% 92%, rgba(47, 124, 214, .30), transparent 70%),
    linear-gradient(135deg, #0a2138 0%, #123861 52%, #1b5aa3 100%);
  overflow: hidden; }
.login-bg { position: absolute; inset: 0; opacity: .14; pointer-events: none;
  background-image:
    radial-gradient(circle at 22% 18%, rgba(255,255,255,.5) 1px, transparent 1.6px),
    radial-gradient(circle at 68% 62%, rgba(255,255,255,.4) 1px, transparent 1.6px);
  background-size: 40px 40px; }
.login-card { width: 424px; border-radius: 18px; padding: 10px 8px; border: 1px solid rgba(255,255,255,.5);
  box-shadow: 0 24px 60px -22px rgba(4, 16, 32, .55);
  animation: login-in .45s cubic-bezier(.2, .7, .3, 1) both; }
.brand { text-align: center; margin: 6px 0 18px; }
.brand h1 {
  font-size: 24px; margin: 12px 0 6px; letter-spacing: .5px;
  background: linear-gradient(120deg, #16406f, #2f7cd6 70%);
  -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;
}
.brand .brand-icon {
  display: inline-block; width: 68px; height: 68px; line-height: 68px; border-radius: 18px;
  background: linear-gradient(135deg, #1b5aa3, #4aa0ff);
  color: #fff; font-size: 26px; font-weight: 700; letter-spacing: 2px;
  box-shadow: 0 14px 28px -12px rgba(27, 90, 163, .8), 0 0 0 6px rgba(47, 124, 214, .10);
}
.w100 { width: 100%; height: 44px; font-size: 15px; letter-spacing: 4px; }
.small { font-size: 12px; }
.demo-tag { cursor: pointer; margin: 4px 6px 0 0; transition: all .15s ease; border-color: #cfe0f5; color: #3a6fb0; }
.demo-tag:hover { color: #fff; background: linear-gradient(135deg, #2f7cd6, #55b0ff); border-color: transparent;
  transform: translateY(-1px); box-shadow: 0 4px 10px -4px rgba(47, 124, 214, .6); }
@keyframes login-in { from { opacity: 0; transform: translateY(16px) scale(.985); } to { opacity: 1; transform: none; } }
</style>
