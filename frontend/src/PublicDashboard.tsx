import React, { useEffect, useState, useRef, useMemo } from 'react';
import { Chart, registerables } from 'chart.js';
import { Activity, Cpu, Database, RefreshCw, BarChart2, CheckCircle2, AlertTriangle, AlertOctagon, Server, Globe } from 'lucide-react';
import { fetchJson, fmtNum, fmtPct, fmtTime, fmtHour, fmtDate } from './utils';
// @ts-ignore
import ReactGlobe from 'react-globe.gl';
import * as THREE from 'three';
import ShinyText from './components/ShinyText';
import MagicRings from './components/MagicRings';
import BorderGlow from './components/BorderGlow';

Chart.register(...registerables);

const CHART_COLORS = ['#5b9bd5', '#4caf93', '#d4a844', '#e0556a', '#9b7ec4', '#56b6c2', '#e08e4a', '#949aa5'];
const PANEL_GLOW_COLORS = ['#818cf8', '#f472b6', '#38bdf8'];
const HERO_GLOW_COLORS = ['#34d399', '#60a5fa', '#c084fc'];
const KPI_GLOW_COLORS = ['#8b5cf6', '#f472b6', '#38bdf8'];
const DANGER_GLOW_COLORS = ['#fb7185', '#f59e0b', '#ef4444'];

type GeoCoords = { name: string; lat: number; lon: number };

const COUNTRY_COORDS: Record<string, GeoCoords> = {
  CN: { name: '中国', lat: 35.8617, lon: 104.1954 },
  US: { name: '美国', lat: 37.0902, lon: -95.7129 },
  DE: { name: '德国', lat: 51.1657, lon: 10.4515 },
  JP: { name: '日本', lat: 36.2048, lon: 138.2529 },
  GB: { name: '英国', lat: 55.3781, lon: -3.4360 },
  FR: { name: '法国', lat: 46.2276, lon: 2.2137 },
  KR: { name: '韩国', lat: 35.9078, lon: 127.7669 },
  SG: { name: '新加坡', lat: 1.3521, lon: 103.8198 },
  RU: { name: '俄罗斯', lat: 61.5240, lon: 105.3188 },
  AU: { name: '澳大利亚', lat: -25.2744, lon: 133.7751 },
  CA: { name: '加拿大', lat: 56.1304, lon: -106.3468 },
  BR: { name: '巴西', lat: -14.2350, lon: -51.9253 },
  IN: { name: '印度', lat: 20.5937, lon: 78.9629 },
  ZA: { name: '南非', lat: -30.5595, lon: 22.9375 },
  NL: { name: '荷兰', lat: 52.1326, lon: 5.2913 },
  HK: { name: '中国香港', lat: 22.3964, lon: 114.1095 },
  TW: { name: '中国台湾', lat: 23.6978, lon: 120.9605 },
  MO: { name: '中国澳门', lat: 22.1987, lon: 113.5439 }
};

const REGION_COORDS: Record<string, GeoCoords> = {
  'CN-BJ': { name: '北京', lat: 39.9042, lon: 116.4074 },
  'CN-TJ': { name: '天津', lat: 39.3434, lon: 117.3616 },
  'CN-HE': { name: '河北', lat: 38.0428, lon: 114.5149 },
  'CN-SX': { name: '山西', lat: 37.8706, lon: 112.5489 },
  'CN-NM': { name: '内蒙古', lat: 43.6530, lon: 111.6708 },
  'CN-LN': { name: '辽宁', lat: 41.8057, lon: 123.4315 },
  'CN-JL': { name: '吉林', lat: 43.8171, lon: 125.3235 },
  'CN-HL': { name: '黑龙江', lat: 45.8038, lon: 126.5349 },
  'CN-SH': { name: '上海', lat: 31.2304, lon: 121.4737 },
  'CN-JS': { name: '江苏', lat: 32.0603, lon: 118.7969 },
  'CN-ZJ': { name: '浙江', lat: 30.2741, lon: 120.1551 },
  'CN-AH': { name: '安徽', lat: 31.8206, lon: 117.2272 },
  'CN-FJ': { name: '福建', lat: 26.0745, lon: 119.2965 },
  'CN-JX': { name: '江西', lat: 28.6820, lon: 115.8579 },
  'CN-SD': { name: '山东', lat: 36.6512, lon: 117.1201 },
  'CN-HA': { name: '河南', lat: 34.7657, lon: 113.7532 },
  'CN-HB': { name: '湖北', lat: 30.5928, lon: 114.3055 },
  'CN-HN': { name: '湖南', lat: 28.2282, lon: 112.9388 },
  'CN-GD': { name: '广东', lat: 23.1291, lon: 113.2644 },
  'CN-GX': { name: '广西', lat: 22.8170, lon: 108.3669 },
  'CN-HI': { name: '海南', lat: 20.0440, lon: 110.1983 },
  'CN-CQ': { name: '重庆', lat: 29.5630, lon: 106.5516 },
  'CN-SC': { name: '四川', lat: 30.5728, lon: 104.0668 },
  'CN-GZ': { name: '贵州', lat: 26.6470, lon: 106.6302 },
  'CN-YN': { name: '云南', lat: 25.0389, lon: 102.7183 },
  'CN-XZ': { name: '西藏', lat: 29.6520, lon: 91.1721 },
  'CN-SN': { name: '陕西', lat: 34.3416, lon: 108.9398 },
  'CN-GS': { name: '甘肃', lat: 36.0611, lon: 103.8343 },
  'CN-QH': { name: '青海', lat: 36.6171, lon: 101.7782 },
  'CN-NX': { name: '宁夏', lat: 38.4872, lon: 106.2309 },
  'CN-XJ': { name: '新疆', lat: 43.8256, lon: 87.6168 }
};

const DEFAULT_GEO_COORDS: GeoCoords = { name: '未知区域', lat: 35, lon: 105 };

function normalizeGeoCode(value?: string | null): string | null {
  if (!value) return null;
  const normalized = value.trim().toUpperCase();
  return normalized && normalized !== 'UNKNOWN' ? normalized : null;
}

function splitGeoKey(key: string): { countryCode: string | null; regionCode: string | null } {
  const trimmed = String(key || '').trim();
  if (!trimmed || trimmed.toLowerCase() === 'unknown') {
    return { countryCode: null, regionCode: null };
  }

  const [countryPart, ...rest] = trimmed.split('-');
  return {
    countryCode: normalizeGeoCode(countryPart),
    regionCode: normalizeGeoCode(rest.join('-') || null)
  };
}

function hashString(value: string): number {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) {
    hash = ((hash * 31) + value.charCodeAt(i)) >>> 0;
  }
  return hash;
}

function wrapLongitude(value: number): number {
  if (value > 180) return value - 360;
  if (value < -180) return value + 360;
  return value;
}

function clampLatitude(value: number): number {
  return Math.max(-75, Math.min(75, value));
}

function resolveGeoCoords(key: string): GeoCoords {
  const { countryCode, regionCode } = splitGeoKey(key);
  const regionKey = countryCode && regionCode ? `${countryCode}-${regionCode}` : null;

  if (regionKey && REGION_COORDS[regionKey]) {
    return REGION_COORDS[regionKey];
  }

  const countryCoords = countryCode ? COUNTRY_COORDS[countryCode] : null;
  if (!countryCoords) {
    return { ...DEFAULT_GEO_COORDS, name: key || DEFAULT_GEO_COORDS.name };
  }

  if (!regionCode) {
    return countryCoords;
  }

  const seed = hashString(regionKey || key);
  const angle = ((seed % 360) * Math.PI) / 180;
  const radius = 1.8 + ((seed >>> 8) % 160) / 100;
  return {
    name: `${countryCoords.name} / ${regionCode}`,
    lat: clampLatitude(countryCoords.lat + Math.sin(angle) * radius * 0.7),
    lon: wrapLongitude(countryCoords.lon + Math.cos(angle) * radius)
  };
}

interface PublicDashboardProps {
  apiPrefix: string;
}


// ---- 3D Digital Earth Globe Component ----
interface GlobeProps {
  geoBreakdown: Record<string, number>;
  totalInstances: number;
  apiPrefix: string;
}

function InteractiveGlobe({ geoBreakdown, totalInstances, apiPrefix }: GlobeProps) {
  const globeRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 600, height: 600 });
  const [countries, setCountries] = useState({ features: [] });

  const globeMaterial = useMemo(() => {
    const mat = new THREE.MeshPhongMaterial();
    mat.color = new THREE.Color('#0a0b12');
    mat.emissive = new THREE.Color('#0a0b12');
    mat.emissiveIntensity = 0.5;
    mat.shininess = 0.8;
    return mat;
  }, []);

  useEffect(() => {
    fetch(`${apiPrefix}/countries.geojson`)
      .then(res => res.json())
      .then(setCountries)
      .catch((err) => console.error("GeoJSON fetch error:", err));
  }, [apiPrefix]);

  useEffect(() => {
    if (globeRef.current) {
      // @ts-ignore
      const controls = globeRef.current.controls();
      if (controls) {
        controls.autoRotate = true;
        controls.autoRotateSpeed = 1.2;
        controls.enableZoom = false;
      }
      // @ts-ignore
      globeRef.current.pointOfView({ altitude: 2.2 });
    }
  }, []);

  useEffect(() => {
    const handleResize = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.offsetWidth,
          height: containerRef.current.offsetHeight
        });
      }
    };
    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const { points, arcs } = useMemo(() => {
    const pts = Object.entries(geoBreakdown)
      .filter(([key, count]) => key !== 'unknown' && Number(count) > 0)
      .map(([key, count]) => {
        const coords = resolveGeoCoords(key);
        return {
          id: key,
          name: coords.name,
          lat: coords.lat,
          lng: coords.lon,
          count
        };
      });

    let hub = pts[0];
    pts.forEach(p => {
      if (!hub || p.count > hub.count) hub = p;
    });

    const a = pts.filter(p => p.id !== hub?.id).map(p => ({
      startLat: hub.lat,
      startLng: hub.lng,
      endLat: p.lat,
      endLng: p.lng,
      color: ['rgba(95, 90, 246, 0.1)', 'rgba(236, 72, 153, 0.8)']
    }));

    return { points: pts, arcs: a };
  }, [geoBreakdown]);

  const getTooltipHtml = (d: any) => `
    <div style="
      background: rgba(18, 19, 30, 0.85);
      border: 1px solid rgba(76, 175, 147, 0.4);
      border-radius: 6px;
      padding: 8px 12px;
      font-family: 'Outfit', sans-serif;
      font-size: 12px;
      color: #fff;
      backdrop-filter: blur(4px);
      box-shadow: 0 4px 12px rgba(0,0,0,0.4);
    ">
      <div style="font-weight: 600; margin-bottom: 4px; color: #4caf93;">${d.name}</div>
      <div style="color: #9ca3af;">活跃实例: <span style="color: #fff; font-weight: 600;">${d.count}</span> 台</div>
      <div style="color: #9ca3af;">占比: <span style="color: #fff;">${totalInstances > 0 ? ((d.count / totalInstances) * 100).toFixed(1) : 0}%</span></div>
    </div>
  `;

  const [isHovered, setIsHovered] = useState(false);

  return (
    <div 
      className="earth-canvas-container" 
      ref={containerRef} 
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <div style={{
        position: 'absolute',
        top: '50%',
        left: '50%',
        width: '350%',
        height: '350%',
        transform: 'translate(-50%, -50%)',
        zIndex: 0,
        pointerEvents: 'none'
      }}>
        <MagicRings
          color="#6366f1"
          colorTwo="#ec4899"
          ringCount={5}
          speed={0.6}
          attenuation={15}
          lineThickness={2.5}
          opacity={0.35}
          followMouse={true}
          mouseInfluence={0.05}
          baseRadius={0.12}
          radiusStep={0.035}
          scaleRate={0.03}
        />
      </div>
      <div style={{
        width: '100%',
        height: '100%',
        position: 'relative',
        zIndex: 1,
        transition: 'transform 0.5s cubic-bezier(0.175, 0.885, 0.32, 1.275)',
        transform: isHovered ? 'scale(1.08)' : 'scale(1)'
      }}>
        <ReactGlobe
        ref={globeRef}
        width={dimensions.width}
        height={dimensions.height}
        backgroundColor="rgba(0,0,0,0)"
        globeImageUrl={null}
        globeMaterial={globeMaterial}
        showAtmosphere={true}
        atmosphereColor="#4f46e5"
        atmosphereAltitude={0.15}
        
        polygonsData={countries.features}
        polygonCapColor={() => 'rgba(255, 255, 255, 0)'}
        polygonSideColor={() => 'rgba(255, 255, 255, 0)'}
        polygonStrokeColor={() => '#6366f1'}
        polygonAltitude={0.005}
        
        arcsData={arcs}
        arcColor="color"
        arcDashLength={0.4}
        arcDashGap={0.2}
        arcDashAnimateTime={2000}
        
        pointsData={points}
        pointLat="lat"
        pointLng="lng"
        pointColor={() => '#4caf93'}
        pointAltitude={0.01}
        pointRadius={(d: any) => Math.max(0.5, Math.min(2, (d.count / totalInstances) * 5))}
        pointsMerge={true}
        
        ringsData={points}
        ringLat="lat"
        ringLng="lng"
        ringColor={() => '#4caf93'}
        ringMaxRadius={(d: any) => Math.max(3, Math.min(8, (d.count / totalInstances) * 15))}
        ringPropagationSpeed={2}
        ringRepeatPeriod={1500}
        
        pointLabel={getTooltipHtml}
        />
      </div>
    </div>
  );
}

// ---- Main Public Dashboard Page ----
export default function PublicDashboard({ apiPrefix }: PublicDashboardProps) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshCountdown, setRefreshCountdown] = useState(15);
  
  const chartTimelineRef = useRef<HTMLCanvasElement | null>(null);
  const chartPerformanceRef = useRef<HTMLCanvasElement | null>(null);
  const chartTrendRef = useRef<HTMLCanvasElement | null>(null);
  const chartVersionsRef = useRef<HTMLCanvasElement | null>(null);
  const chartPlatformRef = useRef<HTMLCanvasElement | null>(null);
  const chartSeverityRef = useRef<HTMLCanvasElement | null>(null);
  const chartCountryRef = useRef<HTMLCanvasElement | null>(null);

  const activeCharts = useRef<Record<string, Chart>>({});

  const loadData = async (isSilent = false) => {
    if (!isSilent) setLoading(true);
    try {
      const overview = await fetchJson(`${apiPrefix}/api/public/overview`);
      setData(overview);
      setError(null);
    } catch (err: any) {
      console.error(err);
      setError(err.message || '加载遥测数据失败');
    } finally {
      if (!isSilent) setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(() => {
      setRefreshCountdown((prev) => {
        if (prev <= 1) {
          loadData(true);
          return 15;
        }
        return prev - 1;
      });
    }, 1000);

    return () => {
      clearInterval(interval);
      Object.values(activeCharts.current).forEach((c) => c.destroy());
    };
  }, []);

  // Intersection Observer for scroll animation
  useEffect(() => {
    if (loading || error || !data) return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible');
          }
        });
      },
      { threshold: 0.1 }
    );

    const sections = document.querySelectorAll('.dashboard-section');
    sections.forEach((section) => observer.observe(section));

    return () => {
      sections.forEach((section) => observer.unobserve(section));
    };
  }, [loading, error, data]);

  useEffect(() => {
    if (!data) return;

    // Destroy existing charts
    Object.values(activeCharts.current).forEach((c) => c.destroy());
    activeCharts.current = {};

    const chartDefaults = {
      color: '#9ca3af',
      borderColor: 'rgba(255, 255, 255, 0.05)',
      font: { family: 'Outfit, sans-serif' }
    };
    
    // 1. Timeline Chart
    if (chartTimelineRef.current) {
      const rows = data.heartbeat_timeline_24h || [];
      const labels = rows.map((r: any) => fmtHour(r.bucket_at));
      const windows = rows.map((r: any) => r.windows || 0);
      const errors = rows.map((r: any) => r.error_events || 0);

      activeCharts.current.timeline = new Chart(chartTimelineRef.current, {
        type: 'bar',
        data: {
          labels,
          datasets: [
            {
              type: 'bar',
              label: '心跳窗口',
              data: windows,
              backgroundColor: 'rgba(91,155,213,0.35)',
              borderColor: 'rgba(91,155,213,0.6)',
              borderWidth: 1,
              borderRadius: 3,
              yAxisID: 'y',
              order: 2,
            },
            {
              type: 'line',
              label: '错误事件',
              data: errors,
              borderColor: '#e0556a',
              backgroundColor: 'rgba(224,85,106,0.1)',
              borderWidth: 2,
              pointRadius: 2,
              pointHoverRadius: 5,
              tension: 0.3,
              fill: true,
              yAxisID: 'y1',
              order: 1,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          plugins: {
            legend: { position: 'top', align: 'end', labels: { boxWidth: 12 } },
          },
          scales: {
            x: { grid: { display: false } },
            y: {
              type: 'linear', position: 'left',
              grid: { color: chartDefaults.borderColor },
            },
            y1: {
              type: 'linear', position: 'right',
              grid: { display: false },
              beginAtZero: true
            }
          }
        }
      });
    }

    // 2. Performance Chart
    if (chartPerformanceRef.current) {
      const rows = data.heartbeat_timeline_24h || [];
      const labels = rows.map((r: any) => fmtHour(r.bucket_at));
      const payloadMb = rows.map((r: any) => ((r.payload_bytes || 0) / 1e6));
      const instances = rows.map((r: any) => r.instance_count || 0);

      activeCharts.current.performance = new Chart(chartPerformanceRef.current, {
        type: 'line',
        data: {
          labels,
          datasets: [
            {
              label: '数据流量 (MB)',
              data: payloadMb,
              borderColor: '#5b9bd5',
              backgroundColor: 'transparent',
              borderWidth: 2,
              pointRadius: 0,
              pointHoverRadius: 4,
              tension: 0.3,
              yAxisID: 'y',
            },
            {
              label: '活跃实例数',
              data: instances,
              borderColor: '#4caf93',
              backgroundColor: 'transparent',
              borderWidth: 2,
              pointRadius: 0,
              pointHoverRadius: 4,
              tension: 0.3,
              yAxisID: 'y1',
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          plugins: {
            legend: { position: 'top', align: 'end', labels: { boxWidth: 12 } },
          },
          scales: {
            x: { grid: { display: false } },
            y: {
              type: 'linear', position: 'left',
              grid: { color: chartDefaults.borderColor },
            },
            y1: {
              type: 'linear', position: 'right',
              grid: { display: false },
              beginAtZero: true
            }
          }
        }
      });
    }

    // 3. Version Trend Chart
    if (chartTrendRef.current) {
      const rows = data.version_adoption_trend || [];
      const labels = rows.map((r: any) => fmtDate(r.bucket_at));
      const versionTotals: Record<string, number> = {};
      for (const r of rows) {
        for (const [ver, cnt] of Object.entries(r.versions || {})) {
          versionTotals[ver] = (versionTotals[ver] || 0) + (cnt as number);
        }
      }
      const topVersions = Object.entries(versionTotals)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 6)
        .map(([ver]) => ver);

      const datasets = topVersions.map((ver, i) => ({
        label: ver,
        data: rows.map((r: any) => r.versions?.[ver] || 0),
        borderColor: CHART_COLORS[i % CHART_COLORS.length],
        backgroundColor: 'transparent',
        borderWidth: 2,
        pointRadius: 3,
        tension: 0.3,
      }));

      if (datasets.length > 0) {
        activeCharts.current.trend = new Chart(chartTrendRef.current, {
          type: 'line',
          data: { labels, datasets },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
              legend: { position: 'top', align: 'end', labels: { boxWidth: 12 } },
            },
            scales: {
              x: { grid: { display: false } },
              y: { grid: { color: chartDefaults.borderColor }, beginAtZero: true }
            }
          }
        });
      }
    }

    // Doughnuts builders helper
    const makeDoughnut = (canvas: HTMLCanvasElement, labels: string[], values: number[], key: string) => {
      const total = values.reduce((a, b) => a + b, 0);
      activeCharts.current[key] = new Chart(canvas, {
        type: 'doughnut',
        data: {
          labels,
          datasets: [{
            data: values,
            backgroundColor: CHART_COLORS.slice(0, labels.length),
            borderColor: '#12131e',
            borderWidth: 2,
            hoverOffset: 4
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

    if (chartVersionsRef.current) {
      const sorted = (data.version_distribution || []).slice().sort((a: any, b: any) => b.count - a.count).slice(0, 8);
      if (sorted.length > 0) {
        makeDoughnut(chartVersionsRef.current, sorted.map((v: any) => v.version), sorted.map((v: any) => v.count), 'versions');
      }
    }

    if (chartPlatformRef.current) {
      const platforms = Object.entries(data.overview?.platform_breakdown || {}).sort((a: any, b: any) => b[1] - a[1]);
      if (platforms.length > 0) {
        makeDoughnut(chartPlatformRef.current, platforms.map((e) => e[0]), platforms.map((e) => e[1] as number), 'platform');
      }
    }

    if (chartSeverityRef.current) {
      const breakdown = Object.entries(data.diagnostic_breakdown_24h || {}).filter(([k, v]) => k !== 'info' || (v as number) > 0).sort((a: any, b: any) => b[1] - a[1]);
      if (breakdown.length > 0) {
        makeDoughnut(chartSeverityRef.current, breakdown.map((e) => e[0]), breakdown.map((e) => e[1] as number), 'severity');
      }
    }

    if (chartCountryRef.current) {
      const countries = Object.entries(data.overview?.country_breakdown || {}).sort((a: any, b: any) => b[1] - a[1]);
      if (countries.length > 0) {
        makeDoughnut(chartCountryRef.current, countries.map((e) => e[0]), countries.map((e) => e[1] as number), 'country');
      }
    }

  }, [data]);

  const scrollToSection = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });
  };

  const renderGlowPanel = (
    children: React.ReactNode,
    options: {
      as?: 'div' | 'section';
      className?: string;
      style?: React.CSSProperties;
      glowColor?: string;
      colors?: string[];
      backgroundColor?: string;
    } = {},
  ) => {
    const Tag = options.as ?? 'div';

    return (
      <BorderGlow
        className={`telemetry-glow-card telemetry-glow-card--panel${options.className ? ` ${options.className}` : ''}`}
        style={options.style}
        edgeSensitivity={26}
        glowColor={options.glowColor ?? '244 95 72'}
        backgroundColor={options.backgroundColor ?? 'rgba(10, 11, 18, 0.82)'}
        borderRadius={16}
        glowRadius={24}
        glowIntensity={0.9}
        coneSpread={14}
        fillOpacity={0.025}
        colors={options.colors ?? PANEL_GLOW_COLORS}
      >
        <Tag className="panel glow-surface">
          {children}
        </Tag>
      </BorderGlow>
    );
  };

  if (loading) {
    return (
      <div className="loading-screen">
        <div className="spinner"></div>
        <p style={{ color: 'var(--text-secondary)' }}>正在载入社区遥测总览...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="telemetry-app">
        <header className="topbar">
          <div className="brand">
            <img src={`${apiPrefix}/logo.png`} className="brand-logo" alt="Logo" />
            <div>
              <h1>Neo-MoFox Telemetry</h1>
              <p>社区遥测 · 运行脉搏</p>
            </div>
          </div>
          <div className="nav-actions">
            <a href="/_cloud_telemetry/admin">管理面板</a>
          </div>
        </header>
        {renderGlowPanel(
          <div className="panel-body" style={{ textAlign: 'center', padding: '48px' }}>
            <AlertOctagon size={48} className="text-danger" style={{ color: 'red', margin: '0 auto 16px' }} />
            <h2 style={{ marginBottom: '8px' }}>服务暂时不可用</h2>
            <p style={{ color: 'var(--text-secondary)' }}>{error}</p>
            <button className="btn primary" onClick={() => loadData()} style={{ marginTop: '20px' }}>重新尝试</button>
          </div>,
          {
            glowColor: '350 85 62',
            colors: DANGER_GLOW_COLORS,
            backgroundColor: 'rgba(30, 11, 18, 0.82)',
          },
        )}
      </div>
    );
  }

  const ov = data?.overview || {};
  const perf = data?.performance_24h || {};
  const timeline = data?.heartbeat_timeline_24h || [];

  // Heatmap helper
  const heatmapData = timeline;
  const heatmapCells = () => {
    if (!heatmapData.length) return <div className="empty-state">暂无心跳数据</div>;
    const maxVal = Math.max(0.01, ...heatmapData.map((r: any) => Number(r.avg_errors_per_heartbeat || 0)));
    return (
      <div className="heatmap-grid">
        {heatmapData.map((r: any, idx: number) => {
          const v = Number(r.avg_errors_per_heartbeat || 0);
          const ratio = Math.min(1, maxVal > 0 ? v / maxVal : 0);
          const h = 140 - ratio * 140;
          const s = 65;
          const l = 20 + ratio * 30;
          const color = ratio === 0 ? 'rgba(255, 255, 255, 0.02)' : `hsl(${h}, ${s}%, ${l}%)`;
          const borderStyle = ratio > 0.5 ? '1px solid rgba(239, 68, 68, 0.4)' : '1px solid rgba(255,255,255,0.02)';
          return (
            <span
              key={idx}
              className="heatmap-cell"
              style={{ background: color, border: borderStyle }}
              title={`${fmtHour(r.bucket_at)} · 平均单次心跳错误 ${v.toFixed(3)} · 累计错误 ${fmtNum(r.error_events)}`}
            />
          );
        })}
      </div>
    );
  };


  // Doughnut panel helper
  const renderDoughnutPanel = (title: string, canvasRef: React.RefObject<HTMLCanvasElement | null>, items: Array<{label: string, count: number}>) => {
    const total = items.reduce((a, b) => a + b.count, 0);
    const sortedItems = [...items].sort((a, b) => b.count - a.count);
    return renderGlowPanel(
      <>
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
            {sortedItems.slice(0, 4).map((item, idx) => (
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
      </>,
      {
        colors: ['#818cf8', '#34d399', '#38bdf8'],
      },
    );
  };

  return (
    <div className="telemetry-app">
      {/* Top Navbar */}
      <header className="topbar">
        <div className="brand">
          <img src={`${apiPrefix}/logo.png`} className="brand-logo" alt="Logo" />
          <div>
            <h1>Neo-MoFox Telemetry</h1>
            <p>社区遥测 · 运行脉搏</p>
          </div>
        </div>
        <div className="nav-actions">
          <div className="refresh-badge">
            <span className="dot"></span>
            <span>{refreshCountdown}s 自动刷新</span>
          </div>
          <button className="nav-btn" onClick={() => loadData(true)} title="手动刷新">
            <RefreshCw size={14} />
          </button>
          <a href="/_cloud_telemetry/admin" className="active">管理后台</a>
        </div>
      </header>

      {/* SECTION 1: HERO LANDING SCREEN (开屏首页) */}
      <section className="hero-section" id="section-hero">
        <div className="hero-left">
          <h1 className="hero-title-gradient" style={{ background: 'none', WebkitTextFillColor: 'initial' }}>
            <ShinyText text="社区遥测全局控制台" speed={3} color="#a5b4fc" shineColor="#ffffff" />
          </h1>
          <p className="hero-subtitle">
            实时汇总来自全球 Neo-MoFox 用户的遥测分析指标。我们致力于以最高的技术透明度和对数据私密性的尊重，追踪平台服务的运行心跳与大语言模型的调用健康态势。
          </p>
          
          <div className="hero-stats-grid">
            <BorderGlow
              className="telemetry-glow-card telemetry-glow-card--hero"
              edgeSensitivity={24}
              glowColor="156 85 55"
              backgroundColor="rgba(11, 16, 20, 0.72)"
              borderRadius={24}
              glowRadius={26}
              glowIntensity={0.95}
              coneSpread={14}
              fillOpacity={0.025}
              colors={HERO_GLOW_COLORS}
            >
              <div className="hero-stat-card active-nodes glow-surface">
                <div className="stat-label">
                  <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span className="dot"></span>
                    当前在线活动节点
                  </span>
                </div>
                <div className="stat-value">{fmtNum(ov.online_instances)}</div>
                <div className="stat-sub">持续心跳接收中</div>
              </div>
            </BorderGlow>
            
            <BorderGlow
              className="telemetry-glow-card telemetry-glow-card--hero"
              edgeSensitivity={24}
              glowColor="244 95 72"
              backgroundColor="rgba(13, 12, 22, 0.72)"
              borderRadius={24}
              glowRadius={26}
              glowIntensity={0.95}
              coneSpread={14}
              fillOpacity={0.025}
              colors={['#a78bfa', '#f472b6', '#60a5fa']}
            >
              <div className="hero-stat-card glow-surface">
                <div className="stat-label">累计注册节点数</div>
                <div className="stat-value">{fmtNum(ov.total_instances)}</div>
                <div className="stat-sub">所有注册的实例数量</div>
              </div>
            </BorderGlow>
          </div>
        </div>

        <div className="hero-right">
          <InteractiveGlobe
            geoBreakdown={ov.region_breakdown || ov.country_breakdown || {}}
            totalInstances={ov.total_instances || 1}
            apiPrefix={apiPrefix}
          />
        </div>

        <div className="scroll-indicator-box" onClick={() => scrollToSection('section-traffic')}>
          <span>向下滚动查看详细数据</span>
          <div className="scroll-arrow"></div>
        </div>
      </section>

      {/* SECTION 2: HEALTH & TRAFFIC (运行与流量态势) */}
      <section className="dashboard-section" id="section-traffic">
        <div className="section-title-box">
          <h2>
            <Activity size={20} style={{ color: 'hsl(var(--success-hsl))' }} />
            <span>运行与遥测上报流量态势</span>
          </h2>
          <p>分析节点的心跳质量、错误记录，以及 Watchdog 服务连接情况</p>
        </div>

        <div className="kpi-row">
          <BorderGlow
            className="telemetry-glow-card telemetry-glow-card--metric"
            edgeSensitivity={24}
            glowColor="244 95 72"
            backgroundColor="rgba(12, 13, 20, 0.72)"
            borderRadius={16}
            glowRadius={22}
            glowIntensity={0.88}
            coneSpread={12}
            fillOpacity={0.02}
            colors={KPI_GLOW_COLORS}
          >
            <div className="kpi-card glow-surface">
              <div className="kpi-label">
                <span>24h 心跳窗口</span>
                <BarChart2 size={14} style={{ color: 'hsl(var(--primary-hsl))' }} />
              </div>
              <div className="kpi-value">{fmtNum(perf.window_count)}</div>
              <div className="kpi-sub">聚合自 {fmtNum(timeline.length)} 个时段</div>
            </div>
          </BorderGlow>

          <BorderGlow
            className="telemetry-glow-card telemetry-glow-card--metric"
            edgeSensitivity={24}
            glowColor="317 95 68"
            backgroundColor="rgba(16, 11, 20, 0.72)"
            borderRadius={16}
            glowRadius={22}
            glowIntensity={0.88}
            coneSpread={12}
            fillOpacity={0.02}
            colors={['#f472b6', '#fb7185', '#a78bfa']}
          >
            <div className="kpi-card glow-surface">
              <div className="kpi-label">
                <span>24h Token 吞吐</span>
                <Cpu size={14} style={{ color: 'hsl(var(--accent-hsl))' }} />
              </div>
              <div className="kpi-value">{fmtNum(perf.total_tokens)}</div>
              <div className="kpi-sub">发生 {fmtNum(perf.request_count)} 次模型调用</div>
            </div>
          </BorderGlow>

          <BorderGlow
            className="telemetry-glow-card telemetry-glow-card--metric"
            edgeSensitivity={24}
            glowColor="156 85 55"
            backgroundColor="rgba(10, 16, 16, 0.72)"
            borderRadius={16}
            glowRadius={22}
            glowIntensity={0.88}
            coneSpread={12}
            fillOpacity={0.02}
            colors={['#34d399', '#60a5fa', '#a78bfa']}
          >
            <div className="kpi-card glow-surface">
              <div className="kpi-label">
                <span>模型响应成功率</span>
                <CheckCircle2 size={14} style={{ color: 'hsl(var(--success-hsl))' }} />
              </div>
              <div className="kpi-value">{fmtPct(perf.success_rate)}</div>
              <div className="kpi-sub">响应平均延时: {Number(perf.average_latency || 0).toFixed(2)}s</div>
            </div>
          </BorderGlow>

          <BorderGlow
            className="telemetry-glow-card telemetry-glow-card--metric"
            edgeSensitivity={24}
            glowColor="212 95 65"
            backgroundColor="rgba(10, 14, 22, 0.72)"
            borderRadius={16}
            glowRadius={22}
            glowIntensity={0.88}
            coneSpread={12}
            fillOpacity={0.02}
            colors={['#38bdf8', '#818cf8', '#34d399']}
          >
            <div className="kpi-card glow-surface">
              <div className="kpi-label">
                <span>综合缓存命中率</span>
                <Database size={14} style={{ color: 'hsl(var(--info-hsl))' }} />
              </div>
              <div className="kpi-value">{fmtPct(perf.cache_hit_rate)}</div>
              <div className="kpi-sub">所有请求的综合缓存命中率</div>
            </div>
          </BorderGlow>
        </div>

        <div className="panel-grid-2">
          {renderGlowPanel(
            <>
            <div className="panel-header">
              <div className="panel-header-title">
                <h3>24h 遥测心跳时间线</h3>
                <p>最近 24 小时每个时段的心跳包数量与错误计数趋势</p>
              </div>
            </div>
            <div className="panel-body">
              <div className="chart-container h-lg">
                <canvas ref={chartTimelineRef}></canvas>
              </div>
            </div>
            </>,
          )}

          {renderGlowPanel(
            <>
            <div className="panel-header">
              <div className="panel-header-title">
                <h3>遥测看门狗健康状态</h3>
                <p>看门狗轮询成功与聊天流超时统计</p>
              </div>
            </div>
            <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
              <div className="watchdog-strip">
                <div className="watchdog-card">
                  <span className="watchdog-val">{perf.watchdog_samples ? `${Number(perf.watchdog_running_samples || 0)}/${perf.watchdog_samples}` : '-'}</span>
                  <span className="watchdog-lbl">看门狗监测成功率</span>
                </div>
                <div className="watchdog-card">
                  <span className="watchdog-val">{perf.watchdog_samples ? `${Number(perf.watchdog_thread_alive_samples || 0)}/${perf.watchdog_samples}` : '-'}</span>
                  <span className="watchdog-lbl">心跳监听线程存活</span>
                </div>
                <div className="watchdog-card">
                  <span className="watchdog-val">{fmtNum(perf.watchdog_registered_streams_max)}</span>
                  <span className="watchdog-lbl">最大并发活跃流计数</span>
                </div>
                <div className="watchdog-card">
                  <span className="watchdog-val" style={{ color: Number(perf.stream_failures_max || 0) > 0 ? 'hsl(var(--warning-hsl))' : 'inherit' }}>
                    {fmtNum(perf.stream_failures_max)}
                  </span>
                  <span className="watchdog-lbl">活跃流最高失败计数</span>
                </div>
              </div>
            </div>
            </>,
            {
              colors: ['#34d399', '#60a5fa', '#818cf8'],
            },
          )}
        </div>
      </section>

      {/* SECTION 3: DISTRIBUTIONS & TRENDS (分布与版本趋势) */}
      <section className="dashboard-section" id="section-trends">
        <div className="section-title-box">
          <h2>
            <Globe size={20} style={{ color: 'hsl(var(--info-hsl))' }} />
            <span>节点分布与应用版本演进</span>
          </h2>
          <p>可视化操作系统、应用版本及 14 天内新注册版本变化的演进</p>
        </div>

        <section className="panel-grid-2" style={{ marginBottom: '20px' }}>
          {renderGlowPanel(
            <>
            <div className="panel-header">
              <div className="panel-header-title">
                <h3>心跳错误热度网格</h3>
                <p>每时段平均产生的错误包（亮色块代表对应时间段有异常报错）</p>
              </div>
            </div>
            <div className="panel-body">
              <div className="heatmap-container">
                {heatmapCells()}
                <div className="heatmap-legend">
                  <span>0.00 / hb (正常无警报)</span>
                  <span className="heatmap-bar"></span>
                  <span>最高报错时段</span>
                </div>
              </div>
            </div>
            </>,
            {
              colors: ['#818cf8', '#f59e0b', '#f472b6'],
            },
          )}

          {renderGlowPanel(
            <>
            <div className="panel-header">
              <div className="panel-header-title">
                <h3>24h 数据流量与活跃变化</h3>
                <p>数据包吞吐 (MB) 与同时段在线的活跃实例数</p>
              </div>
            </div>
            <div className="panel-body">
              <div className="chart-container h-md">
                <canvas ref={chartPerformanceRef}></canvas>
              </div>
            </div>
            </>,
            {
              colors: ['#38bdf8', '#34d399', '#818cf8'],
            },
          )}
        </section>

        <section className="panel-grid-4">
          {renderDoughnutPanel(
            '应用版本分布',
            chartVersionsRef,
            (data.version_distribution || []).map((v: any) => ({ label: v.version, count: v.count }))
          )}
          {renderDoughnutPanel(
            '终端操作系统',
            chartPlatformRef,
            Object.entries(ov.platform_breakdown || {}).map(([label, count]) => ({ label, count: count as number }))
          )}
          {renderDoughnutPanel(
            '异常事件级别 (24h)',
            chartSeverityRef,
            Object.entries(data.diagnostic_breakdown_24h || {}).map(([label, count]) => ({ label, count: count as number }))
          )}
          {renderDoughnutPanel(
            '活跃地域国家',
            chartCountryRef,
            Object.entries(ov.country_breakdown || {}).map(([label, count]) => ({ label, count: count as number }))
          )}
        </section>

        {renderGlowPanel(
          <>
            <div className="panel-header">
              <div className="panel-header-title">
                <h3>新激活实例版本演化 (14天)</h3>
                <p>每日新激活节点采纳不同应用版本的趋势变化图</p>
              </div>
            </div>
            <div className="panel-body">
              <div className="chart-container h-md">
                <canvas ref={chartTrendRef}></canvas>
              </div>
            </div>
          </>,
          {
            style: { marginTop: '24px' },
            colors: ['#818cf8', '#f472b6', '#34d399'],
          },
        )}
      </section>

      {/* SECTION 4: APPLICATION METRICS (业务深度性能分析) */}
      <section className="dashboard-section" id="section-domains">
        <div className="section-title-box">
          <h2>
            <Server size={20} style={{ color: 'hsl(var(--accent-hsl))' }} />
            <span>节点诊断事件域与大模型深度审计</span>
          </h2>
          <p>统计不同事件域（db、runtime、llm等）以及单接口 Token 排行</p>
        </div>

        {renderGlowPanel(
          <>
            <div className="panel-header">
              <div className="panel-header-title">
                <h3>节点遥测事件发生域</h3>
                <p>本地检测到的诊断警告和报错分类</p>
              </div>
            </div>
            <div className="panel-body">
              <div className="domain-grid">
                {(perf.health_domains || []).map((d: any, idx: number) => {
                  const hasErrors = Number(d.error_events) > 0;
                  const hasWarnings = Number(d.warning_events) > 0;
                  let borderCol = 'var(--border)';
                  let icon = <CheckCircle2 size={16} style={{ color: 'hsl(var(--success-hsl))' }} />;
                  if (hasErrors) {
                    borderCol = 'rgba(239, 68, 68, 0.2)';
                    icon = <AlertOctagon size={16} style={{ color: 'hsl(var(--danger-hsl))' }} />;
                  } else if (hasWarnings) {
                    borderCol = 'rgba(245, 158, 11, 0.2)';
                    icon = <AlertTriangle size={16} style={{ color: 'hsl(var(--warning-hsl))' }} />;
                  }
                  
                  return (
                    <div className="domain-card" key={idx} style={{ borderColor: borderCol }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px' }}>
                        <span className="domain-name">{d.domain}</span>
                        {icon}
                      </div>
                      <span className="domain-time">最后上报: {fmtTime(d.last_event_at)}</span>
                      <div className="domain-stats">
                        <span className="chip info">{fmtNum(d.total_events)} 次事件</span>
                        {Number(d.warning_events) > 0 && <span className="chip warn">{d.warning_events} 警告</span>}
                        {Number(d.error_events) > 0 && <span className="chip bad">{d.error_events} 错误</span>}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </>,
          {
            as: 'section',
            style: { marginBottom: '24px' },
            colors: ['#34d399', '#818cf8', '#f59e0b'],
          },
        )}

        {renderGlowPanel(
          <>
            <div className="panel-header">
              <div className="panel-header-title">
                <h3>大语言模型 (LLM) 调用排行榜 (24h)</h3>
                <p>统计前 10 种最活跃的大模型请求（脱敏处理）</p>
              </div>
            </div>
            <div className="panel-body no-padding">
              <div className="table-wrapper">
                <table className="admin-table">
                  <thead>
                    <tr>
                      <th>调用请求名</th>
                      <th>请求计数</th>
                      <th>总消耗 Token</th>
                      <th>平均延时</th>
                      <th>缓存命中率</th>
                      <th>请求成功率</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(perf.top_requests || []).map((r: any, idx: number) => (
                      <tr key={idx}>
                        <td className="mono" style={{ fontWeight: 600, color: 'var(--text)' }}>{r.request_name}</td>
                        <td>{fmtNum(r.request_count)}</td>
                        <td>
                          <div className="cell-bar-container">
                            <span style={{ minWidth: '60px' }}>{fmtNum(r.total_tokens)}</span>
                            <div className="cell-bar">
                              <div
                                className="cell-bar-fill"
                                style={{
                                  width: `${Math.min(100, (r.total_tokens / (perf.total_tokens || 1)) * 100)}%`,
                                  background: 'linear-gradient(90deg, hsl(var(--primary-hsl)), hsl(var(--accent-hsl)))'
                                }}
                              />
                            </div>
                          </div>
                        </td>
                        <td>{Number(r.average_latency || 0).toFixed(2)}s</td>
                        <td>{fmtPct(r.cache_hit_rate)}</td>
                        <td>
                          <span className={`chip ${r.success_rate >= 0.95 ? 'good' : r.success_rate >= 0.85 ? 'warn' : 'bad'}`}>
                            {fmtPct(r.success_rate)}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>,
          {
            as: 'section',
            colors: ['#818cf8', '#f472b6', '#38bdf8'],
          },
        )}
      </section>
    </div>
  );
}
