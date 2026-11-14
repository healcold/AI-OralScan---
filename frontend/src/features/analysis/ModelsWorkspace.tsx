import { zh } from '../../lib/zh'
import { useEffect, useState } from 'react'
import { api, type Model, type ModelStatus } from '../../lib/api'
import { Button } from '../../components/ui/button'

export default function ModelsWorkspace(){
 const [models,setModels]=useState<Model[]>([]);const [status,setStatus]=useState<ModelStatus|null>(null);const [error,setError]=useState('');const [busy,setBusy]=useState('');const [loading,setLoading]=useState(true)
 useEffect(()=>{let live=true;Promise.all([api.models(),api.modelStatus()]).then(([m,s])=>{if(live){setModels(m.items);setStatus(s)}}).catch(e=>{if(live)setError(e instanceof Error?zh(e.message):'无法加载模型')}).finally(()=>{if(live)setLoading(false)});return()=>{live=false}},[])
 async function load(id:string){setBusy(id);setError('');try{setStatus(await api.loadModel(id))}catch(e){setError(e instanceof Error?zh(e.message):'模型加载失败')}finally{setBusy('')}}
 return <section className="panel model-list"><div className="panel-head"><div><h2>口腔研究模型</h2><p>接入模型须明确输入输出约定及真实训练标签。</p></div><span className={`badge ${status?.status==='READY'?'badge-green':'badge-amber'}`}>{!status?'状态不可用':status.status==='READY'?'已就绪':'模型未配置'}</span></div>{loading&&<p role="status" className="model-note">正在加载模型状态…</p>}{error&&<p role="alert" className="acquisition-error model-note">{error}</p>}{!loading&&!error&&models.length===0&&<div className="empty"><h3>尚未配置模型</h3><p>当前尚未配置口腔模型，可通过模型接口注册经过验证的本地 ONNX 模型。</p></div>}{models.map(m=><div className="model-row" key={m.model_id}><div><strong>{m.name} · {m.version}</strong><small>{zh(m.task)} · {m.config.input_size.join(' × ')} · {zh(m.config.resize_mode)} · {m.config.output_layout}</small><small>标签：{m.config.labels.join(', ')}</small></div><Button variant="outline" onClick={()=>void load(m.model_id)} disabled={!!busy}>{busy===m.model_id?'正在加载…':status?.model?.model_id===m.model_id?'重新加载':'加载模型'}</Button></div>)}<div className="panel-footer">加载状态不代表已通过临床验证。模型评分不等于患病概率。</div></section>
}
