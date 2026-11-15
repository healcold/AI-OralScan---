import { expect, test, type Page } from '@playwright/test'

const imageName = 'synthetic-image-with-a-long-file-name-for-narrow-screens.png'
const image = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAACAAAAAYCAIAAAAUMWhjAAAANElEQVR4nGOUjJrGQEvARFPTGUYtIAKMxgFBMBpEBMFoEBEEo0FEEIwGEUEwGkQEAc2DCABLNwE5itR8ggAAAABJRU5ErkJggg==', 'base64')
const viewportSizes = [[320, 568], [390, 844], [430, 932], [768, 1024], [844, 390], [1366, 768], [1920, 1080]]
const firstLine = '这是长回复的开头。'
const lastLine = '这是长回复的结尾。'
const reply = [firstLine, ...Array.from({ length: 18 }, (_, i) => (
  `${i + 1}. 这是一段用于检查页面排版的示例文字。请阅读完这一段，再向下阅读其余内容。`
)), lastLine].join('\n\n')

async function expectNoHorizontalScroll(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1)
}

test('patients can read results, reports and long assistant replies across screen sizes', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.route('**/api/assistant/status', route => route.fulfill({
    json: { configured: true, provider: '测试模型', model: 'responsive-fixture', message: '' },
  }))
  await page.route('**/api/assistant/chat', route => route.fulfill({
    json: { reply, provider: '测试模型', model: 'responsive-fixture', context_included: false },
  }))
  await page.goto('/scan')
  await page.getByLabel('账号', { exact: true }).fill('test-patient-a')
  await page.getByLabel('密码', { exact: true }).fill('fixture-only-patient-a')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await page.locator('input[type=file]').setInputFiles({ name: imageName, mimeType: 'image/png', buffer: image })
  await page.getByRole('button', { name: '确认并保存检查' }).click()
  const saved = page.getByText(/检查记录：.*全部图像已保存/)
  await expect(saved).toBeVisible()
  const scan = (await saved.innerText()).match(/[0-9a-f-]{36}/)![0]

  for (const [width, height] of viewportSizes) {
    await test.step(`${width} × ${height}`, async () => {
      await page.setViewportSize({ width, height })
      await page.goto('/history')
      await page.getByRole('button', { name: '打开检查' }).first().click()
      await expect(page.getByRole('heading', { name: '原始资产' })).toBeVisible()
      await expect(page.locator('.record-detail')).toBeInViewport()
      await expectNoHorizontalScroll(page)

      await page.goto('/analysis?scan=' + scan)
      const xray = page.getByRole('img', { name: '原图 ' + imageName })
      const guide = page.getByRole('region', { name: '小安结果解读' })
      await expect(xray).toBeVisible()
      await expect.poll(() => xray.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0)
      expect((await guide.boundingBox())!.y).toBeGreaterThan((await xray.boundingBox())!.y)
      await expectNoHorizontalScroll(page)

      const shortcut = page.getByRole('link', { name: '问小安' })
      await expect(shortcut).toBeInViewport()
      expect(await shortcut.evaluate(link => Boolean(link.closest('.topbar')))).toBe(true)
      await shortcut.click()
      const prompt = page.getByRole('textbox', { name: '想和小安说的话' })
      await prompt.fill('测试长回复阅读')
      await page.getByText(/我同意将本次对话/).click()
      await page.getByRole('button', { name: '发送给小安' }).click()
      const answer = page.locator('.assistant-message.assistant > div')
      await expect(answer).toHaveText(reply)
      expect(await answer.evaluate(element => {
        const range = document.createRange()
        range.setStart(element.firstChild!, 0)
        range.setEnd(element.firstChild!, 5)
        const first = range.getBoundingClientRect()
        const log = element.closest('[role=log]')!.getBoundingClientRect()
        return first.top >= Math.max(0, log.top) && first.bottom <= Math.min(innerHeight, log.bottom)
      })).toBe(true)
      if (width === 390 || width === 1366) {
        await page.screenshot({ path: test.info().outputPath(`assistant-${width}.png`) })
      }
      if (width <= 850 || height <= 680) {
        expect(await page.getByRole('log').evaluate(log => getComputedStyle(log).overflowY)).toBe('visible')
        await page.getByRole('button', { name: '继续提问' }).click()
        await expect(prompt).toBeFocused()
      }
      await expectNoHorizontalScroll(page)

      await page.getByRole('link', { name: '查看这次检查的报告' }).click()
      const pdf = page.getByRole('button', { name: '生成 PDF' })
      await expect(pdf).toBeEnabled()
      await pdf.scrollIntoViewIfNeeded()
      await expect(pdf).toBeInViewport()
      if (width === 320) {
        await pdf.click()
        const download = page.getByRole('link', { name: '下载 PDF' })
        await expect(download).toBeVisible()
        expect((await page.request.get((await download.getAttribute('href'))!)).ok()).toBe(true)
      }
      await expectNoHorizontalScroll(page)
    })
  }
})
