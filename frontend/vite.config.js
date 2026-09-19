import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

const proxy = {
  '/api': {
    target: process.env.VITE_API_TARGET || 'http://localhost:8000',
    changeOrigin: true,
    rewrite: (p) => p.replace(/^\/api/, ''),
  },
}

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  base: '/',
  server: { port: 5173, proxy },
  preview: { port: 4173, proxy },
})
