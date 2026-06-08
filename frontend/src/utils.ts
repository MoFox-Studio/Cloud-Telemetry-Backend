export function esc(v: any): string {
  return String(v ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

export function fmtNum(v: any): string {
  const num = Number(v);
  if (isNaN(num)) return '0';
  return new Intl.NumberFormat('zh-CN').format(num);
}

export function fmtPct(v: any): string {
  const num = Number(v);
  if (isNaN(num)) return '0.0%';
  return `${(num * 100).toFixed(1)}%`;
}

export function fmtTime(ts: any): string {
  if (!ts) return '-';
  const val = Number(ts);
  if (isNaN(val) || val <= 0) return '-';
  return new Date(val * 1000).toLocaleString('zh-CN', { hour12: false });
}

export function fmtHour(ts: any): string {
  if (!ts) return '-';
  const val = Number(ts);
  if (isNaN(val) || val <= 0) return '-';
  const d = new Date(val * 1000);
  return `${String(d.getHours()).padStart(2, '0')}:00`;
}

export function fmtDate(ts: any): string {
  if (!ts) return '-';
  const val = Number(ts);
  if (isNaN(val) || val <= 0) return '-';
  const d = new Date(val * 1000);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

export function fmtRelative(ts: any): string {
  if (!ts) return '-';
  const val = Number(ts);
  if (isNaN(val) || val <= 0) return '-';
  const now = Math.floor(Date.now() / 1000);
  const diff = now - val;
  if (diff < 0) return '刚刚';
  if (diff < 60) return `${diff} 秒前`;
  const mins = Math.floor(diff / 60);
  if (mins < 60) return `${mins} 分钟前`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} 天前`;
  return fmtTime(ts);
}

export async function fetchJson<T = any>(url: string, apiKey?: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { ...(options.headers as Record<string, string>) };
  if (apiKey) {
    headers['X-API-Key'] = apiKey;
  }
  if (options.body && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  const res = await fetch(url, { ...options, headers });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP 错误 ${res.status}`);
  }
  return res.json() as Promise<T>;
}
