import test from 'node:test';
import assert from 'node:assert/strict';
import { createPollingSession, historySnapshot, drainResults } from './session.js';
test('polling never overlaps and stopped generations cannot apply', async () => {
  let release; let calls = 0; let context;
  const session = createPollingSession(async ctx => { calls++; context = ctx; await new Promise(resolve => { release = resolve; }); }, 1);
  session.start(); await new Promise(resolve => setTimeout(resolve, 8));
  assert.equal(calls, 1); session.stop(); assert.equal(context.current(), false); assert.equal(context.signal.aborted, true); release();
  await new Promise(resolve => setTimeout(resolve, 8)); assert.equal(calls, 1);
});
test('terminal drain replaces snapshot across pages', async () => {
  const offsets = [];
  const result = await drainResults('task', async url => { offsets.push(url); return { data: offsets.length === 1 ? { results: [{code:'a'}], next_offset: 1 } : { results: [{code:'b'}], next_offset: null } }; });
  assert.deepEqual(result.map(x => x.code), ['a', 'b']); assert.match(offsets[1], /offset=1/);
});
test('history normalization attaches lazy URLs and restores platform request', () => {
 const data = historySnapshot({run_id:'r', params:{windows:[5]}, results:[{code:'x'}]});
 assert.deepEqual(data.parameters, {windows:[5]}); assert.equal(data.results[0].kline_url, '/api/history/r/kline/x');
});
test('restarting polling invalidates old completion while a new task continues', async () => {
  const contexts = []; const releases = [];
  const session = createPollingSession(async context => { contexts.push(context); await new Promise(resolve => releases.push(resolve)); }, 100);
  session.start(); session.start();
  assert.equal(contexts[0].current(), false); assert.equal(contexts[1].current(), true);
  releases[0](); session.stop(); releases[1]();
});
test('terminal drain rejects a repeated page cursor', async () => {
  await assert.rejects(drainResults('task', async () => ({ data: { results: [], next_offset: 0 } })), /cursor/);
});
test('unexpected tick rejection is handled and a later poll retries', async () => {
 let calls = 0; const errors = [];
 const session = createPollingSession(async () => { if (++calls === 1) throw new Error('transient'); session.stop(); }, 1, error => errors.push(error.message));
 session.start(); await new Promise(resolve => setTimeout(resolve, 20));
 assert.equal(calls,2); assert.deepEqual(errors,['transient']);
});
