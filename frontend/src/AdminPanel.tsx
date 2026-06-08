import React, { useEffect, useState, useRef } from 'react';
import { Chart, registerables } from 'chart.js';
import { Lock, Unlock, Search, RefreshCw, BarChart2, Server, CheckCircle2, ChevronRight, X, UserCheck, Play, Pause, List, AlertOctagon, ChevronLeft, ChevronsLeft, ChevronsRight } from 'lucide-react';
import { fetchJson, fmtNum, fmtPct, fmtTime, fmtHour, fmtRelative } from './utils';

Chart.register(...registerables);

const CHART_COLORS = ['#5b9bd5', '#4caf93', '#d4a844', '#e0556a', '#9b7ec4', '#56b6c2', '#e08e4a', '#949aa5'];

const renderDoughnutPanel = (
  title: string,
  canvasRef: React.RefObject<HTMLCanvasElement | null>,
  items: Array<{ label: string; count: number }>
) => {
  const total = items.reduce((a, b) => a + b.count, 0);
  return (
    <div className="panel">
      <div className="panel-header">
        <div className="panel-header-title">
          <h3>{title}</h3>
        </div>
      </div>
      <div className="panel-body">
        <div className="chart-container h-sm">
          <canvas ref={canvasRef}></canvas>
        </div>
        <div className="custom-legend">
          {items.slice(0, 4).map((item, idx) => (
            <div className="legend-item" key={idx}>
              <div className="legend-label">
                <span className="legend-color" style={{ backgroundColor: CHART_COLORS[idx % CHART_COLORS.length] }}></span>
                <span>{item.label}</span>
              </div>
              <span className="legend-value">{fmtPct(total > 0 ? item.count / total : 0)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

interface AdminPanelProps {
  apiPrefix: string;
}

interface ToastMessage {
  id: number;
  message: string;
  type: 'success' | 'danger' | 'info';
}

export default function AdminPanel({ apiPrefix }: AdminPanelProps) {
  const [apiKey, setApiKey] = useState(localStorage.getItem('cloudTelemetryAdminKey') || '');
  const [isAuthorized, setIsAuthorized] = useState(false);
  const [currentTab, setCurrentTab] = useState<'dashboard' | 'instances' | 'diagnostics'>('dashboard');
  
  // Data States
  const [overview, setOverview] = useState<any>(null);
  const [diagnostics, setDiagnostics] = useState<any>(null);
  
  // Instances Table States
  const [instances, setInstances] = useState<any[]>([]);
  const [instancesCount, setInstancesCount] = useState(0);
  const [instancesPage, setInstancesPage] = useState(1);
  const [instancesLimit, setInstancesLimit] = useState(20);
  const [sortField, setSortField] = useState('last_heartbeat_received_at');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  
  // Instance Filters
  const [filterSearch, setFilterSearch] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterPlatform, setFilterPlatform] = useState('');
  const [filterVersion, setFilterVersion] = useState('');
  const [filterSuspended, setFilterSuspended] = useState('');
  
  // Drawer state
  const [selectedInstanceId, setSelectedInstanceId] = useState<string | null>(null);
  const [instanceDetail, setInstanceDetail] = useState<any>(null);
  const [drawerTab, setDrawerTab] = useState<'overview' | 'llm' | 'domains' | 'logs'>('overview');
  const [suspendReason, setSuspendReason] = useState('');
  
  // Toast notifications state
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const nextToastId = useRef(0);
  
  const [loading, setLoading] = useState(false);
  const [refreshCountdown, setRefreshCountdown] = useState(30);

  // Charts references
  const chartTimelineRef = useRef<HTMLCanvasElement | null>(null);
  const chartPlatformRef = useRef<HTMLCanvasElement | null>(null);
  const chartCountryRef = useRef<HTMLCanvasElement | null>(null);
  const activeCharts = useRef<Record<string, Chart>>({});

  const showToast = (message: string, type: 'success' | 'danger' | 'info' = 'info') => {
    const id = nextToastId.current++;
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 3200);
  };

  // Main loader
  const loadAdminData = async (isSilent = false) => {
    if (!apiKey) return;
    if (!isSilent) setLoading(true);
    try {
      const api = `${apiPrefix}/api`;
      // Check auth status
      await fetchJson(`${api}/admin/status`, apiKey);
      setIsAuthorized(true);

      const [ovData, diagData] = await Promise.all([
        fetchJson(`${api}/admin/overview/summary`, apiKey),
        fetchJson(`${api}/admin/diagnostics/summary`, apiKey),
      ]);

      setOverview(ovData);
      setDiagnostics(diagData);
      
      // Load instances list
      await loadInstances(isSilent, apiKey);
    } catch (err: any) {
      console.error(err);
      setIsAuthorized(false);
      showToast(err.message || '凭证验证失败，请输入正确的 X-API-Key', 'danger');
    } finally {
      if (!isSilent) setLoading(false);
    }
  };

  // Loader for paginated instances list
  const loadInstances = async (_isSilent = false, keyOverride?: string) => {
    const key = keyOverride || apiKey;
    if (!key) return;
    
    const offset = (instancesPage - 1) * instancesLimit;
    const params = new URLSearchParams({
      offset: String(offset),
      limit: String(instancesLimit),
      sort_by: sortField,
      sort_order: sortOrder,
    });
    
    if (filterStatus) params.set('online_status', filterStatus);
    if (filterPlatform) params.set('platform', filterPlatform);
    if (filterVersion) params.set('app_version', filterVersion);
    if (filterSuspended) params.set('is_suspended', filterSuspended);
    if (filterSearch) params.set('client_instance_id_prefix', filterSearch);

    try {
      const res = await fetchJson(`${apiPrefix}/api/admin/instances?${params.toString()}`, key);
      setInstances(res.items || []);
      setInstancesCount(res.total_count || 0);
    } catch (err: any) {
      console.error(err);
      showToast('加载实例列表失败: ' + err.message, 'danger');
    }
  };

  // Re-run instances load when page/filters/sort updates
  useEffect(() => {
    if (isAuthorized) {
      loadInstances(true);
    }
  }, [instancesPage, instancesLimit, sortField, sortOrder, filterStatus, filterPlatform, filterVersion, filterSuspended]);

  // Load detailed telemetry for drawer
  const loadInstanceDetail = async (id: string) => {
    try {
      const detail = await fetchJson(`${apiPrefix}/api/admin/instances/${encodeURIComponent(id)}`, apiKey);
      setInstanceDetail(detail);
      setSuspendReason(detail.suspension_reason || '');
    } catch (err: any) {
      console.error(err);
      showToast('读取实例详情失败: ' + err.message, 'danger');
      setInstanceDetail(null);
    }
  };

  useEffect(() => {
    if (selectedInstanceId) {
      loadInstanceDetail(selectedInstanceId);
    } else {
      setInstanceDetail(null);
    }
  }, [selectedInstanceId]);

  // Auto reload loop
  useEffect(() => {
    if (apiKey) {
      loadAdminData();
    }
  }, [apiKey]);

  useEffect(() => {
    let interval: any;
    if (isAuthorized) {
      interval = setInterval(() => {
        setRefreshCountdown((prev) => {
          if (prev <= 1) {
            loadAdminData(true);
            return 30;
          }
          return prev - 1;
        });
      }, 1000);
    }
    return () => {
      if (interval) clearInterval(interval);
      Object.values(activeCharts.current).forEach((c) => c.destroy());
    };
  }, [isAuthorized]);

  // Rebuild charts on Dashboard tab
  useEffect(() => {
    if (currentTab !== 'dashboard' || !diagnostics || !overview) return;

    // Clean up
    Object.values(activeCharts.current).forEach((c) => c.destroy());
    activeCharts.current = {};

    const chartDefaults = {
      color: '#9ca3af',
      borderColor: 'rgba(255, 255, 255, 0.05)',
    };

    // 1. Stacked Diagnostics Timeline
    if (chartTimelineRef.current) {
      const rows = diagnostics.diagnostic_timeline_24h || [];
      const labels = rows.map((r: any) => fmtHour(r.bucket_at));
      const infoData = rows.map((r: any) => r.info || 0);
      const warnData = rows.map((r: any) => r.warning || 0);
      const errData = rows.map((r: any) => (r.error || 0) + (r.critical || 0));

      activeCharts.current.timeline = new Chart(chartTimelineRef.current, {
        type: 'bar',
        data: {
          labels,
          datasets: [
            { label: 'info', data: infoData, backgroundColor: 'rgba(91,155,213,0.5)', borderColor: 'rgba(91,155,213,0.7)', borderWidth: 1 },
            { label: 'warning', data: warnData, backgroundColor: 'rgba(212,168,68,0.5)', borderColor: 'rgba(212,168,68,0.7)', borderWidth: 1 },
            { label: 'error/critical', data: errData, backgroundColor: 'rgba(224,85,106,0.5)', borderColor: 'rgba(224,85,106,0.7)', borderWidth: 1 },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          scales: {
            x: { stacked: true, grid: { display: false } },
            y: { stacked: true, grid: { color: chartDefaults.borderColor }, beginAtZero: true },
          },
          plugins: {
            legend: { position: 'top', align: 'end', labels: { boxWidth: 10 } }
          }
        },
      });
    }

    const makeDoughnut = (canvas: HTMLCanvasElement, labels: string[], values: number[], key: string) => {
      const total = values.reduce((a, b) => a + b, 0);
      const COLORS = ['#5b9bd5', '#4caf93', '#d4a844', '#e0556a', '#9b7ec4', '#56b6c2', '#e08e4a', '#949aa5'];
      activeCharts.current[key] = new Chart(canvas, {
        type: 'doughnut',
        data: {
          labels,
          datasets: [{
            data: values,
            backgroundColor: COLORS.slice(0, labels.length),
            borderColor: '#12131e',
            borderWidth: 2,
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          cutout: '70%',
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (ctx) => ` ${ctx.label}: ${fmtNum(ctx.raw)} (${total > 0 ? ((ctx.raw as number / total) * 100).toFixed(1) : 0}%)`
              }
            }
          }
        }
      });
    };

    // 2. Platform Doughnut
    if (chartPlatformRef.current) {
      const platforms = Object.entries(overview.platform_breakdown || {}).sort((a: any, b: any) => b[1] - a[1]);
      if (platforms.length > 0) {
        makeDoughnut(chartPlatformRef.current, platforms.map((e) => e[0]), platforms.map((e) => e[1] as number), 'platform');
      }
    }

    // 3. Country Doughnut
    if (chartCountryRef.current) {
      const countries = Object.entries(overview.country_breakdown || {}).sort((a: any, b: any) => b[1] - a[1]);
      if (countries.length > 0) {
        makeDoughnut(chartCountryRef.current, countries.map((e) => e[0]), countries.map((e) => e[1] as number), 'country');
      }
    }

  }, [currentTab, diagnostics, overview]);

  // Auth management
  const handleSaveKey = () => {
    const inputKey = (document.getElementById('api-key-input') as HTMLInputElement)?.value || '';
    if (!inputKey) {
      showToast('请输入有效的 API Key', 'danger');
      return;
    }
    localStorage.setItem('cloudTelemetryAdminKey', inputKey);
    setApiKey(inputKey);
  };

  const handleClearKey = () => {
    localStorage.removeItem('cloudTelemetryAdminKey');
    setApiKey('');
    setIsAuthorized(false);
    setOverview(null);
    setDiagnostics(null);
    setInstances([]);
    showToast('凭证已清除', 'info');
  };

  // Suspension Actions
  const handleSuspend = async () => {
    if (!selectedInstanceId) return;
    try {
      await fetchJson(
        `${apiPrefix}/api/admin/instances/${encodeURIComponent(selectedInstanceId)}/suspend`,
        apiKey,
        { method: 'POST', body: JSON.stringify({ reason: suspendReason }) }
      );
      showToast('实例已封禁', 'success');
      loadInstanceDetail(selectedInstanceId);
      loadInstances(true);
      // Reload admin summary
      fetchJson(`${apiPrefix}/api/admin/overview/summary`, apiKey).then(setOverview);
    } catch (err: any) {
      showToast('封禁失败: ' + err.message, 'danger');
    }
  };

  const handleResume = async () => {
    if (!selectedInstanceId) return;
    try {
      await fetchJson(
        `${apiPrefix}/api/admin/instances/${encodeURIComponent(selectedInstanceId)}/resume`,
        apiKey,
        { method: 'POST', body: JSON.stringify({}) }
      );
      showToast('实例已解封', 'success');
      loadInstanceDetail(selectedInstanceId);
      loadInstances(true);
      // Reload admin summary
      fetchJson(`${apiPrefix}/api/admin/overview/summary`, apiKey).then(setOverview);
    } catch (err: any) {
      showToast('解封失败: ' + err.message, 'danger');
    }
  };

  // Handle column sorts
  const handleSort = (field: string) => {
    if (sortField === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortOrder('desc');
    }
    setInstancesPage(1);
  };

  // Reset Filters
  const handleResetFilters = () => {
    setFilterSearch('');
    setFilterStatus('');
    setFilterPlatform('');
    setFilterVersion('');
    setFilterSuspended('');
    setInstancesPage(1);
    showToast('筛选器已重置', 'info');
  };

  // Render Auth Key Form when locked
  if (loading && !overview) {
    return (
      <div className="loading-screen">
        <div className="spinner"></div>
        <p style={{ color: 'var(--text-secondary)' }}>正在载入管理数据...</p>
      </div>
    );
  }

  if (!isAuthorized) {
    return (
      <div className="admin-container" style={{ justifyContent: 'center', alignItems: 'center' }}>
        <div className="admin-locked-card">
          <div className="admin-locked-icon">
            <Lock size={28} />
          </div>
          <h2>Telemetry Admin Backend</h2>
          <p>请输入管理员凭证密钥 (X-API-Key) 以管理云端遥测实例并查看诊断趋势。</p>
          <input
            id="api-key-input"
            type="password"
            placeholder="输入 X-API-Key 密钥"
            defaultValue={apiKey}
            style={{
              width: '100%',
              background: 'rgba(0,0,0,0.4)',
              border: '1px solid var(--border)',
              borderRadius: '6px',
              padding: '10px 14px',
              fontSize: '14px',
              outline: 'none',
              marginBottom: '16px',
              textAlign: 'center'
            }}
            onKeyDown={(e) => e.key === 'Enter' && handleSaveKey()}
          />
          <button className="btn primary" onClick={handleSaveKey} style={{ width: '100%', padding: '10px 14px', fontSize: '13px' }}>
            验证凭证并登录
          </button>
        </div>
        
        {/* Global Toast Container */}
        <div className="toast-container">
          {toasts.map((t) => (
            <div className={`toast-msg ${t.type}`} key={t.id}>
              {t.type === 'danger' ? <AlertOctagon size={16} /> : <CheckCircle2 size={16} />}
              <span>{t.message}</span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // Loaded Admin Panel HTML
  const ov = overview || {};
  const diag = diagnostics || {};
  const perf = diag.performance_24h || {};

  // Extract unique platforms/versions for filter dropdowns from overview breakdown if present
  const availablePlatforms = Object.keys(ov.platform_breakdown || {});

  // Instance Detail domain aggregator
  const getAggregatedDrawerDomains = () => {
    if (!instanceDetail) return [];
    const windows = instanceDetail.recent_heartbeat_windows || [];
    const diags = instanceDetail.recent_diagnostic_events || [];
    
    const buckets = new Map<string, any>();
    const ensureBucket = (domain: string) => {
      if (!buckets.has(domain)) {
        buckets.set(domain, { domain, total_events: 0, warning_events: 0, error_events: 0, last_event_at: 0 });
      }
      return buckets.get(domain);
    };

    for (const w of windows) {
      const summary = w.summary || {};
      for (const item of (summary.telemetry_domains || [])) {
        const b = ensureBucket(item.domain || 'unknown');
        b.total_events += Number(item.total_events || 0);
        b.warning_events += Number(item.warning_events || 0);
        b.error_events += Number(item.error_events || 0);
        b.last_event_at = Math.max(b.last_event_at, Number(item.last_event_at || 0));
      }
    }

    for (const ev of diags) {
      const attrs = ev.attributes || {};
      if (!attrs.domain) continue;
      const b = ensureBucket(attrs.domain);
      b.total_events += 1;
      if (ev.severity === 'warning') b.warning_events += 1;
      if (['error', 'critical', 'fatal'].includes(ev.severity)) b.error_events += 1;
      b.last_event_at = Math.max(b.last_event_at, Number(ev.event_at || ev.received_at || 0));
    }

    return [...buckets.values()].sort((a, b) => 
      (b.error_events - a.error_events) || 
      (b.warning_events - a.warning_events) || 
      (b.total_events - a.total_events)
    );
  };

  return (
    <div className="admin-container">
      {/* 1. Left Navigation Sidebar */}
      <aside className="admin-sidebar">
        <div className="admin-sidebar-header">
          <div className="admin-sidebar-logo">
            <img src={`${apiPrefix}/logo.png`} className="brand-logo" alt="Logo" style={{ width: '28px', height: '28px', objectFit: 'contain' }} />
            <div>
              <h2>Telemetry Panel</h2>
              <p>实例治理与诊断</p>
            </div>
          </div>
        </div>

        <nav className="admin-sidebar-menu">
          <button 
            className={`admin-menu-item ${currentTab === 'dashboard' ? 'active' : ''}`}
            onClick={() => { setCurrentTab('dashboard'); setSelectedInstanceId(null); }}
          >
            <BarChart2 size={16} />
            <span>仪表盘总览</span>
          </button>
          <button 
            className={`admin-menu-item ${currentTab === 'instances' ? 'active' : ''}`}
            onClick={() => setCurrentTab('instances')}
          >
            <Server size={16} />
            <span>遥测实例管理</span>
          </button>
          <button 
            className={`admin-menu-item ${currentTab === 'diagnostics' ? 'active' : ''}`}
            onClick={() => { setCurrentTab('diagnostics'); setSelectedInstanceId(null); }}
          >
            <List size={16} />
            <span>全局诊断日志</span>
          </button>
        </nav>

        <div className="admin-sidebar-footer">
          <div className="sidebar-auth-box">
            <h4>
              <span>凭证密钥</span>
              <UserCheck size={12} style={{ color: 'hsl(var(--success-hsl))' }} />
            </h4>
            <div style={{ wordBreak: 'break-all', fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '8px', fontFamily: 'var(--mono)' }}>
              {apiKey.slice(0, 8) + '***' + apiKey.slice(-4)}
            </div>
            <button className="btn secondary" onClick={handleClearKey} style={{ width: '100%' }}>
              <Unlock size={12} />
              <span>注销退出</span>
            </button>
          </div>
        </div>
      </aside>

      {/* 2. Main Viewport wrapper */}
      <div className="admin-view-wrapper">
        {/* Top Navbar */}
        <header className="admin-navbar">
          <div className="admin-navbar-title">
            <span>
              {currentTab === 'dashboard' && '仪表盘总览'}
              {currentTab === 'instances' && '遥测实例管理'}
              {currentTab === 'diagnostics' && '全局诊断日志'}
            </span>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 400 }}>
              {currentTab === 'instances' && `(${fmtNum(instancesCount)} 个实例)`}
            </span>
          </div>

          <div className="admin-navbar-right">
            <div className="refresh-badge">
              <span className="dot"></span>
              <span>{refreshCountdown}s 自动刷新</span>
            </div>
            <button className="btn" onClick={() => loadAdminData()} title="刷新数据">
              <RefreshCw size={12} />
            </button>
            <a href="/_cloud_telemetry/" className="btn secondary">
              <span>返回公开面板</span>
            </a>
          </div>
        </header>

        {/* Dynamic View Loader */}
        <div className="admin-content">
          {/* TAB 1: DASHBOARD VIEW */}
          {currentTab === 'dashboard' && (
            <>
              {/* KPI cards rows */}
              <section className="kpi-row">
                <div className="kpi-card">
                  <div className="kpi-label">在线实例 / 累计</div>
                  <div className="kpi-value">{fmtNum(ov.online_instances)} / {fmtNum(ov.total_instances)}</div>
                  <div className="kpi-sub">已封禁拦截的实例: {fmtNum(ov.suspended_instances)}</div>
                </div>

                <div className="kpi-card">
                  <div className="kpi-label">24h 诊断事件</div>
                  <div className="kpi-value">{fmtNum(diag.diagnostic_count_24h)}</div>
                  <div className="kpi-sub">24h 错误率: {fmtPct(diag.error_rate_24h)}</div>
                </div>

                <div className="kpi-card">
                  <div className="kpi-label">24h 错误事件总数</div>
                  <div className="kpi-value">{fmtNum(diag.error_count_24h)}</div>
                  <div className="kpi-sub">数据来自 {fmtNum(diag.window_count_24h)} 个遥测包</div>
                </div>

                <div className="kpi-card">
                  <div className="kpi-label">LLM 请求健康度</div>
                  <div className="kpi-value">{fmtPct(perf.success_rate)}</div>
                  <div className="kpi-sub">请求数: {fmtNum(perf.request_count)} · 平均延迟: {Number(perf.average_latency || 0).toFixed(2)}s</div>
                </div>
              </section>

              {/* Stacked Timeline Chart & Mini Stats */}
              <section className="panel-grid-2">
                <div className="panel">
                  <div className="panel-header">
                    <div className="panel-header-title">
                      <h3>24h 诊断日志趋势</h3>
                      <p>按事件严重级别(info, warning, error/critical)堆叠统计</p>
                    </div>
                  </div>
                  <div className="panel-body">
                    <div className="chart-container h-md">
                      <canvas ref={chartTimelineRef}></canvas>
                    </div>
                  </div>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <div className="panel">
                    <div className="panel-header">
                      <div className="panel-header-title"><h3>在线状态分布</h3></div>
                    </div>
                    <div className="panel-body">
                      <div className="watchdog-strip" style={{ gridTemplateColumns: 'repeat(2, 1fr)', gap: '10px' }}>
                        <div className="watchdog-card">
                          <span className="watchdog-val" style={{ color: 'hsl(var(--success-hsl))' }}>{fmtNum(ov.online_instances)}</span>
                          <span className="watchdog-lbl">在线活动</span>
                        </div>
                        <div className="watchdog-card">
                          <span className="watchdog-val" style={{ color: 'var(--text-secondary)' }}>{fmtNum(ov.offline_instances)}</span>
                          <span className="watchdog-lbl">离线断连</span>
                        </div>
                        <div className="watchdog-card" style={{ gridColumn: 'span 2' }}>
                          <span className="watchdog-val" style={{ color: 'hsl(var(--danger-hsl))' }}>{fmtNum(ov.suspended_instances)}</span>
                          <span className="watchdog-lbl">封禁拦截实例</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="panel">
                    <div className="panel-header">
                      <div className="panel-header-title"><h3>遥测心跳缺口</h3></div>
                    </div>
                    <div className="panel-body">
                      <div className="watchdog-strip" style={{ gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px' }}>
                        <div className="watchdog-card">
                          <span className="watchdog-val" style={{ color: 'hsl(var(--success-hsl))' }}>{fmtNum(ov.gap_status_breakdown?.healthy || 0)}</span>
                          <span className="watchdog-lbl">连续正常</span>
                        </div>
                        <div className="watchdog-card">
                          <span className="watchdog-val" style={{ color: 'hsl(var(--warning-hsl))' }}>{fmtNum(ov.gap_status_breakdown?.pending || 0)}</span>
                          <span className="watchdog-lbl">待补齐</span>
                        </div>
                        <div className="watchdog-card">
                          <span className="watchdog-val" style={{ color: 'hsl(var(--danger-hsl))' }}>{fmtNum(ov.gap_status_breakdown?.permanent_loss || 0)}</span>
                          <span className="watchdog-lbl">永久丢失</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </section>

              {/* Platform & Country Doughnuts & Active LLM requests */}
              <section className="panel-grid-3">
                {renderDoughnutPanel(
                  '终端操作系统',
                  chartPlatformRef,
                  Object.entries(ov.platform_breakdown || {}).map(([label, count]) => ({ label, count: count as number }))
                )}

                {renderDoughnutPanel(
                  '地理区域分布',
                  chartCountryRef,
                  Object.entries(ov.country_breakdown || {}).map(([label, count]) => ({ label, count: count as number }))
                )}

                {/* System Watchdog Health Panel */}
                <div className="panel">
                  <div className="panel-header">
                    <div className="panel-header-title">
                      <h3>高消耗 LLM 请求 (24h)</h3>
                      <p>按 Token 总量降序排列 (前5名)</p>
                    </div>
                  </div>
                  <div className="panel-body no-padding">
                    <div className="table-wrapper">
                      <table className="admin-table">
                        <thead>
                          <tr>
                            <th>名称</th>
                            <th>计数</th>
                            <th>总 Token</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(perf.top_requests || []).slice(0, 5).map((r: any, idx: number) => (
                            <tr key={idx}>
                              <td className="mono" style={{ fontSize: '11px', maxWidth: '140px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.request_name}</td>
                              <td>{fmtNum(r.request_count)}</td>
                              <td>{fmtNum(r.total_tokens)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              </section>

              {/* Watchdog status strip & Domain event card grid */}
              <section className="panel-grid-2">
                <div className="panel">
                  <div className="panel-header">
                    <div className="panel-header-title"><h3>遥测看门狗健康状态</h3></div>
                  </div>
                  <div className="panel-body">
                    <div className="watchdog-strip">
                      <div className="watchdog-card">
                        <span className="watchdog-val">{perf.watchdog_samples ? `${Number(perf.watchdog_running_samples || 0)}/${perf.watchdog_samples}` : '-'}</span>
                        <span className="watchdog-lbl">看门狗监测成功率</span>
                      </div>
                      <div className="watchdog-card">
                        <span className="watchdog-val">{perf.watchdog_samples ? `${Number(perf.watchdog_thread_alive_samples || 0)}/${perf.watchdog_samples}` : '-'}</span>
                        <span className="watchdog-lbl">守护线程存活率</span>
                      </div>
                      <div className="watchdog-card">
                        <span className="watchdog-val">{fmtNum(perf.watchdog_registered_streams_max)}</span>
                        <span className="watchdog-lbl">历史最大活动流计数</span>
                      </div>
                      <div className="watchdog-card">
                        <span className="watchdog-val" style={{ color: Number(perf.stream_failures_max || 0) > 0 ? 'hsl(var(--danger-hsl))' : 'inherit' }}>
                          {fmtNum(perf.stream_failures_max)}
                        </span>
                        <span className="watchdog-lbl">连接拦截器失败重试</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="panel">
                  <div className="panel-header">
                    <div className="panel-header-title"><h3>遥测健康事件分类域</h3></div>
                  </div>
                  <div className="panel-body" style={{ maxHeight: '200px', overflowY: 'auto' }}>
                    <div className="domain-grid" style={{ gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                      {(perf.health_domains || []).map((d: any, idx: number) => (
                        <div className="domain-card" key={idx} style={{ padding: '8px 12px' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span className="domain-name" style={{ fontSize: '11px' }}>{d.domain}</span>
                            <span className={`chip ${Number(d.error_events) > 0 ? 'bad' : Number(d.warning_events) > 0 ? 'warn' : 'good'}`} style={{ fontSize: '8px', padding: '1px 4px' }}>
                              {Number(d.error_events) > 0 ? 'err' : Number(d.warning_events) > 0 ? 'warn' : 'ok'}
                            </span>
                          </div>
                          <div style={{ display: 'flex', gap: '6px', fontSize: '9px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                            <span>事件: {fmtNum(d.total_events)}</span>
                            {Number(d.error_events) > 0 && <span style={{ color: 'hsl(var(--danger-hsl))' }}>误: {d.error_events}</span>}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </section>

              {/* Recent errors feed table */}
              <section className="panel">
                <div className="panel-header">
                  <div className="panel-header-title">
                    <h3>近期拦截到的 Error / Critical / Fatal 异常诊断事件 (24h)</h3>
                    <p>按接收时间倒序，最多展示最近 80 条错误</p>
                  </div>
                </div>
                <div className="panel-body no-padding">
                  <div className="table-wrapper">
                    <table className="admin-table">
                      <thead>
                        <tr>
                          <th>接收时间</th>
                          <th>实例 ID</th>
                          <th>严重级别</th>
                          <th>事件名称</th>
                          <th>事件摘要说明</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(diag.recent_error_events || []).length === 0 ? (
                          <tr>
                            <td colSpan={5} style={{ textAlign: 'center', padding: '30px', color: 'var(--text-secondary)' }}>
                              最近 24 小时无严重诊断错误事件
                            </td>
                          </tr>
                        ) : (
                          (diag.recent_error_events || []).map((r: any, idx: number) => (
                            <tr key={idx} onClick={() => setSelectedInstanceId(r.client_instance_id_masked || r.client_instance_id)}>
                              <td className="mono">{fmtTime(r.received_at || r.event_at)}</td>
                              <td className="mono" style={{ color: 'hsl(var(--primary-hsl))' }}>{r.client_instance_id_masked || 'anonymous'}</td>
                              <td><span className="chip bad">{r.severity}</span></td>
                              <td className="mono">{r.event_name}</td>
                              <td>{r.summary}</td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </section>
            </>
          )}

          {/* TAB 2: INSTANCES LIST MANAGEMENT */}
          {currentTab === 'instances' && (
            <div className="panel" style={{ flex: 1 }}>
              {/* Dynamic Filter panel */}
              <div className="filter-bar">
                <div className="search-input-wrapper">
                  <Search size={14} />
                  <input
                    type="text"
                    placeholder="按 Client ID 实例前缀模糊检索..."
                    value={filterSearch}
                    onChange={(e) => { setFilterSearch(e.target.value); setInstancesPage(1); }}
                  />
                </div>

                <div className="select-wrapper">
                  <select value={filterStatus} onChange={(e) => { setFilterStatus(e.target.value); setInstancesPage(1); }}>
                    <option value="">在线状态(全部)</option>
                    <option value="active">在线 (Active)</option>
                    <option value="offline">离线 (Offline)</option>
                    <option value="suspended">已封禁 (Suspended)</option>
                  </select>
                </div>

                <div className="select-wrapper">
                  <select value={filterPlatform} onChange={(e) => { setFilterPlatform(e.target.value); setInstancesPage(1); }}>
                    <option value="">终端系统(全部)</option>
                    {availablePlatforms.map((p) => (
                      <option key={p} value={p}>{p}</option>
                    ))}
                  </select>
                </div>

                <div className="select-wrapper">
                  <select value={filterSuspended} onChange={(e) => { setFilterSuspended(e.target.value); setInstancesPage(1); }}>
                    <option value="">封禁态(全部)</option>
                    <option value="true">已封禁</option>
                    <option value="false">未封禁</option>
                  </select>
                </div>

                <button className="btn secondary" onClick={handleResetFilters}>
                  重置筛选
                </button>
              </div>

              {/* Data Table */}
              <div className="panel-body no-padding" style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
                <div className="table-wrapper" style={{ flex: 1 }}>
                  <table className="admin-table">
                    <thead>
                      <tr>
                        <th>Client Instance ID (脱敏)</th>
                        <th className="sortable" onClick={() => handleSort('online_status')}>
                          在线状态 {sortField === 'online_status' && (sortOrder === 'asc' ? '↑' : '↓')}
                        </th>
                        <th>应用版本</th>
                        <th>系统平台</th>
                        <th>国家</th>
                        <th className="sortable" onClick={() => handleSort('last_heartbeat_received_at')}>
                          最后心跳接收时间 {sortField === 'last_heartbeat_received_at' && (sortOrder === 'asc' ? '↑' : '↓')}
                        </th>
                        <th>心跳缺口</th>
                        <th>最高警报</th>
                        <th>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {instances.length === 0 ? (
                        <tr>
                          <td colSpan={9} style={{ textAlign: 'center', padding: '48px', color: 'var(--text-secondary)' }}>
                            没有找到符合过滤条件的遥测实例
                          </td>
                        </tr>
                      ) : (
                        instances.map((item, idx) => (
                          <tr key={idx} onClick={() => setSelectedInstanceId(item.client_instance_id_masked || item.client_instance_id)}>
                            <td className="mono" style={{ fontWeight: 600, color: 'var(--text)' }}>
                              {item.client_instance_id_masked || item.client_instance_id}
                            </td>
                            <td>
                              <span className={`chip ${item.online_status === 'active' ? 'good' : item.online_status === 'suspended' ? 'bad' : 'info'}`}>
                                {item.online_status}
                              </span>
                            </td>
                            <td><span className="chip" style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border)' }}>{item.app_version || '?'}</span></td>
                            <td>{item.platform || '?'}</td>
                            <td><span className="mono">{item.country_code || '-'}</span></td>
                            <td className="mono">{fmtTime(item.last_heartbeat_received_at)}</td>
                            <td>
                              <span className={`chip ${item.gap_status === 'healthy' ? 'good' : item.gap_status === 'pending' ? 'warn' : 'bad'}`}>
                                {item.gap_status}
                              </span>
                            </td>
                            <td>
                              {item.last_diagnostic_severity ? (
                                <span className={`chip ${['error', 'critical', 'fatal'].includes(item.last_diagnostic_severity) ? 'bad' : item.last_diagnostic_severity === 'warning' ? 'warn' : 'info'}`}>
                                  {item.last_diagnostic_severity}
                                </span>
                              ) : (
                                <span style={{ color: 'var(--text-muted)' }}>-</span>
                              )}
                            </td>
                            <td>
                              <button 
                                className="btn primary" 
                                style={{ padding: '3px 8px', height: '24px', fontSize: '10px' }}
                                onClick={(e) => { e.stopPropagation(); setSelectedInstanceId(item.client_instance_id_masked || item.client_instance_id); }}
                              >
                                详情
                              </button>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>

                {/* Pagination Controls */}
                <div className="pagination-bar">
                  <div className="pagination-info">
                    显示第 {instances.length > 0 ? (instancesPage - 1) * instancesLimit + 1 : 0} 至 {Math.min(instancesPage * instancesLimit, instancesCount)} 条记录，共 {fmtNum(instancesCount)} 条
                  </div>

                  <div className="pagination-controls">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginRight: '16px', fontSize: '12px', color: 'var(--text-secondary)' }}>
                      <span>每页显示</span>
                      <div className="select-wrapper">
                        <select 
                          value={instancesLimit} 
                          onChange={(e) => { setInstancesLimit(Number(e.target.value)); setInstancesPage(1); }}
                          style={{ padding: '4px 8px', minWidth: '70px', height: '28px', fontSize: '12px' }}
                        >
                          <option value={20}>20 条</option>
                          <option value={50}>50 条</option>
                          <option value={100}>100 条</option>
                          <option value={200}>200 条</option>
                        </select>
                      </div>
                    </div>

                    <button 
                      className="pagination-btn" 
                      onClick={() => setInstancesPage(1)} 
                      disabled={instancesPage === 1}
                      title="第一页"
                    >
                      <ChevronsLeft size={14} />
                    </button>
                    <button 
                      className="pagination-btn" 
                      onClick={() => setInstancesPage((p) => Math.max(1, p - 1))} 
                      disabled={instancesPage === 1}
                      title="上一页"
                    >
                      <ChevronLeft size={14} />
                    </button>
                    <span style={{ fontSize: '12px', margin: '0 8px', color: 'var(--text)' }}>
                      第 {instancesPage} 页
                    </span>
                    <button 
                      className="pagination-btn" 
                      onClick={() => setInstancesPage((p) => Math.min(Math.ceil(instancesCount / instancesLimit), p + 1))} 
                      disabled={instancesPage >= Math.ceil(instancesCount / instancesLimit)}
                      title="下一页"
                    >
                      <ChevronRight size={14} />
                    </button>
                    <button 
                      className="pagination-btn" 
                      onClick={() => setInstancesPage(Math.ceil(instancesCount / instancesLimit))} 
                      disabled={instancesPage >= Math.ceil(instancesCount / instancesLimit)}
                      title="最后一页"
                    >
                      <ChevronsRight size={14} />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: DIAGNOSTICS GLOBAL LOGS VIEW */}
          {currentTab === 'diagnostics' && (
            <div className="panel" style={{ flex: 1 }}>
              <div className="panel-header">
                <div className="panel-header-title">
                  <h3>最近拦截异常与警告诊断日志</h3>
                  <p>实时提取当前系统数据库中所有实例触发的诊断错误事件流</p>
                </div>
              </div>
              
              <div className="panel-body no-padding" style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
                <div className="table-wrapper" style={{ flex: 1 }}>
                  <table className="admin-table">
                    <thead>
                      <tr>
                        <th>上报时间</th>
                        <th>实例 ID</th>
                        <th>严重级别</th>
                        <th>诊断事件</th>
                        <th>事件说明与详细日志</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(diag.recent_error_events || []).length === 0 ? (
                        <tr>
                          <td colSpan={5} style={{ textAlign: 'center', padding: '48px', color: 'var(--text-secondary)' }}>
                            暂无诊断异常日志
                          </td>
                        </tr>
                      ) : (
                        (diag.recent_error_events || []).map((ev: any, idx: number) => (
                          <tr key={idx} onClick={() => setSelectedInstanceId(ev.client_instance_id_masked || ev.client_instance_id)}>
                            <td className="mono" style={{ whiteSpace: 'nowrap' }}>{fmtTime(ev.received_at || ev.event_at)}</td>
                            <td className="mono" style={{ color: 'hsl(var(--primary-hsl))' }}>
                              {ev.client_instance_id_masked || 'anonymous'}
                            </td>
                            <td>
                              <span className={`chip ${['error', 'critical', 'fatal'].includes(ev.severity) ? 'bad' : ev.severity === 'warning' ? 'warn' : 'info'}`}>
                                {ev.severity}
                              </span>
                            </td>
                            <td className="mono" style={{ fontWeight: 600 }}>{ev.event_name}</td>
                            <td>{ev.summary}</td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 3. Instance Details Sliding Drawer (右侧滑出抽屉) */}
      {selectedInstanceId && (
        <>
          <div className="drawer-overlay" onClick={() => setSelectedInstanceId(null)}></div>
          <div className="drawer-container">
            <div className="drawer-header">
              <div className="drawer-title-box">
                <h3>{instanceDetail?.client_instance_id || selectedInstanceId}</h3>
                <p>
                  系统平台: {instanceDetail?.platform || '?'} · 应用版本: {instanceDetail?.app_version || '?'} · 国家: {instanceDetail?.country_code || '?'}
                </p>
              </div>
              <button className="drawer-close" onClick={() => setSelectedInstanceId(null)}>
                <X size={16} />
              </button>
            </div>

            {/* Tabs inside drawer */}
            <div className="drawer-tabs">
              <button className={`drawer-tab ${drawerTab === 'overview' ? 'active' : ''}`} onClick={() => setDrawerTab('overview')}>基本状态</button>
              <button className={`drawer-tab ${drawerTab === 'llm' ? 'active' : ''}`} onClick={() => setDrawerTab('llm')}>LLM 统计</button>
              <button className={`drawer-tab ${drawerTab === 'domains' ? 'active' : ''}`} onClick={() => setDrawerTab('domains')}>遥测域聚合</button>
              <button className={`drawer-tab ${drawerTab === 'logs' ? 'active' : ''}`} onClick={() => setDrawerTab('logs')}>最近诊断事件 ({instanceDetail?.recent_diagnostic_events?.length || 0})</button>
            </div>

            {/* Drawer Body content */}
            <div className="drawer-body">
              {!instanceDetail ? (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '200px', gap: '10px' }}>
                  <div className="spinner"></div>
                  <p style={{ color: 'var(--text-secondary)' }}>正在载入实例遥测明细...</p>
                </div>
              ) : (
                <>
                  {/* TAB A: OVERVIEW & SUSPENSION */}
                  {drawerTab === 'overview' && (
                    <>
                      {/* Meta metrics grid */}
                      <div className="detail-info-grid">
                        <div className="detail-info-item">
                          <span className="detail-info-label">在线状态</span>
                          <span className="detail-info-value">
                            <span className={`chip ${instanceDetail.online_status === 'active' ? 'good' : instanceDetail.online_status === 'suspended' ? 'bad' : 'info'}`}>
                              {instanceDetail.online_status}
                            </span>
                          </span>
                        </div>
                        <div className="detail-info-item">
                          <span className="detail-info-label">缺口状态</span>
                          <span className="detail-info-value">
                            <span className={`chip ${instanceDetail.gap_status === 'healthy' ? 'good' : instanceDetail.gap_status === 'pending' ? 'warn' : 'bad'}`}>
                              {instanceDetail.gap_status}
                            </span>
                          </span>
                        </div>
                        <div className="detail-info-item">
                          <span className="detail-info-label">最后心跳时间</span>
                          <span className="detail-info-value">{fmtTime(instanceDetail.last_heartbeat_received_at)} ({fmtRelative(instanceDetail.last_heartbeat_received_at)})</span>
                        </div>
                        <div className="detail-info-item">
                          <span className="detail-info-label">首次注册时间</span>
                          <span className="detail-info-value">{fmtTime(instanceDetail.first_registered_at)}</span>
                        </div>
                        <div className="detail-info-item">
                          <span className="detail-info-label">最后心跳结果</span>
                          <span className="detail-info-value mono">{instanceDetail.last_heartbeat_result || '-'}</span>
                        </div>
                        <div className="detail-info-item">
                          <span className="detail-info-label">允许保存 IP</span>
                          <span className="detail-info-value">{instanceDetail.allow_ip_retention ? '是 (True)' : '否 (False)'}</span>
                        </div>
                        <div className="detail-info-item">
                          <span className="detail-info-label">心跳上报序号</span>
                          <span className="detail-info-value mono">Seq #{instanceDetail.last_window_sequence ?? '-'}</span>
                        </div>
                        <div className="detail-info-item">
                          <span className="detail-info-label">离线到期判定</span>
                          <span className="detail-info-value">{fmtTime(instanceDetail.offline_deadline_at)}</span>
                        </div>
                      </div>

                      {/* Suspension form */}
                      <div className={`suspend-panel ${instanceDetail.is_suspended ? 'active' : ''}`}>
                        <h4>
                          {instanceDetail.is_suspended ? (
                            <>
                              <Pause size={16} style={{ color: 'red' }} />
                              <span>实例当前处于「封禁停传」状态</span>
                            </>
                          ) : (
                            <>
                              <Play size={16} style={{ color: 'green' }} />
                              <span>实例运行正常，接收数据中</span>
                            </>
                          )}
                        </h4>
                        
                        <p style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                          封禁该实例后，客户端在下一次上报心跳时会收到停传指令（Status: Rejected Permanent），并自动停止向服务器发送任何遥测数据。
                        </p>
                        
                        <textarea
                          placeholder="输入封禁或审计原因说明 (便于审计日志落库)..."
                          value={suspendReason}
                          onChange={(e) => setSuspendReason(e.target.value)}
                        />
                        
                        <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
                          <button
                            className="btn danger"
                            onClick={handleSuspend}
                            disabled={instanceDetail.is_suspended}
                          >
                            禁止接收遥测数据
                          </button>
                          <button
                            className="btn primary"
                            onClick={handleResume}
                            disabled={!instanceDetail.is_suspended}
                          >
                            解封并恢复接收
                          </button>
                        </div>
                      </div>
                    </>
                  )}

                  {/* TAB B: LLM REQUESTS TABLE */}
                  {drawerTab === 'llm' && (
                    <div className="panel">
                      <div className="panel-header">
                        <div className="panel-header-title"><h3>该实例的 top LLM 请求列表</h3></div>
                      </div>
                      <div className="panel-body no-padding">
                        <div className="table-wrapper">
                          <table className="admin-table">
                            <thead>
                              <tr>
                                <th>接口名称</th>
                                <th>次数</th>
                                <th>耗时</th>
                                <th>成功率</th>
                                <th>缓存</th>
                              </tr>
                            </thead>
                            <tbody>
                              {(() => {
                                // Extract top requests from last heartbeat window summary
                                const latestWindow = (instanceDetail.recent_heartbeat_windows || [])[0] || {};
                                const reqs = latestWindow.summary?.llm_request_name_top || [];
                                if (reqs.length === 0) {
                                  return (
                                    <tr>
                                      <td colSpan={5} style={{ textAlign: 'center', padding: '24px', color: 'var(--text-secondary)' }}>
                                        该实例最近未产生 LLM 遥测上报
                                      </td>
                                    </tr>
                                  );
                                }
                                return reqs.map((r: any, idx: number) => (
                                  <tr key={idx}>
                                    <td className="mono" style={{ fontSize: '11px' }}>{r.request_name}</td>
                                    <td>{fmtNum(r.request_count)}</td>
                                    <td>{Number(r.average_latency || 0).toFixed(2)}s</td>
                                    <td>{fmtPct(r.success_rate)}</td>
                                    <td>{fmtPct(r.cache_hit_rate)}</td>
                                  </tr>
                                ));
                              })()}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* TAB C: TELEMETRY DOMAINS */}
                  {drawerTab === 'domains' && (
                    <div className="domain-grid" style={{ gridTemplateColumns: '1fr 1fr' }}>
                      {getAggregatedDrawerDomains().length === 0 ? (
                        <div className="empty-state" style={{ gridColumn: 'span 2' }}>
                          未发现有事件域指标
                        </div>
                      ) : (
                        getAggregatedDrawerDomains().map((d: any, idx: number) => (
                          <div className="domain-card" key={idx}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                              <span className="domain-name">{d.domain}</span>
                              <span className={`chip ${d.error_events > 0 ? 'bad' : d.warning_events > 0 ? 'warn' : 'good'}`}>
                                {d.error_events > 0 ? 'error' : d.warning_events > 0 ? 'warning' : 'ok'}
                              </span>
                            </div>
                            <span className="domain-time" style={{ display: 'block', marginTop: '4px' }}>
                              最近事件: {fmtTime(d.last_event_at)}
                            </span>
                            <div style={{ display: 'flex', gap: '6px', fontSize: '10px', marginTop: '8px', color: 'var(--text-secondary)' }}>
                              <span className="chip info" style={{ fontSize: '9px', padding: '1px 6px' }}>事件数: {d.total_events}</span>
                              {d.warning_events > 0 && <span style={{ color: 'hsl(var(--warning-hsl))' }}>警告: {d.warning_events}</span>}
                              {d.error_events > 0 && <span style={{ color: 'hsl(var(--danger-hsl))' }}>报错: {d.error_events}</span>}
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  )}

                  {/* TAB D: RECENT DIAGNOSTIC EVENTS */}
                  {drawerTab === 'logs' && (
                    <div className="diagnostic-log-feed">
                      {(instanceDetail.recent_diagnostic_events || []).length === 0 ? (
                        <div className="empty-state">
                          未发现该实例上报的诊断事件日志
                        </div>
                      ) : (
                        (instanceDetail.recent_diagnostic_events || []).map((ev: any, idx: number) => (
                          <div className="diagnostic-log-item" key={idx}>
                            <div className="diagnostic-log-header">
                              <div className="diagnostic-log-title">
                                <span className={`chip ${['error', 'critical', 'fatal'].includes(ev.severity) ? 'bad' : ev.severity === 'warning' ? 'warn' : 'good'}`}>
                                  {ev.severity}
                                </span>
                                <span className="diagnostic-log-name">{ev.event_name}</span>
                              </div>
                              <span className="diagnostic-log-time">{fmtTime(ev.event_at || ev.received_at)}</span>
                            </div>
                            <div className="diagnostic-log-body">
                              {ev.summary}
                            </div>
                            {ev.attributes && Object.keys(ev.attributes).length > 0 && (
                              <div className="diagnostic-log-attributes">
                                {JSON.stringify(ev.attributes)}
                              </div>
                            )}
                          </div>
                        ))
                      )}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </>
      )}

      {/* Global Toast Container */}
      <div className="toast-container">
        {toasts.map((t) => (
          <div className={`toast-msg ${t.type}`} key={t.id}>
            {t.type === 'danger' ? <AlertOctagon size={16} /> : <CheckCircle2 size={16} />}
            <span>{t.message}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
