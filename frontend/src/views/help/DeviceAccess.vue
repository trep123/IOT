<template>
  <div class="page help">
    <div class="page-head">
      <div><h2>设备接入指南</h2><p>设备凭管理员手动生成的接入 Key，通过 HMAC 签名建立 WebSocket 长连接后上线；下方提供 Python / C / C++ / Java 完整示例</p></div>
    </div>

    <div class="card">
      <h3>接入流程</h3>
      <el-steps :active="7" align-center finish-status="success" class="steps">
        <el-step title="设备建档" description="设备列表 → 新建设备" />
        <el-step title="生成接入 Key" description="管理员手动生成，可批量" />
        <el-step title="烧录" description="设备编号 + Key 写入设备" />
        <el-step title="签名建连" description="ts + nonce + HMAC 签名" />
        <el-step title="注册上线" description="发送 register 上报版本" />
        <el-step title="心跳保活" description="按平台下发周期发送" />
        <el-step title="处理指令" description="收到 command 回 ack / result" />
      </el-steps>
      <el-alert type="info" :closable="false" show-icon class="mt">
        <template #title>
          未生成 Key 的设备无法上线；重新生成或吊销 Key 后，旧 Key 立即失效、已有连接会被断开。Key 的生成、查看、吊销均记入「操作审计」。
        </template>
      </el-alert>
    </div>

    <div class="card">
      <h3>接入参数</h3>
      <el-form label-width="96px" class="params">
        <el-form-item label="平台地址"><el-input v-model="server" style="width: 360px" /></el-form-item>
        <el-form-item label="设备">
          <el-select v-model="deviceId" filterable remote clearable :remote-method="searchDevices" placeholder="输入设备编号搜索" style="width: 360px" @change="onDevice">
            <el-option v-for="d in deviceOptions" :key="d.device_id" :value="d.device_id" :label="`${d.device_id}（${d.name}）`">
              <span class="mono">{{ d.device_id }}</span> <span class="muted">{{ d.name }}</span>
              <el-tag size="small" :type="d.has_key ? 'success' : 'warning'" effect="plain" class="opt-tag">{{ d.has_key ? '已有 Key' : '未生成 Key' }}</el-tag>
            </el-option>
          </el-select>
          <el-button v-if="deviceId && !key" class="ml" :icon="'Key'" @click="fillKey">填入该设备 Key</el-button>
          <el-button v-if="deviceId" link type="primary" class="ml" @click="keyOpen = true">管理接入 Key</el-button>
        </el-form-item>
        <el-form-item label="WebSocket">
          <span class="mono">{{ wsBase }}/ws/device/{{ deviceId || '<设备编号>' }}/?ts=&lt;时间戳&gt;&amp;nonce=&lt;随机串&gt;&amp;sign=&lt;签名&gt;</span>
        </el-form-item>
      </el-form>
    </div>

    <div class="card">
      <h3>鉴权签名</h3>
      <p>Key 只用于本地计算签名，<b>不会在网络上传输</b>。每次建立连接都要重新生成时间戳和随机串：</p>
      <CodeBlock title="签名算法" :code="signDoc" />
      <el-table :data="authParams" size="small" border class="mt">
        <el-table-column prop="name" label="参数" width="110"><template #default="{ row }"><span class="mono">{{ row.name }}</span></template></el-table-column>
        <el-table-column prop="desc" label="说明" />
      </el-table>
      <p class="mt">用下面这组数据自测签名实现是否正确：</p>
      <CodeBlock title="签名测试向量" :code="testVector" />
    </div>

    <div class="card">
      <h3>示例代码</h3>
      <p class="muted">四份示例功能一致：签名建连 → register → 心跳 → 处理指令（先回 ack，执行后回 result）→ 断线指数退避重连。在 <span class="mono">execute()</span> 中对接真实硬件。</p>
      <el-tabs v-model="lang" class="langs">
        <el-tab-pane v-for="ex in examples" :key="ex.key" :label="ex.label" :name="ex.key">
          <el-descriptions :column="1" border size="small" class="env">
            <el-descriptions-item label="运行环境">{{ ex.env }}</el-descriptions-item>
            <el-descriptions-item label="依赖">{{ ex.deps }}</el-descriptions-item>
          </el-descriptions>
          <CodeBlock title="安装依赖 / 编译" lang="bash" :code="ex.build" />
          <CodeBlock title="运行" lang="bash" :code="ex.run(runArgs)" />
          <CodeBlock :title="ex.file" :lang="ex.label" :code="ex.source" :filename="ex.file" max-height="640px" />
          <CodeBlock v-for="extra in ex.extras || []" :key="extra.file" :title="extra.file" :code="extra.source" :filename="extra.file" max-height="360px" />
        </el-tab-pane>
      </el-tabs>
    </div>

    <div class="card">
      <h3>消息协议</h3>
      <p class="muted">所有消息都是 JSON 对象，用 <span class="mono">type</span> 区分。完整协议（含升级流程）见仓库 docs/protocol.md。</p>
      <div class="grid grid-2">
        <div>
          <h4>设备 → 平台</h4>
          <el-table :data="uplink" size="small" border>
            <el-table-column prop="type" label="type" width="140"><template #default="{ row }"><span class="mono">{{ row.type }}</span></template></el-table-column>
            <el-table-column prop="desc" label="说明" />
          </el-table>
        </div>
        <div>
          <h4>平台 → 设备</h4>
          <el-table :data="downlink" size="small" border>
            <el-table-column prop="type" label="type" width="140"><template #default="{ row }"><span class="mono">{{ row.type }}</span></template></el-table-column>
            <el-table-column prop="desc" label="说明" />
          </el-table>
        </div>
      </div>
      <CodeBlock title="一次完整交互" lang="json" :code="flowDemo" class="mt" />
    </div>

    <div class="card">
      <h3>关闭码与排查</h3>
      <p class="muted">鉴权失败时平台先发送 <span class="mono">{"type":"auth_failed","code":…,"message":…}</span>，再以同一 code 关闭连接。</p>
      <el-table :data="closeCodes" size="small" border>
        <el-table-column prop="code" label="关闭码" width="90"><template #default="{ row }"><span class="mono">{{ row.code }}</span></template></el-table-column>
        <el-table-column prop="reason" label="含义" width="220" />
        <el-table-column prop="fix" label="处理建议" />
      </el-table>
    </div>

    <div class="card">
      <h3>常见问题</h3>
      <el-collapse>
        <el-collapse-item v-for="(q, i) in faq" :key="i" :title="q.q" :name="i"><div class="faq">{{ q.a }}</div></el-collapse-item>
      </el-collapse>
    </div>

    <KeyDialog v-if="deviceId" v-model="keyOpen" :device-id="deviceId" @changed="onKeyChanged" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { devices } from '@/api'
import CodeBlock from '@/components/CodeBlock.vue'
import KeyDialog from '@/components/KeyDialog.vue'
import pySrc from '@examples/python/device_client.py?raw'
import cSrc from '@examples/c/device_client.c?raw'
import cMake from '@examples/c/Makefile?raw'
import cppSrc from '@examples/cpp/device_client.cpp?raw'
import cppCmake from '@examples/cpp/CMakeLists.txt?raw'
import javaSrc from '@examples/java/src/main/java/DeviceClient.java?raw'
import javaPom from '@examples/java/pom.xml?raw'

const route = useRoute()
const server = ref(location.origin)
const wsBase = computed(() => server.value.replace(/^http/, 'ws').replace(/\/+$/, ''))
const deviceId = ref('')
const key = ref('')
const deviceOptions = ref([])
const keyOpen = ref(false)
const lang = ref('python')

const runArgs = computed(() => `${server.value.replace(/\/+$/, '')} ${deviceId.value || '<设备编号>'} ${key.value || '<接入Key>'} 1.0.0`)

async function searchDevices(q) {
  deviceOptions.value = (await devices.list({ search: q || '', page_size: 20 })).results
}
function onDevice() { key.value = '' }
async function fillKey() {
  const r = await devices.secret(deviceId.value)
  if (r.secret) key.value = r.secret
  else keyOpen.value = true
}
async function onKeyChanged() { key.value = (await devices.secret(deviceId.value)).secret || ''; searchDevices(deviceId.value) }

onMounted(async () => {
  if (route.query.device) {
    deviceId.value = String(route.query.device)
    await searchDevices(deviceId.value)
  } else {
    await searchDevices('')
  }
})

const signDoc = `ts    = 当前 Unix 时间戳（秒），与平台时间偏差不超过 300 秒（设备需 NTP 校时）
nonce = 每次连接新生成的随机串，8~64 位字母 / 数字 / _ / -（同一 nonce 只能使用一次）
data  = 设备编号 + "\\n" + ts + "\\n" + nonce
sign  = 小写十六进制( HMAC-SHA256( key = 接入Key, message = data ) )

ws://<平台地址>/ws/device/<设备编号>/?ts=<ts>&nonce=<nonce>&sign=<sign>
（平台启用 HTTPS 时使用 wss://）`

const testVector = `设备编号  dev-001
接入 Key  0123456789abcdef0123456789abcdef
ts        1763380000
nonce     a1b2c3d4e5f60718
签名串    "dev-001\\n1763380000\\na1b2c3d4e5f60718"
sign      f3591d4d3ba2f0926578b2d00aca065b387ce58b5206a695c83453ec463e719d`

const authParams = [
  { name: 'ts', desc: 'Unix 秒级时间戳；超出 ±300 秒以 4408 拒绝（偏差可由 IOT_DEVICE_AUTH_MAX_SKEW 调整）' },
  { name: 'nonce', desc: '随机串，防重放；重复使用以 4409 拒绝' },
  { name: 'sign', desc: 'HMAC-SHA256 签名的十六进制字符串（64 位）' },
  { name: 'secret', desc: '兼容方式：直接携带明文 Key（?secret=<Key>）。生产环境建议设置 IOT_DEVICE_AUTH_ALLOW_PLAIN=0 关闭' },
]

const examples = [
  {
    key: 'python', label: 'Python', file: 'device_client.py', env: 'Python 3.8+（Linux / Windows / 树莓派）', deps: 'websockets',
    build: 'pip install websockets', run: (a) => `python device_client.py ${a}`, source: pySrc,
  },
  {
    key: 'c', label: 'C', file: 'device_client.c', env: 'Linux / 嵌入式（GCC、交叉编译工具链），C99',
    deps: 'Mongoose 网络库（单文件 mongoose.c / mongoose.h，自带 HMAC-SHA256，无需 OpenSSL）',
    build: `curl -LO https://raw.githubusercontent.com/cesanta/mongoose/7.20/mongoose.c
curl -LO https://raw.githubusercontent.com/cesanta/mongoose/7.20/mongoose.h
make            # 或：cc -O2 -o device_client device_client.c mongoose.c`,
    run: (a) => `./device_client ${a}`, source: cSrc, extras: [{ file: 'Makefile', source: cMake }],
  },
  {
    key: 'cpp', label: 'C++', file: 'device_client.cpp', env: 'C++17（GCC 8+ / Clang 7+ / MSVC 2019+）',
    deps: 'IXWebSocket、nlohmann/json、OpenSSL',
    build: `sudo apt install -y g++ cmake libssl-dev zlib1g-dev nlohmann-json3-dev
git clone https://github.com/machinezone/IXWebSocket && cd IXWebSocket
cmake -B build -DUSE_TLS=1 && cmake --build build -j && sudo cmake --install build && cd ..
cmake -B build && cmake --build build`,
    run: (a) => `./build/device_client ${a}`, source: cppSrc, extras: [{ file: 'CMakeLists.txt', source: cppCmake }],
  },
  {
    key: 'java', label: 'Java', file: 'DeviceClient.java', env: 'JDK 17+（使用 JDK 自带 java.net.http.WebSocket）',
    deps: 'org.json（Maven：org.json:json）',
    build: 'mvn -q package      # 源码放在 src/main/java/DeviceClient.java',
    run: (a) => `java -jar target/device-client.jar ${a}`, source: javaSrc, extras: [{ file: 'pom.xml', source: javaPom }],
  },
]

const uplink = [
  { type: 'register', desc: '连接后第一条消息，携带 version（当前版本号），设备置为在线' },
  { type: 'heartbeat', desc: '周期心跳；周期由 registered.heartbeat_interval 下发，丢失 N 次判离线' },
  { type: 'ack', desc: '收到指令后立即回复，携带 command_id' },
  { type: 'result', desc: '执行结果：command_id、code（0 成功）、data、message' },
  { type: 'upgrade_progress', desc: '升级阶段上报：DOWNLOADING / VERIFYING / INSTALLING / REBOOTING / FAILED' },
  { type: 'version_report', desc: '单独上报版本号' },
]
const downlink = [
  { type: 'registered', desc: '注册成功：server_time、heartbeat_interval（秒）' },
  { type: 'command', desc: '控制指令：command_id、code、params、timeout；OTA_UPGRADE 为升级通知' },
  { type: 'auth_failed', desc: '鉴权失败：code、message，随后以 code 关闭连接' },
  { type: 'error', desc: '消息格式错误等提示' },
]
const flowDemo = `→ {"type":"register","version":"1.0.0"}
← {"type":"registered","server_time":"2026-11-17T23:00:00+08:00","heartbeat_interval":30}
→ {"type":"heartbeat"}                                   // 每 30 秒
← {"type":"command","command_id":101,"code":"REBOOT","params":{"delay":5},"timeout":60}
→ {"type":"ack","command_id":101}
→ {"type":"result","command_id":101,"code":0,"data":{"ok":true},"message":""}`

const closeCodes = [
  { code: 4400, reason: '缺少或格式错误的鉴权参数', fix: '检查 ts 为整数秒、nonce 为 8~64 位字母数字、sign 已携带' },
  { code: 4401, reason: '设备不存在 / Key 或签名错误', fix: '核对设备编号与 Key；签名串用 \\n 分隔且顺序为 编号、ts、nonce；Key 重新生成后需更新设备' },
  { code: 4403, reason: '设备尚未生成接入 Key（或已吊销）', fix: '在「设备详情 → 接入 Key」中生成' },
  { code: 4408, reason: '时间戳偏差超过允许范围', fix: '设备开启 NTP 校时' },
  { code: 4409, reason: 'nonce 重复使用', fix: '每次连接重新生成随机 nonce，不要复用 URL' },
  { code: 4000, reason: '被同一设备的新连接顶替', fix: '正常现象；若反复出现，检查是否有两台设备使用了相同编号' },
]
const faq = [
  { q: '设备一直显示离线？', a: '确认：① 已生成接入 Key 并烧录到设备；② 连接后第一条消息是 register；③ 心跳周期不大于 registered 下发的 heartbeat_interval。心跳超过「周期 × 丢失次数」未到达会被判离线并断开连接，设备应自动重连。' },
  { q: 'Key 泄露了怎么办？', a: '在设备详情中「重新生成」，旧 Key 立即失效、当前连接被断开，把新 Key 写入设备即可；若设备已报废，选择「吊销」。' },
  { q: '量产时如何批量分配 Key？', a: '先批量建档，在设备列表勾选设备后点「批量生成 Key」，下载 CSV（设备编号、接入 Key）交给产线烧录。' },
  { q: '可以不签名、直接带 Key 吗？', a: '可以使用兼容方式 ?secret=<Key>，但 Key 会出现在 URL 和代理日志中。生产环境建议通过 HTTPS（wss://）接入，并设置 IOT_DEVICE_AUTH_ALLOW_PLAIN=0 只允许签名方式。' },
  { q: '升级包怎么下载？', a: '收到 OTA_UPGRADE 指令后，用 params.package.url 下载，附带与上线相同的鉴权参数：?device_id=<编号>&ts=…&nonce=…&sign=…（也可放在请求头 X-Device-Id / X-Device-Ts / X-Device-Nonce / X-Device-Sign）。完整流程参考 docs/protocol.md 与 simulator/device_sim.py。' },
  { q: '同一台设备重复连接会怎样？', a: '新连接会顶替旧连接，旧连接以 4000 关闭。示例代码收到 4000 会立即重连，请确保设备编号全局唯一。' },
]
</script>

<style scoped>
.help h3 { margin: 0 0 12px; font-size: 16px; }
.help h4 { margin: 4px 0 8px; font-size: 14px; color: #475569; }
.help p { color: #475569; line-height: 1.7; margin: 6px 0; font-size: 14px; }
.steps { margin: 8px 0 4px; }
.params :deep(.el-form-item) { margin-bottom: 12px; }
.ml { margin-left: 10px; }
.opt-tag { margin-left: 8px; }
.env { margin-bottom: 4px; }
.faq { white-space: pre-line; line-height: 1.8; color: #475569; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 1100px) { .grid-2 { grid-template-columns: 1fr; } }
</style>
