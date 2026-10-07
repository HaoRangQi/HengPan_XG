import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import { historyQuery, historyLink, hitIdentity, hitMarks, cleanupPayload } from './historyPresentation.js';

test('历史默认按标的展示、A 股、日内周期，不强制今天', () => {
  assert.deepEqual(historyQuery({}), { market: 'a', view: 'symbols', intraday: true, page: 1, page_size: 20 });
  const daily = historyQuery({ market: 'crypto', period: 'd', kind: 'hengpan_u', code: ' BTCUSDT ' });
  assert.equal(daily.frequency, 'd');
  assert.equal(daily.code, 'BTCUSDT');
  assert.equal(historyQuery({ period: 'all' }).intraday, false);
});

test('四个扫描页链接保留市场和扫描类型', () => {
  assert.equal(historyLink('hengpan_a'), '#/history?market=a&kind=hengpan_a');
  assert.equal(historyLink('platform_u'), '#/history?market=crypto&kind=platform_u');
});

test('股票与交易对使用统一展示身份，但不改原结果', () => {
  assert.deepEqual(hitIdentity({ symbol: 'BTCUSDT', base_asset: 'BTC' }), { code: 'BTCUSDT', name: 'BTC' });
  assert.deepEqual(hitIdentity({ code: 'sh.600519', name: '贵州茅台' }), { code: 'sh.600519', name: '贵州茅台' });
});

test('历史图可按命中规则分别展示上下轨，平台保留原标线', () => {
  const hit = { matches: { '1': { upper: 12, lower: 10 }, '2': { upper: 15, lower: 9 } } };
  assert.deepEqual(hitMarks(hit, '2').map(line => line.value), [15, 9]);
  assert.deepEqual(hitMarks({ mark_lines: [{ value: 3 }] }), [{ value: 3 }]);
});

test('清理以预览为默认，体积单位明确换算', () => {
  assert.deepEqual(cleanupPayload({ mode: 'size', value: 100, kind: 'hengpan_a' }),
    { max_kline_bytes: 104857600, kind: 'hengpan_a', apply: false });
});

test('所有清理策略填 0 都可预览清空指定范围', () => {
  for (const [mode, key] of Object.entries({ count: 'keep_count', days: 'keep_days', size: 'max_kline_bytes' })) {
    assert.deepEqual(cleanupPayload({ mode, value: 0 }), { [key]: 0, apply: false });
    assert.deepEqual(cleanupPayload({ mode, value: '0', kind: 'hengpan_u' }),
      { [key]: 0, kind: 'hengpan_u', apply: false });
  }
});

test('清理拒绝空输入和无效保留数量，防止误清空', () => {
  for (const mode of ['count', 'days', 'size']) {
    for (const value of ['', ' ', null, undefined, false, -1, 0.5, NaN]) {
      assert.throws(() => cleanupPayload({ mode, value }), `${mode} 应拒绝 ${String(value)}`);
    }
  }
});

test('历史入口和页面已接入，保留四个旧详情加载路径', async () => {
  const app = await readFile(new URL('../App.vue', import.meta.url), 'utf8');
  assert.match(app, /'\/history':.*component: HistoryView/);
  for (const path of ['../hengpan/HengpanScanView.vue', '../hengpan/CryptoHengpanScanView.vue', './ScanView.vue', './CryptoScanView.vue']) {
    const source = await readFile(new URL(path, import.meta.url), 'utf8');
    assert.match(source, /<HistoryLink kind="(?:hengpan|platform)_[au]"/);
    assert.match(source, /async function loadHistory/);
    assert.match(source, /onActivated\(loadHistories\)/);
  }
  const history = await readFile(new URL('./HistoryView.vue', import.meta.url), 'utf8');
  assert.match(history, /class="segmented"/);
  assert.doesNotMatch(history, /\b(?:seg-group|btn-quiet|tag-primary|class="select")\b/);
  assert.doesNotMatch(history, /@media|\b(?:sm|md|lg):/);
});
