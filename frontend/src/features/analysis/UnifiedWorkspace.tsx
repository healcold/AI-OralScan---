import { zh } from '../../lib/zh'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Scan, type UnifiedAnalysis } from '../../lib/api'

export default function UnifiedWorkspace({ initialScan = '' }: { initialScan?: string }) {
  const [scans, setScans] = useState<Scan[]>([])
  const [scan, setScan] = useState(initialScan)
  const [data, setData] = useState<UnifiedAnalysis | null>(null)
  const [listError, setListError] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let live = true
    api.scans().then(({items}) => {
      if (!live) return
      setScans(items)
      setScan(initialScan || items[0]?.scan_id || '')
    }).catch(e => { if (live) setListError(e instanceof Error ? zh(e.message) : '无法加载检查记录') })
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [initialScan])
  useEffect(() => {
    let live = true
    setData(null)
    setError('')
    if (scan) api.unified(scan).then(result => { if (live) setData(result) })
      .catch(e => { if (live) setError(e instanceof Error ? zh(e.message) : '无法加载结果') })
    return () => { live = false }
  }, [scan])

  return <div className="analysis-content">
    <div className="analysis-selector">
      <label>检查 <select aria-label="多模态检查" value={scan} onChange={e => setScan(e.target.value)}>
        <option value="">选择检查</option>
        {scans.map(item => <option value={item.scan_id} key={item.scan_id}>{item.scan_id}</option>)}
      </select></label>
      {data?.scan_id === scan && <Link className="text-link" to={`/reports?scan=${scan}`}>查看报告</Link>}
    </div>
    {(loading || (scan && !data && !error)) && <p role="status">正在加载分析…</p>}
    {(error || listError) && <p role="alert" className="acquisition-error">{error || listError}</p>}
    {data?.scan_id === scan && <>
      <h3 className="geometry-title">资产与处理状态</h3>
      {data.assets.length === 0 && <p>此检查暂无资产。</p>}
      {data.assets.map(asset => <div className="model-row" key={asset.asset_id}>
        <div>
          <strong>{asset.filename}</strong>
          <small>{zh(asset.modality)} · {zh(asset.source_type)} · {zh(asset.analysis_status)}</small>
          {asset.jobs.map(job => {
            const summary = job.result_summary
            const warnings = Array.isArray(summary.warnings) ? summary.warnings : []
            const model = [summary.model_name, summary.model_version].filter(value => typeof value === 'string').join(' · ')
            return <div key={job.job_id}>
              <small>{summary.is_demo === true && '演示（DEMO） · '}{zh(job.pipeline)} · {zh(job.status)} · {new Date(job.created_at).toLocaleString('zh-CN')}
                {model && ` · ${model}`}{typeof summary.processing_time_ms === 'number' && ` · ${summary.processing_time_ms} ms`}
              </small>
              {typeof summary.error === 'string' && <small>{zh(summary.error)}</small>}
              {warnings.map((warning, index) => <small key={index}>{zh(String(warning))}</small>)}
            </div>
          })}
        </div>
        <Link className="text-link" to={`/analysis?tab=${asset.modality === 'mesh_3d' ? '3d' : 'image'}&scan=${scan}&asset=${asset.asset_id}`}>查看资产分析</Link>
      </div>)}
      <h3 className="geometry-title">分析发现</h3>
      {data.findings.length === 0 ? <p>暂无分析发现。</p> : data.findings.map(finding => {
        const source = data.assets.find(asset => asset.asset_id === finding.asset_id)
        return <div className="model-row" key={finding.finding_id}><div>
          <strong>{finding.evidence.is_demo && '演示（DEMO） · '}{zh(finding.category)}</strong>
          <small>{zh(finding.modality)} · {source?.filename ?? finding.asset_id} · {zh(finding.review_status)}</small>
          <small>{finding.model_version && `模型 ${finding.model_version} · `}
            {finding.confidence === null ? '无模型评分' : `模型评分 ${(finding.confidence * 100).toFixed(1)}%`}
            {' · '}{zh(finding.location?.coordinate_space ?? '无空间位置')}
          </small>
        </div></div>
      })}
      {data.limitations.map(limit => <p className="geometry-warning" key={zh(limit)}>{zh(limit)}</p>)}
    </>}
  </div>
}

