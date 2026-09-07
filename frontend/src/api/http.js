import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '@/router'

const http = axios.create({ baseURL: '/v1', timeout: 60000 })

http.interceptors.request.use((config) => {
  const token = localStorage.getItem('insight_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

http.interceptors.response.use(
  (res) => res.data,
  (err) => {
    const status = err.response?.status
    const msg = err.response?.data?.detail || err.message || '请求失败'
    if (status === 401) {
      localStorage.removeItem('insight_token')
      localStorage.removeItem('insight_user')
      // 登录页的 401(用户名/密码错误等)由 Login 页自行提示具体原因;
      // 其它页面的 401 视为登录态失效, 清除会话并跳回登录。
      if (router.currentRoute.value.path !== '/login') {
        router.push('/login')
        ElMessage.error('登录已失效，请重新登录')
      }
    } else {
      ElMessage.error(msg)
    }
    return Promise.reject(err)
  },
)

export default http
