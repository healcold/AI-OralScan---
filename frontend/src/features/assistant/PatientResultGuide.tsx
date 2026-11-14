import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, HeartHandshake, LoaderCircle, ShieldCheck } from 'lucide-react'
import { api, ApiError, type AssistantMessage, type AssistantReply, type AssistantStatus } from '../../lib/api'
import { Button } from '../../components/ui/button'
import XiaoAnAvatar from '../../components/XiaoAnAvatar'
import './patient-result-guide.css'

export type GuidePhase = 'waiting' | 'analyzing' | 'ready' | 'demo' | 'failed'
const introductions: Record<GuidePhase, { label: string; title: string; text: string }> = {
  waiting: { label: '陪你完成检查', title: '图片收到了，我们一步一步来。', text: '先完成图像分析，有了文字结果后，我可以陪你理解，再一起整理就医时要问的问题。' },
  analyzing: { label: '图像分析中', title: '正在分析，我在这里陪你。', text: '结果准备好后，我会提示你。等待期间不需要重复点击，也可以先想一想哪里不舒服、持续了多久。' },
  ready: { label: '可以解读结果', title: '结果已准备好，我们一起慢慢看。', text: '我可以把当前图像的文字结果解释得容易理解一些，并结合你的不适描述，整理就医建议和看诊前的准备。' },
  demo: { label: '当前为演示', title: '这是示例，我们先不据此判断病情。', text: '演示标记不代表你的检查发现。你仍然可以和我聊聊自己的不适，实际情况需要由口腔医生检查确认。' },
  failed: { label: '分析未完成', title: '这次分析没有完成，图片还在。', text: '可以稍后重试。现在还不能依据这张图片解释病情；如果已经不舒服，也可以先向口腔医生咨询。' },
}

export default function PatientResultGuide({ scanId, assetId, phase, modelReady, onAnalyze }: {
  scanId: string; assetId: string; phase: GuidePhase; modelReady: boolean; onAnalyze: () => void
}) {
  const id = useId()
  const [status, setStatus] = useState<AssistantStatus | null>(null)
  const [statusError, setStatusError] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const [symptoms, setSymptoms] = useState('')
  const [consent, setConsent] = useState(false)
  const [pending, setPending] = useState(false)
  const [reply, setReply] = useState<AssistantReply | null>(null)
  const [history, setHistory] = useState<AssistantMessage[]>([])
  const [error, setError] = useState('')
  const controller = useRef<AbortController | null>(null)
  const mounted = useRef(true)
  const intro = introductions[phase]

  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false; controller.current?.abort() }
  }, [])
  useEffect(() => {
    let live = true
    api.assistantStatus().then(value => { if (live) { setStatus(value); setStatusError(false) } })
      .catch(() => { if (live) setStatusError(true) })
    return () => { live = false }
  }, [attempt])

  async function explain(question?: string) {
    if (controller.current || !consent || !status?.configured || statusError || phase !== 'ready') return
    const abort = new AbortController()
    controller.current = abort
    const timeout = window.setTimeout(() => abort.abort('timeout'), ((status.timeout_seconds ?? 55) + 5) * 1000)
    const text = question ? `${question}${symptoms.trim() ? '\n我补充的不适描述：' + symptoms.trim() : ''}` : `请温和地解释当前图像的已有分析结果，帮助我理解，并整理就医建议和就诊前的准备。不要把模型标记当作确诊，也不要根据分数判断病情严重程度。${symptoms.trim() ? '\n我补充的不适描述：' + symptoms.trim() : '\n我暂未补充症状，请说明哪些情况还需要与医生确认。'}`
    const previous = [...history.slice(-6)]
    const encoder = new TextEncoder()
    while (previous.length && encoder.encode(previous.map(m => m.content).join('') + text).length > (status.max_history_bytes ?? 14000)) previous.splice(0, 2)
    const outgoing: AssistantMessage[] = [...previous, { role: 'user', content: text }]
    setPending(true); setError('')
    try {
      const result = await api.assistantChat(outgoing, scanId, abort.signal, status.local ? 'ollama' : 'deepseek', { asset_id: assetId, intent: 'explain_result' })
      if (abort.signal.aborted || !mounted.current) return
      setReply(result); setHistory([...outgoing, { role: 'assistant', content: result.reply }])
    } catch (cause) {
      if (!mounted.current || (abort.signal.aborted && abort.signal.reason !== 'timeout')) return
      if (cause instanceof ApiError && cause.code === 'ASSISTANT_PROVIDER_CHANGED') { setConsent(false); setStatus(null); setAttempt(n => n + 1) }
      setError(abort.signal.aborted ? '等待有些久，还没有收到完整解读。描述已保留，可以稍后重试。' : cause instanceof Error ? cause.message : '暂时没有连接上，描述已保留，请稍后重试。')
    } finally {
      window.clearTimeout(timeout)
      if (controller.current === abort) { controller.current = null; if (mounted.current) setPending(false) }
    }
  }
  function stop() {
    controller.current?.abort(); controller.current = null; setPending(false)
    setError('已停止等待，你的描述仍在，需要时可以重新生成解读。')
  }
  function submit(event: FormEvent) { event.preventDefault(); void explain() }

  return <section className="patient-guide" aria-label="小安结果解读">
    <header className="patient-guide-header">
      <XiaoAnAvatar thinking={pending || phase === 'analyzing'}/>
      <div><span className="patient-guide-kicker">小安 · AI 陪伴助理</span><h2>{intro.title}</h2></div>
      <span className={`patient-guide-state state-${phase}`} role="status">{intro.label}</span>
    </header>
    <p className="patient-guide-intro">{intro.text}</p>
    {phase === 'ready' ? <>
      <form onSubmit={submit} className="patient-guide-form">
        <label htmlFor={`${id}-symptoms`}>想补充哪里不舒服吗？<span>可选</span></label>
        <textarea id={`${id}-symptoms`} rows={2} maxLength={500} value={symptoms} readOnly={pending} placeholder="例如：左侧牙龈疼了三天，有些肿。请勿填写姓名、电话等身份信息。" onChange={event => { setSymptoms(event.target.value); setConsent(false); setReply(null); setHistory([]); setError('') }}/>
        <label className="patient-guide-consent"><input type="checkbox" checked={consent} disabled={pending || !status} onChange={event => setConsent(event.target.checked)}/><span>我同意使用当前图像的文字分析结果和上述描述，交给{status?.local ? '本地模型' : status?.provider ?? '所选模型服务'}生成解读。不发送原始图片。</span></label>
        <div className="patient-guide-submit">
          <Button type="submit" disabled={!consent || pending || !status?.configured || statusError}>{pending ? <LoaderCircle size={17} className="guide-spinner"/> : <HeartHandshake size={17}/>} {pending ? '小安正在整理…' : reply ? '重新生成解读' : '解读结果与就医建议'}</Button>
          {pending && <button className="patient-guide-text-button" type="button" onClick={stop}>停止等待</button>}
          {!consent && <small>勾选说明后，小安再开始解读。</small>}
        </div>
      </form>
      {(statusError || status && !status.configured) && <p className="patient-guide-offline" role="status">小安暂时还不能生成解读，检查结果仍可查看。<button type="button" onClick={() => { setConsent(false); setStatus(null); setStatusError(false); setAttempt(n => n + 1) }}>重新连接</button></p>}
      {pending && <p className="patient-guide-thinking" role="status">正在结合这张图像的文字结果整理回答，首次运行可能稍久。</p>}
      {error && <p className="patient-guide-error" role="alert">{error}</p>}
      {reply && <article className={`patient-guide-answer ${reply.urgent ? 'is-urgent' : ''}`} aria-label="小安的结果说明" aria-live={reply.urgent ? 'assertive' : 'polite'} role={reply.urgent ? 'alert' : undefined}>
        <h3>{reply.urgent ? '请先及时获得现场帮助' : '小安陪你理解'}</h3>
        <div className="patient-guide-answer-text">{reply.reply.replace(/\*\*([^*]+)\*\*/g, '$1')}</div>
        <p className="patient-guide-source">{reply.urgent ? '平台紧急就医提示 · 未调用模型' : reply.provider === '健康引导' ? '平台健康提示 · 请与口腔医生确认具体情况' : `${reply.provider} · ${reply.model} · ${reply.context_included ? '已结合当前图像文字结果' : '未使用检查结果，仅作一般健康引导'}`}</p>
        {!reply.urgent && <div className="patient-guide-followups" aria-label="继续了解">
          {['需要挂什么科？', '就诊前准备什么？', '这个结果有哪些不确定性？'].map(question => <button key={question} type="button" disabled={pending || !consent} onClick={() => void explain(question)}>{question}</button>)}
        </div>}
      </article>}
    </> : <div className="patient-guide-actions">
      {(phase === 'waiting' || phase === 'failed') && modelReady && <Button onClick={onAnalyze}>开始图像分析<ArrowRight size={16}/></Button>}
      {phase === 'waiting' && !modelReady && <span className="patient-guide-unavailable">影像分析暂未就绪，先保留好图片。有不适时可以先咨询口腔医生。</span>}
    </div>}
    <div className="patient-guide-footer"><span><ShieldCheck size={15}/> 帮助理解，不替代口腔医生检查。</span><Link to={`/assistant?scan=${encodeURIComponent(scanId)}`}>更多口腔健康问题<ArrowRight size={14}/></Link>{phase === 'ready' && <Link to={`/reports?scan=${encodeURIComponent(scanId)}`}>查看这次检查的报告<ArrowRight size={14}/></Link>}</div>
    <p className="patient-guide-urgent-note">如出现呼吸困难、面颈部迅速肿胀或持续大量出血，请立即联系当地急救。</p>
  </section>
}
