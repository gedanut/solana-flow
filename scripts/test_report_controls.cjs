// Execute the actual offline controls against a small DOM interface.
// This is a logic test, not a substitute for browser layout verification.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
function control() {
  return { value: '', handlers: {}, addEventListener(event, callback) { this.handlers[event] = callback; } };
}
const elements = Object.fromEntries(['search', 'asset', 'direction', 'status', 'row-count', 'empty']
  .map(id => [id, control()]));
const rows = [
  {textContent: 'signature-one SOL 0.100', dataset: {asset: 'SOL', direction: 'in', status: 'success'}},
  {textContent: 'signature-two SOL -0.002', dataset: {asset: 'SOL', direction: 'out', status: 'failed'}},
  {textContent: 'signature-three SPL:mint 0', dataset: {asset: 'SPL:mint', direction: 'zero', status: 'success'}}
];
vm.runInNewContext(fs.readFileSync('src/solana_flow/assets/report.js', 'utf8'), {
  document: {getElementById: id => elements[id], querySelectorAll: () => rows}
});
const visible = () => rows.filter(row => !row.hidden).length;
function set(id, value) { elements[id].value = value; elements[id].handlers.input(); }
assert.equal(visible(), 3);
set('status', 'failed'); assert.equal(visible(), 1);
set('direction', 'in'); assert.equal(visible(), 0); assert.equal(elements.empty.hidden, false);
set('status', ''); assert.equal(visible(), 1);
set('direction', ''); set('asset', 'SPL:mint'); assert.equal(visible(), 1);
set('search', 'SIGNATURE-THREE'); assert.equal(visible(), 1);
set('search', 'missing'); assert.equal(visible(), 0);
set('asset', ''); set('search', ''); set('direction', 'zero'); assert.equal(visible(), 1);
assert.equal(elements['row-count'].textContent, '1 of 3 ledger rows');
console.log('Report controls: 10 assertions passed.');
