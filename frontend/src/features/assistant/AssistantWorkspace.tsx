import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ArrowRight, Check, HeartHandshake, LoaderCircle, MessageCircle, RefreshCw, Send, ShieldCheck, Sparkles } from 'lucide-react'
import { api, type AssistantMessage, type AssistantStatus, type Scan } from '../../lib/api'
import { Button } from '../../components/ui/button'
import './assistant.css'

const starters = [
  {title:'牙齿不舒服',text:'我的牙齿最近有些不舒服，也有点担心。我应该先留意哪些情况？',icon:MessageCircle},
  {title:'看不懂检查结果',text:'我想了解口腔检查中常见的专业词语，应该怎样和医生确认自己的情况？',icon:Sparkles},
  {title:'看牙前有些紧张',text:'我一想到看牙就很紧张，担心会疼，可以陪我一起做些准备吗？',icon:HeartHandshake},
  {title:'不知道怎么开始',text:'我是第一次使用这个工作台，可以一步一步引导我上传图片和查看检查吗？',icon:ArrowRight},
]

export default function AssistantWorkspace() {
  const [params] = useSearchParams()
  const initialScan = params.get('scan') ?? ''
  const [status,setStatus] = useState<AssistantStatus|null>(null)
  const [statusError,setStatusError] = useState('')
  const [statusAttempt,setStatusAttempt] = useState(0)
  const [messages,setMessages] = useState<AssistantMessage[]>([])
  const [draft,setDraft] = useState('')
  const [pending,setPending] = useState(false)
  const [error,setError] = useState('')
  const [consent,setConsent] = useState(false)
  const [scans,setScans] = useState<Scan[]>([])
  const [scansError,setScansError] = useState('')
  const [scanId,setScanId] = useState(initialScan)
  const [includeScan,setIncludeScan] = useState(false)
  const [usedContext,setUsedContext] = useState(false)
  const [replyModel,setReplyModel] = useState('')
  const [replyProvider,setReplyProvider] = useState('')
  const [replyUrgent,setReplyUrgent] = useState(false)
  const controllerRef = useRef<AbortController|null>(null)
  const endRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    let live = true
    api.assistantStatus().then(result => {if(live){setStatus(result);setStatusError('')}})
      .catch(() => {if(live)setStatusError('暂时无法确认连接状态，请稍后重试。')})
    return () => {live=false}
  },[statusAttempt])
  useEffect(() => {
    let live = true
    api.scans().then(result => {if(live)setScans(result.items)})
      .catch(() => {if(live)setScansError('暂时无法读取检查列表，仍可进行普通问答。')})
    return () => {live=false;controllerRef.current?.abort()}
  },[])
  useEffect(() => {endRef.current?.scrollIntoView?.({behavior:'smooth',block:'nearest'})},[messages,pending,error])

  function resetConversation() {
    setMessages([]);setDraft('');setError('');setUsedContext(false);setReplyModel('');setReplyProvider('');setReplyUrgent(false);setConsent(false)
  }
  function chooseStarter(text:string) {setDraft(text);inputRef.current?.focus()}
  async function send(event:FormEvent) {
    event.preventDefault()
    const text = draft.trim()
    if(!text || text.length>3000 || pending || !status?.configured || statusError || !consent) return
    const controller = new AbortController()
    controllerRef.current = controller
    const timeout = window.setTimeout(() => controller.abort('timeout'),((status.timeout_seconds??55)+5)*1000)
    const history = messages.slice(-20)
    while(history.length && history.reduce((sum,m)=>sum+m.content.length,0)+text.length>24000) history.splice(0,2)
    if(status.max_history_bytes) {
      const encoder = new TextEncoder()
      while(history.length && history.reduce((sum,m)=>sum+encoder.encode(m.content).length,0)+encoder.encode(text).length>status.max_history_bytes) history.splice(0,2)
    }
    const outgoing:AssistantMessage[] = [...history,{role:'user',content:text}]
    setPending(true);setError('')
    try {
      const result = await api.assistantChat(outgoing,includeScan&&scanId?scanId:undefined,controller.signal,status.local?'ollama':'deepseek')
      if(controller.signal.aborted) return
      setMessages([...outgoing,{role:'assistant',content:result.reply}])
      setUsedContext(result.context_included);setReplyModel(result.model);setReplyProvider(result.provider);setReplyUrgent(result.urgent??false);setDraft('')
    } catch(cause) {
      if(controller.signal.aborted && controller.signal.reason !== 'timeout') return
      setError(controller.signal.aborted?'等待有些久，暂时没有收到完整回答。问题已保留，你可以再试一次。':cause instanceof Error?cause.message:'暂时连接不上，问题已保留，请稍后再试。')
    } finally {
      window.clearTimeout(timeout)
      if(controllerRef.current===controller){controllerRef.current=null;setPending(false)}
    }
  }
  function stopWaiting() {
    controllerRef.current?.abort()
    setPending(false);setError('已停止等待。问题已保留，需要时可以重新发送。')
  }
  function onKeyDown(event:KeyboardEvent<HTMLTextAreaElement>) {
    if(event.key==='Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();event.currentTarget.form?.requestSubmit()
    }
  }

  return <>
    <div className="page-title assistant-title"><div><div className="eyebrow">陪伴 · 了解 · 下一步</div><h1>AI 助理</h1><p>关于口腔健康的担心，我们可以慢慢聊。</p></div><Button variant="outline" disabled={pending||messages.length===0} onClick={resetConversation}><RefreshCw size={15}/> 开始新对话</Button></div>
    <div className="assistant-layout">
      <section className="assistant-chat panel" aria-label="口腔健康对话">
        <header className="assistant-chat-header"><div className="assistant-avatar"><HeartHandshake size={22}/></div><div><strong>小安 · 口腔健康 AI 助理</strong><span>认真听你说，也陪你找到下一步</span></div><span className={`assistant-connection ${status?.configured?'ready':''}`} role="status"><i/>{statusError?'连接待恢复':status===null?'连接中':status.configured?'可以聊聊':'正在准备'}</span></header>
        <div className="assistant-messages" role="log" aria-label="对话记录" aria-live="polite" aria-relevant="additions text">
          {messages.length===0&&!pending?<div className="assistant-welcome"><div className="assistant-welcome-icon"><Sparkles size={28}/></div><span className="assistant-kicker">你好，我是小安</span><h2>不用急着把一切说清楚，<br/>从你最在意的事开始。</h2><p>牙齿的不舒服、看不懂的检查词语，<br/>或是看牙前的一点紧张，都可以和我说。</p><div className="assistant-starters">{starters.map(({title,text,icon:Icon})=><button key={title} type="button" onClick={()=>chooseStarter(text)}><Icon size={17}/><span>{title}</span><ArrowRight size={14}/></button>)}</div></div>:<>
            {messages.map((message,index)=><article className={`assistant-message ${message.role}`} key={index}><span className="assistant-message-name">{message.role==='user'?'你':'小安 · AI'}</span><div>{message.role==='assistant'?message.content.replace(/\*\*([^*]+)\*\*/g,'$1'):message.content}</div></article>)}
            {pending&&<><article className="assistant-message user"><span className="assistant-message-name">你</span><div>{draft.trim()}</div></article><div className="assistant-thinking" role="status"><LoaderCircle size={17} className="assistant-spin"/>小安正在认真整理回答…<button type="button" onClick={stopWaiting}>停止等待</button></div></>}
          </>}
          <div ref={endRef}/>
        </div>
        <div className="assistant-compose">
          {statusError?<div className="assistant-preparing" role="alert">{statusError}<button onClick={()=>{setStatus(null);setStatusError('');setStatusAttempt(n=>n+1)}} type="button">重新连接</button></div>:status&&!status.configured?<div className="assistant-preparing"><span className="assistant-soft-dot"/><span>AI 助理还在准备中，暂时不能回复。你可以先选择话题，或写下想问的问题。</span><button type="button" onClick={()=>{setStatus(null);setStatusAttempt(n=>n+1)}}>检查连接</button></div>:null}
          {error&&<div className="assistant-error" role="alert">{error}</div>}
          <form onSubmit={event=>void send(event)}>
            <label className="assistant-sr-only" htmlFor="assistant-question">想和小安说的话</label>
            <textarea id="assistant-question" ref={inputRef} value={draft} readOnly={pending} onChange={event=>setDraft(event.target.value)} onKeyDown={onKeyDown} maxLength={3000} placeholder="说说哪里不舒服，或者你现在最担心什么…" rows={3} aria-describedby="assistant-input-hint"/>
            <div className="assistant-input-bottom"><span id="assistant-input-hint">{draft.length}/3000 · Enter 发送，Shift + Enter 换行</span><Button type="submit" disabled={!status?.configured||!!statusError||pending||!consent||!draft.trim()}><Send size={15}/>{pending?'整理回答中':'发送给小安'}</Button></div>
          </form>
          {status?.local&&<p className="assistant-local-note"><ShieldCheck size={14}/> 免费本地模型 · 对话在这台电脑上处理</p>}
          <label className="assistant-consent"><input type="checkbox" checked={consent} disabled={pending||!status} onChange={event=>setConsent(event.target.checked)}/><span>{status?.local?'我同意在本机处理本次对话':'我同意将本次对话'}{includeScan?'及所选检查的文字摘要':''}{status?.local?'，用于生成回答。':`发送给 ${status?.provider??'所选模型服务'}，用于生成回答。`}请勿填写姓名、电话等身份信息。</span></label>
          {replyModel&&<p className="assistant-source">{replyUrgent?'紧急就医提示由平台直接提供，未调用模型。请优先联系急救。':replyProvider==='健康引导'?'平台健康提示：具体情况和舒适措施请与口腔医生确认。':replyProvider==='平台引导'?'操作步骤由平台提供，依据当前工作台功能整理。':`由 ${replyProvider} · ${replyModel} 生成${usedContext?' · 已结合所选检查文字摘要':' · 仅依据对话文字'}。回答供理解与就医准备参考。`}</p>}
        </div>
      </section>
      <aside className="assistant-aside">
        <section className="assistant-care-card"><HeartHandshake size={23}/><h2>先照顾你的感受</h2><p>担心和紧张都很正常。你不需要一次描述完整，也可以直接告诉小安：“我有点害怕。”</p><div><Check size={14}/> 不催促，慢慢说明白</div><div><Check size={14}/> 用容易理解的话解释</div><div><Check size={14}/> 一起整理接下来的安排</div></section>
        <section className="assistant-context panel"><h2>一起看看检查</h2><p>如果愿意，可以让小安结合一份已保存检查的文字结果来解释。</p><label htmlFor="assistant-scan">选择检查</label><select id="assistant-scan" value={scanId} disabled={pending} onChange={event=>{setScanId(event.target.value);setIncludeScan(false);setConsent(false);resetConversation()}}><option value="">暂不选择</option>{scans.map(scan=><option key={scan.scan_id} value={scan.scan_id}>{new Date(scan.created_at).toLocaleString('zh-CN')} · {scan.scan_id.slice(0,8)}</option>)}</select>
          <label className="assistant-context-check"><input type="checkbox" checked={includeScan} disabled={!scanId||pending} onChange={event=>{setIncludeScan(event.target.checked);setConsent(false);resetConversation()}}/><span>结合这份检查的文字摘要</span></label><small>仅发送分析状态与结果摘要，不发送原始图片、三维文件或身份字段。切换检查会开始新对话。</small>{scansError&&<p role="status">{scansError}</p>}{!scansError&&scans.length===0&&<p className="assistant-no-record">还没有保存的检查，也可以直接聊聊。</p>}</section>
        <section className="assistant-boundary"><ShieldCheck size={18}/><div><h2>帮助理解，也尊重专业判断</h2><p>小安可以解释症状的可能原因和报告术语，无法直接看图、确诊或完成病理诊断。具体情况请由口腔医生结合检查判断。</p><p>如果出现呼吸困难、面颈部迅速肿胀或持续大量出血，请立即就医。</p></div></section>
      </aside>
    </div>
  </>
}
