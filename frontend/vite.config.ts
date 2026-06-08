import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: path.resolve(__dirname, '../static'),
    emptyOutDir: false,
    rollupOptions: {
      input: {
        telemetry: path.resolve(__dirname, 'src/main.tsx'),
      },
      output: {
        entryFileNames: 'telemetry.js',
        chunkFileNames: 'telemetry.js',
        assetFileNames: (assetInfo) => {
          if (assetInfo.name && assetInfo.name.endsWith('.css')) {
            return 'telemetry.css';
          }
          return '[name].[ext]';
        },
      },
    },
    cssCodeSplit: false,
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
});
