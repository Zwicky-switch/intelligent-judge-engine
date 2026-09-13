import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
// 仅全局注册项目实际使用的图标(21个), 替代全量注册(数百个), 减小打包体积
import {
  ArrowLeft, Back, Clock, Cpu, DataAnalysis, Delete, Document, EditPen,
  Files, Grid, Histogram, Lock, MagicStick, Monitor, Plus, Position,
  Refresh, RefreshRight, Search, SwitchButton, User,
} from '@element-plus/icons-vue'

import App from './App.vue'
import router from './router'
import './styles/main.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: zhCn })
// 按需注册图标
const ICONS = {
  ArrowLeft, Back, Clock, Cpu, DataAnalysis, Delete, Document, EditPen,
  Files, Grid, Histogram, Lock, MagicStick, Monitor, Plus, Position,
  Refresh, RefreshRight, Search, SwitchButton, User,
}
for (const [name, comp] of Object.entries(ICONS)) {
  app.component(name, comp)
}
app.mount('#app')
