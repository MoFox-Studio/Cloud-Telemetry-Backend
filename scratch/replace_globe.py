import sys

def process():
    file_path = r'c:\Projects\python\MoFox\cloud_telemetry_backend\frontend\src\PublicDashboard.tsx'
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Find the imports to update
    for i, line in enumerate(lines):
        if line.startswith("import React, { useEffect, useState, useRef } from 'react';"):
            lines[i] = "import React, { useEffect, useState, useRef, useMemo } from 'react';\n"
        if line.startswith("import { fetchJson"):
            lines.insert(i+1, "import ReactGlobe from 'react-globe.gl';\n")
            break

    # Find the start of the InteractiveGlobe implementation
    start_idx = -1
    for i, line in enumerate(lines):
        if line.startswith("const SPHERE_RADIUS = 210;"):
            start_idx = i
            break
            
    # Find the end of InteractiveGlobe
    end_idx = -1
    for i in range(start_idx, len(lines)):
        if line.startswith("// ---- Main Public Dashboard Page ----") or "// ---- Main Public Dashboard Page ----" in lines[i]:
            end_idx = i
            break

    new_globe = """
// ---- 3D Digital Earth Globe Component ----
interface GlobeProps {
  activeRegions: Record<string, number>;
  totalInstances: number;
}

function InteractiveGlobe({ activeRegions, totalInstances }: GlobeProps) {
  const globeRef = useRef<any>();
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 600, height: 600 });

  useEffect(() => {
    if (globeRef.current) {
      const controls = globeRef.current.controls();
      controls.autoRotate = true;
      controls.autoRotateSpeed = 1.2;
      controls.enableZoom = false;
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
    const pts = Object.entries(activeRegions).map(([code, count]) => {
      const coords = COUNTRY_COORDS[code] || { name: code, lat: 35, lon: 105 };
      return {
        id: code,
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
  }, [activeRegions]);

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

  return (
    <div className="earth-canvas-container" ref={containerRef} style={{ width: '100%', height: '100%', position: 'relative', minHeight: '600px' }}>
      <ReactGlobe
        ref={globeRef}
        width={dimensions.width}
        height={dimensions.height}
        backgroundColor="rgba(0,0,0,0)"
        globeImageUrl="//unpkg.com/three-globe/example/img/earth-dark.jpg"
        bumpImageUrl="//unpkg.com/three-globe/example/img/earth-topology.png"
        
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
        pointRadius={d => Math.max(0.5, Math.min(2, (d.count / totalInstances) * 5))}
        pointsMerge={true}
        
        ringsData={points}
        ringLat="lat"
        ringLng="lng"
        ringColor={() => '#4caf93'}
        ringMaxRadius={d => Math.max(3, Math.min(8, (d.count / totalInstances) * 15))}
        ringPropagationSpeed={2}
        ringRepeatPeriod={1500}
        
        pointLabel={getTooltipHtml}
      />
    </div>
  );
}

"""
    
    if start_idx != -1 and end_idx != -1:
        new_lines = lines[:start_idx] + [new_globe] + lines[end_idx:]
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        print(f"Successfully replaced InteractiveGlobe. Removed lines {start_idx} to {end_idx}.")
    else:
        print(f"Failed to find indices: start={start_idx}, end={end_idx}")

if __name__ == '__main__':
    process()
