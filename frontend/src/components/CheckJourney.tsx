import { ArrowRight, Check, HeartHandshake } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button } from './ui/button'
import XiaoAnAvatar from './XiaoAnAvatar'

const steps = ['上传资料', '查看分析', '理解结果', '查看报告']

export function CheckSteps({ current }: { current: number }) {
  return <ol className="check-steps" aria-label="检查流程">
    {steps.map((label, index) => <li key={label} aria-current={index === current ? 'step' : undefined} className={index < current ? 'previous' : ''}>
      <span>{index + 1}</span><strong>{label}</strong>
    </li>)}
  </ol>
}

export function SavedCheckActions({ scanId, assetId, isMesh = false }: { scanId: string; assetId?: string; isMesh?: boolean }) {
  const query = new URLSearchParams({ scan: scanId, ...(isMesh ? { tab: '3d' } : {}), ...(assetId ? { asset: assetId } : {}) })
  return <section className="check-next" aria-label="保存后的下一步">
    <div className="check-next-companion"><XiaoAnAvatar/><div><span className="check-next-kicker"><Check size={16}/> 资料已保存</span><h3>{isMesh ? '接下来，查看三维模型' : '图片保存好了，小安陪你看结果'}</h3><p>{isMesh ? '可以查看模型和几何指标，也可以让小安解释文字摘要。' : '先完成图像分析，再由小安解释文字结果，一起整理就医建议。'}</p></div></div>
    <div className="check-next-actions">
      <Button asChild><Link to={`/analysis?${query}`}>{isMesh ? '查看三维模型' : '查看图像与分析'}<ArrowRight size={16}/></Link></Button>
      <Button asChild variant="outline"><Link to={`/assistant?scan=${encodeURIComponent(scanId)}`}><HeartHandshake size={16}/> 问问小安</Link></Button>
    </div>
  </section>
}

export function ResultNextActions({ scanId }: { scanId: string }) {
  return <section className="check-next check-next-results" aria-label="结果查看后的下一步">
    <div><h3>我们一起了解下一步</h3><p>小安可以帮助理解已有的文字结果；没有分析结果时，也可以询问一般口腔健康问题。</p></div>
    <div className="check-next-actions">
      <Button asChild><Link to={`/assistant?scan=${encodeURIComponent(scanId)}`}><HeartHandshake size={16}/> 请小安解释</Link></Button>
      <Button asChild variant="outline"><Link to={`/reports?scan=${encodeURIComponent(scanId)}`}>查看报告<ArrowRight size={16}/></Link></Button>
    </div>
  </section>
}
