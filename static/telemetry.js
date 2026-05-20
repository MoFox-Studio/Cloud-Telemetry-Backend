const script = document.currentScript;
const prefix = script?.dataset.prefix || '/_cloud_telemetry';
const page = script?.dataset.page || 'public';
const api = `${prefix}/api`;
const app = document.querySelector('#app');

const state = {
  apiKey: localStorage.getItem('cloudTelemetryAdminKey') || '',
  instances: [],
  selectedId: null,
  overview: null,
  diagnostics: null,
  detail: null,
};

function esc(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function fmtNum(value) {
  return new Intl.NumberFormat('zh-CN').format(Number(value || 0));
}

function fmtPct(value) {
  return `${(Number(value || 0) * 100).toFixed(1)}%`;
}

function fmtTime(ts) {
  if (!ts) return '-';
  return new Date(Number(ts) * 1000).toLocaleString('zh-CN', { hour12: false });
}

function clsStatus(status) {
  if (status === 'active') return 'good';
  if (status === 'suspended') return 'bad';
  return 'warn';
}

function toast(message) {
  const node = document.createElement('div');
  node.className = 'toast';
  node.textContent = message;
  document.body.appendChild(node);
  setTimeout(() => node.remove(), 3200);
}

async function fetchJson(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (state.apiKey) headers['X-API-Key'] = state.apiKey;
  if (options.body && !headers['Content-Type']) headers['Content-Type'] = 'application/json';
  const response = await fetch(url, { ...options, headers });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json();
}

function topbar({ admin = false } = {}) {
  return `
    <header class="topbar">
      <div class="brand">
        <div class="brand-mark">M</div>
        <div>
          <h1>${admin ? 'Telemetry Admin' : 'Neo-MoFox Telemetry'}</h1>
          <p>${admin ? '稳定性排查与实例治理工作台' : '来自运行中实例的社区健康脉搏'}</p>
        </div>
      </div>
      <nav class="nav-actions">
        <a href="${prefix}/">公开总览</a>
        <a href="${prefix}/admin">管理员面板</a>
      </nav>
    </header>`;
}

function metric(label, value, note = '') {
  return `<article class="metric-card"><label>${esc(label)}</label><strong>${esc(value)}</strong><small>${esc(note)}</small></article>`;
}

function bars(items, labelKey, valueKey) {
  const max = Math.max(1, ...items.map((item) => Number(item[valueKey] || 0)));
  if (!items.length) return '<div class="empty">暂无数据</div>';
  return `<div class="bar-list">${items.map((item) => {
    const value = Number(item[valueKey] || 0);
    const pct = Math.max(3, (value / max) * 100);
    return `<div class="bar-row">
      <span class="bar-label" title="${esc(item[labelKey])}">${esc(item[labelKey])}</span>
      <span class="bar-track"><span class="bar-fill" style="width:${pct}%"></span></span>
      <span class="mono">${fmtNum(value)}</span>
    </div>`;
  }).join('')}</div>`;
}

function timeline(items, key, warnKey = null, errKey = null) {
  const max = Math.max(1, ...items.map((item) => {
    return Number(item[key] || 0) + Number(item[warnKey] || 0) + Number(item[errKey] || 0);
  }));
  return `<div class="timeline">${items.map((item) => {
    const total = Number(item[key] || 0) + Number(item[warnKey] || 0) + Number(item[errKey] || 0);
    const height = Math.max(3, (total / max) * 126);
    const klass = Number(item[errKey] || 0) > 0 ? 'err' : Number(item[warnKey] || 0) > 0 ? 'warn' : '';
    return `<span class="timeline-bar ${klass}" title="${fmtTime(item.bucket_at)} · ${fmtNum(total)}" style="height:${height}px"></span>`;
  }).join('')}</div>`;
}

function heatColor(value, max) {
  const ratio = Math.max(0, Math.min(1, max > 0 ? value / max : 0));
  const hue = 138 - ratio * 138;
  return `hsl(${hue} 78% 52%)`;
}

function errorHeatmap(data) {
  const rows = data?.heartbeat_timeline_24h || [];
  const max = Math.max(0.1, ...rows.map((item) => Number(item.avg_errors_per_heartbeat || 0)));
  const cells = rows.map((row) => {
    const value = Number(row.avg_errors_per_heartbeat || 0);
    return `<span class="pulse-cell" style="background:${heatColor(value, max)}" title="${fmtTime(row.bucket_at)} · 平均错误 ${value.toFixed(2)} / 心跳 · 错误 ${fmtNum(row.error_events)}"></span>`;
  }).join('');
  return `<div class="pulse-grid heatmap">${cells}</div>
    <div class="heat-legend"><span>0</span><span></span><strong>${max.toFixed(2)} / 心跳</strong></div>`;
}

async function loadPublic() {
  const data = await fetchJson(`${api}/public/overview`);
  state.overview = data;
  renderPublic(data);
}

function renderPublic(data = state.overview) {
  const overview = data?.overview || {};
  const perf = data?.performance_24h || {};
  const versionItems = (data?.version_distribution || [])
    .slice()
    .sort((a, b) => Number(b.count || 0) - Number(a.count || 0));
  app.innerHTML = `
    ${topbar()}
    <main>
      <section class="hero-band">
        <div class="community-panel">
          <div>
            <span class="kicker">Live community telemetry</span>
            <h2>每一个在线实例，都是 MoFox 正在呼吸的一小格。</h2>
            <p>这里展示匿名汇总后的遥测信号：在线规模、版本迁移、运行健康度和整体性能趋势。数据会自动刷新，帮助大家看到项目正在被真实使用，也帮助我们把体验调得更稳。</p>
          </div>
          <div class="status-strip">
            <div class="mini-stat"><strong>${fmtNum(overview.online_instances)}</strong><span>当前在线</span></div>
            <div class="mini-stat"><strong>${fmtNum(overview.total_instances)}</strong><span>累计实例</span></div>
            <div class="mini-stat"><strong>${fmtPct(perf.success_rate)}</strong><span>LLM 成功率</span></div>
            <div class="mini-stat"><strong>${Number(perf.average_latency || 0).toFixed(2)}s</strong><span>平均请求耗时</span></div>
          </div>
        </div>
        <aside class="heartbeat-board">
          <div class="section-head">
            <div>
              <h3>24 小时错误热度</h3>
              <p>每个色块代表一小时，颜色表示平均每次心跳携带的错误计数。</p>
            </div>
            <span class="chip good">自动刷新</span>
          </div>
          ${errorHeatmap(data)}
        </aside>
      </section>

      <section class="section grid-4">
        ${metric('24h 心跳窗口', fmtNum(perf.window_count), '已接收窗口数')}
        ${metric('24h Token', fmtNum(perf.total_tokens), '按 request name 汇总')}
        ${metric('缓存命中率', fmtPct(perf.cache_hit_rate), 'LLM 窗口内平均')}
        ${metric('DB 错误事件', fmtNum(perf.db_health?.error_events), `${fmtNum(perf.db_health?.warning_events)} 个 warning`)}
      </section>

      <section class="section grid-3">
        <div class="panel">
          <div class="section-head"><div><h3>版本分布</h3><p>观察新版本迁移节奏</p></div></div>
          ${bars(versionItems, 'version', 'count')}
        </div>
        <div class="panel">
          <div class="section-head"><div><h3>运行健康</h3><p>来自 watchdog、任务与 stream loop</p></div></div>
          ${healthPanel(perf)}
        </div>
        <div class="panel">
          <div class="section-head"><div><h3>健康事件域</h3><p>db / runtime / llm 等本地遥测事件</p></div></div>
          ${domainList(perf.health_domains || [])}
        </div>
      </section>

      <section class="section panel">
        <div class="section-head"><div><h3>最活跃 LLM 请求</h3><p>按 token 总消耗排序，只展示聚合数据</p></div></div>
        ${requestTable(perf.top_requests || [])}
      </section>
    </main>`;
}

function requestTable(rows, { showBaseUrls = false } = {}) {
  if (!rows.length) return '<div class="empty">暂无 LLM 聚合数据</div>';
  const baseUrlHead = showBaseUrls ? '<th>Base URL</th>' : '';
  return `<div class="table-wrap"><table>
    <thead><tr><th>Request name</th><th>请求数</th><th>Token</th><th>平均耗时</th><th>缓存命中</th><th>成功率</th>${baseUrlHead}</tr></thead>
    <tbody>${rows.map((row) => `<tr>
      <td class="mono">${esc(row.request_name)}</td>
      <td>${fmtNum(row.request_count)}</td>
      <td>${fmtNum(row.total_tokens)}</td>
      <td>${Number(row.average_latency || 0).toFixed(2)}s</td>
      <td>${fmtPct(row.cache_hit_rate)}</td>
      <td>${fmtPct(row.success_rate)}</td>
      ${showBaseUrls ? `<td>${esc((row.base_urls || []).join(', ') || '-')}</td>` : ''}
    </tr>`).join('')}</tbody>
  </table></div>`;
}

function healthPanel(perf) {
  const running = Number(perf.watchdog_running_samples || 0);
  const samples = Number(perf.watchdog_samples || 0);
  const alive = Number(perf.watchdog_thread_alive_samples || 0);
  return `<div class="bar-list">
    <div class="mini-stat"><strong>${samples ? `${running}/${samples}` : '-'}</strong><span>Watchdog running samples</span></div>
    <div class="mini-stat"><strong>${samples ? `${alive}/${samples}` : '-'}</strong><span>Watchdog thread alive samples</span></div>
    <div class="mini-stat"><strong>${fmtNum(perf.watchdog_registered_streams_max)}</strong><span>Watchdog registered streams max</span></div>
    <div class="mini-stat"><strong>${fmtNum(perf.stream_failures_max)}</strong><span>Stream loop failure counter max</span></div>
  </div>`;
}

function domainList(rows) {
  if (!rows.length) return '<div class="empty">暂无健康事件域数据</div>';
  return `<div class="bar-list">${rows.map((row) => `<div class="domain-row">
    <div><strong>${esc(row.domain)}</strong><small>${fmtTime(row.last_event_at)}</small></div>
    <span class="chips"><span class="chip">${fmtNum(row.total_events)} total</span><span class="chip warn">${fmtNum(row.warning_events)} warn</span><span class="chip bad">${fmtNum(row.error_events)} err</span></span>
  </div>`).join('')}</div>`;
}

function aggregateInstanceDomains(windows, diagnostics) {
  const buckets = new Map();
  const ensureBucket = (domain) => {
    const key = String(domain || 'unknown');
    if (!buckets.has(key)) {
      buckets.set(key, {
        domain: key,
        total_events: 0,
        warning_events: 0,
        error_events: 0,
        last_event_at: 0,
      });
    }
    return buckets.get(key);
  };

  for (const window of windows || []) {
    const summary = window.summary || {};
    for (const item of summary.telemetry_domains || []) {
      const bucket = ensureBucket(item.domain);
      bucket.total_events += Number(item.total_events || 0);
      bucket.warning_events += Number(item.warning_events || 0);
      bucket.error_events += Number(item.error_events || 0);
      bucket.last_event_at = Math.max(bucket.last_event_at, Number(item.last_event_at || 0));
    }
  }

  for (const event of diagnostics || []) {
    const attrs = event.attributes || {};
    if (!attrs.domain) continue;
    const bucket = ensureBucket(attrs.domain);
    bucket.total_events += 1;
    if (event.severity === 'warning') bucket.warning_events += 1;
    if (['error', 'critical', 'fatal'].includes(event.severity)) bucket.error_events += 1;
    bucket.last_event_at = Math.max(bucket.last_event_at, Number(event.event_at || event.received_at || 0));
  }

  return [...buckets.values()].sort((a, b) => (
    (b.error_events - a.error_events)
    || (b.warning_events - a.warning_events)
    || (b.total_events - a.total_events)
    || a.domain.localeCompare(b.domain)
  ));
}

function adminShell(content) {
  return `${topbar({ admin: true })}<main class="admin-layout">${adminSidebar()}<section>${content}</section></main>`;
}

function adminSidebar() {
  return `<aside class="sidebar">
    <div class="auth-panel">
      <h3>管理员凭证</h3>
      <input id="api-key" type="password" placeholder="X-API-Key" value="${esc(state.apiKey)}">
      <div class="chips">
        <button class="primary" id="save-key">保存并刷新</button>
        <button id="clear-key">清除</button>
      </div>
    </div>
    <div class="auth-panel">
      <h3>实例筛选</h3>
      <div class="filter-row">
        <select id="status-filter">
          <option value="">全部状态</option>
          <option value="active">在线</option>
          <option value="offline">离线</option>
          <option value="suspended">已封禁</option>
        </select>
        <input id="prefix-filter" placeholder="client id 前缀">
      </div>
      <div class="chips"><button id="reload-admin">刷新</button></div>
    </div>
    <div class="auth-panel">
      <h3>实例列表</h3>
      <div id="instance-list" class="instance-list">${instanceList()}</div>
    </div>
  </aside>`;
}

function instanceList() {
  if (!state.instances.length) return '<div class="empty">暂无实例</div>';
  return state.instances.map((item) => {
    const key = instanceKey(item);
    return `<button class="instance-item ${state.selectedId === key ? 'active' : ''}" data-instance="${esc(key)}">
    <span class="instance-id">${esc(item.client_instance_id_masked || item.client_instance_id)}</span>
    <span class="chips">
      <span class="chip ${clsStatus(item.online_status)}">${esc(item.online_status)}</span>
      <span class="chip">${esc(item.app_version || 'unknown')}</span>
      ${item.is_suspended ? '<span class="chip bad">封禁</span>' : ''}
    </span>
  </button>`;
  }).join('');
}

function instanceKey(item) {
  return item.client_instance_id || item.client_instance_id_masked || '';
}

async function loadAdmin() {
  if (!state.apiKey) {
    renderAdminLocked();
    return;
  }
  const statusFilter = document.querySelector('#status-filter')?.value || '';
  const prefixFilter = document.querySelector('#prefix-filter')?.value || '';
  const params = new URLSearchParams({
    limit: '80',
    sort_by: 'last_heartbeat_received_at',
    sort_order: 'desc',
  });
  if (statusFilter) params.set('online_status', statusFilter);
  if (prefixFilter) params.set('client_instance_id_prefix', prefixFilter);
  const [overview, diagnostics, list] = await Promise.all([
    fetchJson(`${api}/admin/overview/summary`),
    fetchJson(`${api}/admin/diagnostics/summary`),
    fetchJson(`${api}/admin/instances?${params.toString()}`),
  ]);
  state.overview = overview;
  state.diagnostics = diagnostics;
  state.instances = list.items || [];
  if (!state.selectedId && state.instances[0]) state.selectedId = instanceKey(state.instances[0]);
  if (state.selectedId) {
    state.detail = await fetchJson(`${api}/admin/instances/${encodeURIComponent(state.selectedId)}`);
  }
  renderAdmin();
}

function renderAdminLocked() {
  app.innerHTML = adminShell(`<div class="panel"><h2>需要管理员凭证</h2><p class="muted">输入 X-API-Key 后可以查看诊断趋势、实例详情并执行封禁/解封操作。</p></div>`);
  bindAdminEvents();
}

function renderAdmin() {
  const overview = state.overview || {};
  const diagnostics = state.diagnostics || {};
  const perf = diagnostics.performance_24h || {};
  app.innerHTML = adminShell(`
    <section class="grid-4">
      ${metric('在线实例', fmtNum(overview.online_instances), `总计 ${fmtNum(overview.total_instances)}`)}
      ${metric('24h 报错计数', fmtNum(diagnostics.error_count_24h), 'error / critical / fatal')}
      ${metric('24h 诊断事件', fmtNum(diagnostics.diagnostic_count_24h), 'warning / error / critical')}
      ${metric('LLM 成功率', fmtPct(perf.success_rate), `${fmtNum(perf.request_count)} 次请求`)}
    </section>

    <section class="section grid-2">
      <div class="panel">
        <div class="section-head"><div><h3>报错趋势</h3><p>最近 24 小时诊断严重级别</p></div></div>
        ${timeline(diagnostics.diagnostic_timeline_24h || [], 'info', 'warning', 'error')}
      </div>
      <div class="panel">
        <div class="section-head"><div><h3>高消耗请求</h3><p>包含每个 request name 的缓存命中率</p></div></div>
        ${requestTable(perf.top_requests || [], { showBaseUrls: true })}
      </div>
    </section>

    <section class="section grid-2">
      <div class="panel">
        <div class="section-head"><div><h3>运行健康事件</h3><p>watchdog / db / runtime 聚合信号</p></div></div>
        ${healthPanel(perf)}
      </div>
      <div class="panel">
        <div class="section-head"><div><h3>Telemetry domains</h3><p>本地采集的健康事件域</p></div></div>
        ${domainList(perf.health_domains || [])}
      </div>
    </section>

    <section class="section">
      ${detailPanel(state.detail)}
    </section>

    <section class="section panel">
      <div class="section-head"><div><h3>近期错误</h3><p>按接收时间倒序</p></div></div>
      ${errorTable(diagnostics.recent_error_events || [])}
    </section>`);
  bindAdminEvents();
}

function detailPanel(detail) {
  if (!detail) return '<div class="empty">选择一个实例查看详情</div>';
  const latest = (detail.recent_heartbeat_windows || [])[0] || {};
  const summary = latest.summary || {};
  const perf = summary.llm_request_name_top || [];
  const diagnostics = detail.recent_diagnostic_events || [];
  const domains = aggregateInstanceDomains(detail.recent_heartbeat_windows || [], diagnostics);
  return `<div class="panel">
    <div class="section-head">
      <div>
        <h2 class="mono">${esc(detail.client_instance_id_masked || detail.client_instance_id)}</h2>
        <p>${esc(detail.platform || 'unknown')} · ${esc(detail.app_version || 'unknown')}</p>
      </div>
      <div class="chips">
        <button class="danger" id="suspend-instance" ${detail.is_suspended ? 'disabled' : ''}>封禁</button>
        <button class="success" id="resume-instance" ${detail.is_suspended ? '' : 'disabled'}>解封</button>
      </div>
    </div>
    <div class="detail-grid">
      <div>
        <div class="chips">
          <span class="chip ${clsStatus(detail.online_status)}">${esc(detail.online_status)}</span>
          <span class="chip">${esc(detail.gap_status)}</span>
          <span class="chip">seq ${esc(detail.last_window_sequence ?? '-')}</span>
        </div>
        <p class="muted">最近心跳：${fmtTime(detail.last_heartbeat_received_at)}<br>最近诊断：${fmtTime(detail.last_diagnostic_at)} · ${esc(detail.last_diagnostic_severity || '-')}</p>
        <textarea id="suspend-reason" placeholder="封禁原因，便于审计和团队协作">${esc(detail.suspension_reason || '')}</textarea>
      </div>
      <div>
        ${requestTable(perf, { showBaseUrls: true })}
      </div>
    </div>
    <div class="section grid-2">
      <div>
        <div class="section-head"><div><h3>Telemetry domains</h3><p>来自该实例近期心跳窗口和诊断事件的 domain 明细</p></div></div>
        ${domainList(domains)}
      </div>
      <div>
        <div class="section-head"><div><h3>Recent diagnostics</h3><p>该实例最近诊断事件，含 attributes</p></div></div>
        ${diagnosticTable(diagnostics)}
      </div>
    </div>
  </div>`;
}

function errorTable(rows) {
  if (!rows.length) return '<div class="empty">最近 24 小时没有 error/critical 事件</div>';
  return `<div class="table-wrap"><table>
    <thead><tr><th>时间</th><th>级别</th><th>事件</th><th>摘要</th></tr></thead>
    <tbody>${rows.map((row) => `<tr>
      <td>${fmtTime(row.received_at)}</td>
      <td><span class="chip bad">${esc(row.severity)}</span></td>
      <td class="mono">${esc(row.event_name)}</td>
      <td>${esc(row.summary)}</td>
    </tr>`).join('')}</tbody>
  </table></div>`;
}

function diagnosticTable(rows) {
  if (!rows.length) return '<div class="empty">暂无诊断事件</div>';
  return `<div class="table-wrap"><table>
    <thead><tr><th>时间</th><th>级别</th><th>事件</th><th>摘要</th><th>Attributes</th></tr></thead>
    <tbody>${rows.map((row) => `<tr>
      <td>${fmtTime(row.received_at)}</td>
      <td><span class="chip ${row.severity === 'error' ? 'bad' : row.severity === 'warning' ? 'warn' : ''}">${esc(row.severity)}</span></td>
      <td class="mono">${esc(row.event_name)}</td>
      <td>${esc(row.summary)}</td>
      <td class="mono">${esc(JSON.stringify(row.attributes || {}))}</td>
    </tr>`).join('')}</tbody>
  </table></div>`;
}

function bindAdminEvents() {
  document.querySelector('#save-key')?.addEventListener('click', () => {
    state.apiKey = document.querySelector('#api-key')?.value || '';
    localStorage.setItem('cloudTelemetryAdminKey', state.apiKey);
    void loadAdmin().catch((error) => toast(error.message));
  });
  document.querySelector('#clear-key')?.addEventListener('click', () => {
    state.apiKey = '';
    localStorage.removeItem('cloudTelemetryAdminKey');
    renderAdminLocked();
  });
  document.querySelector('#reload-admin')?.addEventListener('click', () => {
    state.selectedId = null;
    void loadAdmin().catch((error) => toast(error.message));
  });
  document.querySelectorAll('[data-instance]').forEach((button) => {
    button.addEventListener('click', async () => {
      state.selectedId = button.dataset.instance;
      state.detail = await fetchJson(`${api}/admin/instances/${encodeURIComponent(state.selectedId)}`);
      renderAdmin();
    });
  });
  document.querySelector('#suspend-instance')?.addEventListener('click', async () => {
    const reason = document.querySelector('#suspend-reason')?.value || 'manual suspension';
    await fetchJson(`${api}/admin/instances/${encodeURIComponent(state.selectedId)}/suspend`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
    toast('实例已封禁');
    await loadAdmin();
  });
  document.querySelector('#resume-instance')?.addEventListener('click', async () => {
    await fetchJson(`${api}/admin/instances/${encodeURIComponent(state.selectedId)}/resume`, {
      method: 'POST',
      body: JSON.stringify({}),
    });
    toast('实例已解封');
    await loadAdmin();
  });
}

if (page === 'admin') {
  renderAdminLocked();
  void loadAdmin().catch((error) => toast(error.message));
  setInterval(() => void loadAdmin().catch(() => {}), 30000);
} else {
  void loadPublic().catch((error) => {
    app.innerHTML = `${topbar()}<main class="section"><div class="panel"><h2>遥测暂时不可用</h2><p class="muted">${esc(error.message)}</p></div></main>`;
  });
  setInterval(() => void loadPublic().catch(() => {}), 15000);
}
