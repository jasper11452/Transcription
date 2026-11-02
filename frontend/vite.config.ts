import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'url'
import { dirname, resolve } from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': resolve(__dirname, './src'),
    },
  },
  base: '/static/dist/',
  build: {
    outDir: '../src/transcript/web/static/dist',
    emptyOutDir: true,
    manifest: true, // 后端 validate_dist 依赖 .vite/manifest.json 校验产物完整性
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
        task: resolve(__dirname, 'task.html'),
      },
    },
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8765',
        changeOrigin: true,
      },
    },
  },
})
