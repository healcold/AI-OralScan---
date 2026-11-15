import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { api } from '../../lib/api'
import SessionGate from './SessionGate'

afterEach(() => vi.restoreAllMocks())

it('shows a failed logout and allows a successful retry', async () => {
  vi.spyOn(api, 'account').mockResolvedValue({ username: 'patient', role: 'patient' })
  vi.spyOn(api, 'logout').mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(undefined)
  render(<MemoryRouter><SessionGate>{(_account, logout) => <button onClick={() => void logout()}>退出</button>}</SessionGate></MemoryRouter>)
  fireEvent.click(await screen.findByText('退出'))
  expect(await screen.findByRole('alert')).toHaveTextContent('退出登录未完成')
  fireEvent.click(screen.getByText('退出'))
  expect(await screen.findByLabelText('密码')).toBeInTheDocument()
})
