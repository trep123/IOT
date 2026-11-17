<template>
  <div class="login">
    <div class="hero">
      <div class="brand"><div class="logo"><el-icon><Connection /></el-icon></div>IoT 设备管理平台</div>
      <h1>设备在线 · 远程控制 · 固件升级</h1>
      <p>一处掌握所有设备的在线状态，批量下发指令，灰度发布新版本，异常时一键回滚。</p>
      <ul>
        <li><el-icon><Monitor /></el-icon>心跳检测与在线状态实时推送</li>
        <li><el-icon><Operation /></el-icon>单发 / 批量控制，关键操作二次确认与审计</li>
        <li><el-icon><Box /></el-icon>灰度 → 全量发布，失败率超阈值自动暂停</li>
      </ul>
    </div>
    <div class="panel">
      <el-form class="form" :model="form" @submit.prevent="submit">
        <h2>登录</h2>
        <p class="muted">使用平台账号登录管理控制台</p>
        <el-form-item><el-input v-model="form.username" size="large" placeholder="用户名" prefix-icon="User" /></el-form-item>
        <el-form-item><el-input v-model="form.password" size="large" type="password" show-password placeholder="密码" prefix-icon="Lock" /></el-form-item>
        <el-alert v-if="err" :title="err" type="error" :closable="false" show-icon class="err" />
        <el-button type="primary" size="large" native-type="submit" :loading="loading" class="btn">登 录</el-button>
        <p class="tip muted">演示环境执行 <code>python manage.py init_demo</code> 后可用 admin / admin123 登录</p>
      </el-form>
    </div>
  </div>
</template>
<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuth } from '@/stores/auth'
import { drfError } from '@/api/http'

const form = reactive({ username: '', password: '' })
const loading = ref(false)
const err = ref('')
const auth = useAuth()
const router = useRouter()
const route = useRoute()
async function submit() {
  if (!form.username || !form.password) { err.value = '请输入用户名和密码'; return }
  loading.value = true
  err.value = ''
  try {
    await auth.login(form.username, form.password)
    router.replace(route.query.next || '/dashboard')
  } catch (e) {
    err.value = e?.response?.status === 400 ? '用户名或密码错误' : drfError(e)
  } finally { loading.value = false }
}
</script>
<style scoped>
.login { display: grid; grid-template-columns: 1.2fr 1fr; min-height: 100vh; }
.hero { background: radial-gradient(circle at 20% 20%, #3b82f6 0, transparent 45%), linear-gradient(135deg, #1e1b4b, #172554 60%, #0c4a6e); color: #fff; padding: 64px 72px; display: flex; flex-direction: column; justify-content: center; }
.brand { display: flex; align-items: center; gap: 12px; font-size: 18px; font-weight: 600; margin-bottom: 48px; }
.logo { width: 40px; height: 40px; border-radius: 10px; background: #3b82f6; display: grid; place-items: center; font-size: 22px; }
h1 { font-size: 34px; margin: 0 0 16px; letter-spacing: 1px; }
.hero p { color: #c7d2fe; font-size: 15px; line-height: 1.8; max-width: 460px; margin: 0 0 32px; }
.hero ul { list-style: none; padding: 0; margin: 0; display: grid; gap: 14px; color: #e0e7ff; }
.hero li { display: flex; align-items: center; gap: 10px; }
.hero li .el-icon { width: 30px; height: 30px; border-radius: 8px; background: rgba(255,255,255,.12); }
.panel { display: grid; place-items: center; background: #fff; }
.form { width: 360px; }
.form h2 { margin: 0 0 6px; font-size: 24px; }
.form > p { margin: 0 0 28px; }
.err { margin-bottom: 16px; }
.btn { width: 100%; }
.tip { font-size: 12px; margin-top: 18px; text-align: center; }
code { background: #f1f5f9; padding: 1px 5px; border-radius: 4px; }
@media (max-width: 900px) { .login { grid-template-columns: 1fr; } .hero { display: none; } }
</style>
