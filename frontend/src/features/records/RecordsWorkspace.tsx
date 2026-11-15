import { zh } from '../../lib/zh'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Button } from '../../components/ui/button'
import { api, type HistoryFilters, type Scan, type UnifiedAnalysis } from '../../lib/api'
import ReportList from './ReportList'

function dateBoundary(value: string, nextDay = false) {
  if (!value) return undefined
  const date = new Date(`${value}T00:00:00`)
  if (nextDay) date.setDate(date.getDate() + 1)
  return date.toISOString()
}

export default function RecordsWorkspace({ kind }: { kind: 'history' | 'reports' }) {
  const [params, setParams] = useSearchParams()
  const selected = params.get('scan') ?? ''
  const [scans, setScans] = useState<Scan[]>([])
  const [query, setQuery] = useState('')
  const [modality, setModality] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [filters, setFilters] = useState<HistoryFilters>({})
  const [revision, setRevision] = useState(0)
  const [details, setDetails] = useState<UnifiedAnalysis | null>(null)
  const [error, setError] = useState('')
  const [detailsError, setDetailsError] = useState('')
  const [actionError, setActionError] = useState('')
  const [loading, setLoading] = useState(true)
  const [deleting, setDeleting] = useState('')
  const detailRef = useRef<HTMLElement>(null)

  useEffect(() => {
    let current = true
    setLoading(true)
    setError('')
    api.scans(filters).then(({items}) => { if (current) setScans(items) })
      .catch(e => { if (current) setError(e instanceof Error ? zh(e.message) : '无法加载检查记录') })
      .finally(() => { if (current) setLoading(false) })
    return () => { current = false }
  }, [filters, revision])

  useEffect(() => {
    let current = true
    setDetails(null)
    setDetailsError('')
    if (selected && kind === 'history') {
      api.unified(selected).then(data => { if (current) setDetails(data) })
        .catch(e => { if (current) setDetailsError(e instanceof Error ? zh(e.message) : '无法加载检查') })
    }
    return () => { current = false }
  }, [kind, selected])

  useEffect(() => {
    if (details?.scan_id === selected) detailRef.current?.scrollIntoView({ block: 'nearest' })
  }, [details, selected])

  function apply(event: FormEvent) {
    event.preventDefault()
    setActionError('')
    if (from && to && from > to) {
      setActionError('结束日期不能早于开始日期。')
      return
    }
    setFilters({scan_id: query.trim(), modality, from: dateBoundary(from), to: dateBoundary(to, true)})
  }

  async function remove(scan: Scan) {
    if (!window.confirm(`删除检查 ${scan.scan_id} 及其资产和已保存报告？`)) return
    setDeleting(scan.scan_id)
    setActionError('')
    try {
      await api.delete(scan.scan_id)
      if (scan.scan_id === selected) setParams({})
      setRevision(value => value + 1)
    } catch (e) {
      setActionError(e instanceof Error ? zh(e.message) : '无法删除检查')
      if (e instanceof Error && 'code' in e && e.code === 'STORAGE_CLEANUP_PENDING' && scan.scan_id === selected) setParams({})
      setRevision(value => value + 1)
    } finally {
      setDeleting('')
    }
  }

  return <div className="analysis-content records-workspace">
    {kind === 'history' && <form className="analysis-selector" onSubmit={apply}>
      <label>检查编号 <input value={query} maxLength={36} onChange={e => setQuery(e.target.value)}/></label>
      <label>开始日期 <input type="date" value={from} onChange={e => setFrom(e.target.value)}/></label>
      <label>结束日期 <input type="date" value={to} onChange={e => setTo(e.target.value)}/></label>
      <label>数据类型 <select value={modality} onChange={e => setModality(e.target.value)}>
        <option value="">所有类型</option><option value="image_2d">二维图像</option>
        <option value="mesh_3d">三维网格</option><option value="mixed">二维与三维混合</option>
      </select></label>
      <Button type="submit">应用筛选</Button>
    </form>}
    {loading && <p role="status">正在加载检查…</p>}
    {error && <><p role="alert">无法加载记录</p><p>{error}</p></>}
    {actionError && <p role="alert" className="acquisition-error">{actionError}</p>}
    {!loading && !error && scans.length === 0 && <p>暂无匹配的检查。</p>}
    {!loading && !error && (kind === 'reports'
      ? <label className="analysis-selector">检查 <select value={selected} onChange={e => setParams(e.target.value ? {scan:e.target.value} : {})}>
        <option value="">选择检查</option>
        {scans.map(scan => <option key={scan.scan_id} value={scan.scan_id}>{scan.scan_id}</option>)}
      </select></label>
      : <ul className="record-items">{scans.map(scan => <li key={scan.scan_id}>
        <div><strong>{scan.scan_id}</strong><small>{new Date(scan.created_at).toLocaleString('zh-CN')} · {scan.source_types.map(zh).join('、') || '暂无资产'}</small></div>
        <div className="record-actions">
          <Button variant="outline" onClick={() => setParams({scan: scan.scan_id})}>打开检查</Button>
          <Button variant="outline" disabled={!!deleting} onClick={() => void remove(scan)}>删除</Button>
        </div>
      </li>)}</ul>)}
    {selected && kind === 'reports' && !loading && !error && (scans.some(scan => scan.scan_id === selected)
      ? <ReportList key={selected} scanId={selected}/>
      : <p role="status">这份检查不在你的记录中，请重新选择。</p>)}
    {detailsError && <p role="alert">{detailsError}</p>}
    {selected && kind === 'history' && !details && !detailsError && <p role="status">正在加载检查详情…</p>}
    {details?.scan_id === selected && <section ref={detailRef} className="record-detail">
      <h2>检查 {details.scan_id}</h2>
      <div className="record-actions">
        <Link className="text-link" to={`/analysis?tab=unified&scan=${selected}`}>查看已保存分析</Link>
        <Link className="text-link" to={`/reports?scan=${selected}`}>查看报告</Link>
      </div>
      <h3>原始资产</h3>
      {details.assets.length === 0 && <p>暂无已保存资产。</p>}
      <ul>{details.assets.map(asset => <li key={asset.asset_id}>
        <a className="text-link" href={`/api/scans/${selected}/assets/${asset.asset_id}/content`} target="_blank" rel="noreferrer">{asset.filename}</a>
        {' · '}{zh(asset.modality)} · {zh(asset.analysis_status)}
        {asset.modality === 'mesh_3d' && <> · <Link className="text-link" to={`/analysis?tab=3d&scan=${selected}&asset=${asset.asset_id}`}>打开三维视图</Link></>}
      </li>)}</ul>
      <h3>已保存报告</h3>
      <ReportList key={selected} scanId={selected} canGenerate={false}/>
    </section>}
  </div>
}
