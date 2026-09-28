import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('主菜单按横盘、平台、工具顺序排列', async () => {
  const source = await readFile(new URL('./App.vue', import.meta.url), 'utf8');
  const labels = ['横盘-A', '横盘-U', '平台-A', '平台-U', '旧版', '数据', '接口'];
  const positions = labels.map(label => source.indexOf(`short: '${label}'`));

  assert.ok(positions.every(position => position >= 0));
  assert.deepEqual(positions, [...positions].sort((left, right) => left - right));
  assert.match(source, /'\/crypto-a':/);
  assert.match(source, /'\/crypto-u':/);
  assert.match(source, /'\/platform':[^\n]+component: ComingSoonView/);
  assert.match(source, /'\/crypto-a':[^\n]+label: '平台-A'[^\n]+component: ScanView/);
  assert.match(source, /'\/crypto-u':[^\n]+label: '平台-U'[^\n]+component: ComingSoonView/);
});
