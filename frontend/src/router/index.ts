import { createRouter, createWebHistory } from 'vue-router'
import AppLayout from '../components/AppLayout.vue'

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
      ],
    },
  ],
})

// 路由守卫：未登录跳 /login
router.beforeEach((to) => {
  const token = localStorage.getItem('edututor_token')
  if (to.path !== '/login' && !token) return '/login'
  if (to.path === '/login' && token) return '/chat'
  return true
})

export default router