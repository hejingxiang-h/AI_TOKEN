import { management } from '../api/management'
import ManagementView from '../views/ManagementView.vue'
import { useAuth } from '../stores/auth'
import { createRouter, createWebHistory } from 'vue-router'
import AppLayout from '../layouts/AppLayout.vue'
import { sections } from '../mock/catalog'
import DashboardView from '../views/DashboardView.vue'
import LoginView from '../views/LoginView.vue'
import RecordsView from '../views/RecordsView.vue'
import RiskView from '../views/RiskView.vue'
import SystemHealthView from '../views/SystemHealthView.vue'
const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: LoginView, meta: { title: '登录' } },
    {
      path: '/',
      component: AppLayout,
      children: [
        { path: '', redirect: '/dashboard' },
        { path: 'dashboard', component: DashboardView, meta: { title: '首页工作台', live: true } },
        {
          path: 'statistics',
          component: DashboardView,
          props: { statistics: true },
          meta: { title: 'Token 统计', live: true },
        },
        ...management.map((section) => ({
          path: section.path,
          component: ManagementView,
          props: { section },
          meta: { title: section.title, live: true },
        })),
        {
          path: 'calls',
          component: DashboardView,
          props: { recordsOnly: true },
          meta: { title: '调用记录', live: true },
        },
        {
          path: 'audit',
          component: RiskView,
          props: { audit: true },
          meta: { title: '操作日志', live: true },
        },
        { path: 'alerts', component: RiskView, meta: { title: '风险告警', live: true } },
        ...sections
          .filter((section) => !['calls', 'audit', 'alerts'].includes(section.path))
          .map((section) => ({
            path: section.path,
            component: RecordsView,
            props: { section },
            meta: { title: section.title },
          })),
        { path: 'system/health', component: SystemHealthView, meta: { title: '系统健康' } },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
  ],
})
router.beforeEach(async (to) => {
  const auth = useAuth()
  await auth.restore()
  if (to.path !== '/login' && !auth.user) return { path: '/login', query: { next: to.fullPath } }
  if (to.path === '/login' && auth.user) return '/dashboard'
})
export default router
