import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, 'src') },
  },
  server: {
    port: 3000,
    proxy: {
      // dev1's :8000 was taken down; the dev2 backend :8002 (same Neo4j, + the
      // trust/coverage/promote features) now serves the whole API for prod.
      '/api': 'http://127.0.0.1:8002',
    },
  },
  preview: {
    port: 3000,
    proxy: {
      // dev1's :8000 was taken down; the dev2 backend :8002 (same Neo4j, + the
      // trust/coverage/promote features) now serves the whole API for prod.
      '/api': 'http://127.0.0.1:8002',
    },
  },
});
