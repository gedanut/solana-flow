const {test, expect} = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

async function loaded(page) {
  await expect(page.locator('#global-status')).toContainText('Capture loaded');
}
async function openDetails(page, label) {
  const summary = page.locator('summary', {hasText: label});
  if (!(await summary.evaluate(node => node.parentElement.open))) await summary.click();
}
function exactSnapshot() {
  return JSON.stringify({schema_version: 1, wallet: '11111111111111111111111111111111', cluster: 'synthetic', synthetic: true,
    captured_at: '2026-01-06T00:00:00Z', coverage: {limit: 1, pages: 1, cap_reached: true, reached_history: false, partial: false, discovery: 'wallet-account-keys-only'},
    warnings: [], unavailable_signatures: [], transactions: [{slot: 100, blockTime: 1767657600,
      transaction: {signatures: ['SYNTHETIC-E2E-exact'], message: {accountKeys: ['11111111111111111111111111111111', 'other']}},
      meta: {err: null, fee: 0, preBalances: ['__EXACT_PRE__', 0], postBalances: ['__EXACT_POST__', 0], preTokenBalances: [], postTokenBalances: []}}]})
    .replace('"__EXACT_PRE__"', '900719925474099300001').replace('"__EXACT_POST__"', '900719925474099300002');
}

test.describe.serial('local evidence workflow', () => {
  test('inspect, filter, switch wallets, compare and download', async ({page}) => {
    const errors = []; page.on('pageerror', error => errors.push(error.message));
    await page.goto('/'); await loaded(page);
    await expect(page.locator('#wallet-list button')).toHaveCount(2);
    await expect(page.locator('#open-import')).toBeInViewport();
    await expect(page.locator('#open-capture')).toBeInViewport();
    await page.locator('#open-import').click();
    await expect(page.locator('#import-file')).toBeVisible();
    await expect(page.locator('#import-file')).toBeFocused();
    await page.locator('#open-capture').click();
    await expect(page.locator('#job-limit')).toBeVisible();
    await expect(page.locator('#job-limit')).toBeFocused();
    await page.evaluate(() => scrollTo(0, 0));
    await expect(page.locator('#provenance')).toContainText('SYNTHETIC EVIDENCE');
    await expect(page.locator('#row-count')).toHaveText('16 matching movements');
    await page.locator('#ledger-rows button').first().click();
    await expect(page.locator('#evidence-json')).toContainText('preBalances');
    await page.locator('#search').fill('no-such-evidence');
    await expect(page.locator('#row-count')).toHaveText('0 matching movements');
    await page.locator('#reset-filters').click();
    await page.locator('#direction-filter').selectOption('zero');
    await expect(page.locator('#row-count')).toHaveText('1 matching movements');
    await page.locator('#reset-filters').click();
    await page.locator('#compare-submit').click();
    await expect(page.locator('#compare-result')).toContainText('Added signatures · 5');
    await expect(page.locator('#compare-result')).toContainText('Removed signatures · 2');
    await expect(page.locator('#compare-result')).toContainText('Changed signatures · 1');
    await page.locator('#capture-select').selectOption('1'); await loaded(page);
    await expect(page.locator('#row-count')).toHaveText('13 matching movements');
    await page.locator('#wallet-list button').nth(1).click(); await loaded(page);
    await expect(page.locator('#capture-select')).toHaveValue('4');
    const download = page.waitForEvent('download'); await page.locator('#export-json').click();
    const file = await download;
    const stream = await file.createReadStream(); const chunks = []; for await (const chunk of stream) chunks.push(chunk);
    const ledger = JSON.parse(Buffer.concat(chunks).toString());
    expect(ledger.rows).toHaveLength(16); expect(ledger.synthetic).toBe(true);
    const a11y = await new AxeBuilder({page}).analyze();
    expect(a11y.violations).toEqual([]); expect(errors).toEqual([]);
  });

  test('browser import preserves huge integers and rejects duplicate keys', async ({page}) => {
    await page.goto('/'); await loaded(page);
    await openDetails(page, 'Import snapshot JSON');
    const raw = exactSnapshot();
    await page.locator('#import-label').fill('Exact integer import');
    await page.locator('#import-file').setInputFiles({name: 'exact.json', mimeType: 'application/json', buffer: Buffer.from(raw)});
    await page.locator('#import-submit').click();
    await expect(page.locator('#import-feedback')).toContainText('Saved capture reloaded');
    await expect(page.locator('#row-count')).toHaveText('1 matching movements');
    await expect(page.locator('#ledger-rows')).toContainText('0.000000001');
    await page.locator('#ledger-rows button').click();
    await expect(page.locator('#evidence-json')).toContainText('900719925474099300001');
    await expect(page.locator('#evidence-json')).toContainText('900719925474099300002');
    const duplicate = raw.replace('"schema_version":1', '"schema_version":2,"schema_version":1');
    await page.locator('#import-file').setInputFiles({name: 'duplicate.json', mimeType: 'application/json', buffer: Buffer.from(duplicate)});
    await page.locator('#import-submit').click();
    await expect(page.locator('#import-feedback')).toContainText('Invalid');
    const captures = await (await page.request.get('/api/captures')).json();
    expect(captures.captures).toHaveLength(5);
    await page.reload(); await loaded(page);
    await expect(page.locator('#ledger-rows')).toContainText('0.000000001');
  });

  test('register wallet, run real asynchronous local-RPC fixture job and open result', async ({page}) => {
    await page.goto('/'); await loaded(page);
    await openDetails(page, 'Register wallet');
    await page.locator('#wallet-address').fill('Vote111111111111111111111111111111111111111');
    await page.locator('#wallet-label').fill('E2E RPC fixture');
    await page.locator('#wallet-cluster').selectOption('devnet');
    await page.locator('#register-submit').click();
    await expect(page.locator('#wallet-feedback')).toContainText('registered');
    await expect(page.locator('#capture-context')).toContainText('No captures');
    await openDetails(page, 'Capture from configured RPC');
    await page.locator('#include-tokens').check();
    await page.locator('#job-limit').fill('2');
    await page.locator('#job-submit').click();
    await expect(page.locator('#job-feedback')).toContainText('submitted');
    await expect.poll(async () => {
      const response = await page.request.get('/api/jobs'); const data = await response.json(); return data.jobs[0]?.status;
    }).toBe('partial');
    await page.locator('#refresh-jobs').click();
    await expect(page.locator('#job-list')).toContainText('partial');
    await page.locator('#job-list button').first().click(); await loaded(page);
    await expect(page.locator('#row-count')).toHaveText('0 matching movements');
    await expect(page.locator('#provenance')).toContainText('PARTIAL');
    await expect(page.locator('#wallet-context')).toContainText('E2E RPC fixture');
  });
});

test('public static adapter has working evidence and no pretend write actions', async ({page}) => {
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await page.goto('http://127.0.0.1:8879/explorer/'); await loaded(page);
  await expect(page.locator('#mode-label')).toHaveText('Read-only static demonstration');
  await expect(page.locator('#register-submit')).toBeDisabled();
  await expect(page.locator('#import-submit')).toBeDisabled();
  await expect(page.locator('#job-submit')).toBeDisabled();
  await page.locator('#compare-submit').click();
  await expect(page.locator('#compare-result')).toContainText('Added signatures · 5');
  await page.locator('#search').fill('SYNTHETIC-W1-SYNTHETIC-004');
  await expect(page.locator('#row-count')).toHaveText('2 matching movements');
  await page.locator('#ledger-rows button').first().click();
  await expect(page.locator('#evidence-json')).toContainText('preBalances');
  await page.setViewportSize({width:390, height:844});
  await page.locator('#ledger-rows button').first().click();
  await expect(page.locator('#inspector-heading')).toBeInViewport();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});

test('mobile workspace is accessible and fits viewport', async ({page}) => {
  await page.setViewportSize({width:390, height:844});
  await page.goto('http://127.0.0.1:8879/explorer/'); await loaded(page);
  await page.locator('#rail-toggle').click();
  await expect(page.locator('#wallet-list button').first()).toBeVisible();
  await page.locator('#wallet-list button').nth(1).click(); await loaded(page);
  await page.locator('#ledger-rows button').first().click();
  await expect(page.locator('#inspector-heading')).toBeInViewport();
  await expect(page.locator('#evidence-json')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
});
