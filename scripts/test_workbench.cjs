'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
let flow = {};
try { flow = require('../src/solana_flow/assets/workbench.js'); } catch (error) { if (error.code !== 'MODULE_NOT_FOUND') throw error; }

const response = (value, status = 200) => new Response(JSON.stringify(value), {status, headers:{'Content-Type':'application/json'}});

const rows = [
  {signature:'sig-A',asset:'SOL',mint:null,decimals:9,amount_base_units:'9007199254740993001',decimal_amount:'9007199254.740993001',direction:'in',status:'success',time:1767229200},
  {signature:'sig-B',asset:'SOL',mint:null,decimals:9,amount_base_units:'-1',decimal_amount:'-0.000000001',direction:'out',status:'failed',time:null},
  {signature:'sig-C',asset:'SPL',mint:'mint-1',decimals:6,amount_base_units:'2',decimal_amount:'0.000002',direction:'in',status:'unknown',time:1767229200}
];
test('movement filters intersect, search case-insensitively, then paginate', () => {
  assert.equal(typeof flow.filterMovements, 'function');
  assert.deepEqual(flow.filterMovements(rows,{asset:'SOL',direction:'out',status:'failed',search:'SIG-b',limit:50,offset:0}).rows,[rows[1]]);
  const page=flow.filterMovements(rows,{limit:1,offset:1});
  assert.equal(page.total,3); assert.deepEqual(page.rows,[rows[1]]);
  assert.equal(flow.filterMovements(rows,{search:'no match'}).total,0);
  assert.equal(flow.filterMovements(rows,{asset:'mint-1'}).total,1);
});

test('analytics aggregate exact base units separately by mint and decimals, include unknown dates', () => {
  assert.equal(typeof flow.analytics, 'function');
  const result=flow.analytics({synthetic:true,partial:true,ledger:{rows,transaction_count:3,failed_count:1,wallet_paid_fees_base_units:'1',gaps:[{}]}});
  assert.equal(result.assets[0].net_base_units,'9007199254740993000');
  assert.equal(result.assets[0].net,'9007199254.740993000');
  assert.equal(result.assets[0].outflow,'0.000000001');
  assert.equal(result.assets.length,2); assert.equal(result.failed_count,1); assert.equal(result.gap_count,1);
  assert.equal(result.synthetic,true); assert.equal(result.partial,true);
  assert.ok(result.daily.some(item=>item.date==='Unknown'));
});

test('capture comparison counts distinct signatures and exact per-asset deltas', () => {
  assert.equal(typeof flow.compareCaptures,'function');
  const result=flow.compareCaptures({ledger:{rows:rows.slice(0,2)}},{ledger:{rows:[{...rows[0],amount_base_units:'3'},rows[2]]}});
  assert.deepEqual(result.added_signatures,['sig-C']); assert.deepEqual(result.removed_signatures,['sig-B']);
  assert.deepEqual(result.changed_signatures,['sig-A']);
  assert.equal(result.assets[0].delta_base_units,'-9007199254740992997');
});
test('inspector returns only the selected transaction balance evidence', () => {
  assert.equal(typeof flow.evidenceFor,'function');
  const transaction={signature:'sig-A',transaction:{message:{accountKeys:['wallet']}},meta:{preBalances:[1],postBalances:[2],fee:1,err:null,logMessages:['secret-provider-log']}};
  const evidence=flow.evidenceFor({snapshot:{transactions:[transaction,{signature:'other'}]}},rows[0]);
  assert.deepEqual(evidence.meta.preBalances,[1]); assert.equal(evidence.meta.logMessages,undefined);
  assert.equal(flow.evidenceFor({snapshot:{}},rows[0]).unavailable,true);
});

test('local adapter uses relative API paths and session token for writes', async () => {
  assert.equal(typeof flow.createAdapter,'function');
  const calls=[];
  const api=await flow.createAdapter({fetch:async(url,options={})=>{ calls.push([url,options]); return response(url==='api/session'?{token:'local-token',mode:'local'}:{wallets:[]}); }});
  await api.get('wallets'); await api.post('wallets',{address:'abc',cluster:'devnet',label:'name'});
  assert.equal(api.mode,'local'); assert.equal(calls[1][0],'api/wallets');
  assert.equal(calls[2][1].headers['X-Solana-Flow-Token'],'local-token');
  assert.deepEqual(JSON.parse(calls[2][1].body),{address:'abc',cluster:'devnet',label:'name'});
});
test('static adapter never posts and scopes movements, summaries and comparison', async () => {
  assert.equal(typeof flow.createAdapter,'function');
  const data={wallets:[{id:1}],captures:[{id:1,wallet_id:1,ledger:{rows:rows.slice(0,2)}},{id:2,wallet_id:1,ledger:{rows}}],jobs:[]};
  const calls=[];
  const api=await flow.createAdapter({staticMode:true,fetch:async url=>{calls.push(url); return response(data);}});
  assert.deepEqual(calls,['demo-data.json']);
  assert.equal((await api.get('movements',{wallet_id:1,capture_id:2,asset:'SOL'})).total,2);
  assert.equal((await api.get('analytics',{capture_id:2})).row_count,3);
  assert.deepEqual((await api.get('compare',{before:1,after:2})).added_signatures,['sig-C']);
  await assert.rejects(api.post('jobs',{}),/read-only/i);
  await assert.rejects(api.importSnapshot('{"slot":9007199254740993}', 'demo'),/read-only/i);
  assert.deepEqual(calls,['demo-data.json']);
  await assert.rejects(api.get('captures/99'),/not found/i);
});
test('session 404 falls back to demo; other failures do not silently become demo', async () => {
  assert.equal(typeof flow.createAdapter,'function');
  const fallback=await flow.createAdapter({fetch:async url=>url==='api/session'?response({error:'Not found'},404):response({wallets:[],captures:[]})});
  assert.equal(fallback.mode,'static');
  await assert.rejects(flow.createAdapter({fetch:async()=>response({error:'Local service unavailable'},503)}),/Local service unavailable/);
});

if (process.env.WORKBENCH_BROWSER_TESTS === '1') test('browser: static investigation, evidence, filters, exports and read-only controls', async () => {
  const fs=require('node:fs'); const path=require('node:path');
  const {chromium}=require('@playwright/test');
  const browser=await chromium.launch({headless:true});
  try {
    const page=await browser.newPage(); const errors=[]; page.on('pageerror',error=>errors.push(error.message));
    const data={wallets:[{id:1,label:'Investigation wallet',address:'wallet-A',cluster:'synthetic'}],captures:[{id:1,wallet_id:1,label:'First capture',synthetic:true,captured_at:'2026-01-01T00:00:00Z',ledger:{rows},snapshot:{transactions:[{signature:'sig-A',slot:'EXACT_SLOT',meta:{preBalances:['EXACT_PRE'],postBalances:['EXACT_POST']},transaction:{message:{accountKeys:['wallet-A']}}}]}}]};
    await page.route('http://workbench.test/**',async route=>{
      const file=new URL(route.request().url()).pathname.split('/').pop();
      if(file==='demo-data.json') return route.fulfill({contentType:'application/json',body:JSON.stringify(data).replace('"EXACT_SLOT"','9007199254740993').replace('"EXACT_PRE"','18446744073709551615').replace('"EXACT_POST"','18446744073709551614')});
      if(file==='session') return route.fulfill({status:404,json:{error:'Not found'}});
      const name=file||'workbench.html';
      const target=path.join(__dirname,'../src/solana_flow/assets',name);
      if(!fs.existsSync(target)) return route.fulfill({status:404,body:'Missing frontend'});
      return route.fulfill({path:target,contentType:name.endsWith('.js')?'application/javascript':name.endsWith('.css')?'text/css':'text/html'});
    });
    await page.goto('http://workbench.test/');
    await page.locator('#row-count').filter({hasText:'3'}).waitFor();
    assert.match(await page.locator('#provenance').innerText(),/SYNTHETIC/);
    await page.getByRole('button',{name:'Inspect sig-A',exact:true}).click();
    assert.match(await page.locator('#evidence-json').innerText(),/preBalances/);
    for(const exact of ['9007199254740993','18446744073709551615','18446744073709551614']) assert.ok((await page.locator('#evidence-json').innerText()).includes(exact));
    await page.locator('#search').fill('not-present');
    await page.locator('#ledger-message').filter({hasText:'No movements match'}).waitFor();
    await page.getByRole('button',{name:'Reset filters'}).click();
    await page.locator('#row-count').filter({hasText:'3'}).waitFor();
    assert.equal(await page.locator('#import-submit').isDisabled(),true);
    assert.equal(await page.locator('#job-submit').isDisabled(),true);
    assert.equal(await page.locator('#register-submit').isDisabled(),true);
    const download=page.waitForEvent('download'); await page.locator('#export-json').click();
    assert.match((await download).suggestedFilename(),/json$/);
    assert.deepEqual(errors,[]);
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
  } finally { await browser.close(); }
});

async function withLocalWorkbench(check) {
  const fs=require('node:fs'), path=require('node:path');
  const {chromium}=require('@playwright/test');
  const browser=await chromium.launch({headless:true});
  try {
    const page=await browser.newPage(), posts=[], errors=[];
    page.setDefaultTimeout(5000); page.on('pageerror',error=>errors.push(error.message));
    const wallet={id:1,label:'Synthetic test wallet',address:'wallet-A',cluster:'synthetic'};
    const captures=[{id:1,wallet_id:1,label:'Earlier import, later source time',captured_at:'2026-10-10T00:00:00Z',ledger:{rows}},
      {id:2,wallet_id:1,label:'Latest import, older source time',captured_at:'2026-01-01T00:00:00Z',ledger:{rows}}];
    await page.route('http://workbench.test/**',async route=>{
      const url=new URL(route.request().url()), api=url.pathname.replace(/^\/api\//,'');
      if(url.pathname.startsWith('/api/')) {
        if(api==='session') return route.fulfill({json:{token:'browser-token',capture_enabled:false}});
        if(api==='wallets') return route.fulfill({json:{wallets:[wallet]}});
        if(api==='captures') return route.fulfill({json:{captures}});
        if(api.startsWith('captures/')) return route.fulfill({json:captures.find(item=>String(item.id)===api.split('/')[1])});
        if(api==='analytics') return route.fulfill({json:flow.analytics(captures[0])});
        if(api==='movements') return route.fulfill({json:flow.filterMovements(rows,Object.fromEntries(url.searchParams))});
        if(api==='jobs') return route.fulfill({json:{jobs:[{id:7,wallet_id:1,status:'partial',capture_id:2,limit:20}]}});
        if(api==='import') {
          const body=route.request().postData(); posts.push(body);
          if((body.match(/"slot"/g)||[]).length>1) return route.fulfill({status:400,json:{error:'Duplicate JSON key: slot'}});
          return route.fulfill({json:{capture:captures[1]}});
        }
        return route.fulfill({status:404,json:{error:'Missing test route'}});
      }
      const name=url.pathname.split('/').pop()||'workbench.html', target=path.join(__dirname,'../src/solana_flow/assets',name);
      if(!fs.existsSync(target)) return route.fulfill({status:404,body:'Missing frontend'});
      return route.fulfill({path:target,contentType:name.endsWith('.js')?'application/javascript':name.endsWith('.css')?'text/css':'text/html'});
    });
    await page.goto('http://workbench.test/');
    await page.locator('#row-count').filter({hasText:'3 matching'}).waitFor();
    await check({page,posts}); assert.deepEqual(errors,[]);
  } finally { await browser.close(); }
}

if (process.env.WORKBENCH_BROWSER_TESTS === '1') test('browser: import keeps unsafe integers and duplicate keys; malformed JSON never posts', async () => {
  await withLocalWorkbench(async ({page,posts})=>{
    await page.getByText('Import snapshot JSON',{exact:true}).click();
    const upload=async raw=>{
      await page.locator('#import-file').setInputFiles({name:'snapshot.json',mimeType:'application/json',buffer:Buffer.from(raw)});
      await page.locator('#import-submit').click();
    };
    await upload('{invalid');
    await page.locator('#import-feedback').filter({hasText:'Invalid JSON'}).waitFor();
    assert.equal(posts.length,0);
    const label='evidence " label'; await page.locator('#import-label').fill(label);
    const raw=' {"slot":9007199254740993,"preBalances":[18446744073709551615],"slot":9007199254740995} ';
    await upload(raw);
    await page.waitForFunction(()=>document.getElementById('import-feedback').textContent!=='Working…');
    assert.deepEqual(posts,['{"snapshot":'+raw+',"label":'+JSON.stringify(label)+'}']);
    assert.match(await page.locator('#import-feedback').innerText(),/Duplicate JSON key: slot/);
    const valid=' {"slot":9007199254740993,"preBalances":[18446744073709551615]} ';
    await upload(valid);
    await page.locator('#import-feedback').filter({hasText:'Snapshot imported'}).waitFor();
    assert.equal(posts[1],'{"snapshot":'+valid+',"label":'+JSON.stringify(label)+'}');
    assert.equal(await page.locator('#capture-select').inputValue(),'2');
  });
});

if (process.env.WORKBENCH_BROWSER_TESTS === '1') test('browser: partial terminal jobs keep their status and open their capture', async () => {
  await withLocalWorkbench(async ({page})=>{
    assert.match(await page.locator('#job-list .job-state').innerText(),/#7 · partial/);
    await page.getByRole('button',{name:'Open capture #2',exact:true}).click();
    await page.locator('#capture-context').filter({hasText:'Capture #2'}).waitFor();
  });
});

if (process.env.WORKBENCH_BROWSER_TESTS === '1') test('browser: latest import wins over source timestamp and manual history remains selectable', async () => {
  await withLocalWorkbench(async ({page})=>{
    assert.equal(await page.locator('#capture-select').inputValue(),'2');
    assert.deepEqual(await page.locator('#capture-select option').evaluateAll(items=>items.map(item=>item.value)),['2','1']);
    assert.match(await page.locator('#capture-context').innerText(),/latest import/i);
    assert.equal(await page.locator('#compare-before').inputValue(),'1');
    assert.equal(await page.locator('#compare-after').inputValue(),'2');
    await page.locator('#capture-select').selectOption('1');
    await page.locator('#capture-context').filter({hasText:'Capture #1'}).waitFor();
    assert.doesNotMatch(await page.locator('#capture-context').innerText(),/latest import/i);
  });
});

test('CSV export preserves exact amounts and neutralizes spreadsheet text formulas', () => {
  assert.equal(typeof flow.ledgerCSV,'function');
  const csv=flow.ledgerCSV([{...rows[0],signature:'=HYPERLINK("x")',asset:' +CMD'}]);
  assert.ok(csv.includes('9007199254.740993001')); assert.ok(csv.includes("'=HYPERLINK")); assert.ok(csv.includes("' +CMD"));
});

test('comparison includes unavailable and zero-movement source signatures and changed metadata', () => {
  const before={ledger:{rows:[rows[0]]},snapshot:{transactions:[{transaction:{signatures:['sig-A']},meta:{fee:1}}],unavailable_signatures:['gap-only']}};
  const after={ledger:{rows:[rows[0]]},snapshot:{transactions:[{transaction:{signatures:['sig-A']},meta:{fee:2}},{transaction:{signatures:['zero-row']},meta:{fee:0}}],unavailable_signatures:[]}};
  const result=flow.compareCaptures(before,after);
  assert.deepEqual(result.changed_signatures,['sig-A']); assert.deepEqual(result.added_signatures,['zero-row']); assert.deepEqual(result.removed_signatures,['gap-only']);
});
test('static daily analytics expose per-asset movement counts, not misleading transaction counts', () => {
  const daily=flow.analytics({ledger:{rows}}).daily;
  assert.equal(daily.find(item=>item.asset==='SOL').count,1);
  assert.equal(daily.find(item=>item.asset==='SPL').net,'0.000002');
  assert.ok(daily.some(item=>item.date==='Unknown'));
});

test('filters match backend search semantics: identifiers only, zero direction', () => {
  assert.equal(flow.filterMovements(rows,{search:'9007199254.740993001'}).total,0);
  assert.equal(flow.filterMovements([{...rows[0],direction:'zero'}],{direction:'zero'}).total,1);
  assert.equal(flow.filterMovements(rows,{search:'mint-1'}).total,1);
});
test('local adapter exposes capture availability supplied by session', async () => {
  const api=await flow.createAdapter({fetch:async()=>response({token:'token',mode:'local',capture_enabled:false})});
  assert.equal(api.captureEnabled,false);
});

test('static search does not match across identifier field boundaries', () => {
  assert.equal(flow.filterMovements(rows,{search:'sig-A SOL'}).total,0);
});

test('snapshot import transmits original JSON lexemes and duplicate keys with escaped label', async () => {
  const calls=[];
  const api=await flow.createAdapter({fetch:async(url,options={})=>{
    calls.push([url,options]); return response(url==='api/session'?{token:'import-token'}:{capture:{id:1}});
  }});
  const raw=' {"slot":9007199254740993,"preBalances":[18446744073709551615],"slot":9007199254740995} \n';
  const label='quote " and newline\n';
  await api.importSnapshot(raw,label);
  assert.equal(calls[1][0],'api/import');
  assert.equal(calls[1][1].method,'POST');
  assert.equal(calls[1][1].headers['X-Solana-Flow-Token'],'import-token');
  assert.equal(calls[1][1].body,'{"snapshot":'+raw+',"label":'+JSON.stringify(label)+'}');
});

test('lossless JSON decoding preserves unsafe numeric lexemes without changing strings or safe numbers', () => {
  const text=String.raw`{"slot":9007199254740993,"negative":-9007199254740993,"max":9007199254740991,"min":-9007199254740991,"next":9007199254740992,"zero":0,"decimal":1.25,"small":1e-3,"safeExponent":1e3,"largeExponent":1e30,"overflow":1e400,"largeFraction":9007199254740993.5,"amount":"9007199254740993001","escaped":"quote: \"9007199254740993\" slash: \\ end","array":[null,true,18446744073709551615]}`;
  const parsed=flow.parseLosslessJSON(text);
  assert.equal(parsed.slot,'9007199254740993'); assert.equal(parsed.negative,'-9007199254740993');
  assert.equal(parsed.max,Number.MAX_SAFE_INTEGER); assert.equal(parsed.min,Number.MIN_SAFE_INTEGER);
  assert.equal(parsed.next,'9007199254740992'); assert.equal(parsed.zero,0);
  assert.equal(parsed.decimal,1.25); assert.equal(parsed.small,0.001); assert.equal(parsed.safeExponent,1000);
  assert.equal(parsed.largeExponent,'1e30'); assert.equal(parsed.overflow,'1e400');
  assert.equal(parsed.largeFraction,'9007199254740993.5');
  assert.equal(parsed.amount,'9007199254740993001');
  assert.equal(parsed.escaped,JSON.parse(text).escaped);
  assert.deepEqual(parsed.array,[null,true,'18446744073709551615']);
  for (const malformed of ['{9007199254740993:0}','[01]','[1e]','[1.]','[NaN]','[Infinity]','{"a":"unterminated}',String.raw`["\q"]`,'[1,]']) {
    assert.throws(()=>flow.parseLosslessJSON(malformed),SyntaxError,malformed);
  }
});

test('local and static capture responses preserve exact slot and native balance evidence', async () => {
  const raw='{"id":1,"wallet_id":1,"snapshot":{"transactions":[{"signature":"sig-A","slot":9007199254740993,"meta":{"preBalances":[18446744073709551615],"postBalances":[18446744073709551614]}}]},"ledger":{"rows":[]}}';
  for (const staticMode of [false,true]) {
    const api=await flow.createAdapter({staticMode,fetch:async url=>url==='api/session'?response({token:'x'}):new Response(staticMode?'{"captures":['+raw+']}':raw)});
    const capture=await api.get('captures/1');
    const evidence=flow.evidenceFor(capture,rows[0]);
    assert.equal(evidence.slot,'9007199254740993');
    assert.deepEqual(evidence.meta.preBalances,['18446744073709551615']);
    assert.deepEqual(evidence.meta.postBalances,['18446744073709551614']);
    assert.ok(JSON.stringify(evidence).includes('18446744073709551615'));
  }
});

test('comparison signature lists sort deterministically regardless of source order', () => {
  const tx=(signature,fee)=>({signature,meta:{fee}});
  const before={snapshot:{transactions:[tx('z-removed',1),tx('z-changed',1),tx('a-removed',1),tx('a-changed',1)]}};
  const after={snapshot:{transactions:[tx('z-added',1),tx('z-changed',2),tx('a-added',1),tx('a-changed',2)]}};
  const result=flow.compareCaptures(before,after);
  assert.deepEqual(result.added_signatures,['a-added','z-added']);
  assert.deepEqual(result.removed_signatures,['a-removed','z-removed']);
  assert.deepEqual(result.changed_signatures,['a-changed','z-changed']);
});

test('base units format exactly beyond floating point range', () => {
  assert.equal(typeof flow.formatUnits, 'function');
  assert.equal(flow.formatUnits('900719925474099312345', 9), '900719925474.099312345');
  assert.equal(flow.formatUnits('-1', 9), '-0.000000001');
  assert.equal(flow.formatUnits('0', 6), '0.000000');
  assert.equal(flow.formatUnits('42', 0), '42');
  assert.equal(flow.formatUnits('bad', 9), 'Unknown');
});
