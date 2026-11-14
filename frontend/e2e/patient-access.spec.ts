import { expect, test, type Page } from '@playwright/test'

async function login(page: Page, suffix: 'a' | 'b') {
  await page.getByLabel('账号', { exact: true }).fill('test-patient-' + suffix)
  await page.getByLabel('密码', { exact: true }).fill('fixture-only-patient-' + suffix)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('button', { name: '退出登录' })).toBeVisible()
}

test('patients can register and reset their password using Chinese recovery text', async ({ page }) => {
  await page.goto('/login')
  await page.getByRole('link', { name: '注册账号' }).click()
  await expect(page).toHaveURL(/\/register$/)
  const phone = '13900006123'
  const password = 'demo!6'
  const prompt = '我记得课堂上的哪件事？'
  const answer = '松鼠'
  await page.getByLabel('手机号', { exact: true }).fill(phone)
  await page.getByLabel('设置密码').fill(password)
  await page.getByLabel('找回提示', { exact: true }).selectOption('custom')
  await page.getByLabel('自定义提示').fill(prompt)
  const recoveryAnswer = page.getByLabel('找回答案')
  await expect(recoveryAnswer).toHaveAttribute('type', 'text')
  await recoveryAnswer.focus()
  await page.keyboard.insertText(answer)
  await page.getByRole('button', { name: '隐藏答案' }).click()
  await expect(recoveryAnswer).toHaveAttribute('type', 'password')
  await page.getByRole('button', { name: '显示答案' }).click()
  await expect(recoveryAnswer).toHaveValue(answer)
  const confirmation = page.getByLabel('确认密码')
  await confirmation.fill('different')
  const create = page.getByRole('button', { name: '创建账号' })
  await create.click()
  await expect(page.getByRole('alert')).toHaveText('两次输入的密码不一致，请重新确认。')
  await confirmation.fill(password)
  await create.click()
  await expect(page.getByRole('heading', { name: '账号创建成功' })).toBeVisible()
  expect((await page.request.get('/api/auth/me')).status()).toBe(401)
  await page.getByRole('link', { name: '返回登录' }).click()
  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByLabel('账号', { exact: true })).toHaveValue(phone)
  const loginPassword = page.getByLabel('密码', { exact: true })
  await expect(loginPassword).toHaveValue('')
  await loginPassword.fill(password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('heading', { name: '我的检查' })).toBeVisible()
  await expect(page.getByText('暂无匹配的检查。')).toBeVisible()

  await page.getByRole('button', { name: '退出登录' }).click()
  await page.getByRole('link', { name: '忘记密码？' }).click()
  await expect(page).toHaveURL(/\/forgot-password$/)
  await page.getByLabel('手机号', { exact: true }).fill(phone)
  await page.getByLabel('找回提示', { exact: true }).selectOption('custom')
  const resetPrompt = page.getByLabel('自定义提示')
  await resetPrompt.fill('与注册不同的中文提示')
  const resetAnswer = page.getByLabel('找回答案')
  await expect(resetAnswer).toHaveAttribute('type', 'text')
  await resetAnswer.focus()
  await page.keyboard.insertText(answer)
  const newPassword = 'new-fixture-password'
  await page.getByLabel('新密码（至少 6 个字符）').fill(newPassword)
  await page.getByLabel('确认新密码').fill(newPassword)
  await page.getByRole('button', { name: '重设密码' }).click()
  await expect(page.getByRole('alert')).toContainText('无法核对找回信息')
  await resetPrompt.fill(prompt)
  await page.getByRole('button', { name: '重设密码' }).click()
  await expect(page.getByRole('heading', { name: '密码已重设' })).toBeVisible()
  await page.getByRole('link', { name: '返回登录' }).click()
  await expect(page.getByLabel('账号', { exact: true })).toHaveValue(phone)
  await page.getByLabel('密码', { exact: true }).fill(newPassword)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('heading', { name: '我的检查' })).toBeVisible()
})

test('patients only see their own checks and copied links remain private', async ({ page: a, browser }) => {
  // Public HTTP does not expose randomUUID. Exercise upload and persistence
  // with that API absent, even though the test server uses trusted localhost.
  await a.addInitScript(() => {
    Object.defineProperty(globalThis.crypto, 'randomUUID', { value: undefined, configurable: true })
  })
  await a.goto('/scan')
  await expect(a.getByRole('heading', { name: '登录口腔检查工作台' })).toBeVisible()
  await expect(a.locator('input[type=file]')).toHaveCount(0)
  await login(a, 'a')
  const buffer = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAACAAAAAYCAIAAAAUMWhjAAAANElEQVR4nGOUjJrGQEvARFPTGUYtIAKMxgFBMBpEBMFoEBEEo0FEEIwGEUEwGkQEAc2DCABLNwE5itR8ggAAAABJRU5ErkJggg==', 'base64')
  await a.locator('input[type=file]').setInputFiles({ name: 'patient-a-synthetic.png', mimeType: 'image/png', buffer })
  await expect(a.getByAltText('预览 patient-a-synthetic.png')).toBeVisible()
  await a.getByRole('button', { name: '确认并保存检查' }).click()
  const scan = (await a.getByText(/检查记录：.*全部图像已保存/).innerText()).match(/[0-9a-f-]{36}/)![0]
  await a.goto('/history')
  await expect(a.getByText(scan, { exact: true })).toBeVisible()
  const { items } = await (await a.request.get('/api/scans/' + scan + '/assets')).json()
  const imageUrl = '/api/scans/' + scan + '/assets/' + items[0].asset_id + '/content'

  await a.goto('/reports?scan=' + scan)
  const created = a.waitForResponse(r => r.url().endsWith('/reports') && r.request().method() === 'POST')
  await a.getByRole('button', { name: '生成 PDF' }).click()
  const report = await created
  expect(report.status()).toBe(201)
  const { download_url } = await report.json()
  expect((await a.request.get(download_url)).ok()).toBeTruthy()
  expect((await a.request.get(imageUrl)).ok()).toBeTruthy()

  const contextB = await browser.newContext({ baseURL: test.info().project.use.baseURL, viewport: {width: 390, height: 844} })
  try {
    const b = await contextB.newPage()
    await b.goto('/history')
    await login(b, 'b')
    await expect(b.getByRole('heading', { name: '我的检查' })).toBeVisible()
    await expect(b.getByText('暂无匹配的检查。')).toBeVisible()
    await expect(b.getByText(scan, { exact: true })).toHaveCount(0)
    await expect(b.getByRole('link', { name: '模型管理' })).toHaveCount(0)
    await b.goto('/assistant?scan=' + scan)
    await expect(b.getByText('还没有保存的检查，也可以直接聊聊。')).toBeVisible()
    await expect(b.getByRole('combobox', { name: '选择检查' }).locator('option')).toHaveCount(1)
    expect((await b.goto(download_url))?.status()).toBe(404)
    expect((await b.goto(imageUrl))?.status()).toBe(404)
    expect((await b.request.delete('/api/scans/' + scan)).status()).toBe(404)
  } finally { await contextB.close() }

  await a.getByRole('button', { name: '退出登录' }).click()
  await expect(a.getByRole('heading', { name: '登录口腔检查工作台' })).toBeVisible()
  expect((await a.request.get(download_url)).status()).toBe(401)
})
