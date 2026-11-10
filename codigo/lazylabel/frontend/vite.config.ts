import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(import.meta.dirname, 'src') } },
  base: '/static/app/',
  build: {
    outDir: '../src/lazylabel/web/static/app',
    emptyOutDir: true,
    assetsDir: 'assets',
    rollupOptions: { output: {
      entryFileNames: 'assets/[name].js',
      chunkFileNames: 'assets/[name].js',
      assetFileNames: 'assets/[name][extname]',
    } },
  },
})
