# 管理端前端设计

管理端是独立的单页应用（`frontend/`），只通过 DRF 接口（`/api/`）和管理端 WebSocket（`/ws/admin/`）与后端交互，
不依赖 Django 模板。构建产物由 Django 以 `/static/` 提供，前端路由由后端兜底返回 `index.html`。

## 1. 技术选型

| 方面 | 选择 | 理由 |
|---|---|---|
| 框架 | Vue 3（`<script setup>`）+ Vite | 组合式 API 便于抽取列表、实时刷新等通用逻辑；Vite 构建快 |
| 组件库 | Element Plus（中文语言包） | 后台场景组件齐全：表格、筛选、分步表单、对话框、时间范围 |
| 状态 | Pinia | 登录态与 WebSocket 连接是全局单例 |
| 请求 | axios | 统一注入 Token、统一解析 DRF 错误 |
| 图表 | ECharts（按需引入） | 在线率、型号/版本分布、升级阶段分布 |
| 时间 | dayjs | 「几秒前」等相对时间 |

## 2. 信息架构

```
登录
└─ 主框架（侧边栏 + 顶栏：面包屑 / 实时推送状态与事件流 / 用户菜单）
   ├─ 运行总览                     在线率、型号与版本分布、进行中的升级任务与批次、最近状态变更、实时事件
   ├─ 设备在线管理
   │  ├─ 设备列表 → 设备详情       组合筛选、在线统计、导出、建档（一次性展示密钥）、单发指令、勾选后批量控制
   │  │                           详情：心跳/上下线时间、指令记录、状态变更时间线、升级记录、密钥查看与重置
   │  ├─ 设备分组                 分组维护，设备数可跳转到筛选后的设备列表
   │  └─ 状态变更记录             原因、上一状态持续时长、时间区间筛选、导出
   ├─ 设备控制
   │  ├─ 指令记录                 全生命周期时间点、参数与结果展开查看
   │  ├─ 批量控制 → 批次详情       分步创建；进度条（成功/失败/取消）；明细按状态筛选；取消、失败重试
   │  └─ 指令模板                 参数定义表格化编辑（类型/必填/范围/可选值/默认值）、关键操作开关
   ├─ 系统版本管理
   │  ├─ 版本与升级包             版本 CRUD、发布/废弃；展开行管理升级包（拖拽上传、浏览器内算 SHA-256、重新校验、下载）
   │  └─ 升级任务 → 任务详情       创建（目标版本、范围、灰度比例、指定灰度设备、失败率阈值）
   │                              详情：流程步骤条、统计卡、阶段分布图、自动排除设备、逐台进度、开始/推进全量/暂停/继续/重试/回滚
   └─ 操作审计                    类型/对象/操作人/结果/时间筛选，详情 JSON 展开，导出
```

## 3. 关键交互

- **在线状态是前置条件**：单发指令可选「离线直接拒绝 / 排队上线后下发」；批量控制在第三步选择离线策略；目标范围选择器实时显示「匹配 N 台，其中在线 M 台」。
- **关键操作**：模板标记为关键时，单发与批量都会先弹出二次确认框（说明设备、指令、参数），确认后才带 `confirm=true` 提交；表单顶部有红色提示，结果写入审计。
- **批量控制向导**：① 选指令并按 `param_schema` 动态生成参数表单（整数/小数/布尔/枚举/字符串，含范围与默认值提示）→ ② 目标范围（指定设备 / 分组 / 条件 / 全部）→ ③ 离线策略、并发上限与汇总确认。
- **灰度发布**：任务详情顶部步骤条展示「已创建 → 灰度 → 全量 → 完成/已回滚」；灰度全部结束后出现「推进全量」并在确认框里展示灰度成功/失败数；自动暂停时以红色提示给出原因，并说明「继续」不再计入已确认的失败。
- **回滚**：只列出比当前目标版本更旧的可发布版本，可设置回滚的灰度比例与失败率阈值，提交后跳转到新的回滚任务。
- **升级进度**：逐台记录用五段进度条（下载 → 校验 → 安装 → 重启 → 成功）表示当前阶段，失败整段标红。

## 4. 实时刷新

`stores/realtime.js` 维护唯一的 `ws/admin/?token=` 连接（断线指数退避重连），按事件名分发：

| 事件 | 刷新的页面 |
|---|---|
| `device_status` / `device_version` | 总览、设备列表与统计、设备详情、状态变更记录 |
| `command_update` | 指令记录、设备详情、批次明细、单发对话框中的执行结果 |
| `batch_update` | 批量控制列表、批次详情、总览 |
| `task_update` / `upgrade_record` | 升级任务列表与详情、设备详情的升级记录、总览 |

页面通过 `useRealtimeRefresh(events, fn, { filter })` 订阅：按对象 ID 过滤无关事件，并节流合并突发事件，组件卸载时自动退订。

## 5. 与 DRF 的约定

- 列表统一使用 `useTable`：传 `page` / `page_size` / `ordering`，读取 `count` / `results`；表头排序映射为 `ordering=-field`。
- 空筛选值不发送；多选筛选拼成逗号分隔（对应 `__in` 过滤器）。
- 错误统一解析：`{"detail": ...}` 或 `{"字段": ["原因"]}` 转为一条中文提示；`401` 回到登录页。
- 导出 CSV 用带 Token 的请求下载 Blob，避免 Token 出现在 URL 中。

## 6. 目录

```
frontend/
  index.html  vite.config.js  package.json
  src/
    main.js  App.vue
    api/        http.js（axios、Token、DRF 错误解析、下载）  index.js（按资源封装全部接口）
    stores/     auth.js（登录态）  realtime.js（管理端 WebSocket）
    router/     menu.js（菜单与页面）  index.js（路由与登录守卫）
    utils/      dict.js（枚举中文与颜色）  format.js  params.js  useTable.js  useRealtimeRefresh.js
    components/ Layout  EventFeed  DictTag  StatCard  EChart  DevicePicker  ScopePicker
                ParamForm  CommandDialog  BatchDialog  UpgradeProgress
    views/      Login  Dashboard  Devices  DeviceDetail  Groups  StatusLogs  Commands
                Batches  BatchDetail  Templates  Versions  Tasks  TaskDetail  Audit
```

## 7. 开发与部署

```bash
cd frontend && npm install
npm run dev        # http://localhost:5173 ，/api 与 /ws 代理到 IOT_BACKEND（默认 http://127.0.0.1:8000）
npm run build      # 输出 frontend/dist，由 Django 在 / 提供
```

Docker 镜像分两阶段：先用 Node 构建前端，再把 `dist` 拷进 Python 镜像，单个 daphne 进程同时提供 API、WebSocket 与页面。
