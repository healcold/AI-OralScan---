import { zh } from '../lib/zh'
import { useEffect, useState, type ReactNode } from 'react'
import { Link, NavLink, Route, Routes, useLocation, useSearchParams } from 'react-router-dom'
import { Activity, ArrowRight, Box, Camera, Check, CircleHelp, ClipboardList, Clock3, FileClock, FileImage, FileText, Grid2X2, Layers3, Menu, HeartHandshake, Monitor, MoreHorizontal, Plus, ScanLine, Settings2, ShieldCheck, Sparkles, Stethoscope, X } from 'lucide-react'
import { api, type Scan, type Asset } from '../lib/api'
import { Button } from '../components/ui/button'
import Acquisition from '../features/acquisition/Acquisition'
import ScanShowcase from '../features/acquisition/ScanShowcase'
import MeshImport from '../features/mesh/MeshImport'
import GeometryWorkspace from '../features/mesh/GeometryWorkspace'
import AnalysisWorkspace from '../features/analysis/AnalysisWorkspace'
import ModelsWorkspace from '../features/analysis/ModelsWorkspace'
import UnifiedWorkspace from '../features/analysis/UnifiedWorkspace'
import RecordsWorkspace from '../features/records/RecordsWorkspace'
import AssistantWorkspace from '../features/assistant/AssistantWorkspace'

const nav = [
  { label: '总览', path: '/', icon: Grid2X2 }, { label: '扫描工作台', path: '/scan', icon: ScanLine },
  { label: '分析', path: '/analysis', icon: Activity }, { label: 'AI 助理', path: '/assistant', icon: HeartHandshake }, { label: '报告', path: '/reports', icon: FileText },
  { label: '历史记录', path: '/history', icon: FileClock }, { label: '模型管理', path: '/models', icon: Layers3 },
  { label: '设备管理', path: '/devices', icon: Monitor }, { label: '设置', path: '/settings', icon: Settings2 },
]
const modes = [ { id: 'image', title: '上传图片', description: '上传口腔照片，整理检查资料。', formats: 'JPG, PNG, WEBP', icon: FileImage }, { id: 'camera', title: '摄像头采集', description: '通过摄像头拍摄并采集图像。', formats: '浏览器摄像头', icon: Camera }, { id: '3d', title: '导入三维模型', description: '导入口腔三维模型，查看几何结构。', formats: 'STL, OBJ, PLY', icon: Box } ] as const
type Mode = typeof modes[number]['id']
function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: string }) { return <span className={`badge badge-${tone}`}>{children}</span> }
function Panel({ children, className = '' }: { children: ReactNode; className?: string }) { return <section className={`panel ${className}`}>{children}</section> }
function PanelHead({ title, sub, right }: { title: string; sub?: string; right?: ReactNode }) { return <div className="panel-head"><div><h2>{title}</h2>{sub && <p>{sub}</p>}</div>{right}</div> }
function Empty({ icon: Icon = ClipboardList, title, text, action }: { icon?: typeof ClipboardList; title: string; text: string; action?: ReactNode }) { return <div className="empty"><div className="empty-icon"><Icon size={23}/></div><h3>{title}</h3><p>{text}</p>{action}</div> }
function PageTitle({ eyebrow, title, description, action }: { eyebrow: string; title: string; description: string; action?: ReactNode }) { return <div className="page-title"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>{action}</div> }
function useScans() {
  const [scans,setScans]=useState<Scan[]>([]); const [assets,setAssets]=useState<Asset[]>([]); const [state,setState]=useState<'loading'|'ready'|'error'>('loading'); const [message,setMessage]=useState('')
  async function reload() { setState('loading'); try { const data=await api.scans(); const all=await Promise.all(data.items.map(scan=>api.assets(scan.scan_id))); setScans(data.items); setAssets(all.flatMap(x=>x.items)); setState('ready') } catch(e) { setMessage(e instanceof Error?zh(e.message):'后端服务不可用'); setState('error') } }
  useEffect(()=>{ void reload() },[])
  return {scans,assets,state,message,reload}
}
function Dashboard() { const {scans,assets,state,message,reload}=useScans(); const [modelStatus,setModelStatus]=useState('检查中'); useEffect(()=>{let live=true;api.modelStatus().then(s=>{if(live)setModelStatus(s.status==='READY'?'已就绪':'尚未配置')}).catch(()=>{if(live)setModelStatus('不可用')});return()=>{live=false}},[]); const today=new Date().toDateString(); const stats=[{label:'检查总数',value:scans.length,icon:ScanLine,color:'blue'},{label:"今日检查",value:scans.filter(s=>new Date(s.created_at).toDateString()===today).length,icon:Clock3,color:'cyan'},{label:'二维图像',value:scans.filter(s=>assets.some(a=>a.scan_id===s.scan_id && a.modality==='image_2d')).length,icon:FileImage,color:'purple'},{label:'摄像头采集',value:scans.filter(s=>s.source_types.includes('camera')).length,icon:Camera,color:'teal'},{label:'三维模型',value:scans.filter(s=>assets.some(a=>a.scan_id===s.scan_id && a.modality==='mesh_3d')).length,icon:Box,color:'orange'}]; return <><PageTitle eyebrow="工作台" title="工作台总览" description="从一张图像开始，集中管理检查、分析与报告。" action={<Button asChild><Link to="/scan"><Plus size={17}/> 新建检查</Link></Button>}/>{state==='loading'?<Panel><Empty title="正在加载检查" text="正在读取检查记录。"/></Panel>:state==='error'?<Panel><Empty title="无法加载检查记录" text={message} action={<Button variant="outline" onClick={()=>void reload()}>重试</Button>}/></Panel>:<><div className="stats-grid">{stats.map(s=><Panel key={s.label} className="stat"><div className="stat-top"><div className={`icon-tile ${s.color}`}><s.icon size={19}/></div></div><p>{s.label}</p><div className="stat-value">{s.value}</div><span className="stat-change"><small>已保存记录</small></span></Panel>)}</div><div className="dashboard-grid"><Panel><PanelHead title="最近检查" sub="已保存的检查" right={<Link className="text-link" to="/history">查看历史记录 <ArrowRight size={14}/></Link>}/>{scans.length===0?<Empty title="暂无检查记录" text="新建一次检查，开始整理图像与三维模型。"/>:<div className="activity-list">{scans.slice(0,5).map(scan=><div className="activity-row" key={scan.scan_id}><div className="icon-tile blue"><ScanLine size={17}/></div><div><strong>{scan.scan_id}</strong><small>{new Date(scan.created_at).toLocaleString('zh-CN')} · {zh(scan.status)}</small></div></div>)}</div>}</Panel><Panel><PanelHead title="开始采集" sub="选择适合的数据来源"/><div className="quick-list">{modes.map(m=><Link to={`/scan?mode=${m.id}`} className="quick-item" key={m.id}><div className="icon-tile blue"><m.icon size={19}/></div><span><strong>{m.title}</strong><small>{m.formats}</small></span><ArrowRight size={16}/></Link>)}</div><div className="quick-note"><ShieldCheck size={16}/> 三种数据来源，同一检查管理</div></Panel></div></>}<div className="bottom-grid"><Panel><PanelHead title="系统状态" sub="模型与采集设备"/><div className="status-row"><div className="status-icon"><Layers3 size={18}/></div><div><strong>人工智能模型</strong><small>口腔模型</small></div><Badge tone="amber">{modelStatus}</Badge></div><div className="status-row"><div className="status-icon"><Monitor size={18}/></div><div><strong>设备</strong><small>连接状态</small></div><Badge>尚未检查</Badge></div></Panel></div></> }
function Workspace() {
 const location=useLocation(); const fromUrl=new URLSearchParams(location.search).get('mode'); const [mode,setMode]=useState<Mode>(modes.some(m=>m.id===fromUrl)?fromUrl as Mode:'image')
 useEffect(()=>{if(modes.some(m=>m.id===fromUrl))setMode(fromUrl as Mode)},[fromUrl]); const selected=modes.find(m=>m.id===mode)!
 return <><PageTitle eyebrow="数据采集" title="扫描工作台" description="选择图片、摄像头或三维模型，开始一次检查。"/><ScanShowcase/><div className="notice"><Sparkles size={18}/><div><strong>选择数据来源</strong><span>确认后保存图像，原始文件将完整保留。</span></div></div><div className="mode-grid" role="tablist" aria-label="扫描来源">{modes.map(m=><button role="tab" aria-selected={mode===m.id} className={`mode-card ${mode===m.id?'selected':''}`} key={m.id} onClick={()=>setMode(m.id)}><div className="mode-card-top"><div className="icon-tile blue"><m.icon size={21}/></div>{mode===m.id&&<span className="selected-check"><Check size={12}/></span>}</div><strong>{m.title}</strong><span>{m.description}</span><small>{m.formats}</small></button>)}</div><Panel className="workspace-panel"><PanelHead title={selected.title} sub={selected.description} />{mode==='3d'?<MeshImport/>:<Acquisition key={mode} source={mode==='image'?'upload':'camera'}/>}</Panel><div className="info-line"><ShieldCheck size={16}/> 本平台用于研究与辅助筛查，分析结果不构成临床诊断。</div></>
}
function Analysis() {
 const [params,setParams]=useSearchParams()
 const scanId=params.get('scan')??''
 const assetId=params.get('asset')??''
 const tab=params.get('tab')??'image'
 const tabs=[{id:'image',label:'图像分析',icon:FileImage},{id:'3d',label:'三维分析',icon:Box},{id:'unified',label:'统一分析',icon:Layers3}]
 return <><PageTitle eyebrow="结果查看" title="分析" description="查看每份图像与三维模型的分析结果和来源。"/>
   <div className="tabs" role="tablist" aria-label="Analysis view">{tabs.map(({id,label,icon:Icon})=>
     <button key={id} role="tab" aria-selected={tab===id} onClick={()=>setParams(scanId?{tab:id,scan:scanId}:{tab:id})}><Icon size={16}/>{label}</button>
   )}</div>
   {tab==='unified'?<UnifiedWorkspace key={scanId} initialScan={scanId}/>:tab==='3d'
     ?<GeometryWorkspace key={scanId+assetId} initialScan={scanId} initialAsset={assetId}/>
     :<AnalysisWorkspace key={scanId+assetId} initialScan={scanId} initialAsset={assetId}/>}
 </> 
}
function Records({kind}: {kind:'reports'|'history'}) {
 const reports=kind==='reports'
 return <><PageTitle eyebrow={reports?'检查报告':'检查档案'} title={reports?'报告':'历史记录'}
   description={reports?'生成检查报告，或下载已保存的 PDF 与 JSON 文件。':'按编号、日期和数据类型查找已保存的检查。'}/>
   <RecordsWorkspace key={kind} kind={kind}/>
 </>
}
function Models() { return <><PageTitle eyebrow="管理" title="模型管理" description="查看已注册模型的版本、输入配置与标签。"/><ModelsWorkspace/></> }
function Devices() { return <><PageTitle eyebrow="管理" title="设备管理" description="查看图像采集来源与设备状态。"/><div className="two-col"><Panel><PanelHead title="浏览器摄像头" sub="通过支持的浏览器使用" right={<Badge>尚未检查</Badge>}/><Empty icon={Camera} title="摄像头待连接" text="前往扫描工作台，授权摄像头并选择采集设备。"/></Panel><Panel><PanelHead title="口腔扫描仪" sub="专业扫描设备接入" right={<Badge>尚未配置</Badge>}/><Empty icon={Monitor} title="尚未接入口腔扫描仪" text="获得兼容设备及官方开发文档后，可接入专业扫描仪。"/></Panel></div></> }
function Settings() { const [compact,setCompact]=useState(false); return <><PageTitle eyebrow="偏好设置" title="设置" description="调整工作台的显示偏好。"/><Panel className="settings-panel"><PanelHead title="工作台偏好" sub="当前偏好在本次页面打开期间生效。"/><label className="setting-row"><span><strong>简短名称</strong><small>预览工作台名称的简短显示形式。</small></span><input type="checkbox" checked={compact} onChange={e=>setCompact(e.target.checked)}/></label><div className="setting-preview">预览：{compact?'OralScan':'口腔扫描工作台'}</div><div className="panel-footer"><ShieldCheck size={16}/> 本平台提供研究与辅助筛查参考，临床诊断应由专业口腔医生确定。</div></Panel></> }
function App() { const [menu,setMenu]=useState(false); const location=useLocation(); useEffect(()=>setMenu(false),[location.pathname]); const current=nav.find(n=>n.path===location.pathname)?.label ?? '工作台'; return <div className="app"><aside className={`sidebar ${menu?'sidebar-open':''}`}><div className="brand"><div className="brand-mark"><ScanLine size={22}/></div><div><strong>AI OralScan</strong><small>多模态口腔影像工作台</small></div><button className="close-menu" onClick={()=>setMenu(false)} aria-label="关闭导航"><X size={19}/></button></div><div className="side-label">工作空间</div><nav aria-label="主导航">{nav.map(n=><div key={n.path}>{n.path==='/models' && <div className="side-label manage-label">管理与设置</div>}<NavLink to={n.path} end={n.path==='/'} className={({isActive})=>`nav-link ${isActive?'active':''}`}><n.icon size={18}/><span>{n.label}</span></NavLink></div>)}</nav><div className="sidebar-bottom"><div className="help-card"><div className="help-icon"><CircleHelp size={19}/></div><strong>开始一次检查</strong><p>选择采集方式，整理口腔图像与模型。</p><Link to="/scan">进入扫描工作台 <ArrowRight size={14}/></Link></div><div className="profile"><div className="avatar">OS</div><div><strong>口腔影像工作台</strong><small>本地工作台</small></div><MoreHorizontal size={18}/></div></div></aside>{menu && <button className="backdrop" aria-label="关闭导航" onClick={()=>setMenu(false)}/>}<div className="main-wrap"><header className="topbar"><div className="top-left"><button className="menu-button" onClick={()=>setMenu(true)} aria-label="打开导航"><Menu size={21}/></button><span>工作台</span><span className="slash">/</span><strong>{current}</strong></div><div className="top-right"><span className="top-demo"><span/> 本地工作台</span><Link to="/settings" className="top-icon" aria-label="设置"><Settings2 size={18}/></Link><div className="top-avatar">OS</div></div></header><main className="content"><Routes><Route path="/assistant" element={<AssistantWorkspace key={location.search}/>}/><Route path="/" element={<Dashboard/>}/><Route path="/scan" element={<Workspace/>}/><Route path="/analysis" element={<Analysis/>}/><Route path="/reports" element={<Records kind="reports"/>}/><Route path="/history" element={<Records kind="history"/>}/><Route path="/models" element={<Models/>}/><Route path="/devices" element={<Devices/>}/><Route path="/settings" element={<Settings/>}/><Route path="*" element={<><PageTitle eyebrow="404" title="页面不存在" description="该页面暂不可用。"/><Button asChild><Link to="/">返回总览</Link></Button></>}/></Routes><footer><span>© 2026 AI OralScan · 研究工作台</span><span><Stethoscope size={14}/> 辅助筛查参考，非临床诊断</span></footer></main></div>{location.pathname!=='/assistant'&&<Link className="assistant-shortcut" to={new URLSearchParams(location.search).get('scan')?`/assistant?scan=${encodeURIComponent(new URLSearchParams(location.search).get('scan')!)}`:'/assistant'}><HeartHandshake size={18}/> 和小安聊聊</Link>}</div> }
export default App
