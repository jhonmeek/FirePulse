import { defineConfig, devices } from '@playwright/test'

/**
 * Tests de parcours et d'accessibilité sur le **build de démo autonome** (`--mode demo`) :
 * aucun backend ni réseau requis, c'est exactement l'artefact de secours du jour J.
 * Navigateur : Chrome installé sur la machine (`channel: 'chrome'`), pas de téléchargement.
 */
const PORT = 4180

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list']],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    channel: 'chrome',
    locale: 'fr-FR',
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], channel: 'chrome', viewport: { width: 1440, height: 900 } } },
    { name: 'mobile', use: { ...devices['Pixel 7'], channel: 'chrome' }, testMatch: /parcours\.spec\.ts/ },
  ],
  webServer: {
    command: `npm run build:demo && npx vite preview --mode demo --outDir dist-demo --port ${PORT} --strictPort --host 127.0.0.1`,
    url: `http://127.0.0.1:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
  },
})
