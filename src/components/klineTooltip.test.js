import test from 'node:test';
import assert from 'node:assert/strict';
import { calculateBarMetrics, formatKlineTooltip } from './klineTooltip.js';

test('K 线提示使用中文标签并计算涨跌幅和振幅', () => {
  const rows = [
    { date: '2026-09-24 11:30:00', open: 3.55, close: 3.60, low: 3.50, high: 3.65, volume: 10000 },
    { date: '2026-09-24 15:00:00', open: 3.65, close: 3.73, low: 3.64, high: 3.73, volume: 29548164 },
  ];

  const metrics = calculateBarMetrics(rows, 1);
  assert.equal(metrics.prevClose, 3.60);
  assert.equal(metrics.change, (3.73 - 3.60) / 3.60);
  assert.equal(metrics.amplitude, (3.73 - 3.64) / 3.73);

  const html = formatKlineTooltip([{ seriesName: 'K线', dataIndex: 1 }], rows);
  for (const label of ['开', '收', '高', '低', '涨跌幅', '振幅', '前收', '成交量']) {
    assert.match(html, new RegExp(label));
  }
  assert.match(html, /\+3\.61%/);
  assert.match(html, /2\.41%/);
  assert.doesNotMatch(html, /\b(?:open|close|lowest|highest)\b/i);
});
