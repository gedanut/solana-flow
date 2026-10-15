const {defineConfig} = require('@playwright/test');
module.exports = defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 30000,
  use: {baseURL: 'http://127.0.0.1:8878', trace: 'retain-on-failure', screenshot: 'only-on-failure'},
  reporter: [['list'], ['html', {open: 'never'}]],
  webServer: [
    {command: `${process.env.E2E_PYTHON || 'python'} scripts/e2e_server.py`, url: 'http://127.0.0.1:8878/api/session', reuseExistingServer: false, timeout: 30000},
    {command: `${process.env.E2E_PYTHON || 'python'} -m http.server 8879 --bind 127.0.0.1 --directory docs`, url: 'http://127.0.0.1:8879/explorer/', reuseExistingServer: false, timeout: 30000}
  ]
});
