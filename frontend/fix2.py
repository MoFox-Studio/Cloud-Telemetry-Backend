import re

with open('src/PublicDashboard.tsx', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Imports
code = code.replace(
    "import * as THREE from 'three';",
    "import * as THREE from 'three';\nimport ShinyText from './components/ShinyText';\nimport MagicRings from './components/MagicRings';"
)

# 2. InteractiveGlobe return block
orig_globe_ret = """  return (
    <div className="earth-canvas-container" ref={containerRef} style={{ width: '100%', height: '100%', position: 'relative', minHeight: '600px' }}>
      <ReactGlobe"""

new_globe_ret = """  const [isHovered, setIsHovered] = useState(false);

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
        <ReactGlobe"""
code = code.replace(orig_globe_ret, new_globe_ret)

orig_globe_end = """        pointLabel={getTooltipHtml}
      />
    </div>
  );"""

new_globe_end = """        pointLabel={getTooltipHtml}
        />
      </div>
    </div>
  );"""
code = code.replace(orig_globe_end, new_globe_end)

# 3. renderDoughnutPanel
orig_doughnut = """  const renderDoughnutPanel = (title: string, canvasRef: React.RefObject<HTMLCanvasElement | null>, items: Array<{label: string, count: number}>) => {
    const total = items.reduce((a, b) => a + b.count, 0);
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
            {items.slice(0, 4).map((item, idx) => ("""

new_doughnut = """  const renderDoughnutPanel = (title: string, canvasRef: React.RefObject<HTMLCanvasElement | null>, items: Array<{label: string, count: number}>) => {
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
            {sortedItems.slice(0, 4).map((item, idx) => ("""
code = code.replace(orig_doughnut, new_doughnut)

# 4. ShinyText
orig_h1 = """<h1 className="hero-title-gradient">社区遥测全局控制台</h1>"""
new_h1 = """<h1 className="hero-title-gradient" style={{ background: 'none', WebkitTextFillColor: 'initial' }}>
            <ShinyText text="社区遥测全局控制台" speed={3} color="#a5b4fc" shineColor="#ffffff" />
          </h1>"""
code = code.replace(orig_h1, new_h1)

with open('src/PublicDashboard.tsx', 'w', encoding='utf-8') as f:
    f.write(code)

print("Applied clean fixes.")
