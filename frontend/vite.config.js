import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api/platform': 'http://127.0.0.1:8100',
      '/api/auth': 'http://127.0.0.1:8100',
      '/api': 'http://localhost:8000',
    },
  },
})
