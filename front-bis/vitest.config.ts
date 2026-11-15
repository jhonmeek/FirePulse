import { fileURLToPath } from 'node:url'
import { mergeConfig, defineConfig } from 'vitest/config'
import viteConfig from './vite.config.ts'

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/__tests__/setup.ts'],
      root: fileURLToPath(new URL('./', import.meta.url)),
      env: { VITE_USE_MOCKS: 'true' },
      testTimeout: 15000,
    },
  }),
)
