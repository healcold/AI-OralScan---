import { fileURLToPath } from 'node:url'
import { test, expect, type Page } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  const response = await page.request.post('/api/auth/login', {data: {username: 'test-admin', password: 'fixture-only-workspace-admin'}})
  expect(response.ok()).toBeTruthy()
})

const fixture = (name: string) => fileURLToPath(new URL(`../../backend/tests/fixtures/meshes/${name}`, import.meta.url))
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAACAAAAAYCAIAAAAUMWhjAAAANElEQVR4nGOUjJrGQEvARFPTGUYtIAKMxgFBMBpEBMFoEBEEo0FEEIwGEUEwGkQEAc2DCABLNwE5itR8ggAAAABJRU5ErkJggg==','base64')
const image = {name:'synthetic.png',mimeType:'image/png',buffer:png}

test('Chinese navigation and acquisition remain usable on mobile and desktop', async ({page}) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.setViewportSize({width: 1440, height: 1000})
  await page.goto('/scan')
  await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN')
  await expect(page.getByRole('heading', {level: 1})).toHaveText('扫描工作台')
  await page.screenshot({path: '../../outputs/oralscan-zh-desktop.png', fullPage: true})
  await page.setViewportSize({width: 390, height: 844})
  for (const name of ['分析', '报告', '我的检查', '模型管理', '设备管理', '设置', '总览', '扫描工作台']) {
    await page.getByRole('button', {name: '打开导航'}).click()
    await page.getByRole('navigation', {name: '主导航'}).getByRole('link', {name, exact: true}).click()
    await expect(page.getByRole('heading', {level: 1})).toHaveText(name === '总览' ? '工作台总览' : name)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
  await page.getByRole('tab', {name: /导入三维模型/}).click()
  await expect(page.getByLabel('模型单位')).toHaveValue('unknown')
  await page.getByRole('tab', {name: /上传图片/}).click()
  await page.locator('input[type=file]').setInputFiles(image)
  await expect(page.getByAltText('预览 synthetic.png')).toBeVisible()
  await page.screenshot({path: '../../outputs/oralscan-zh-mobile.png', fullPage: true})
  expect(errors).toEqual([])
})

async function saveFrames(page: Page) {
  await page.getByRole('button',{name:'确认并保存检查'}).click()
  const saved = page.getByText(/检查记录：.*全部图像已保存/)
  await expect(saved).toBeVisible()
  return (await saved.innerText()).match(/[0-9a-f-]{36}/)![0]
}

async function analyzeImage(page: Page, scan: string) {
  await page.goto(`/analysis?scan=${scan}`)
  await page.getByRole('button',{name:'分析图像'}).click()
  await expect(page.getByText('演示（DEMO） · 最近任务：已完成')).toBeVisible()
  const overlay = page.getByLabel('检测结果叠加层')
  await expect(overlay.locator('rect')).toHaveCount(1)
  await expect(overlay.locator('image')).toHaveCount(1)
}

async function attachMesh(page: Page, name: string, scan?: string) {
  await page.goto('/scan?mode=3d')
  if (scan) await page.getByLabel('检查记录').selectOption(scan)
  await page.locator('input[type=file]').setInputFiles(fixture(name))
  await page.getByRole('button',{name:'验证并导入'}).click()
  const saved = page.getByText(/已保存到检查/)
  await expect(saved).toBeVisible()
  await expect(page.getByRole('button',{name:'线框视图'})).toBeEnabled()
  await page.getByRole('button',{name:'线框视图'}).click()
  await expect(page.getByRole('button',{name:'实体视图'})).toHaveAttribute('aria-pressed','true')
  await page.getByRole('button',{name:'重置视角'}).click()
  return (await saved.innerText()).match(/[0-9a-f-]{36}/)![0]
}

async function analyzeMesh(page: Page, scan: string) {
  await page.goto(`/analysis?tab=3d&scan=${scan}`)
  await page.getByRole('button',{name:'分析几何'}).click()
  await expect(page.getByText('分析状态：已完成')).toBeVisible()
}

async function report(page: Page, scan: string, format: 'PDF'|'JSON') {
  await page.goto(`/reports?scan=${scan}`)
  const generated = page.waitForResponse(response => response.url().endsWith(`/scans/${scan}/reports`) && response.request().method() === 'POST')
  await page.getByRole('button',{name:`生成 ${format}`}).click()
  const response = await generated
  expect(response.status()).toBe(201)
  const {download_url} = await response.json()
  const download = page.locator(`a[href="${download_url}"]`)
  await expect(download).toHaveText(`下载 ${format}`)
  const content = await page.request.get(download_url)
  expect(content.ok()).toBeTruthy()
  if (format === 'PDF') {
    expect((await content.body()).subarray(0,5).toString()).toBe('%PDF-')
    return null
  }
  const snapshot = await content.json()
  expect(snapshot.disclaimer).toContain('不构成临床诊断')
  expect(snapshot.assets.every((asset:{preview:{status:string}}) => asset.preview.status === 'available')).toBe(true)
  return snapshot
}

test('Image upload, preservation, synthetic ONNX analysis and PDF', async ({page}) => {
  await page.goto('/scan')
  await page.locator('input[type=file]').setInputFiles(image)
  await expect(page.getByAltText('预览 synthetic.png')).toBeVisible()
  const scan = await saveFrames(page)
  const {items} = await (await page.request.get(`/api/scans/${scan}/assets`)).json()
  const original = await page.request.get(`/api/scans/${scan}/assets/${items[0].asset_id}/content`)
  expect(await original.body()).toEqual(png)
  await analyzeImage(page,scan)
  await report(page,scan,'PDF')
})

test('Camera stream, two captures, synthetic ONNX analysis and JSON', async ({page}) => {
  // A browser MediaStream from a canvas covers the capture path without claiming physical camera access.
  await page.addInitScript(() => {
    Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:{
      getUserMedia: async () => {
        const canvas = document.createElement('canvas')
        canvas.width=320
        canvas.height=240
        const ctx=canvas.getContext('2d')!
        ctx.fillStyle='#15748b'
        ctx.fillRect(0,0,320,240)
        return canvas.captureStream(10)
      },
      enumerateDevices: async () => [{kind:'videoinput',deviceId:'fixture',label:'Fixture camera'}],
    }})
  })
  await page.goto('/scan?mode=camera')
  await page.getByRole('button',{name:'开启摄像头'}).click()
  await page.waitForFunction(() => !!document.querySelector('video')?.videoWidth)
  await page.getByRole('button',{name:'拍摄图像'}).click()
  await page.getByRole('button',{name:'拍摄图像'}).click()
  await expect(page.locator('.frame')).toHaveCount(2)
  const scan = await saveFrames(page)
  expect(await page.locator('video').evaluate(video => (video as HTMLVideoElement).srcObject === null)).toBe(true)
  await analyzeImage(page,scan)
  const snapshot = await report(page,scan,'JSON')
  expect(snapshot.is_demo).toBe(true)
  expect(snapshot.assets.map((asset:{source_type:string}) => asset.source_type)).toEqual(['camera','camera'])
  expect(snapshot.findings[0].model_version).toBe('demo-v1')
})

test('3D import through viewer, geometry analysis and PDF', async ({page}) => {
  const scan = await attachMesh(page,'tetra_binary.stl')
  await analyzeMesh(page,scan)
  await expect(page.getByRole('heading',{name:'网格分析结果'})).toBeVisible()
  await report(page,scan,'PDF')
})

test('Mixed scan, separate pipelines, unified findings and saved report', async ({page}) => {
  await page.goto('/scan')
  await page.locator('input[type=file]').setInputFiles(image)
  const scan = await saveFrames(page)
  await attachMesh(page,'open.obj',scan)
  await analyzeImage(page,scan)
  await analyzeMesh(page,scan)
  await page.goto(`/analysis?tab=unified&scan=${scan}`)
  await expect(page.getByText('synthetic.png',{exact:true})).toBeVisible()
  await expect(page.getByText('open.obj',{exact:true})).toBeVisible()
  const snapshot = await report(page,scan,'JSON')
  expect(snapshot.assets).toHaveLength(2)
  expect(new Set(snapshot.findings.map((finding:{modality:string})=>finding.modality))).toEqual(new Set(['image_2d','mesh_3d']))
  await page.goto(`/history?scan=${scan}`)
  await expect(page.getByRole('link',{name:'下载 JSON'})).toBeVisible()
  await page.reload()
  await expect(page.getByRole('link',{name:'下载 JSON'})).toBeVisible()
  page.once('dialog',dialog=>dialog.accept())
  await page.locator('.record-items li').filter({hasText:scan}).getByRole('button',{name:'删除'}).click()
  await expect(page.getByRole('heading',{name:`检查 ${scan}`})).toHaveCount(0)
  expect((await page.request.get(`/api/scans/${scan}`)).status()).toBe(404)
})

test('Backend connection failure surfaces in History', async ({page}) => {
  await page.route('**/api/scans', route=>route.abort('connectionrefused'))
  await page.goto('/history')
  await expect(page.getByText('无法加载记录')).toBeVisible()
  await page.unroute('**/api/scans')
  await page.reload()
  await expect(page.getByText('无法加载记录')).toHaveCount(0)
  await expect(page.getByRole('status')).toHaveCount(0)
})

test('Camera permission denial is actionable', async ({page}) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:{
      getUserMedia: async () => { throw new DOMException('Denied','NotAllowedError') },
    }})
  })
  await page.goto('/scan?mode=camera')
  await page.getByRole('button',{name:'开启摄像头'}).click()
  await expect(page.getByRole('alert')).toContainText('摄像头权限被拒绝')
  await expect(page.getByRole('button',{name:'拍摄图像'})).toBeDisabled()
})

test('Browser upload timeout releases the save control', async ({page}) => {
  await page.addInitScript(() => {
    const timeout = Object.getOwnPropertyDescriptor(XMLHttpRequest.prototype,'timeout')!
    Object.defineProperty(XMLHttpRequest.prototype,'timeout',{
      get:timeout.get,
      set(value:number) { timeout.set!.call(this,Math.min(value,150)) },
    })
  })
  await page.route('**/api/scans/*/assets', async route => {
    await new Promise(resolve=>setTimeout(resolve,500))
    await route.abort().catch(()=>{})
  })
  await page.goto('/scan')
  await page.locator('input[type=file]').setInputFiles(image)
  await page.getByRole('button',{name:'确认并保存检查'}).click()
  await expect(page.getByRole('alert')).toContainText('上传超时')
  await expect(page.getByRole('button',{name:'确认并保存检查'})).toBeEnabled()
})

