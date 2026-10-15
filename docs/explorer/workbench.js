/* Solana Flow investigation workbench. No third-party runtime dependencies. */
(function (root) {
  'use strict';
  function formatUnits(value, decimals) {
    if (!/^-?\d+$/.test(String(value)) || !Number.isInteger(decimals) || decimals < 0 || decimals > 255) return 'Unknown';
    const units = BigInt(value);
    const digits = (units < 0n ? -units : units).toString().padStart(decimals + 1, '0');
    return (units < 0n ? '-' : '') + (decimals ? digits.slice(0, -decimals) + '.' + digits.slice(-decimals) : digits);
  }
  function filterMovements(rows, filters = {}) {
    const matched = rows.filter(row =>
      (!filters.asset || (row.mint || row.asset) === filters.asset) &&
      (!filters.direction || row.direction === filters.direction) &&
      (!filters.status || row.status === filters.status) &&
      (!filters.search || [row.signature, row.mint || row.asset].some(value => String(value || '').toLowerCase().includes(filters.search.toLowerCase()))));
    const limit = Math.max(1, Math.min(500, parseInt(filters.limit, 10) || 50));
    const offset = Math.max(0, parseInt(filters.offset, 10) || 0);
    return { rows: matched.slice(offset, offset + limit), total: matched.length, limit, offset };
  }
  function ledgerRows(capture) {
    return Array.isArray(capture?.ledger) ? capture.ledger : (capture?.ledger?.rows || capture?.rows || []);
  }
  function utcDay(time) {
    const date = time == null ? null : new Date(typeof time === 'number' ? time * 1000 : time);
    return date && !Number.isNaN(date.getTime()) ? date.toISOString().slice(0, 10) : 'Unknown';
  }
  function analytics(capture) {
    const rows = ledgerRows(capture), ledger = capture.ledger || {};
    const assets = new Map(), days = new Map();
    for (const row of rows) {
      const key = JSON.stringify([row.asset, row.mint, row.decimals]);
      if (!assets.has(key)) assets.set(key, {asset: row.asset, mint: row.mint, decimals: row.decimals, incoming: 0n, outgoing: 0n});
      const item = assets.get(key);
      const amount = /^-?\d+$/.test(String(row.amount_base_units)) ? BigInt(row.amount_base_units) : 0n;
      if (amount > 0n) item.incoming += amount; else item.outgoing -= amount;
      const date = utcDay(row.time), dayKey = JSON.stringify([date, row.asset, row.mint, row.decimals]);
      if (!days.has(dayKey)) days.set(dayKey, {date, asset: row.asset, mint: row.mint, decimals: row.decimals, count: 0, net: 0n});
      days.get(dayKey).count++; days.get(dayKey).net += amount;
    }
    return {
      assets: [...assets.values()].map(item => ({asset: item.asset, mint: item.mint, decimals: item.decimals,
        inflow: formatUnits(item.incoming.toString(), item.decimals), outflow: formatUnits(item.outgoing.toString(), item.decimals),
        net: formatUnits((item.incoming - item.outgoing).toString(), item.decimals), net_base_units: (item.incoming - item.outgoing).toString()})),
      daily: [...days.values()].sort((a, b) => a.date.localeCompare(b.date)).map(day => ({...day, net: formatUnits(day.net.toString(), day.decimals), net_base_units: day.net.toString()})),
      transaction_count: ledger.transaction_count ?? new Set(rows.map(row => row.signature)).size,
      row_count: rows.length, failed_count: ledger.failed_count ?? new Set(rows.filter(row => row.status === 'failed').map(row => row.signature)).size,
      gap_count: (ledger.gaps || capture.snapshot?.gaps || []).length,
      wallet_paid_fees_base_units: ledger.wallet_paid_fees_base_units ?? '0',
      synthetic: !!(capture.synthetic || ledger.synthetic || capture.snapshot?.synthetic),
      partial: !!(capture.partial || ledger.coverage?.partial || capture.snapshot?.coverage?.partial)
    };
  }
  function compareCaptures(before, after) {
    const group = capture => {
      if (capture.snapshot) {
        const canonical = value => {
          if (Array.isArray(value)) return value.map(canonical);
          if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])]));
          return value;
        };
        const sources = new Map((capture.snapshot.unavailable_signatures || []).map(signature => [signature, null]));
        for (const tx of capture.snapshot.transactions || []) sources.set(tx.signature || tx.transaction?.signatures?.[0], JSON.stringify(canonical(tx)));
        return sources;
      }
      const map = new Map();
      for (const row of ledgerRows(capture)) {
        if (!map.has(row.signature)) map.set(row.signature, []);
        map.get(row.signature).push(JSON.stringify([row.asset, row.mint, row.decimals, row.amount_base_units, row.status]));
      }
      return new Map([...map].map(([signature, entries]) => [signature, entries.sort().join('|')]));
    };
    const a = group(before), b = group(after), totals = new Map();
    for (const [side, capture] of [['before', before], ['after', after]]) {
      for (const asset of analytics(capture).assets) {
        const key = JSON.stringify([asset.asset, asset.mint, asset.decimals]);
        if (!totals.has(key)) totals.set(key, {...asset, before: '0', after: '0'});
        totals.get(key)[side] = asset.net_base_units;
      }
    }
    return {added_signatures: [...b.keys()].filter(key => !a.has(key)).sort(), removed_signatures: [...a.keys()].filter(key => !b.has(key)).sort(),
      changed_signatures: [...b.keys()].filter(key => a.has(key) && a.get(key) !== b.get(key)).sort(),
      assets: [...totals.values()].map(asset => ({...asset, delta_base_units: (BigInt(asset.after) - BigInt(asset.before)).toString(), delta: formatUnits((BigInt(asset.after) - BigInt(asset.before)).toString(), asset.decimals)}))};
  }
  function evidenceFor(capture, row) {
    const source = (capture.snapshot?.transactions || []).find(tx => (tx.signature || tx.transaction?.signatures?.[0]) === row.signature);
    if (!source) return {unavailable: true, signature: row.signature, reason: 'Source transaction unavailable in this capture.'};
    const meta = {};
    for (const key of ['err', 'fee', 'preBalances', 'postBalances', 'preTokenBalances', 'postTokenBalances', 'loadedAddresses']) {
      if (source.meta && Object.hasOwn(source.meta, key)) meta[key] = source.meta[key];
    }
    return {signature: row.signature, slot: source.slot, blockTime: source.blockTime, version: source.version,
      accountKeys: source.transaction?.message?.accountKeys || [], meta};
  }
  function parseLosslessJSON(text) {
    // Validate before rewriting: invalid numeric object keys must not become valid
    // quoted keys. This temporary parse is never used as evidence or reserialized.
    JSON.parse(text);
    const tokens = /"(?:\\[\s\S]|[^"\\])*"|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/g;
    return JSON.parse(text.replace(tokens, token => {
      if (token[0] === '"') return token;
      const unsafe = /^-?\d+$/.test(token)
        ? BigInt(token) > 9007199254740991n || BigInt(token) < -9007199254740991n
        : !Number.isFinite(Number(token)) || Math.abs(Number(token)) >= Number.MAX_SAFE_INTEGER;
      // Large decimal/exponent tokens also remain exact text, never rounded into
      // an integer. Ordinary fractional/scientific values keep JSON number types.
      return unsafe ? JSON.stringify(token) : token;
    }));
  }
  async function createAdapter({fetch: fetcher, staticMode = false}) {
    async function decode(response) {
      if (!response.ok) {
        let message = 'Request failed. Retry or check the local service.';
        try { message = parseLosslessJSON(await response.text()).error || message; } catch (_) { /* Non-JSON server errors are not rendered. */ }
        throw new Error(message);
      }
      return parseLosslessJSON(await response.text());
    }
    let session;
    if (!staticMode) {
      const response = await fetcher('api/session', {cache: 'no-store'});
      if (response.status === 404) staticMode = true;
      else session = await decode(response);
    }
    if (!staticMode) return {mode: 'local', captureEnabled: session.capture_enabled === true,
      get: (path, params = {}) => decodeRequest('api/' + path + (Object.keys(params).length ? '?' + new URLSearchParams(params) : '')),
      post: (path, body) => postJSON(path, JSON.stringify(body)),
      importSnapshot: (raw, label) => postJSON('import', '{"snapshot":' + raw + ',"label":' + JSON.stringify(label) + '}')};
    function postJSON(path, body) {
      return decodeRequest('api/' + path, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Solana-Flow-Token': session.token}, body});
    }
    async function decodeRequest(url, options = {}) { return decode(await fetcher(url, {cache: 'no-store', ...options})); }
    const data = await decodeRequest('demo-data.json');
    const capture = id => {
      const item = (data.captures || []).find(item => String(item.id) === String(id));
      if (!item) throw new Error('Capture not found.');
      return item;
    };
    const readOnly = async () => { throw new Error('This demonstration is read-only. Start Solana Flow locally to import or capture.'); };
    return {mode: 'static', post: readOnly, importSnapshot: readOnly,
      get: async (path, params = {}) => {
        if (path === 'wallets') return {wallets: data.wallets || []};
        if (path === 'captures') return {captures: (data.captures || []).filter(item => !params.wallet_id || String(item.wallet_id) === String(params.wallet_id))};
        if (path.startsWith('captures/')) return capture(path.split('/')[1]);
        if (path === 'jobs') return {jobs: []};
        if (path === 'compare') return compareCaptures(capture(params.before), capture(params.after));
        if (path === 'analytics') return analytics(capture(params.capture_id));
        if (path === 'movements') {
          const selected = capture(params.capture_id);
          const rows = params.wallet_id && String(selected.wallet_id) !== String(params.wallet_id) ? [] : ledgerRows(selected);
          return filterMovements(rows.map(row => ({...row, wallet_id: selected.wallet_id, capture_id: selected.id})), params);
        }
        throw new Error('Unsupported read-only operation.');
      }};
  }
  function ledgerCSV(rows) {
    const columns = ['signature', 'slot', 'time', 'status', 'asset', 'mint', 'amount_base_units', 'decimals', 'decimal_amount', 'direction', 'wallet_paid_fee_base_units', 'synthetic'];
    const textFields = new Set(['signature', 'asset', 'mint', 'status', 'direction']);
    const quote = value => '"' + String(value ?? '').replace(/"/g, '""') + '"';
    return columns.join(',') + '\r\n' + rows.map(row => columns.map(key => {
      let value = String(row[key] ?? '');
      if (textFields.has(key) && /^\s*[=+\-@\t\r\n]/.test(value)) value = "'" + value;
      return quote(value);
    }).join(',')).join('\r\n') + '\r\n';
  }
  const exported = { formatUnits, filterMovements, analytics, compareCaptures, evidenceFor, parseLosslessJSON, createAdapter, ledgerCSV };
  if (typeof module !== 'undefined' && module.exports) module.exports = exported;
  if (!root.document) return;

  const $ = id => root.document.getElementById(id);
  const state = {api: null, wallets: [], wallet: null, captures: [], capture: null, offset: 0, total: 0, generation: 0, movementRequest: 0, comparisonRequest: 0, jobs: [], timer: null};
  const el = (tag, text, className) => {
    const node = root.document.createElement(tag);
    if (text !== undefined) node.textContent = String(text ?? 'Unknown');
    if (className) node.className = className;
    return node;
  };
  function message(text, error = false) {
    $('global-status').textContent = text;
    $('global-status').classList.toggle('error', error);
  }
  function detail(list, label, value, mono = false) {
    const group = el('div'); group.append(el('dt', label), el('dd', value ?? 'Unknown', mono ? 'mono' : ''));
    list.append(group);
  }
  function option(select, value, label) {
    const item = el('option', label); item.value = String(value); select.append(item);
  }
  function captureName(capture) { return (capture.label || 'Capture #' + capture.id) + ' · ' + (capture.captured_at || 'Unknown time'); }
  function clearInspector() {
    $('movement-detail').replaceChildren(); $('evidence-json').hidden = true;
    $('inspector-help').textContent = 'Choose a signature in the ledger. Source account keys, pre/post balances and transaction metadata appear here.';
  }
  function clearCapture() {
    state.capture = null; state.total = 0; state.offset = 0; state.movementRequest++;
    $('ledger-rows').replaceChildren(); $('asset-totals').replaceChildren(); $('capture-stats').replaceChildren();
    $('coverage-content').replaceChildren(); $('daily-content').replaceChildren(); $('provenance').hidden = true;
    $('ledger-message').hidden = false; $('ledger-message').textContent = 'No captures yet. Import a snapshot or start a local capture.';
    $('row-count').textContent = 'No capture selected'; $('capture-context').textContent = 'No captures for this wallet.';
    $('export-csv').disabled = true; $('export-json').disabled = true; $('previous-page').disabled = true; $('next-page').disabled = true;
    $('page-context').textContent = 'Page 0 of 0'; clearInspector();
  }
  function renderWallets() {
    $('wallet-list').replaceChildren();
    if (!state.wallets.length) $('wallet-list').append(el('p', 'No wallets yet. Register a wallet or import a snapshot.'));
    for (const wallet of state.wallets) {
      const button = el('button', undefined, 'wallet-button'); button.type = 'button';
      button.setAttribute('aria-current', String(String(wallet.id) === String(state.wallet?.id)));
      button.append(el('strong', wallet.label || 'Unlabelled wallet'), el('small', wallet.address, 'mono'), el('small', wallet.cluster || 'Unknown cluster', 'cluster'));
      button.addEventListener('click', () => selectWallet(wallet.id).catch(error => message(error.message, true)));
      $('wallet-list').append(button);
    }
  }
  async function loadWallets(preferredWallet, preferredCapture) {
    const data = await state.api.get('wallets'); state.wallets = data.wallets || [];
    const selected = state.wallets.find(item => String(item.id) === String(preferredWallet ?? state.wallet?.id)) || state.wallets[0];
    renderWallets();
    if (selected) await selectWallet(selected.id, preferredCapture);
    else { state.wallet = null; clearCapture(); $('wallet-context').textContent = 'No wallets registered. Import evidence or register an address to begin.'; message('Workspace is empty. Your first import will create a wallet.'); }
  }
  async function selectWallet(id, preferredCapture) {
    const generation = ++state.generation; state.comparisonRequest++; clearTimeout(searchTimer);
    state.wallet = state.wallets.find(item => String(item.id) === String(id));
    clearCapture(); renderWallets(); $('filter-form').reset();
    $('wallet-context').textContent = (state.wallet.label || 'Unlabelled wallet') + ' · ' + state.wallet.address + ' · ' + state.wallet.cluster;
    $('capture-select').disabled = true; $('compare-before').disabled = true; $('compare-after').disabled = true; $('compare-submit').disabled = true;
    $('compare-result').textContent = 'Loading capture history…';
    $('job-fields').disabled = !state.api.captureEnabled;
    message('Loading capture history…');
    const data = await state.api.get('captures', {wallet_id: id});
    if (generation !== state.generation) return;
    state.captures = (data.captures || []).slice().sort((a, b) => BigInt(a.id) > BigInt(b.id) ? -1 : BigInt(a.id) < BigInt(b.id) ? 1 : 0);
    for (const select of [$('capture-select'), $('compare-before'), $('compare-after')]) { select.replaceChildren(); for (const capture of state.captures) option(select, capture.id, captureName(capture)); }
    $('capture-select').disabled = !state.captures.length;
    const comparable = state.captures.length > 1;
    $('compare-before').disabled = !comparable; $('compare-after').disabled = !comparable; $('compare-submit').disabled = !comparable;
    $('compare-result').textContent = comparable ? 'Choose before and after captures, then compare evidence.' : 'Two captures are needed for a comparison.';
    if (comparable) $('compare-before').value = state.captures[1].id;
    const selected = state.captures.find(item => String(item.id) === String(preferredCapture)) || state.captures[0];
    if (selected) { $('capture-select').value = selected.id; await selectCapture(selected.id); }
    else { option($('capture-select'), '', 'No captures yet'); message('No captures for this wallet. Import evidence or start a capture.'); }
  }
  async function selectCapture(id) {
    const generation = ++state.generation; clearCapture(); $('filter-form').reset(); message('Loading capture evidence…');
    const scope = {wallet_id: state.wallet.id, capture_id: id};
    const [capture, summary] = await Promise.all([state.api.get('captures/' + id), state.api.get('analytics', scope)]);
    if (generation !== state.generation) return;
    state.capture = capture.capture || capture; state.offset = 0;
    $('capture-context').textContent = 'Capture #' + id + (String(id) === String(state.captures[0]?.id) ? ' · latest import' : ' · historical import') + ' · source capture time: ' + (state.capture.captured_at || 'Unknown time') + ' · immutable evidence';
    $('export-csv').disabled = false; $('export-json').disabled = false;
    renderOverview(summary); await loadMovements();
  }
  function renderOverview(summary) {
    $('capture-stats').replaceChildren();
    for (const [label, value] of [['Transactions', summary.transaction_count], ['Movements', summary.row_count], ['Failed', summary.failed_count], ['Evidence gaps', summary.gap_count]]) detail($('capture-stats'), label, value);
    detail($('capture-stats'), 'Wallet-paid fees · SOL', formatUnits(summary.wallet_paid_fees_base_units, 9), true);
    const capture = state.capture, ledger = capture.ledger || {};
    const synthetic = summary.synthetic || capture.synthetic || capture.snapshot?.synthetic;
    $('provenance').hidden = false;
    $('provenance').textContent = (synthetic ? 'SYNTHETIC EVIDENCE · Demonstration only. No real wallet or chain transactions. ' : 'SCOPED EVIDENCE · ') + (summary.partial ? 'PARTIAL capture: some source evidence is unavailable. ' : '') + 'Observed balance changes, not complete wallet history. Fees and rent may be included.';
    $('asset-totals').replaceChildren(); $('asset-filter').replaceChildren(); option($('asset-filter'), '', 'All assets');
    for (const asset of summary.assets || []) {
      const row = el('tr'), name = el('td'); name.append(el('span', asset.asset || 'Unknown', 'asset-name'));
      if (asset.mint) name.append(el('span', asset.mint, 'mint'));
      row.append(name);
      for (const key of ['inflow', 'outflow', 'net']) row.append(el('td', asset[key] ?? 'Unknown', 'numeric amount'));
      $('asset-totals').append(row); option($('asset-filter'), asset.mint || asset.asset, asset.mint ? asset.asset + ' · ' + asset.mint : asset.asset);
    }
    if (!(summary.assets || []).length) { const row = el('tr'), cell = el('td', 'No attributable asset movements in this capture.'); cell.colSpan = 4; row.append(cell); $('asset-totals').append(row); }
    const coverage = el('pre', JSON.stringify({coverage: ledger.coverage || capture.snapshot?.coverage || 'Unknown', warnings: ledger.warnings || capture.snapshot?.warnings || [], gaps: ledger.gaps || capture.snapshot?.gaps || []}, null, 2));
    $('coverage-content').replaceChildren(coverage); $('daily-content').replaceChildren(el('h3', 'Daily movement activity · UTC'));
    for (const day of summary.daily || []) $('daily-content').append(el('span', (day.date || day.day || 'Unknown date') + ' · ' + (day.mint || day.asset || 'All assets') + ': ' + (day.count ?? day.transaction_count ?? 'Unknown') + ' movements' + (day.net == null ? '' : ' · net ' + day.net), 'daily-row'));
    if (!(summary.daily || []).length) $('daily-content').append(el('p', 'No dated activity available.'));
  }
  function filters() {
    const values = {wallet_id: state.wallet.id, capture_id: state.capture.id, limit: $('page-size').value, offset: state.offset};
    for (const [id, key] of [['asset-filter', 'asset'], ['direction-filter', 'direction'], ['status-filter', 'status'], ['search', 'search']]) if ($(id).value) values[key] = $(id).value;
    return values;
  }
  async function loadMovements() {
    if (!state.capture) return;
    const request = ++state.movementRequest, generation = state.generation;
    $('ledger-table').setAttribute('aria-busy', 'true'); $('ledger-message').hidden = false; $('ledger-message').textContent = 'Loading movements…';
    $('previous-page').disabled = true; $('next-page').disabled = true; clearInspector();
    try {
      const result = await state.api.get('movements', filters());
      if (request !== state.movementRequest || generation !== state.generation) return;
      state.total = result.total; $('ledger-rows').replaceChildren();
      for (const movement of result.rows || []) {
        const row = el('tr'), first = el('td');
        const time = movement.time == null ? null : new Date(typeof movement.time === 'number' ? movement.time * 1000 : movement.time);
        first.append(el('span', time && !Number.isNaN(time.getTime()) ? time.toISOString().replace('T', ' ').replace('.000Z', '') : 'Unknown time', 'timestamp'));
        const inspect = el('button', movement.signature || 'Unknown signature', 'signature-button'); inspect.type = 'button'; inspect.setAttribute('aria-label', 'Inspect ' + movement.signature);
        inspect.addEventListener('click', () => {
          for (const sibling of $('ledger-rows').children) sibling.classList.remove('selected'); row.classList.add('selected');
          $('movement-detail').replaceChildren(); $('inspector-help').textContent = 'Source evidence for the selected movement. Amounts below remain exact text.';
          for (const [label, value] of [['Signature', movement.signature], ['Asset / mint', movement.mint || movement.asset], ['Net base units', movement.amount_base_units], ['Decimals', movement.decimals], ['Status', movement.status], ['Slot', movement.slot], ['Wallet-paid fee · base units', movement.wallet_paid_fee_base_units]]) detail($('movement-detail'), label, value, true);
          $('evidence-json').textContent = JSON.stringify(evidenceFor(state.capture, movement), null, 2); $('evidence-json').hidden = false; $('inspector-heading').focus({preventScroll: true});
        }); first.append(inspect); row.append(first);
        const asset = el('td'); asset.append(el('span', movement.asset, 'asset-name')); if (movement.mint) asset.append(el('span', movement.mint, 'mint')); row.append(asset);
        row.append(el('td', movement.decimal_amount ?? formatUnits(movement.amount_base_units, movement.decimals), 'numeric amount ' + (movement.direction === 'in' ? 'inflow' : movement.direction === 'out' ? 'outflow' : '')));
        const status = el('td', movement.direction === 'in' ? 'Inflow' : movement.direction === 'out' ? 'Outflow' : 'No change'); status.append(el('span', movement.status || 'unknown', 'status-tag ' + (['success', 'failed', 'unknown'].includes(movement.status) ? movement.status : 'unknown'))); row.append(status); $('ledger-rows').append(row);
      }
      $('ledger-message').hidden = !!result.rows?.length;
      $('ledger-message').textContent = state.total ? 'No movements on this page. Use Previous or reset filters.' : 'No movements match these filters. Reset filters to see the full capture.';
      $('row-count').textContent = state.total + ' matching movements';
      const limit = parseInt($('page-size').value, 10), start = state.total ? state.offset + 1 : 0, end = Math.min(state.offset + (result.rows || []).length, state.total);
      $('page-context').textContent = start + '–' + end + ' of ' + state.total;
      $('previous-page').disabled = state.offset === 0; $('next-page').disabled = state.offset + limit >= state.total;
      message('Capture loaded. Select a signature to inspect its source evidence.');
    } catch (error) {
      if (request !== state.movementRequest || generation !== state.generation) return;
      $('ledger-rows').replaceChildren(); $('row-count').textContent = 'Movements unavailable'; $('ledger-message').textContent = 'Could not load movements. Reset filters or refresh this wallet to retry.'; message(error.message, true);
    } finally { if (request === state.movementRequest) $('ledger-table').setAttribute('aria-busy', 'false'); }
  }
  async function compare() {
    const before = $('compare-before').value, after = $('compare-after').value;
    if (!before || !after || before === after) { $('compare-result').textContent = 'Choose two different captures to compare.'; return; }
    const request = ++state.comparisonRequest; $('compare-submit').disabled = true; $('compare-result').textContent = 'Comparing evidence…';
    try {
      const result = await state.api.get('compare', {before, after}); if (request !== state.comparisonRequest) return;
      $('compare-result').replaceChildren();
      for (const [key, title] of [['added_signatures', 'Added signatures'], ['removed_signatures', 'Removed signatures'], ['changed_signatures', 'Changed signatures']]) {
        const items = result[key] || [], group = el('div', undefined, 'diff-group'); group.append(el('h3', title + ' · ' + items.length));
        if (items.length) { const list = el('ul'); for (const item of items) list.append(el('li', typeof item === 'string' ? item : JSON.stringify(item))); group.append(list); }
        else group.append(el('p', 'None observed.')); $('compare-result').append(group);
      }
      const pre = el('pre', JSON.stringify(result.assets || [], null, 2)); pre.className = 'comparison-assets'; pre.setAttribute('aria-label', 'Per-asset comparison amounts'); $('compare-result').append(el('h3', 'Per-asset change · exact base units'), pre);
    } catch (error) { if (request === state.comparisonRequest) $('compare-result').textContent = error.message; }
    finally { if (request === state.comparisonRequest) $('compare-submit').disabled = false; }
  }
  function download(text, filename, type) {
    const url = URL.createObjectURL(new Blob([text], {type})), link = el('a'); link.href = url; link.download = filename; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function exportCapture(format) {
    if (!state.capture) return;
    if (state.api.mode === 'local') {
      const link = el('a'); link.href = 'api/export?' + new URLSearchParams({capture_id: state.capture.id, format}); link.download = 'ledger.' + format; link.click();
    } else download(format === 'csv' ? ledgerCSV(ledgerRows(state.capture)) : JSON.stringify(state.capture.ledger || {rows: ledgerRows(state.capture)}, null, 2), 'capture-' + state.capture.id + '-ledger.' + format, format === 'csv' ? 'text/csv;charset=utf-8' : 'application/json');
  }
  async function submit(form, feedbackId, action) {
    const button = form.querySelector('button[type=submit]'); button.disabled = true; $(feedbackId).textContent = 'Working…'; $(feedbackId).classList.remove('error');
    try { const text = await action(); $(feedbackId).textContent = text; }
    catch (error) { $(feedbackId).textContent = error.message; $(feedbackId).classList.add('error'); }
    finally { button.disabled = state.api.mode !== 'local' || (form.id === 'job-form' && !state.api.captureEnabled); }
  }
  async function refreshJobs() {
    if (!state.api || state.api.mode !== 'local') { $('jobs-status').textContent = 'Live jobs are available only in a local workspace.'; return; }
    try {
      const {jobs = []} = await state.api.get('jobs');
      const newlyCompleted = jobs.some(job => job.capture_id && state.jobs.some(old => old.id === job.id && !old.capture_id));
      state.jobs = jobs; $('job-list').replaceChildren();
      $('jobs-status').textContent = jobs.length ? 'Local job state · refreshes every 5 seconds while this page is visible.' : 'No background jobs. Start a capture to collect evidence.';
      for (const job of jobs) {
        const item = el('li'), status = ['queued', 'running', 'succeeded', 'partial', 'failed', 'cancelled', 'interrupted', 'completed', 'pending'].includes(job.status) ? job.status : 'unknown';
        item.append(el('span', '#' + job.id + ' · ' + status, 'job-state'), el('span', 'Wallet #' + job.wallet_id + ' · limit ' + job.limit));
        if (job.error) item.append(el('span', job.error, 'muted'));
        if (job.capture_id) { const button = el('button', 'Open capture #' + job.capture_id); button.addEventListener('click', () => loadWallets(job.wallet_id, job.capture_id).catch(error => message(error.message, true))); item.append(button); }
        $('job-list').append(item);
      }
      if (newlyCompleted) message('A background capture completed. Open it from the job list.');
    } catch (error) { $('jobs-status').textContent = 'Could not refresh jobs: ' + error.message; }
  }
  let searchTimer;
  function scheduleFilter() { clearTimeout(searchTimer); state.offset = 0; searchTimer = setTimeout(loadMovements, 220); }
  $('filter-form').addEventListener('submit', event => { event.preventDefault(); clearTimeout(searchTimer); state.offset = 0; loadMovements(); });
  $('search').addEventListener('input', scheduleFilter);
  for (const id of ['asset-filter', 'direction-filter', 'status-filter', 'page-size']) $(id).addEventListener('change', () => { clearTimeout(searchTimer); state.offset = 0; loadMovements(); });
  $('reset-filters').addEventListener('click', () => { clearTimeout(searchTimer); $('filter-form').reset(); state.offset = 0; loadMovements(); });
  $('previous-page').addEventListener('click', () => { state.offset = Math.max(0, state.offset - parseInt($('page-size').value, 10)); loadMovements(); });
  $('next-page').addEventListener('click', () => { state.offset += parseInt($('page-size').value, 10); loadMovements(); });
  $('capture-select').addEventListener('change', () => selectCapture($('capture-select').value).catch(error => message(error.message, true)));
  $('refresh-wallets').addEventListener('click', () => loadWallets().catch(error => message(error.message, true)));
  $('refresh-jobs').addEventListener('click', refreshJobs);
  $('export-csv').addEventListener('click', () => exportCapture('csv')); $('export-json').addEventListener('click', () => exportCapture('json'));
  $('compare-form').addEventListener('submit', event => { event.preventDefault(); compare(); });
  $('rail-toggle').addEventListener('click', () => { const open = $('wallet-panel').classList.toggle('open'); $('rail-toggle').setAttribute('aria-expanded', String(open)); $('rail-toggle').textContent = open ? 'Hide wallets' : 'Show wallets'; });
  $('wallet-form').addEventListener('submit', event => {
    event.preventDefault(); submit(event.currentTarget, 'wallet-feedback', async () => {
      const result = await state.api.post('wallets', {address: $('wallet-address').value.trim(), cluster: $('wallet-cluster').value, label: $('wallet-label').value});
      const wallet = result.wallet || result; await loadWallets(wallet.id); return 'Wallet registered and verified in the workspace.';
    });
  });
  $('import-form').addEventListener('submit', event => {
    event.preventDefault(); submit(event.currentTarget, 'import-feedback', async () => {
      const file = $('import-file').files[0]; if (!file) throw new Error('Choose a snapshot JSON file.');
      if (file.size > 16 * 1024 * 1024 - 1024) throw new Error('Snapshot is too large for the 16 MiB local API limit.');
      const raw = await file.text();
      try { JSON.parse(raw); } catch (_) { throw new Error('Invalid JSON. Choose a schema-v1 snapshot file.'); }
      // Syntax checking above must never reconstruct evidence: the server needs
      // original integer lexemes and duplicate keys for strict validation.
      const result = await state.api.importSnapshot(raw, $('import-label').value);
      const capture = result.capture || result; await loadWallets(capture.wallet_id, capture.id); return 'Snapshot imported. Saved capture reloaded from the workspace.';
    });
  });
  $('job-form').addEventListener('submit', event => {
    event.preventDefault(); submit(event.currentTarget, 'job-feedback', async () => {
      if (!state.wallet) throw new Error('Select or register a wallet first.');
      const result = await state.api.post('jobs', {wallet_id: state.wallet.id, limit: parseInt($('job-limit').value, 10), include_tokens: $('include-tokens').checked});
      await refreshJobs(); return 'Capture job #' + (result.job?.id || result.id || 'queued') + ' submitted. Follow its state below.';
    });
  });
  async function initialize() {
    $('retry').hidden = true; message('Connecting to workspace…');
    try {
      state.api = await createAdapter({fetch: root.fetch.bind(root), staticMode: root.document.documentElement.dataset.mode === 'static'});
      const local = state.api.mode === 'local'; $('mode-label').textContent = local ? 'Local workspace · read-only RPC' : 'Read-only static demonstration'; $('static-notice').hidden = local;
      $('wallet-fields').disabled = !local; $('import-fields').disabled = !local; $('job-fields').disabled = !state.api.captureEnabled; $('refresh-jobs').disabled = !local;
      if (local && !state.api.captureEnabled) $('rpc-help').textContent = 'Live capture is disabled: no server RPC endpoint is configured. Start solana-flow serve with SOLANA_FLOW_RPC_URL set (or --rpc-url). Never paste endpoint credentials into this page.';
      await Promise.all([loadWallets(), refreshJobs()]);
      clearInterval(state.timer); if (local) state.timer = setInterval(() => { if (!root.document.hidden) refreshJobs(); }, 5000);
    } catch (error) { message('Workspace unavailable: ' + error.message, true); $('retry').hidden = false; $('wallet-list').replaceChildren(el('p', 'Workspace could not be loaded. Retry the connection.')); }
  }
  $('retry').addEventListener('click', initialize);
  root.addEventListener('pagehide', () => clearInterval(state.timer));
  initialize();
})(typeof window !== 'undefined' ? window : globalThis);
