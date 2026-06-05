import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Dev proxy: the React app calls /api/*, Vite forwards to the ASCIR backend on
// :3000, so the browser sees same-origin requests (no CORS changes needed).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:3000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
});
