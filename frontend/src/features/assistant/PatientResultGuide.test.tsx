import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, type AssistantReply } from '../../lib/api'
import PatientResultGuide, { type GuidePhase } from './PatientResultGuide'

beforeEach(() => {
  vi.spyOn(api, 'assistantStatus').mockResolvedValue({ configured: true, local: true, provider: '本地 Qwen', model: 'qwen', message: '就绪' })
})
afterEach(() => vi.restoreAllMocks())
function show(phase: GuidePhase = 'ready') {
  return render(<MemoryRouter><PatientResultGuide scanId="s1" assetId="a1" phase={phase} modelReady onAnalyze={vi.fn()}/></MemoryRouter>)
}
async function agree() {
  await waitFor(() => expect(screen.getByRole('checkbox')).toBeEnabled())
  fireEvent.click(screen.getByRole('checkbox'))
}
const response: AssistantReply = { reply: '这里是对所选图像的解释，请预约口腔科确认。', provider: '本地 Qwen', model: 'qwen', context_included: true }

describe('in-place result companion', () => {
  it('waits for consent and scopes the interpretation and follow-up to the selected image', async () => {
    const chat = vi.spyOn(api, 'assistantChat').mockResolvedValue(response)
    show()
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '左侧牙龈疼了三天' } })
    expect(screen.getByRole('button', { name: '解读结果与就医建议' })).toBeDisabled()
    expect(chat).not.toHaveBeenCalled()
    await agree()
    fireEvent.click(screen.getByRole('button', { name: '解读结果与就医建议' }))
    await screen.findByText(response.reply)
    expect(chat.mock.calls[0][0][0].content).toContain('左侧牙龈疼了三天')
    expect(chat.mock.calls[0][1]).toBe('s1')
    expect(chat.mock.calls[0][3]).toBe('ollama')
    expect(chat.mock.calls[0][4]).toEqual({ asset_id: 'a1', intent: 'explain_result' })
    fireEvent.click(screen.getByRole('button', { name: '需要挂什么科？' }))
    await waitFor(() => expect(chat).toHaveBeenCalledTimes(2))
    expect(chat.mock.calls[1][0].map(m => m.role)).toEqual(['user', 'assistant', 'user'])
    expect(chat.mock.calls[1][4]?.asset_id).toBe('a1')
  })

  it.each(['waiting', 'analyzing', 'demo', 'failed'] as GuidePhase[])('does not interpret %s as patient findings', async phase => {
    const chat = vi.spyOn(api, 'assistantChat')
    show(phase)
    expect(screen.queryByRole('button', { name: '解读结果与就医建议' })).not.toBeInTheDocument()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(chat).not.toHaveBeenCalled()
  })

  it('keeps symptoms after a failure and requires consent again when they change', async () => {
    vi.spyOn(api, 'assistantChat').mockRejectedValueOnce(new Error('这张图像还没有已完成的分析结果。')).mockResolvedValueOnce(response)
    show()
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '牙疼三天' } })
    await agree(); fireEvent.click(screen.getByRole('button', { name: '解读结果与就医建议' }))
    await screen.findByRole('alert')
    expect(screen.getByRole('textbox')).toHaveValue('牙疼三天')
    fireEvent.click(screen.getByRole('button', { name: '解读结果与就医建议' }))
    await screen.findByText(response.reply)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '现在有些肿' } })
    expect(screen.getByRole('checkbox')).not.toBeChecked()
    expect(screen.queryByText(response.reply)).not.toBeInTheDocument()
  })

  it('shows immediate emergency guidance with its source and no routine follow-up choices', async () => {
    vi.spyOn(api, 'assistantChat').mockResolvedValue({ ...response, reply: '请现在联系当地急救。', provider: '就医引导', model: '固定紧急提示', urgent: true, context_included: false })
    show(); await agree()
    fireEvent.click(screen.getByRole('button', { name: '解读结果与就医建议' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('请现在联系当地急救')
    expect(screen.getByText('平台紧急就医提示 · 未调用模型')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '需要挂什么科？' })).not.toBeInTheDocument()
  })

  it('aborts a pending interpretation when switching to another image', async () => {
    let signal: AbortSignal | undefined
    vi.spyOn(api, 'assistantChat').mockImplementation((_messages, _scan, currentSignal) => {
      signal = currentSignal
      return new Promise<AssistantReply>((_resolve, reject) => currentSignal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError'))))
    })
    const view = show(); await agree()
    fireEvent.click(screen.getByRole('button', { name: '解读结果与就医建议' }))
    await screen.findByRole('button', { name: '停止等待' })
    view.rerender(<MemoryRouter><PatientResultGuide key="a2" scanId="s1" assetId="a2" phase="ready" modelReady onAnalyze={vi.fn()}/></MemoryRouter>)
    expect(signal?.aborted).toBe(true)
    expect(screen.getByRole('checkbox')).not.toBeChecked()
    expect(screen.queryByRole('article')).not.toBeInTheDocument()
  })
})
