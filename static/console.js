/* IoT 设备管理平台 - 管理端（原生 JS，调用标准 DRF 接口） */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const tag = (v, label) => `<span class="tag ${esc(v)}">${esc(label || v)}</span>`;
const fmt = (t) => (t ? new Date(t).toLocaleString("zh-CN", { hour12: false }) : "");
let token = localStorage.getItem("iot_token");

function toast(msg, error = false) {
  const d = document.createElement("div");
  d.textContent = msg;
  if (error) d.className = "error";
  $("#toast").append(d);
  setTimeout(() => d.remove(), 4000);
}

function errText(data) {
  if (!data) return "请求失败";
  if (typeof data === "string") return data;
  if (data.detail) return data.detail;
  return Object.entries(data).map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`).join("；");
}

async function api(path, { method = "GET", body, form, query } = {}) {
  let url = "/api/" + path.replace(/^\//, "");
  if (query) {
    const q = new URLSearchParams(Object.entries(query).filter(([, v]) => v !== "" && v != null));
    if ([...q].length) url += (url.includes("?") ? "&" : "?") + q;
  }
  const headers = { Authorization: `Token ${token}` };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const resp = await fetch(url, { method, headers, body: form || (body !== undefined ? JSON.stringify(body) : undefined) });
  if (resp.status === 401) { logout(); throw new Error("请重新登录"); }
  const data = resp.headers.get("content-type")?.includes("json") ? await resp.json() : null;
  if (!resp.ok) { const m = errText(data); toast(m, true); throw new Error(m); }
  return data;
}

async function download(path, query) {
  const q = new URLSearchParams(Object.entries(query || {}).filter(([, v]) => v));
  const resp = await fetch(`/api/${path}?${q}`, { headers: { Authorization: `Token ${token}` } });
  const blob = await resp.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = path.split("/").filter(Boolean)[0] + ".csv";
  a.click();
}

const formData = (form) => {
  const o = {};
  new FormData(form).forEach((v, k) => { if (!(v instanceof File)) o[k] = v; });
  for (const el of form.querySelectorAll("input[type=datetime-local]")) if (o[el.name]) o[el.name] = new Date(o[el.name]).toISOString();
  return o;
};

function parseJSON(text, field) {
  try { return text ? JSON.parse(text) : {}; } catch { toast(`${field} 不是合法 JSON`, true); throw new Error("bad json"); }
}

function buildScope(type, value) {
  if (type === "all") return { all: true };
  if (type === "group_id") return { group_id: Number(value) };
  if (type === "filters") return { filters: parseJSON(value, "筛选条件") };
  return { device_ids: value.split(/[,\s]+/).filter(Boolean) };
}

/* ---------------- 列表 + 分页 ---------------- */
function makeList({ table, pager, path, columns, filterForm, extraQuery }) {
  const state = { page: 1 };
  async function load(page = state.page) {
    state.page = page;
    const query = { page, ...(filterForm ? formData($(filterForm)) : {}), ...(extraQuery ? extraQuery() : {}) };
    const data = await api(path, { query });
    $(table).innerHTML = `<tr>${columns.map((c) => `<th>${c[0]}</th>`).join("")}</tr>` +
      data.results.map((r) => `<tr>${columns.map((c) => `<td class="${c[2] || ""}">${c[1](r)}</td>`).join("")}</tr>`).join("");
    const pages = Math.max(1, Math.ceil(data.count / 20));
    $(pager).innerHTML = `共 ${data.count} 条 · 第 ${page}/${pages} 页
      <button ${data.previous ? "" : "disabled"} data-p="${page - 1}">上一页</button>
      <button ${data.next ? "" : "disabled"} data-p="${page + 1}">下一页</button>`;
    $$("button[data-p]", $(pager)).forEach((b) => (b.onclick = () => load(Number(b.dataset.p))));
    return data;
  }
  if (filterForm) $(filterForm).addEventListener("submit", (e) => { e.preventDefault(); load(1); });
  return { load, reload: () => load(state.page) };
}

/* ---------------- 设备 ---------------- */
const deviceList = makeList({
  table: "#deviceTable", pager: "#devicePager", path: "devices/", filterForm: "#deviceFilter",
  columns: [
    ["编号", (d) => esc(d.device_id)], ["名称", (d) => esc(d.name)], ["型号", (d) => esc(d.model)],
    ["分组", (d) => esc(d.group_name)], ["当前版本", (d) => esc(d.current_version)],
    ["在线状态", (d) => tag(d.online_status, d.online_status_display)],
    ["最近上线", (d) => fmt(d.last_online_at)], ["最近心跳", (d) => fmt(d.last_heartbeat_at)],
    ["操作", (d) => `<span class="actions"><button onclick="showStatusLogs('${esc(d.device_id)}')">状态记录</button><button onclick="showSecret('${esc(d.device_id)}')">接入密钥</button><button onclick="quickCommand('${esc(d.device_id)}')">控制</button></span>`],
  ],
});

async function loadDeviceStats() {
  const s = await api("devices/summary/");
  $("#deviceStats").innerHTML = `<div class="stat">设备总数<b>${s.total}</b></div><div class="stat">在线<b style="color:#16a34a">${s.online}</b></div><div class="stat">离线<b style="color:#6b7280">${s.offline}</b></div>` +
    s.by_version.map((v) => `<div class="stat">v${esc(v.current_version || "-")}<b>${v.count}</b></div>`).join("");
}

function modal(html) { $("#modalBody").innerHTML = html; $("#modal").showModal(); }

window.showStatusLogs = async (id) => {
  const data = await api(`devices/${id}/status-logs/`);
  modal(`<h3>${esc(id)} 状态变更记录</h3><table><tr><th>时间</th><th>变更</th><th>原因</th><th>上一状态持续</th></tr>` +
    data.results.map((l) => `<tr><td>${fmt(l.occurred_at)}</td><td>${tag(l.from_status)} → ${tag(l.to_status)}</td><td>${esc(l.reason_display)}</td><td>${l.duration_seconds ?? "-"} 秒</td></tr>`).join("") + "</table>");
};
window.showSecret = async (id) => {
  const s = await api(`devices/${id}/secret/`);
  modal(`<h3>${esc(id)} 接入信息</h3><pre>ws://${location.host}/ws/device/${esc(id)}/?secret=${esc(s.secret)}</pre>`);
};
window.quickCommand = (id) => { switchTab("commands"); $("#cmdForm [name=device_id]").value = id; };

$("#exportDevices").onclick = () => download("devices/export/", formData($("#deviceFilter")));
$("#newDevice").onclick = async () => {
  const groups = await api("groups/", { query: { page_size: 500 } });
  modal(`<h3>新增设备</h3><form id="devForm" class="inline">
    <label>编号<input name="device_id" required></label><label>名称<input name="name" required></label>
    <label>型号<input name="model" required></label><label>初始版本<input name="current_version"></label>
    <label>分组<select name="group_id"><option value="">无</option>${groups.results.map((g) => `<option value="${g.group_id}">${esc(g.name)}</option>`).join("")}</select></label>
    <button class="primary">保存</button></form>`);
  $("#devForm").onsubmit = async (e) => {
    e.preventDefault();
    const body = formData(e.target);
    body.group_id = body.group_id ? Number(body.group_id) : null;
    const d = await api("devices/", { method: "POST", body });
    modal(`<h3>已创建 ${esc(d.device_id)}</h3><p>设备接入密钥（请妥善保存）：</p><pre>${esc(d.secret)}</pre>`);
    deviceList.reload(); loadDeviceStats();
  };
};

/* ---------------- 指令模板 ---------------- */
let templates = [];
async function loadTemplates() {
  templates = (await api("command-templates/", { query: { page_size: 500, is_system: false } })).results;
  $$(".tplSelect").forEach((s) => (s.innerHTML = templates.map((t) => `<option value="${t.template_id}">${esc(t.name)} (${esc(t.code)})${t.is_critical ? " ⚠关键" : ""}</option>`).join("")));
}
const tplOf = (id) => templates.find((t) => t.template_id === Number(id));
function confirmCritical(tpl, target) {
  return !tpl?.is_critical || confirm(`【关键操作二次确认】\n指令：${tpl.name}(${tpl.code})\n对象：${target}\n确定执行？`);
}

/* ---------------- 单设备控制 ---------------- */
const cmdList = makeList({
  table: "#cmdTable", pager: "#cmdPager", path: "commands/", filterForm: "#cmdFilter",
  columns: [
    ["编号", (c) => c.command_id], ["设备", (c) => esc(c.device_id)], ["指令", (c) => esc(c.template_name) + (c.is_critical ? " ⚠" : "")],
    ["参数", (c) => esc(JSON.stringify(c.params)), "wrap"], ["状态", (c) => tag(c.status, c.status_display)],
    ["结果", (c) => esc(c.error_msg || (c.result_data ? JSON.stringify(c.result_data) : "")), "wrap"],
    ["批次", (c) => c.batch_id ?? ""], ["操作人", (c) => esc(c.operator_id)], ["下发", (c) => fmt(c.sent_at)], ["完成", (c) => fmt(c.finished_at)],
  ],
});
$("#cmdForm").onsubmit = async (e) => {
  e.preventDefault();
  const f = formData(e.target);
  const tpl = tplOf(f.template_id);
  if (!confirmCritical(tpl, f.device_id)) return;
  await api("commands/", { method: "POST", body: { device_id: f.device_id, template_id: Number(f.template_id), params: parseJSON(f.params, "参数"), offline_policy: f.offline_policy, confirm: !!tpl?.is_critical } });
  toast("指令已提交"); cmdList.load(1);
};

/* ---------------- 批量控制 ---------------- */
const batchList = makeList({
  table: "#batchTable", pager: "#batchPager", path: "command-batches/",
  columns: [
    ["批次", (b) => b.batch_id], ["指令", (b) => esc(b.template_name)], ["状态", (b) => tag(b.status, b.status_display)],
    ["总数", (b) => b.total], ["成功", (b) => b.success], ["失败", (b) => b.failed], ["待执行", (b) => b.pending],
    ["成功率", (b) => (b.success_rate == null ? "-" : (b.success_rate * 100).toFixed(1) + "%")],
    ["并发", (b) => b.concurrency], ["离线策略", (b) => b.offline_policy], ["操作人", (b) => esc(b.operator_id)], ["创建", (b) => fmt(b.created_at)],
    ["操作", (b) => `<span class="actions"><button onclick="batchCommands(${b.batch_id})">明细</button>${b.status === "RUNNING" ? `<button class="danger" onclick="batchCancel(${b.batch_id})">取消</button>` : ""}${["PARTIAL_FAILED", "CANCELLED"].includes(b.status) && b.failed ? `<button onclick="batchRetry(${b.batch_id}, ${b.template_id})">重试失败</button>` : ""}</span>`],
  ],
});
$("#batchForm").onsubmit = async (e) => {
  e.preventDefault();
  const f = formData(e.target);
  const tpl = tplOf(f.template_id);
  const scope = buildScope(f.scope_type, f.scope_value);
  if (!confirmCritical(tpl, JSON.stringify(scope))) return;
  await api("command-batches/", { method: "POST", body: { template_id: Number(f.template_id), params: parseJSON(f.params, "参数"), target_scope: scope, offline_policy: f.offline_policy, concurrency: Number(f.concurrency), confirm: !!tpl?.is_critical } });
  toast("批次已创建"); batchList.load(1);
};
window.batchCancel = async (id) => { if (confirm("取消未下发的指令？")) { await api(`command-batches/${id}/cancel/`, { method: "POST" }); batchList.reload(); } };
window.batchRetry = async (id, tplId) => {
  if (!confirmCritical(tplOf(tplId), `批次 ${id} 的失败设备`)) return;
  await api(`command-batches/${id}/retry/`, { method: "POST", body: { confirm: true } }); toast("已生成重试批次"); batchList.load(1);
};
window.batchCommands = async (id) => {
  const data = await api(`command-batches/${id}/commands/`, { query: { page_size: 200 } });
  modal(`<h3>批次 ${id} 明细</h3><table><tr><th>设备</th><th>状态</th><th>结果</th></tr>` +
    data.results.map((c) => `<tr><td>${esc(c.device_id)}</td><td>${tag(c.status, c.status_display)}</td><td class="wrap">${esc(c.error_msg || JSON.stringify(c.result_data ?? ""))}</td></tr>`).join("") + "</table>");
};

/* ---------------- 版本与升级包 ---------------- */
async function loadVersions() {
  const data = await api("firmware-versions/", { query: { page_size: 200 } });
  $$(".versionSelect").forEach((s) => (s.innerHTML = data.results.filter((v) => v.status === "DRAFT").map((v) => `<option value="${v.version_id}">${esc(v.version_no)}</option>`).join("")));
  $$(".releasableSelect").forEach((s) => (s.innerHTML = data.results.filter((v) => v.status === "RELEASABLE").map((v) => `<option value="${v.version_id}">${esc(v.version_no)}</option>`).join("")));
  $("#versionTable").innerHTML = "<tr><th>版本号</th><th>适用型号</th><th>最低可升级</th><th>状态</th><th>升级包</th><th>更新说明</th><th>操作</th></tr>" +
    data.results.map((v) => `<tr><td>${esc(v.version_no)}</td><td>${esc(v.applicable_models.join(", "))}</td><td>${esc(v.min_upgradable_version)}</td>
      <td>${tag(v.status, v.status_display)}</td>
      <td>${v.packages.map((p) => `${p.package_type}${p.base_version ? "(" + esc(p.base_version) + "→)" : ""} ${(p.size / 1024).toFixed(1)}KB ${p.verified ? "✔" : "✘"} <a href="#" onclick="verifyPkg(${p.package_id});return false">校验</a>`).join("<br>")}</td>
      <td class="wrap">${esc(v.release_notes)}</td>
      <td class="actions">${v.status === "DRAFT" ? `<button class="primary" onclick="versionAction(${v.version_id},'publish')">置为可发布</button>` : ""}${v.status === "RELEASABLE" ? `<button onclick="versionAction(${v.version_id},'deprecate')">废弃</button>` : ""}</td></tr>`).join("");
  return data.results;
}
$("#versionForm").onsubmit = async (e) => {
  e.preventDefault();
  const f = formData(e.target);
  await api("firmware-versions/", { method: "POST", body: { ...f, applicable_models: f.applicable_models.split(/[,\s]+/).filter(Boolean) } });
  toast("版本已创建（草稿）"); e.target.reset(); loadVersions();
};
$("#packageForm").onsubmit = async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const p = await api("upgrade-packages/", { method: "POST", form: fd });
  toast(`上传成功 SHA-256: ${p.checksum.slice(0, 16)}…`); e.target.reset(); loadVersions();
};
window.versionAction = async (id, act) => { await api(`firmware-versions/${id}/${act}/`, { method: "POST" }); toast("操作成功"); loadVersions(); };
window.verifyPkg = async (id) => { const r = await api(`upgrade-packages/${id}/verify/`, { method: "POST" }); toast(r.verified ? "校验值与签名均通过" : "校验失败", !r.verified); loadVersions(); };

/* ---------------- 升级任务 ---------------- */
let currentTask = null;
const progressBar = (s) => `<span class="bar"><i style="width:${(s.progress * 100).toFixed(0)}%"></i></span> ${s.success + s.failed}/${s.total}`;
const taskList = makeList({
  table: "#taskTable", pager: "#taskPager", path: "upgrade-tasks/",
  columns: [
    ["任务", (t) => t.task_id], ["类型", (t) => (t.task_type === "ROLLBACK" ? `回滚(原#${t.parent_task_id})` : "升级")], ["目标版本", (t) => esc(t.version_no)],
    ["状态", (t) => tag(t.status, t.status_display) + (t.pause_reason ? `<br><small>${esc(t.pause_reason)}</small>` : "")],
    ["进度", (t) => progressBar(t.stats)], ["成功", (t) => t.stats.success], ["失败", (t) => t.stats.failed],
    ["灰度", (t) => `${t.stats.gray.success}/${t.stats.gray.total}`], ["阈值", (t) => (t.failure_threshold * 100).toFixed(0) + "%"], ["创建", (t) => fmt(t.created_at)],
    ["操作", (t) => taskButtons(t)],
  ],
});
function taskButtons(t) {
  const b = [`<button onclick="openTask(${t.task_id})">详情</button>`];
  if (t.status === "CREATED") b.push(`<button class="primary" onclick="taskAction(${t.task_id},'start')">开始灰度</button>`);
  if (t.status === "GRAY") b.push(`<button class="primary" onclick="taskAction(${t.task_id},'promote','确认推进全量？')">推进全量</button>`);
  if (["GRAY", "FULL"].includes(t.status)) b.push(`<button onclick="taskAction(${t.task_id},'pause')">暂停</button>`);
  if (t.status === "PAUSED") b.push(`<button onclick="taskAction(${t.task_id},'resume','确认继续？已发生的失败将不再计入熔断阈值')">继续</button>`);
  if (t.stats.failed && !["CREATED", "ROLLED_BACK"].includes(t.status)) b.push(`<button onclick="taskAction(${t.task_id},'retry-failed')">重试失败</button>`);
  if (t.task_type === "UPGRADE" && ["GRAY", "FULL", "PAUSED", "COMPLETED"].includes(t.status)) b.push(`<button class="danger" onclick="rollback(${t.task_id})">回滚</button>`);
  return `<span class="actions">${b.join("")}</span>`;
}
$("#taskForm").onsubmit = async (e) => {
  e.preventDefault();
  const f = formData(e.target);
  const t = await api("upgrade-tasks/", { method: "POST", body: {
    version_id: Number(f.version_id), target_scope: buildScope(f.scope_type, f.scope_value), gray_ratio: Number(f.gray_ratio),
    gray_device_ids: f.gray_device_ids.split(/[,\s]+/).filter(Boolean), failure_threshold: Number(f.failure_threshold) } });
  toast(`任务 #${t.task_id} 已创建：${t.stats.total} 台可升级，${t.excluded.length} 台被排除`);
  taskList.load(1); openTask(t.task_id);
};
window.taskAction = async (id, act, ask) => {
  if (ask && !confirm(ask)) return;
  await api(`upgrade-tasks/${id}/${act}/`, { method: "POST", body: {} }); toast("操作成功"); taskList.reload(); if (currentTask === id) openTask(id);
};
window.rollback = async (id) => {
  const versions = (await api("firmware-versions/", { query: { status: "RELEASABLE", page_size: 200 } })).results;
  modal(`<h3>回滚任务 #${id}</h3><p>为已升级成功的设备生成回滚任务，原任务标记为已回滚。</p>
    <form id="rbForm" class="inline"><label>回滚到<select name="target_version_id">${versions.map((v) => `<option value="${v.version_id}">${esc(v.version_no)}</option>`).join("")}</select></label>
    <label>灰度比例<input name="gray_ratio" type="number" step="0.01" min="0.01" max="1" value="1"></label><button class="danger">确认回滚</button></form>`);
  $("#rbForm").onsubmit = async (e) => {
    e.preventDefault();
    const f = formData(e.target);
    const r = await api(`upgrade-tasks/${id}/rollback/`, { method: "POST", body: { target_version_id: Number(f.target_version_id), gray_ratio: Number(f.gray_ratio) } });
    $("#modal").close(); toast(r.rollback_task ? `已生成回滚任务 #${r.rollback_task.task_id}` : "没有需要回滚的设备"); taskList.load(1);
  };
};
window.openTask = async (id) => {
  currentTask = id;
  const [t, recs] = await Promise.all([api(`upgrade-tasks/${id}/`), api(`upgrade-tasks/${id}/records/`, { query: { page_size: 500 } })]);
  const el = $("#taskDetail");
  el.classList.remove("hidden");
  el.innerHTML = `<h3>任务 #${t.task_id} → ${esc(t.version_no)} ${tag(t.status, t.status_display)} <button onclick="openTask(${id})">刷新</button></h3>
    <p>阶段分布：${Object.entries(t.stats.by_stage).map(([k, v]) => `${tag(k)} ${v}`).join("　")}</p>
    ${t.excluded.length ? `<details><summary>自动排除 ${t.excluded.length} 台</summary>${t.excluded.map((x) => `${esc(x.device_id)}：${esc(x.reason)}`).join("<br>")}</details>` : ""}
    <table><tr><th>设备</th><th>阶段</th><th>灰度/全量</th><th>版本</th><th>进度</th><th>失败原因</th><th>重试</th><th>更新时间</th></tr>
    ${recs.results.map((r) => `<tr id="rec-${r.record_id}"><td>${esc(r.device_id)}</td><td>${tag(r.stage, r.stage_display)}</td><td>${r.phase === "GRAY" ? "灰度" : "全量"}</td><td>${esc(r.from_version)} → ${esc(r.to_version)}</td><td><span class="bar"><i style="width:${r.progress}%"></i></span> ${r.progress}%</td><td class="wrap">${esc(r.error_msg)}</td><td>${r.retry_count}</td><td>${fmt(r.updated_at)}</td></tr>`).join("")}</table>`;
};

/* ---------------- 审计 ---------------- */
const auditList = makeList({
  table: "#auditTable", pager: "#auditPager", path: "operation-logs/", filterForm: "#auditFilter",
  columns: [
    ["时间", (o) => fmt(o.op_time)], ["操作人", (o) => esc(o.operator_id)], ["类型", (o) => esc(o.op_type_display)],
    ["对象", (o) => `${esc(o.target_type)} ${esc(o.target_id)}`], ["结果", (o) => tag(o.result)], ["详情", (o) => esc(JSON.stringify(o.detail)), "wrap"],
  ],
});
$("#exportAudit").onclick = () => download("operation-logs/export/", formData($("#auditFilter")));
const OP_TYPES = { CRITICAL_COMMAND: "关键指令下发", CRITICAL_COMMAND_RESULT: "关键指令结果", BATCH_CONTROL: "批量控制", BATCH_CANCEL: "取消批次", VERSION_PUBLISH: "版本发布", VERSION_DEPRECATE: "版本废弃", PACKAGE_UPLOAD: "上传升级包", UPGRADE_CREATE: "创建升级任务", UPGRADE_START: "开始灰度", UPGRADE_PROMOTE: "推进全量", UPGRADE_PAUSE: "暂停升级", UPGRADE_AUTO_PAUSE: "自动暂停", UPGRADE_RESUME: "继续升级", UPGRADE_RETRY: "重试失败设备", ROLLBACK: "版本回滚" };
$("#opTypeSelect").innerHTML += Object.entries(OP_TYPES).map(([k, v]) => `<option value="${k}">${v}</option>`).join("");

/* ---------------- 标签页 / 实时推送 ---------------- */
const loaders = {
  devices: () => { deviceList.load(); loadDeviceStats(); },
  commands: () => cmdList.load(), batches: () => batchList.load(),
  versions: () => loadVersions(), tasks: () => { loadVersions(); taskList.load(); }, audit: () => auditList.load(),
};
let activeTab = "devices";
function switchTab(name) {
  activeTab = name;
  $$("#tabs a").forEach((a) => a.classList.toggle("active", a.dataset.tab === name));
  $$("main > section").forEach((s) => s.classList.toggle("hidden", s.id !== `tab-${name}`));
  loaders[name]();
}
$$("#tabs a").forEach((a) => (a.onclick = () => switchTab(a.dataset.tab)));

const debounced = {};
function refreshSoon(key, fn) { clearTimeout(debounced[key]); debounced[key] = setTimeout(fn, 400); }

function connectEvents() {
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/admin/?token=${token}`);
  ws.onopen = () => $("#wsState").classList.remove("off");
  ws.onclose = () => { $("#wsState").classList.add("off"); if (token) setTimeout(connectEvents, 3000); };
  ws.onmessage = (e) => {
    const { event, data } = JSON.parse(e.data);
    if (event === "device_status") {
      toast(`${data.device_id} ${data.online_status === "ONLINE" ? "上线" : "离线"}（${data.reason}）`);
      if (activeTab === "devices") refreshSoon("dev", () => { deviceList.reload(); loadDeviceStats(); });
    } else if (event === "device_version" && activeTab === "devices") refreshSoon("dev", () => deviceList.reload());
    else if (event === "command_update" && activeTab === "commands") refreshSoon("cmd", () => cmdList.reload());
    else if (event === "batch_update" && activeTab === "batches") refreshSoon("batch", () => batchList.reload());
    else if (event === "task_update" && activeTab === "tasks") {
      refreshSoon("task", () => taskList.reload());
      if (data.status === "PAUSED" && data.pause_reason) toast(`任务 #${data.task_id}：${data.pause_reason}`, true);
    } else if (event === "upgrade_record" && activeTab === "tasks" && currentTask === data.task_id) refreshSoon("rec", () => openTask(currentTask));
  };
}

/* ---------------- 登录 ---------------- */
function logout() { token = null; localStorage.removeItem("iot_token"); $("#app").classList.add("hidden"); $("#login").classList.remove("hidden"); }
$("#logout").onclick = logout;
$("#loginForm").onsubmit = async (e) => {
  e.preventDefault();
  const resp = await fetch("/api/auth/token/", { method: "POST", body: new FormData(e.target) });
  const data = await resp.json();
  if (!resp.ok) { $("#loginErr").textContent = "用户名或密码错误"; return; }
  token = data.token; localStorage.setItem("iot_token", token);
  localStorage.setItem("iot_user", e.target.username.value);
  start();
};
async function start() {
  $("#login").classList.add("hidden"); $("#app").classList.remove("hidden");
  $("#who").textContent = localStorage.getItem("iot_user") || "";
  const groups = await api("groups/", { query: { page_size: 500 } });
  $$(".groupSelect").forEach((s) => (s.innerHTML = `<option value="">全部分组</option>` + groups.results.map((g) => `<option value="${g.group_id}">${esc(g.name)}</option>`).join("")));
  await loadTemplates();
  switchTab("devices");
  connectEvents();
}
token ? start() : logout();
