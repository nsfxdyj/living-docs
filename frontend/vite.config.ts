import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Proxy API calls to the FastAPI backend during local development.
export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
