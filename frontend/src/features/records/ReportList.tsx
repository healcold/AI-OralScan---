import { zh } from '../../lib/zh'
import { useEffect, useState } from 'react'
import { Button } from '../../components/ui/button'
import { api, type ReportFormat, type SavedReport } from '../../lib/api'

export default function ReportList({ scanId, canGenerate = true }: { scanId: string; canGenerate?: boolean }) {
  const [reports, setReports] = useState<SavedReport[]>([])
  const [busy, setBusy] = useState<ReportFormat | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  useEffect(() => {
    let current = true
    api.reports(scanId).then(({items}) => { if (current) setReports(items) })
      .catch(e => { if (current) setError(e instanceof Error ? zh(e.message) : '无法加载报告') })
      .finally(() => { if (current) setLoading(false) })
    return () => { current = false }
  }, [scanId])

  async function generate(format: ReportFormat) {
    setBusy(format)
    setError('')
    try {
      const report = await api.createReport(scanId, format)
      setReports(items => [report, ...items])
    } catch (e) {
      setError(e instanceof Error ? zh(e.message) : '报告生成失败')
    } finally {
      setBusy(null)
    }
  }

  return <section aria-label="检查报告" className="saved-reports">
    {canGenerate && <div className="record-actions">
      <Button onClick={() => void generate('pdf')} disabled={!!busy || loading}>生成 PDF</Button>
      <Button variant="outline" onClick={() => void generate('json')} disabled={!!busy || loading}>生成 JSON</Button>
    </div>}
    {busy && <p role="status">正在生成 {busy.toUpperCase()} 报告…</p>}
    {loading && <p role="status">正在加载已保存报告…</p>}
    {error && <p role="alert">{error}</p>}
    {!loading && !error && reports.length === 0 && <p>此检查暂无已保存报告。</p>}
    <ul>{reports.map(report => <li key={report.report_id}>
      <span>{report.is_demo && '演示（DEMO） · '}{report.format.toUpperCase()} · {new Date(report.created_at).toLocaleString('zh-CN')}</span>
      <a className="text-link" href={report.download_url} download>下载 {report.format.toUpperCase()}</a>
    </li>)}</ul>
  </section>
}
