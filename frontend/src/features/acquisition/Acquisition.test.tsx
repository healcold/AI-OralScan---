import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import Acquisition from './Acquisition'

describe('image and camera acquisition', () => {
  afterEach(()=>vi.unstubAllGlobals())
  it('rejects unsupported files with a clear message', async () => {
    const {container}=render(<Acquisition source="upload"/>); const file=new File(['bad'],'bad.txt',{type:'text/plain'})
    fireEvent.change(container.querySelector('input[type=file]')!,{target:{files:[file]}})
    expect(await screen.findByRole('alert')).toHaveTextContent('请选择 JPG、PNG 或 WebP')
  })
  it('shows camera permission denial', async () => {
    vi.stubGlobal('navigator',{mediaDevices:{getUserMedia:vi.fn().mockRejectedValue(new DOMException('denied','NotAllowedError')),addEventListener:vi.fn(),removeEventListener:vi.fn()}})
    render(<Acquisition source="camera"/>); fireEvent.click(screen.getByRole('button',{name:'开启摄像头'}))
    expect(await screen.findByRole('alert')).toHaveTextContent('摄像头权限被拒绝')
  })
  it('releases the camera when leaving the workspace', async () => {
    const stop=vi.fn(); const track={stop,addEventListener:vi.fn()}; const stream={getTracks:()=>[track],getVideoTracks:()=>[track]}
    vi.stubGlobal('navigator',{mediaDevices:{getUserMedia:vi.fn().mockResolvedValue(stream),enumerateDevices:vi.fn().mockResolvedValue([]),addEventListener:vi.fn(),removeEventListener:vi.fn()}})
    const play=vi.spyOn(HTMLMediaElement.prototype,'play').mockResolvedValue(undefined)
    const view=render(<Acquisition source="camera"/>);fireEvent.click(screen.getByRole('button',{name:'开启摄像头'}))
    await waitFor(()=>expect(screen.getByRole('button',{name:'停止采集'})).toBeEnabled())
    view.unmount();expect(stop).toHaveBeenCalledOnce();play.mockRestore()
  })
})

