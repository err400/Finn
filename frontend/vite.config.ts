import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  const configured = (process.env.VITE_API_BASE_URL ?? env.VITE_API_BASE_URL ?? '').trim()
  const placeholder = /YOUR-RENDER-SERVICE|example\.onrender\.com/i.test(configured)
  const apiBase = configured && !placeholder ? configured : mode === 'production'
    ? 'https://finn-zqtt.onrender.com/api/v1'
    : 'http://127.0.0.1:8001/api/v1'
  return {
    plugins: [react(), tailwindcss()],
    define: { 'import.meta.env.VITE_API_BASE_URL': JSON.stringify(apiBase) },
  }
})
