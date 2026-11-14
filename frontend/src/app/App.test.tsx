import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
const scan = {scan_id:'00000000-0000-4000-8000-000000000001',created_at:'2026-11-13T12:00:00Z',updated_at:'2026-11-13T12:00:00Z',status:'draft',source_types:[],metadata:{}}
beforeEach(() => { vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ok: true, status: 200, json: async () => url==='/api/models/status'?{status:'MODEL_NOT_CONFIGURED',model:null}:url.endsWith('/assets') ? {items: []} : url.endsWith('/analysis')?{jobs:[],findings:[]}:{items: [scan]}}))) })
function show(path: string) { return render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>) }
describe('workspace navigation', () => {
  it('opens every page through navigation', () => { show('/'); const navigation = within(screen.getByRole('navigation', { name: '主导航' })); for (const name of ['扫描工作台','分析','AI 助理','报告','历史记录','模型管理','设备管理','设置','总览']) { fireEvent.click(navigation.getByRole('link', { name })); expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(name === '总览' ? '工作台总览' : name) } })
  it('switches independent acquisition tabs', () => { show('/scan'); fireEvent.click(screen.getByRole('tab', { name: /摄像头采集/ })); expect(screen.getByRole('button', { name: '开启摄像头' })).toBeInTheDocument(); fireEvent.click(screen.getByRole('tab', { name: /导入三维模型/ })); expect(screen.getByText('将三维模型拖放到这里')).toBeInTheDocument() })
  it('switches analysis tabs', () => { show('/analysis'); fireEvent.click(screen.getByRole('tab', { name: /三维分析/ })); expect(screen.getByText('尚未选择三维模型')).toBeInTheDocument() })
  it('shows scan data returned by the API', async () => { show('/history'); expect(await screen.findByText(scan.scan_id)).toBeInTheDocument(); expect(fetch).toHaveBeenCalledWith('/api/scans', undefined) })
  it('shows backend errors', async () => { vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('网络不可用'))); show('/history'); expect(await screen.findByText('无法加载记录')).toBeInTheDocument(); expect(screen.getByText('网络不可用')).toBeInTheDocument() })
})
