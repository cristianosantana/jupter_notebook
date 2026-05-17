import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Em dev, proxy evita CORS se a API não listar o origin do Vite.
// Em produção, defina VITE_ORION_API_BASE (ex.: https://api.exemplo.com).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      '/api': {
        target: process.env.VITE_DEV_PROXY_TARGET ?? 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
