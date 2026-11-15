import { afterEach, expect, it, vi } from 'vitest'
import { api } from './api'

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

it('releases stalled authentication requests so the user can retry', async () => {
  vi.useFakeTimers()
  vi.stubGlobal('fetch', vi.fn((_url, init: RequestInit) => new Promise((_resolve, reject) => {
    init.signal!.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
  })))
  const result = expect(api.account()).rejects.toMatchObject({ code: 'REQUEST_TIMEOUT' })
  await vi.advanceTimersByTimeAsync(15_000)
  await result
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok: true, status: 200, json: async () => ({username: 'retry', role: 'patient'})}))
  await expect(api.account()).resolves.toMatchObject({username: 'retry'})
  expect(vi.getTimerCount()).toBe(0)
})
