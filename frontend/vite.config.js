
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/upload': 'http://127.0.0.1:8000',
      '/query': 'http://127.0.0.1:8000',
      '/columns': 'http://127.0.0.1:8000',
      '/preview': 'http://127.0.0.1:8000'
    }
  },
})
