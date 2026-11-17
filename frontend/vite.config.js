import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// 后端地址：开发时通过代理转发 /api 与 /ws，避免跨域
const backend = process.env.IOT_BACKEND || 'http://127.0.0.1:8000'

export default defineConfig(({ command }) => ({
  // 构建产物由 Django staticfiles 提供，统一挂在 /static/ 下
  base: command === 'build' ? '/static/' : '/',
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      // 设备接入示例源码（帮助页以 ?raw 方式引入，与仓库 examples/ 保持唯一来源）
      '@examples': fileURLToPath(new URL('../examples/device', import.meta.url)),
    },
  },
  server: {
    fs: { allow: ['..'] },
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': { target: backend, changeOrigin: true },
      '/ws': { target: backend.replace(/^http/, 'ws'), ws: true, changeOrigin: true },
      '/admin': { target: backend, changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    chunkSizeWarningLimit: 1500,
  },
}))
