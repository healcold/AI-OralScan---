import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, type AssistantReply } from '../../lib/api'
import AssistantWorkspace from './AssistantWorkspace'

beforeEach(() => {
  vi.spyOn(api,'assistantStatus').mockResolvedValue({configured:true,provider:'DeepSeek',model:'deepseek-flash',message:'可以开始对话'})
  vi.spyOn(api,'scans').mockResolvedValue({items:[]})
})
afterEach(() => vi.restoreAllMocks())

function show() {return render(<MemoryRouter><AssistantWorkspace/></MemoryRouter>)}
function question(text:string) {fireEvent.change(screen.getByRole('textbox',{name:'想和小安说的话'}),{target:{value:text}})}
function agree() {fireEvent.click(screen.getByRole('checkbox',{name:/我同意/}))}

describe('patient assistant',()=>{
  it('labels immediate emergency guidance as platform advice rather than a model answer',async()=>{
    vi.spyOn(api,'assistantChat').mockResolvedValue({reply:'如果症状正在发生，请立即联系当地急救。',provider:'就医引导',model:'固定紧急提示',context_included:false,urgent:true})
    show();await screen.findByText('可以聊聊')
    question('现在呼吸困难');agree();fireEvent.click(screen.getByRole('button',{name:'发送给小安'}))
    await screen.findByText('如果症状正在发生，请立即联系当地急救。')
    expect(screen.getByText('紧急就医提示由平台直接提供，未调用模型。请优先联系急救。')).toBeInTheDocument()
    expect(screen.queryByText(/由 DeepSeek/)).not.toBeInTheDocument()
  })
  it('correctly describes free local processing and sends the selected provider',async()=>{
    vi.mocked(api.assistantStatus).mockResolvedValue({configured:true,local:true,provider:'本地 Qwen',model:'qwen3.5:2b-q4_K_M',message:'可以开始对话',max_history_bytes:14000,timeout_seconds:120})
    const chat=vi.spyOn(api,'assistantChat').mockResolvedValue({reply:'我们可以先聊聊你的担心。',provider:'本地 Qwen',model:'qwen3.5:2b-q4_K_M',context_included:false})
    show();await screen.findByText('免费本地模型 · 对话在这台电脑上处理')
    expect(screen.getByRole('checkbox',{name:/我同意在本机处理/})).toBeInTheDocument()
    expect(screen.queryByText(/发送给 DeepSeek/)).not.toBeInTheDocument()
    question('我有些紧张');agree();fireEvent.click(screen.getByRole('button',{name:'发送给小安'}))
    await screen.findByText('我们可以先聊聊你的担心。')
    expect(chat.mock.calls[0][3]).toBe('ollama')
    expect(screen.getByText(/由 本地 Qwen/)).toBeInTheDocument()
  })
  it('offers a draft without pretending to answer when no key is configured',async()=>{
    vi.mocked(api.assistantStatus).mockResolvedValue({configured:false,provider:'DeepSeek',model:'deepseek-flash',message:'未配置'})
    const chat = vi.spyOn(api,'assistantChat')
    show()
    expect(await screen.findByText(/AI 助理还在准备中/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'看牙前有些紧张'}))
    expect(screen.getByRole('textbox')).toHaveValue('我一想到看牙就很紧张，担心会疼，可以陪我一起做些准备吗？')
    agree()
    expect(screen.getByRole('button',{name:'发送给小安'})).toBeDisabled()
    expect(chat).not.toHaveBeenCalled()
  })

  it('requires consent and preserves multi-turn conversation',async()=>{
    const chat = vi.spyOn(api,'assistantChat').mockResolvedValue({reply:'我听到了你的担心，我们慢慢说。',provider:'DeepSeek',model:'deepseek-flash',context_included:false})
    show()
    await screen.findByText('可以聊聊')
    question('我害怕看牙')
    expect(screen.getByRole('button',{name:'发送给小安'})).toBeDisabled()
    agree();fireEvent.click(screen.getByRole('button',{name:'发送给小安'}))
    expect(await screen.findByText('我听到了你的担心，我们慢慢说。')).toBeInTheDocument()
    expect(chat.mock.calls[0][0]).toEqual([{role:'user',content:'我害怕看牙'}])
    expect(chat.mock.calls[0][1]).toBeUndefined()
    question('我可以做什么准备？')
    fireEvent.click(screen.getByRole('button',{name:'发送给小安'}))
    await waitFor(()=>expect(chat).toHaveBeenCalledTimes(2))
    expect(chat.mock.calls[1][0].map(m=>m.role)).toEqual(['user','assistant','user'])
  })

  it('keeps the question after an error and can stop waiting without a fake answer',async()=>{
    vi.spyOn(api,'assistantChat').mockRejectedValueOnce(new Error('现在咨询的人有些多，请稍等片刻再试。'))
      .mockImplementationOnce((_messages,_scan,signal)=>new Promise<AssistantReply>((_resolve,reject)=>signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')))))
    show();await screen.findByText('可以聊聊')
    question('我的牙疼');agree();fireEvent.click(screen.getByRole('button',{name:'发送给小安'}))
    expect(await screen.findByRole('alert')).toHaveTextContent('现在咨询的人有些多')
    expect(screen.getByRole('textbox')).toHaveValue('我的牙疼')
    fireEvent.click(screen.getByRole('button',{name:'发送给小安'}))
    fireEvent.click(await screen.findByRole('button',{name:'停止等待'}))
    expect(await screen.findByRole('alert')).toHaveTextContent('已停止等待')
    expect(screen.getByRole('textbox')).toHaveValue('我的牙疼')
    expect(screen.queryByText(/由 DeepSeek/)).not.toBeInTheDocument()
  })

  it('only includes a scan when explicitly enabled and clears history when context changes',async()=>{
    const scanId='00000000-0000-4000-8000-000000000001'
    vi.mocked(api.scans).mockResolvedValue({items:[{scan_id:scanId,created_at:'2026-11-14T00:00:00Z',updated_at:'2026-11-14T00:00:00Z',status:'draft',source_types:[],metadata:{}}]})
    const chat = vi.spyOn(api,'assistantChat').mockResolvedValue({reply:'我们一起了解这份检查的文字结果。',provider:'DeepSeek',model:'deepseek-flash',context_included:true})
    show();await screen.findByText('可以聊聊')
    fireEvent.click(screen.getByText('结合检查解释'))
    await screen.findByRole('option',{name:/00000000/})
    fireEvent.change(screen.getByRole('combobox',{name:'选择检查'}),{target:{value:scanId}})
    fireEvent.click(screen.getByRole('checkbox',{name:'结合这份检查的文字摘要'}))
    question('请解释检查');agree();fireEvent.click(screen.getByRole('button',{name:'发送给小安'}))
    await screen.findByText('我们一起了解这份检查的文字结果。')
    expect(chat.mock.calls[0][1]).toBe(scanId)
    fireEvent.click(screen.getByRole('checkbox',{name:'结合这份检查的文字摘要'}))
    expect(screen.queryByText('我们一起了解这份检查的文字结果。')).not.toBeInTheDocument()
    expect(screen.getByRole('checkbox',{name:/我同意/})).not.toBeChecked()
  })
})
