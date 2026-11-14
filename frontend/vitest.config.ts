import { fileURLToPath } from 'node:url'
import { mergeConfig, defineConfig, configDefaults } from 'vitest/config'
import viteConfig from './vite.config.ts'

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      exclude: [...configDefaults.exclude, 'e2e/**'],
      root: fileURLToPath(new URL('./', import.meta.url)),
      // Les tests tournent toujours sur les mocks, même si un .env.local local pointe vers l'API.
      env: { VITE_USE_MOCKS: 'true' },
      // Tests lourds (calendrier de 300 cellules, grille mock de 300 Ko) : 5 s par défaut
      // provoquait des échecs aléatoires sous charge (build en parallèle, runner CI).
      testTimeout: 15000,
    },
  }),
)
