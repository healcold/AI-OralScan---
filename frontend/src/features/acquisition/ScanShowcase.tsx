import { useEffect, useState } from 'react'
import { Activity, ArrowRight, Check, CircleDot, Cpu, ScanLine, Sparkles } from 'lucide-react'

const stages = ['影像校准', '区域扫描', '结果整理']
const findings = [
  { label: 'Crowding · 拥挤区域', score: '示例', tone: 'mint' },
  { label: 'Spacing · 间隙区域', score: '示例', tone: 'violet' },
  { label: 'Diastema · 牙间隙', score: '示例', tone: 'blue' },
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
      <div className="showcase-model"><span className="model-pulse"><Cpu size={15}/></span><div><strong>影像识别工作流</strong><small>实时影像 · 结构化标记</small></div><span className="model-ready">演示模式</span></div>
      <button className="showcase-start" onClick={() => { setRunning(false); window.setTimeout(() => setRunning(true), 20) }} disabled={running}>
        {running ? <><Activity size={16}/> 正在扫描</> : completed ? <><ScanLine size={16}/> 再看一次</> : <><ScanLine size={16}/> 开始扫描演示</>}<ArrowRight size={15}/>
      </button>
      <small className="showcase-footnote">演示界面 · 结果为模拟展示，不构成诊断或真实模型推理</small>
    </div>
    <div className="showcase-stage">
      <div className="stage-top"><span><CircleDot size={13}/> LIVE SCAN</span><span className="stage-mode">{running ? 'ANALYZING' : completed ? 'COMPLETE' : 'STANDBY'}</span></div>
      <div className="scan-art" aria-hidden="true">
        <div className="art-grid"/><div className="art-glow"/>
        <img className="scan-photo" src="/assets/scan-detection-example.png" alt="四视角口腔影像与示例检测框"/>
        {running && <div className="scan-line"/>}
        <div className="art-caption"><span>四视角口腔影像 · 检测框示例</span><span>2 × 2 VIEWS</span></div>
      </div>
      <div className="stage-progress"><div className="stage-track">{stages.map((item, i) => <div className={`stage-step ${stage >= i ? 'done' : ''}`} key={item}><span>{stage > i || completed ? <Check size={12}/> : `0${i+1}`}</span>{item}</div>)}</div><div className="stage-bar"><i style={{width: `${Math.max(0, stage) / 3 * 100}%`}}/></div></div>
      <div className="showcase-results"><div className="results-heading"><strong>检测结果示例</strong><span>{completed ? '示例已展开' : '等待扫描演示'}</span></div><div className="result-pills">{findings.map(f=><div key={f.label} className={`result-pill ${completed ? 'revealed' : ''}`}><i className={f.tone}/><span>{f.label}</span><b>{completed ? f.score : '—'}</b></div>)}</div><small>采用你提供的检测结果画面作展示参考；不代表当前网站模型推理或诊断。</small></div>
    </div>
  </section>
}
