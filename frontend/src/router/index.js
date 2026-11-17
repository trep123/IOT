import { createRouter, createWebHistory } from 'vue-router'
import { getToken } from '@/api/http'
import Layout from '@/components/Layout.vue'
import { menu } from './menu'

export { menu }

const flat = menu.flatMap((m) => (m.children ? m.children : [m]))

const routes = [
  { path: '/login', component: () => import('@/views/Login.vue'), meta: { public: true, title: '登录' } },
  {
    path: '/',
    component: Layout,
    redirect: '/dashboard',
    children: [
      ...flat.map((m) => ({ path: m.path.slice(1), component: m.component, meta: { title: m.title } })),
      { path: 'devices/:id', component: () => import('@/views/DeviceDetail.vue'), meta: { title: '设备详情', parent: '/devices' } },
      { path: 'batches/:id', component: () => import('@/views/BatchDetail.vue'), meta: { title: '批次详情', parent: '/batches' } },
      { path: 'tasks/:id', component: () => import('@/views/TaskDetail.vue'), meta: { title: '升级任务详情', parent: '/tasks' } },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach((to) => {
  if (!to.meta.public && !getToken()) return { path: '/login', query: { next: to.fullPath } }
  if (to.path === '/login' && getToken()) return '/dashboard'
  document.title = `${to.meta.title || ''} · IoT 设备管理平台`
})

export default router
