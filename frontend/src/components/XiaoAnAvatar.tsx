import './xiaoan-avatar.css'

export default function XiaoAnAvatar({ thinking = false }: { thinking?: boolean }) {
  return <span className={`xiaoan-avatar ${thinking ? 'is-thinking' : ''}`} role="img" aria-label={thinking ? '小安正在整理回答' : '小安 AI 助理'}>
    <svg viewBox="0 0 80 80" fill="none" aria-hidden="true">
      <circle cx="40" cy="40" r="37" fill="#E7F3F2"/>
      <path d="M23 25c5-5 10-3 17-1 7-2 12-4 17 1 8 9 1 22-2 31-2 8-7 7-10 0l-3-7c-1-2-3-2-4 0l-3 7c-3 7-8 8-10 0-3-9-10-22-2-31Z" fill="white" stroke="#438E94" strokeWidth="2.5"/>
      <g className="xiaoan-eyes" stroke="#306D78" strokeWidth="3.5" strokeLinecap="round"><path d="M31 36v3M49 36v3"/></g>
      <path d="M35 43q5 5 10 0" stroke="#438E94" strokeWidth="2.3" strokeLinecap="round"/>
      <circle cx="28" cy="43" r="3" fill="#F4C8BC"/><circle cx="52" cy="43" r="3" fill="#F4C8BC"/>
      <path d="m61 14 1.5 4.5L67 20l-4.5 1.5L61 26l-1.5-4.5L55 20l4.5-1.5L61 14Z" fill="#7AB8B5"/>
    </svg>
    {thinking && <span className="xiaoan-thinking-dots" aria-hidden="true"><i/><i/><i/></span>}
  </span>
}
