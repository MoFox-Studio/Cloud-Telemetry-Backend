import re

with open('src/PublicDashboard.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# The file got completely corrupted around useMemo. Let's fix it manually with regex.
# We want to replace from "  const { points, arcs } = useMemo" up to "<ReactGlobe" with the correct code.

start_str = "  const { points, arcs } = useMemo(() => {"
end_str = "        <ReactGlobe"

start_idx = content.find(start_str)
end_idx = content.find(end_str, start_idx)

if start_idx != -1 and end_idx != -1:
    correct_code = """  const { points, arcs } = useMemo(() => {
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
        width: '250%',
        height: '250%',
        transform: 'translate(-50%, -50%)',
        zIndex: 0,
        pointerEvents: 'none'
      }}>
        <MagicRings
          color="#6366f1"
          colorTwo="#ec4899"
          ringCount={5}
          speed={0.6}
          attenuation={12}
          lineThickness={2}
          opacity={0.7}
          followMouse={true}
          mouseInfluence={0.05}
          baseRadius={0.17}
          radiusStep={0.05}
          scaleRate={0.05}
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
"""
    new_content = content[:start_idx] + correct_code + content[end_idx:]
    with open('src/PublicDashboard.tsx', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Fixed!")
else:
    print("Could not find blocks.")
