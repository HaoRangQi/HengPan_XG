import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('A 股数据管理按日线、60 分钟、5 分钟展示周期层级', async () => {
  const source = await readFile(new URL('./DataView.vue', import.meta.url), 'utf8');
  const periods = ['日线', '60 分钟', '5 分钟'];
  const positions = periods.map(label => source.indexOf(`label: '${label}'`));

  assert.ok(positions.every(position => position >= 0));
  assert.deepEqual(positions, [...positions].sort((left, right) => left - right));
  assert.match(source, /const activePeriod = ref\('60'\)/);
  assert.match(source, /key: '5'.+disabled: true/);
  assert.match(source, /aria-label="行情周期"/);
});

test('日线未接入时不复用 60 分钟行情面板', async () => {
  const source = await readFile(new URL('./DataView.vue', import.meta.url), 'utf8');

  assert.match(source, /v-show="activePeriod === '60'"/);
  assert.match(source, /本地日线行情尚未接入/);
});
