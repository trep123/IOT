<template>
  <el-container class="layout">
    <el-aside :width="collapsed ? '64px' : '220px'" class="aside">
      <div class="brand" @click="$router.push('/dashboard')">
        <div class="logo"><el-icon><Connection /></el-icon></div>
        <span v-show="!collapsed">IoT 设备管理</span>
      </div>
      <el-menu :default-active="active" :collapse="collapsed" router class="menu"
               background-color="transparent" text-color="#c7d2fe" active-text-color="#ffffff"
               :default-openeds="openeds">
        <template v-for="m in menu" :key="m.title">
          <el-sub-menu v-if="m.children" :index="m.title">
            <template #title><el-icon><component :is="m.icon" /></el-icon><span>{{ m.title }}</span></template>
            <el-menu-item v-for="c in m.children" :key="c.path" :index="c.path">{{ c.title }}</el-menu-item>
          </el-sub-menu>
          <el-menu-item v-else :index="m.path">
            <el-icon><component :is="m.icon" /></el-icon><template #title>{{ m.title }}</template>
          </el-menu-item>
        </template>
      </el-menu>
    </el-aside>
    <el-container class="main-wrap">
      <el-header class="header">
        <div class="left">
          <el-icon class="toggle" @click="collapsed = !collapsed"><Fold v-if="!collapsed" /><Expand v-else /></el-icon>
          <el-breadcrumb separator="/">
            <el-breadcrumb-item v-if="parentTitle" :to="route.meta.parent">{{ parentTitle }}</el-breadcrumb-item>
            <el-breadcrumb-item>{{ route.meta.title }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="right">
          <el-popover placement="bottom-end" :width="380" trigger="click">
            <template #reference>
              <div class="rt" :class="{ on: rt.connected }">
                <span class="dot" />{{ rt.connected ? '实时推送已连接' : '实时推送重连中' }}
                <el-badge v-if="rt.events.length" :value="rt.events.length" :max="99" class="badge" />
              </div>
            </template>
            <div class="feed-title">最近实时事件</div>
            <EventFeed :events="rt.events" :limit="20" />
          </el-popover>
          <el-dropdown @command="onCmd">
            <span class="user"><el-avatar :size="28" class="avatar">{{ (auth.username || 'U')[0].toUpperCase() }}</el-avatar>{{ auth.username }}</span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="api"><el-icon><Link /></el-icon>可浏览 API</el-dropdown-item>
                <el-dropdown-item command="admin"><el-icon><Setting /></el-icon>Django Admin</el-dropdown-item>
                <el-dropdown-item command="logout" divided><el-icon><SwitchButton /></el-icon>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>
      <el-main class="main">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in"><component :is="Component" :key="route.fullPath" /></transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { menu } from '@/router/menu'
import { useAuth } from '@/stores/auth'
import { useRealtime } from '@/stores/realtime'
import EventFeed from './EventFeed.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuth()
const rt = useRealtime()
const collapsed = ref(false)
const active = computed(() => route.meta.parent || route.path)
const openeds = menu.filter((m) => m.children).map((m) => m.title)
const parentTitle = computed(() => {
  const p = route.meta.parent
  return p && menu.flatMap((m) => m.children || [m]).find((m) => m.path === p)?.title
})

function onCmd(c) {
  if (c === 'logout') { rt.disconnect(); auth.logout(); router.push('/login') }
  if (c === 'api') window.open('/api/', '_blank')
  if (c === 'admin') window.open('/admin/', '_blank')
}
onMounted(() => rt.connect())
onBeforeUnmount(() => rt.disconnect())
</script>

<style scoped>
.layout { height: 100vh; }
.aside { background: linear-gradient(180deg, #1e1b4b 0%, #172554 100%); transition: width .2s; overflow-x: hidden; }
.brand { height: 60px; display: flex; align-items: center; gap: 10px; padding: 0 16px; color: #fff; font-weight: 600; font-size: 16px; cursor: pointer; white-space: nowrap; }
.logo { width: 32px; height: 32px; flex: none; border-radius: 8px; background: #3b82f6; display: grid; place-items: center; font-size: 18px; }
.menu { border-right: none; }
.menu :deep(.el-menu-item.is-active) { background: rgba(59, 130, 246, .35) !important; border-radius: 6px; }
.menu :deep(.el-menu-item), .menu :deep(.el-sub-menu__title) { margin: 2px 8px; border-radius: 6px; height: 44px; }
.menu :deep(.el-menu-item:hover), .menu :deep(.el-sub-menu__title:hover) { background: rgba(255, 255, 255, .08) !important; }
.menu :deep(.el-menu) { background: transparent !important; }
.header { height: 60px; background: #fff; border-bottom: 1px solid var(--el-border-color-light); display: flex; align-items: center; justify-content: space-between; }
.left, .right { display: flex; align-items: center; gap: 18px; }
.toggle { font-size: 20px; cursor: pointer; color: #64748b; }
.rt { display: flex; align-items: center; gap: 6px; font-size: 13px; color: #94a3b8; cursor: pointer; padding: 4px 10px; border-radius: 14px; background: #f1f5f9; }
.rt.on { color: #15803d; background: #f0fdf4; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: #cbd5e1; }
.rt.on .dot { background: #22c55e; box-shadow: 0 0 0 3px rgba(34, 197, 94, .2); }
.badge { margin-left: 4px; }
.badge :deep(.el-badge__content) { position: static; transform: none; }
.user { display: flex; align-items: center; gap: 8px; cursor: pointer; color: #334155; outline: none; }
.avatar { background: #2563eb; }
.main { background: var(--bg); padding: 20px; overflow-y: auto; }
.feed-title { font-weight: 600; margin-bottom: 8px; }
</style>
