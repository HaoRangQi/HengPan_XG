import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('平台扫描默认选中标准窗口 60、80、100', async () => {
  const source = await readFile(new URL('./ScanView.vue', import.meta.url), 'utf8');
  assert.match(source, /\{ name: '标准', value: '60,80,100' \}/);
  assert.match(source, /windowsInput: '60,80,100'/);
});

test('基础条件把来源和窗口、周期和阈值拆成两行', async () => {
  const source = await readFile(new URL('./ScanView.vue', import.meta.url), 'utf8');
  assert.match(source, /class="base-conditions-primary"/);
  assert.match(source, /class="base-conditions-metrics"/);
});
