import { defineConfig } from 'vite'

const base = process.env.PAGES_BASE_PATH || '/'

if (!base.startsWith('/') || !base.endsWith('/')) {
  throw new Error(`PAGES_BASE_PATH must start and end with "/": ${base}`)
}

export default defineConfig({
  base,
  build: {
    chunkSizeWarningLimit: 1200,
  },
})
