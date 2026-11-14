import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from '@playwright/test'

const backend = fileURLToPath(new URL('../backend/', import.meta.url))
const work = mkdtempSync(join(tmpdir(), 'oralscan-e2e-'))
// FastAPI gets an empty database and a separate private directory for every run.
const env = {
  ORALSCAN_DATABASE_URL: `sqlite:///${join(work, 'scan.db').replaceAll('\\', '/')}`,
  ORALSCAN_STORAGE_DIR: join(work, 'private'),
  ORALSCAN_MODELS_DIR: join(work, 'models'),
  ORALSCAN_MAX_UPLOAD_BYTES: '26214400',
  ORALSCAN_UPLOAD_BODY_TIMEOUT_SECONDS: '60',
  ORALSCAN_REPORT_FONT: '',
}
const python = process.env.ORALSCAN_TEST_PYTHON ?? (process.platform === 'win32'
  ? '.venv/Scripts/python.exe' : '.venv/bin/python')
const edge = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'

export default defineConfig({
  testDir: './e2e',
  timeout: 90_000,
  expect: { timeout: 12_000 },
  workers: 1,
  use: {
    baseURL: 'http://127.0.0.1:55173',
    launchOptions: {
      executablePath: process.env.ORALSCAN_TEST_BROWSER || (process.platform === 'win32' && existsSync(edge) ? edge : undefined),
      args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
    },
  },
  webServer: [
    { command: `"${python}" tests/browser_server.py`, cwd: backend, env, url: 'http://127.0.0.1:5800/api/health', timeout: 90_000, reuseExistingServer: false },
    { command: 'pnpm exec vite preview --host 127.0.0.1 --port 55173 --strictPort', env: { ORALSCAN_API_TARGET: 'http://127.0.0.1:5800' }, url: 'http://127.0.0.1:55173', reuseExistingServer: false },
  ],
})
