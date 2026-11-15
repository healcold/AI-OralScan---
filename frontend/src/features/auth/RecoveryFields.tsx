import { useState } from 'react'
import { recoveryQuestions } from './recovery'

export default function RecoveryFields({ setup, question, answer, customPrompt, onQuestion, onAnswer, onCustomPrompt, busy }: {
  setup?: boolean
  question: string
  answer: string
  customPrompt: string
  onQuestion: (value: string) => void
  onAnswer: (value: string) => void
  onCustomPrompt: (value: string) => void
  busy: boolean
}) {
  // Password inputs can disable Chinese IME on some Windows/browser setups.
  const [visible, setVisible] = useState(true)
  return <fieldset className="auth-recovery">
    <legend>{setup ? '设置密码找回方式' : '填写注册时的找回信息'}</legend>
    {setup && <p>选一个容易记住的提示，再填一个只有你知道的答案。请勿使用真实姓名、生日或手机号。</p>}
    <label htmlFor="recovery-question">找回提示</label>
    <select id="recovery-question" value={question} onChange={event => onQuestion(event.target.value)} required disabled={busy}>
      <option value="">请选择提示</option>
      {recoveryQuestions.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
    </select>
    {question === 'custom' && <>
      <label htmlFor="recovery-custom">自定义提示</label>
      <input id="recovery-custom" type="text" inputMode="text" autoComplete="off" maxLength={60} required disabled={busy}
        value={customPrompt} onChange={event => onCustomPrompt(event.target.value)}
        placeholder={setup ? '例如：我记得课堂上的哪件事？' : '请输入注册时填写的提示'}/>
      {setup && <p className="auth-hint">可以用中文。重设密码时需要重新输入同一个提示。</p>}
    </>}
    <label htmlFor="recovery-answer">找回答案</label>
    <p id="recovery-answer-hint" className="auth-hint">支持中文和英文。输入后可点「隐藏答案」。</p>
    <div className="auth-answer-row">
      <input id="recovery-answer" type={visible ? 'text' : 'password'} inputMode="text" autoComplete="off" autoCapitalize="none"
        spellCheck={false} aria-describedby="recovery-answer-hint" value={answer} onChange={event => onAnswer(event.target.value)}
        required disabled={busy}/>
      <button type="button" aria-controls="recovery-answer" onClick={() => setVisible(current => !current)}>{visible ? '隐藏答案' : '显示答案'}</button>
    </div>
  </fieldset>
}
