import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('主菜单按横盘、平台、工具顺序排列', async () => {
  const source = await readFile(new URL('./App.vue', import.meta.url), 'utf8');
  const labels = ['横盘-A', '横盘-U', '平台-A', '平台-U', '旧版', '数据', '接口', 'AI', '关于'];
  const positions = labels.map(label => source.indexOf(`short: '${label}'`));

  assert.ok(positions.every(position => position >= 0));
  assert.deepEqual(positions, [...positions].sort((left, right) => left - right));
  assert.match(source, /'\/crypto-a':/);
  assert.match(source, /'\/crypto-u':/);
  assert.match(source, /'\/ai':/);
  assert.match(source, /'\/platform':[^\n]+component: CryptoHengpanScanView/);
  assert.match(source, /'\/crypto-a':[^\n]+label: '平台-A'[^\n]+component: ScanView/);
  assert.match(source, /'\/crypto-u':[^\n]+label: '平台-U'[^\n]+component: CryptoScanView/);
  assert.match(source, /'\/ai':[^\n]+label: 'AI'[^\n]+component: ComingSoonView/);
  assert.match(source, /'\/about':[^\n]+label: '关于'[^\n]+component: AboutView/);
});

test('Baostock 数据源卡片展示请求和限制时长说明', async () => {
  const source = await readFile(new URL('./views/data/SourceDocsPanel.vue', import.meta.url), 'utf8');

  assert.match(source, /IP 日请求 5 万次/);
  assert.match(source, /限制时长 = 本年累计限制次数 × 6 小时/);
});

test('关于页展示作者并提供项目参考和 Baostock 知识库入口', async () => {
  const source = await readFile(new URL('./views/AboutView.vue', import.meta.url), 'utf8');

  assert.match(source, /作者[\s\S]*熊猫吃竹子[\s\S]*版本[\s\S]*1\.0\.0/);
  assert.match(source, /href="https:\/\/github\.com\/24mlight\/a-share-platform-stocks-selection"/);
  assert.match(source, /href="https:\/\/www\.baostock\.com\/mainContent\?file=stockKData\.md"/);
  assert.equal((source.match(/target="_blank"/g) || []).length, 2);
  assert.equal((source.match(/rel="noopener noreferrer"/g) || []).length, 2);
});

test('关于页用三步说明首次使用流程并明确数据库自动创建', async () => {
  const source = await readFile(new URL('./views/AboutView.vue', import.meta.url), 'utf8');

  assert.match(source, /操作指南[\s\S]*同步数据[\s\S]*运行扫描[\s\S]*查看与复盘/);
  assert.match(source, /数据库和数据表会自动创建/);
  assert.match(source, /\.reference-link\s*\{[^}]*text-decoration:\s*underline;/);
});
