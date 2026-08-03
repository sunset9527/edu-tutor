import { createRouter, createWebHistory } from 'vue-router'
import AppLayout from '../components/AppLayout.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: AppLayout,
      children: [
        { path: '', redirect: '/chat' },
        { path: 'chat', name: 'chat', component: () => import('../views/ChatView.vue') },
        { path: 'students', name: 'students', component: () => import('../views/StudentView.vue') },
        { path: 'memories', name: 'memories', component: () => import('../views/MemoryView.vue') },
        { path: 'graph', name: 'graph', component: () => import('../views/GraphView.vue') },
        { path: 'report', name: 'report', component: () => import('../views/ReportView.vue') },
      ],
    },
  ],
})

export default router