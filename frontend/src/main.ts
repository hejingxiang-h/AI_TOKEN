import { ElMessage } from 'element-plus'
import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import './assets/base.css'
import './assets/admin.css'
import 'element-plus/theme-chalk/base.css'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/dialog/style/css'
import 'element-plus/es/components/menu/style/css'
import 'element-plus/es/components/menu-item/style/css'
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/skeleton/style/css'
import 'element-plus/es/components/skeleton-item/style/css'
import router from './router'

const app = createApp(App)

app.config.errorHandler = () => ElMessage.error('页面发生错误，请刷新后重试')
router.onError(() => ElMessage.error('页面加载失败，请刷新后重试'))

app.use(createPinia())
app.use(router)
app.mount('#app')
