import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('A 股和加密货币都按日线、60 分钟、5 分钟展示周期层级', async () => {
  const source = await readFile(new URL('./DataView.vue', import.meta.url), 'utf8');
  const periods = ['日线', '60 分钟', '5 分钟'];
  const positions = periods.map(label => source.indexOf(`label: '${label}'`));

  assert.ok(positions.every(position => position >= 0));
  assert.deepEqual(positions, [...positions].sort((left, right) => left - right));
  assert.match(source, /const activePeriods = reactive\(\{ ashare: '60', crypto: '60' \}\)/);
  assert.match(source, /key: '5'.+disabled: true/);
  assert.equal(source.match(/aria-label="行情周期"/g)?.length, 2);
  assert.match(source, /activePeriods\.ashare/);
  assert.match(source, /activePeriods\.crypto/);
});

test('日线未接入时不复用 60 分钟行情面板', async () => {
  const source = await readFile(new URL('./DataView.vue', import.meta.url), 'utf8');

  assert.match(source, /v-show="activePeriods\.ashare === '60'"/);
  assert.match(source, /v-show="activePeriods\.crypto === '60'"/);
  assert.match(source, /本地 A 股日线行情尚未接入/);
  assert.match(source, /本地加密货币日线行情尚未接入/);
});
