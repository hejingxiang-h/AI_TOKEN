import { createRouter, createWebHistory } from 'vue-router'
import AppLayout from '../layouts/AppLayout.vue'
import { sections } from '../mock/catalog'
import DashboardView from '../views/DashboardView.vue'
import LoginView from '../views/LoginView.vue'
import RecordsView from '../views/RecordsView.vue'
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
        { path: 'dashboard', component: DashboardView, meta: { title: '首页工作台' } },
        {
          path: 'statistics',
          component: DashboardView,
          props: { statistics: true },
          meta: { title: 'Token 统计' },
        },
        ...sections.map((section) => ({
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
router.beforeEach((to) => {
  try {
    const signed = Boolean(sessionStorage.getItem('gateway-demo-session'))
    if (to.path !== '/login' && !signed) return { path: '/login', query: { next: to.fullPath } }
    if (to.path === '/login' && signed) return '/dashboard'
  } catch {
    if (to.path !== '/login') return '/login'
  }
})
export default router
