import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '../../components/ui/button'
import { api, ApiError } from '../../lib/api'
import RecoveryFields from './RecoveryFields'
import { recoveryError } from './recovery'

export default function ResetPasswordForm({ initialPhone }: { initialPhone: string }) {
  const [phone, setPhone] = useState(initialPhone)
  const [question, setQuestion] = useState('')
  const [customPrompt, setCustomPrompt] = useState('')
  const [answer, setAnswer] = useState('')
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [complete, setComplete] = useState(false)
  const success = useRef<HTMLHeadingElement>(null)

  useEffect(() => { if (complete) success.current?.focus() }, [complete])

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    const number = phone.trim()
    const invalid = recoveryError(number, password, confirmation, question, answer.trim(), customPrompt)
    if (invalid) { setError(invalid); return }
    setBusy(true); setError('')
    try {
      await api.resetPassword(number, password, question, answer.trim(), question === 'custom' ? customPrompt.trim() : '')
      setPhone(number); setAnswer(''); setCustomPrompt(''); setPassword(''); setConfirmation(''); setComplete(true)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '暂时无法重设密码，请稍后再试。')
    } finally { setBusy(false) }
  }

  if (complete) return <div className="auth-success">
    <h2 ref={success} tabIndex={-1}>密码已重设</h2>
    <p>请用新密码重新登录。此账号此前的登录已失效。</p>
    <Button asChild><Link to="/login" state={{phone}}>返回登录</Link></Button>
  </div>

  return <>
    <form noValidate onSubmit={event => void submit(event)}>
      <label htmlFor="reset-phone">手机号</label>
      <input id="reset-phone" type="tel" inputMode="numeric" autoComplete="username" value={phone} maxLength={32} required
        onChange={event => setPhone(event.target.value)} disabled={busy}/>
      <RecoveryFields question={question} answer={answer} customPrompt={customPrompt} onQuestion={setQuestion}
        onAnswer={setAnswer} onCustomPrompt={setCustomPrompt} busy={busy}/>
      <label htmlFor="reset-password">新密码（至少 6 个字符）</label>
      <input id="reset-password" type="password" autoComplete="new-password" value={password} maxLength={128} required
        onChange={event => setPassword(event.target.value)} disabled={busy}/>
      <label htmlFor="reset-confirm">确认新密码</label>
      <input id="reset-confirm" type="password" autoComplete="new-password" value={confirmation} maxLength={128} required
        onChange={event => setConfirmation(event.target.value)} disabled={busy}/>
      {error && <p role="alert">{error}</p>}
      <Button type="submit" disabled={busy}>{busy ? '正在核对…' : '重设密码'}</Button>
    </form>
    <p className="auth-note"><Link to="/login">返回登录</Link></p>
  </>
}
