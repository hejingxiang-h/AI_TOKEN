import vue from '@vitejs/plugin-vue'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = env.BACKEND_TARGET || 'http://127.0.0.1:8000'
  const proxy = {
    '/health': { target },
    '/api': { target },
    '/docs': { target },
    '/openapi.json': { target },
  }

  return {
    plugins: [vue()],
    build: {
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (id.includes('/node_modules/echarts/')) return 'echarts'
            if (id.includes('/node_modules/zrender/')) return 'echarts'
          },
        },
      },
    },
    server: { host: '127.0.0.1', proxy },
    preview: { host: '127.0.0.1', proxy },
  }
})
