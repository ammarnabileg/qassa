import react from '@vitejs/plugin-react'
import { execSync } from 'node:child_process'
import { defineConfig } from 'vitest/config'

const run = (args: string) => { try { return execSync(`python3 ../scripts/version.py ${args}`).toString().trim() } catch { return '' } }
const version = process.env.QASSA_VERSION || run('') || 'unknown'
const channel = process.env.QASSA_CHANNEL || run('--channel') || 'debug'

export default defineConfig({
  plugins: [react()],
  define: { __APP_VERSION__: JSON.stringify(version), __APP_CHANNEL__: JSON.stringify(channel) },
  server: { port: 5173, proxy: { '/api': { target: process.env.API_URL ?? 'http://localhost:8000', changeOrigin: false } } },
  test: { environment: 'node' },
})
