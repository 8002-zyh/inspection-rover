// Execute the actual native-injected JS, without a WebView, HTTP, or hardware.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('android/app/src/main/java/cn/rtrc/patrol/MainActivity.java', 'utf8');
const declaration = source.match(/private static final String STOP_JS =([\s\S]*?);\r?\n/)[1];
const script = declaration.match(/"(?:[^"\\]|\\.)*"/g).map(JSON.parse).join('');

for (const state of [
  {lease: null, routeWatchToken: null, expected: 0},
  {lease: 'active-manual-test', routeWatchToken: null, expected: 1},
  {lease: null, routeWatchToken: 'active-route-test', expected: 1},
]) {
  let calls = 0;
  const context = {lease: state.lease, routeWatchToken: state.routeWatchToken,
    heldKeys: new Set(['forward']), stop() { calls++; }};
  assert.equal(vm.runInNewContext(script, context), true);
  assert.equal(calls, state.expected);
  assert.equal(context.lease, null);
  assert.equal(context.routeWatchToken, null);
  assert.equal(context.heldKeys.size, 0);
}
let builtInCalls = 0;
assert.equal(vm.runInNewContext(script, {stop() {builtInCalls++;}}), true);
assert.equal(builtInCalls, 0, 'Do not send stop/401 on the pre-login document');
assert.equal(vm.runInNewContext(script, {lease:null,routeWatchToken:null,heldKeys:null}), false,
  'Unexpected document state must request a reload, not resume old controls');
console.log('PASS: native lifecycle JS clears manual/route state, skips pre-login stop, signals reload on invalid state');
