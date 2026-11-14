import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// Separate build for the SYNTHETIC render-benchmark harness (never part of the app build).
export default defineConfig({
  root: 'bench',
  plugins: [react()],
  build: { outDir: 'dist', emptyOutDir: true, chunkSizeWarningLimit: 5000 },
  preview: { port: 4190, strictPort: true, host: '127.0.0.1' },
});
