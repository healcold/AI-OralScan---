export const recoveryQuestions = [
  { id: 'father', label: '想到父亲时，我会记起什么？' },
  { id: 'mother', label: '想到母亲时，我会记起什么？' },
  { id: 'teacher', label: '想到我敬重的老师时，我会记起什么？' },
  { id: 'custom', label: '自定义提示（可填中文）' },
] as const

export function recoveryError(phone: string, password: string, confirmation: string, question: string, answer: string, customPrompt: string) {
  if (!/^1[3-9][0-9]{9}$/.test(phone)) return '请输入有效的中国大陆 11 位手机号。'
  if (Array.from(password).length < 6 || !password.trim()) return '密码至少 6 个字符，且不能全部为空白。'
  if (password !== confirmation) return '两次输入的密码不一致，请重新确认。'
  if (!question) return '请选择一个找回提示。'
  if (!answer) return '请填写找回答案。'
  if (question === 'custom') {
    const prompt = customPrompt.trim().normalize('NFC')
    if (!prompt) return '请填写自定义提示，可输入中文。'
    if (prompt === answer.normalize('NFC') || prompt.includes(phone)) return '请勿在提示里填写答案或手机号。'
  }
  if (answer === password.trim() || answer.includes(phone)) {
    return '找回答案不能和密码相同，也不要包含手机号。'
  }
  return ''
}
