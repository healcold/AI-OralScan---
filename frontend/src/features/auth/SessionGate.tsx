import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { ScanLine } from 'lucide-react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import RegistrationForm from './RegistrationForm'
import { api, ApiError, type Account } from '../../lib/api'
import { Button } from '../../components/ui/button'
import './auth.css'

type State = { phase: 'loading' | 'signed-out' | 'unavailable' } | { phase: 'ready'; account: Account }

export default function SessionGate({ children }: {
  children: (account: Account, signOut: () => Promise<void>) => ReactNode
}) {
  const location = useLocation()
  const navigate = useNavigate()
  const registration = location.pathname === '/register'
  const [state, setState] = useState<State>({ phase: 'loading' })
  const [revision, setRevision] = useState(0)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let live = true
    const expired = () => { setPassword(''); setState({ phase: 'signed-out' }) }
    const restored = (event: PageTransitionEvent) => {
      if (event.persisted) { setState({ phase: 'loading' }); setRevision(current => current + 1) }
    }
    window.addEventListener('oralscan:session-expired', expired)
    window.addEventListener('pageshow', restored)
    api.account().then(account => {
      if (live) setState({ phase: 'ready', account })
    }).catch(cause => {
      if (live) setState({ phase: cause instanceof ApiError && cause.status === 401 ? 'signed-out' : 'unavailable' })
    })
    return () => {
      live = false
      window.removeEventListener('oralscan:session-expired', expired)
      window.removeEventListener('pageshow', restored)
    }
  }, [revision])

  useEffect(() => {
    setError('')
    setPassword('')
    const phone = (location.state as {phone?: string} | null)?.phone
    if (phone) setUsername(phone)
  }, [location.pathname, location.state])

  async function enter(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    setBusy(true); setError('')
    try {
      const account = await api.login(username.trim(), password)
      setPassword(''); setState({ phase: 'ready', account })
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '暂时无法连接，请稍后再试。')
    } finally { setBusy(false) }
  }

  async function signOut() {
    await api.logout()
    setError(''); setPassword(''); setUsername(''); setState({ phase: 'signed-out' }); navigate('/login', {replace: true})
  }

  if (state.phase === 'ready') return children(state.account, signOut)
  return <main className="auth-screen">
    <section className="auth-card" aria-labelledby="login-title">
      <div className="auth-brand"><ScanLine size={24}/> AI OralScan</div>
      <h1 id="login-title">{registration ? '注册患者账号' : '登录口腔检查工作台'}</h1>
      <p>{registration ? '请用自己的中国大陆手机号注册，并自行设置密码。' : '使用手机号或已有账号登录，查看自己的检查、照片和报告。'}</p>
      {state.phase === 'loading' ? <p role="status">正在确认登录状态…</p>
        : state.phase === 'unavailable' ? <div role="alert">暂时无法连接工作台。<Button variant="outline" onClick={() => { setState({ phase: 'loading' }); setRevision(current => current + 1) }}>重试</Button></div>
        : registration ? <RegistrationForm/>
        : <><form onSubmit={event => void enter(event)}>
          <label htmlFor="login-username">账号</label>
          <input id="login-username" value={username} onChange={event => setUsername(event.target.value)} autoComplete="username" autoCapitalize="none" required maxLength={64}/>
          <label htmlFor="login-password">密码</label>
          <input id="login-password" type="password" value={password} onChange={event => setPassword(event.target.value)} autoComplete="current-password" required maxLength={128}/>
          {error && <p role="alert">{error}</p>}
          <Button type="submit" disabled={busy || !username.trim() || !password}>{busy ? '正在登录…' : '登录'}</Button>
        </form><p className="auth-note">没有账号？<Link to="/register">注册账号</Link></p></>}
    </section>
  </main>
}
