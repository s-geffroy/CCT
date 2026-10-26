import { defineConfig, devices } from '@playwright/test';

// L'application tourne dans le service Compose `app` ; ce conteneur la joint
// par le reseau interne. Rien n'est publie sur l'hote.
export default defineConfig({
  testDir: './specs',
  outputDir: './results/artifacts',
  timeout: 30_000,
  retries: 0,
  workers: 1,
  reporter: [['list'], ['html', { outputFolder: './results/report', open: 'never' }]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://cct-web:8000',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    locale: 'fr-FR',
  },
  projects: [
    { name: 'desktop-1280', use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 900 } } },
    { name: 'laptop-1024', use: { ...devices['Desktop Chrome'], viewport: { width: 1024, height: 768 } } },
  ],
});
