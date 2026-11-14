import { useEffect, useState } from 'react'
import { Activity, ArrowRight, Check, CircleDot, Cpu, ScanLine, Sparkles } from 'lucide-react'

const stages = ['影像校准', '区域扫描', '结果整理']
const findings = [
  { label: '牙面区域 A', score: '0.94', tone: 'mint', position: 'one' },
  { label: '牙面区域 B', score: '0.87', tone: 'violet', position: 'two' },
  { label: '软组织区域', score: '0.82', tone: 'blue', position: 'three' },
]

export default function ScanShowcase() {
  const [running, setRunning] = useState(false)
  const [stage, setStage] = useState(-1)
  useEffect(() => {
    if (!running) return
    setStage(0)
    const timers = [
      window.setTimeout(() => setStage(1), 800),
      window.setTimeout(() => setStage(2), 1650),
      window.setTimeout(() => { setStage(3); setRunning(false) }, 2500),
    ]
    return () => timers.forEach(window.clearTimeout)
  }, [running])
  const completed = stage === 3
  return <section className={`scan-showcase ${running ? 'is-running' : ''}`} aria-label="智能扫描演示">
    <div className="showcase-copy">
      <div className="showcase-kicker"><Sparkles size={14}/> ORALSCAN VISION <span>交互演示</span></div>
      <h2>让每一次扫描<br/><em>清晰可见</em></h2>
      <p>从影像采集到区域标记，预览智能分析工作流与结果呈现方式。</p>
      <div className="showcase-model"><span className="model-pulse"><Cpu size={15}/></span><div><strong>YOLO 口腔影像模型</strong><small>best.onnx · 6 个模型标签</small></div><span className="model-ready">演示模式</span></div>
      <button className="showcase-start" onClick={() => { setRunning(false); window.setTimeout(() => setRunning(true), 20) }} disabled={running}>
        {running ? <><Activity size={16}/> 正在扫描</> : completed ? <><ScanLine size={16}/> 再看一次</> : <><ScanLine size={16}/> 开始扫描演示</>}<ArrowRight size={15}/>
      </button>
      <small className="showcase-footnote">演示界面 · 结果为模拟展示，不构成诊断或真实模型推理</small>
    </div>
    <div className="showcase-stage">
      <div className="stage-top"><span><CircleDot size={13}/> LIVE SCAN</span><span className="stage-mode">{running ? 'ANALYZING' : completed ? 'COMPLETE' : 'STANDBY'}</span></div>
      <div className="scan-art" aria-hidden="true">
        <div className="art-grid"/><div className="art-glow"/>
        <svg className="mouth-illustration" viewBox="0 0 520 300" fill="none">
          <path d="M76 110c34-50 100-69 184-67 83-2 151 17 184 67-22 17-46 27-74 27-34 0-57-14-110-14s-77 14-110 14c-28 0-52-10-74-27Z" fill="#f8e9e8" stroke="#f2c6cf" strokeWidth="2"/>
          <path d="M105 130c40 20 77 17 155 17s115 3 155-17c-8 48-37 100-69 119-20 12-42 14-86 14s-66-2-86-14c-32-19-61-71-69-119Z" fill="#b94d6b" fillOpacity=".86" stroke="#ec9caf" strokeWidth="2"/>
          <path d="M132 136c9 26 17 47 30 57 13 9 29 7 39-4 9-10 8-35 8-49-28 1-51 2-77-4Zm80 4c-1 20-3 41 7 53 10 13 29 13 40 0 10-12 8-33 7-53-20-2-36-2-54 0Zm60 0c-1 20-3 41 7 53 11 13 30 13 40 0 10-12 8-33 7-53-18-2-34-2-54 0Zm60 0c0 14-1 39 8 49 10 11 26 13 39 4 13-10 21-31 30-57-26 6-49 5-77 4Z" fill="#fff9f5" stroke="#eacdd0" strokeWidth="2"/>
          <path d="M88 113c38 23 76 30 172 30s134-7 172-30" stroke="#f5a9bc" strokeWidth="2" strokeDasharray="5 8"/>
        </svg>
        {findings.map(f => <div key={f.position} className={`scan-box ${f.position} ${completed ? 'box-visible' : ''}`}><i/><span>{f.label}</span></div>)}
        {running && <div className="scan-line"/>}
        <div className="art-caption"><span>影像区域识别</span><span>640 × 640</span></div>
      </div>
      <div className="stage-progress"><div className="stage-track">{stages.map((item, i) => <div className={`stage-step ${stage >= i ? 'done' : ''}`} key={item}><span>{stage > i || completed ? <Check size={12}/> : `0${i+1}`}</span>{item}</div>)}</div><div className="stage-bar"><i style={{width: `${Math.max(0, stage) / 3 * 100}%`}}/></div></div>
      <div className="showcase-results"><div className="results-heading"><strong>区域标记</strong><span>{completed ? '3 个演示标记' : '等待扫描'}</span></div><div className="result-pills">{findings.map(f=><div key={f.position} className={`result-pill ${completed ? 'revealed' : ''}`}><i className={f.tone}/><span>{f.label}</span><b>{completed ? f.score : '—'}</b></div>)}</div><small>显示分值仅用于界面演示，不代表患病概率。</small></div>
    </div>
  </section>
}
