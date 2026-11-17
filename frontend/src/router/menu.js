// 侧边栏菜单与页面路由的单一来源（独立文件，避免 Layout ↔ router 循环引用）
export const menu = [
  { path: '/dashboard', title: '运行总览', icon: 'DataBoard', component: () => import('@/views/Dashboard.vue') },
  {
    title: '设备在线管理', icon: 'Monitor', children: [
      { path: '/devices', title: '设备列表', component: () => import('@/views/Devices.vue') },
      { path: '/groups', title: '设备分组', component: () => import('@/views/Groups.vue') },
      { path: '/status-logs', title: '状态变更记录', component: () => import('@/views/StatusLogs.vue') },
    ],
  },
  {
    title: '设备控制', icon: 'Operation', children: [
      { path: '/commands', title: '指令记录', component: () => import('@/views/Commands.vue') },
      { path: '/batches', title: '批量控制', component: () => import('@/views/Batches.vue') },
      { path: '/templates', title: '指令模板', component: () => import('@/views/Templates.vue') },
    ],
  },
  {
    title: '系统版本管理', icon: 'Box', children: [
      { path: '/versions', title: '版本与升级包', component: () => import('@/views/Versions.vue') },
      { path: '/tasks', title: '升级任务', component: () => import('@/views/Tasks.vue') },
    ],
  },
  { path: '/audit', title: '操作审计', icon: 'Document', component: () => import('@/views/Audit.vue') },
  {
    title: '帮助', icon: 'QuestionFilled', children: [
      { path: '/help/device-access', title: '设备接入指南', component: () => import('@/views/help/DeviceAccess.vue') },
    ],
  },
]
