import { defineConfig } from 'vite'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [
    tailwindcss(),
  ],
  define: {
    'import.meta.env.VITE_API_BASE_URL': 'window.location.port === "5173" ? "http://" + window.location.hostname + ":8000" : window.location.origin'
  },
  server: {
    host: '0.0.0.0',
    port: 5173
  }
})