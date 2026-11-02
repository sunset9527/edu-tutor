import { createRouter, createWebHistory } from 'vue-router'
import { ElMessage } from 'element-plus'
import AppLayout from '../components/AppLayout.vue'
import { readStoredUser, resolveRouteAccess } from './adminAccess'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('../views/LoginView.vue') },
    {
      path: '/',
      component: AppLayout,
      children: [
        { path: '', redirect: '/chat' },
        { path: 'chat', name: 'chat', component: () => import('../views/ChatView.vue') },
        { path: 'quiz', name: 'quiz', component: () => import('../views/QuizView.vue') },
        { path: 'students', name: 'students', component: () => import('../views/StudentView.vue') },
        { path: 'memories', name: 'memories', component: () => import('../views/MemoryView.vue') },
        { path: 'graph', name: 'graph', component: () => import('../views/GraphView.vue') },
        { path: 'report', name: 'report', component: () => import('../views/ReportView.vue') },
        { path: 'settings', name: 'settings', component: () => import('../views/SettingsView.vue') },
        {
          path: 'admin/knowledge',
          name: 'knowledge-admin',
          meta: { requiresAdmin: true },
          component: () => import('../views/KnowledgeAdminView.vue'),
        },
      ],
    },
  ],
})

// 路由守卫：未登录跳 /login
router.beforeEach((to) => {
  const token = localStorage.getItem('edututor_token')
  const result = resolveRouteAccess(
    { path: to.path, requiresAdmin: Boolean(to.meta.requiresAdmin) },
    token || '',
    readStoredUser(),
  )
  if (result === '/chat' && to.meta.requiresAdmin) {
    ElMessage.warning('当前账号没有教材治理权限')
  }
  return result
})

export default router
