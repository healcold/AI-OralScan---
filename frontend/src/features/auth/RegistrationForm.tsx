import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '../../components/ui/button'
import { api, ApiError } from '../../lib/api'
import RecoveryFields from './RecoveryFields'
import { recoveryError } from './recovery'

export default function RegistrationForm() {
  const [phone, setPhone] = useState('')
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [question, setQuestion] = useState('')
  const [customPrompt, setCustomPrompt] = useState('')
  const [answer, setAnswer] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [registered, setRegistered] = useState(false)
  const success = useRef<HTMLHeadingElement>(null)

  useEffect(() => { if (registered) success.current?.focus() }, [registered])

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    const number = phone.trim()
    const invalid = recoveryError(number, password, confirmation, question, answer.trim(), customPrompt)
    if (invalid) { setError(invalid); return }
    setBusy(true); setError('')
    try {
      await api.register(number, password, question, answer.trim(), question === 'custom' ? customPrompt.trim() : '')
      setPhone(number); setPassword(''); setConfirmation(''); setAnswer(''); setCustomPrompt(''); setRegistered(true)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '暂时无法注册，请检查连接后再试。')
    } finally { setBusy(false) }
  }

  if (registered) return <div className="auth-success">
    <h2 ref={success} tabIndex={-1}>账号创建成功</h2>
    <p>请返回登录页面，使用刚注册的手机号和密码登录。</p>
    <Button asChild><Link to="/login" state={{phone}}>返回登录</Link></Button>
  </div>

  return <>
    <form noValidate onSubmit={event => void submit(event)}>
      <label htmlFor="register-phone">手机号</label>
      <input id="register-phone" type="tel" inputMode="numeric" autoComplete="username" value={phone}
        onChange={event => setPhone(event.target.value)} required maxLength={32} placeholder="请输入 11 位手机号" disabled={busy}/>
      <label htmlFor="register-password">设置密码</label>
      <input id="register-password" type="password" autoComplete="new-password" value={password}
        onChange={event => setPassword(event.target.value)} required minLength={6} maxLength={128} disabled={busy} aria-describedby="register-password-hint"/>
      <p id="register-password-hint" className="auth-hint">至少 6 个字符，建议用较长且不与其他网站重复的密码。</p>
      <label htmlFor="register-confirm">确认密码</label>
      <input id="register-confirm" type="password" autoComplete="new-password" value={confirmation}
        onChange={event => setConfirmation(event.target.value)} required maxLength={128} disabled={busy}/>
      <RecoveryFields setup question={question} answer={answer} customPrompt={customPrompt} onQuestion={setQuestion}
        onAnswer={setAnswer} onCustomPrompt={setCustomPrompt} busy={busy}/>
      {error && <p role="alert">{error}</p>}
      <Button type="submit" disabled={busy}>{busy ? '正在注册…' : '创建账号'}</Button>
    </form>
    <p className="auth-note">已有账号？<Link to="/login">返回登录</Link></p>
  </>
}
