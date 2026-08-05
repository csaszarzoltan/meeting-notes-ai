import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The SPA is served by FastAPI at /app/live (product_app.py), with static
// assets mounted at /app/live/assets. `base` must match so the built
// index.html references the absolute asset URLs the server actually serves.
export default defineConfig({
  plugins: [react()],
  base: '/app/',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: false,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/app': 'http://localhost:8000',
    },
  },
});
