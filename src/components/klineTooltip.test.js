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

const distanceRows = Array.from({ length: 300 }, (_, index) => ({
  date: `K线 ${index}`, open: 10, close: 10, low: 9, high: 11,
}));
const tooltipText = html => html.replace(/<[^>]*>/g, '');

for (const [index, distance] of [[299, 0], [298, 1], [219, 80], [0, 299]]) {
  test(`大图第 ${index} 根 K 线距最新一根 ${distance} 根`, () => {
    const html = formatKlineTooltip([{ seriesName: 'K线', dataIndex: index }], distanceRows, {
      showDistanceToLatest: true,
    });
    assert.match(tooltipText(html), new RegExp(`距离${distance} 根`));
  });
}

test('大图只有一根 K 线时距离为 0', () => {
  const html = formatKlineTooltip({ seriesName: 'K线', dataIndex: 0 }, distanceRows.slice(0, 1), {
    showDistanceToLatest: true,
  });
  assert.match(tooltipText(html), /距离0 根/);
});

test('距离优先使用 K 线的原始索引，不受均线顺序影响', () => {
  const html = formatKlineTooltip([
    { seriesName: 'MA5', dataIndex: 220, value: 10 },
    { seriesName: 'K线', dataIndex: 219 },
  ], distanceRows, { showDistanceToLatest: true });
  assert.match(tooltipText(html), /距离80 根/);
});

test('预览图默认不增加距离行', () => {
  const html = formatKlineTooltip([{ seriesName: 'K线', dataIndex: 219 }], distanceRows);
  assert.doesNotMatch(html, /距离/);
});

test('没有对应 K 线时不显示距离', () => {
  assert.equal(formatKlineTooltip([], [], { showDistanceToLatest: true }), '');
  assert.equal(formatKlineTooltip({ seriesName: 'K线', dataIndex: 300 }, distanceRows, {
    showDistanceToLatest: true,
  }), '');
});
