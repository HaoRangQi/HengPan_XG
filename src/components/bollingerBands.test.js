import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { formatKlineTooltip } from './klineTooltip.js';
import { calculateBollingerBands, withBollingerBands } from './bollingerBands.js';

const rows = Array.from({ length: 120 }, (_, i) => {
  const close = 100 + 2 * Math.sin(i * 2 * Math.PI / 30);
  return { date: String(i).padStart(3, '0'), open: close, close, high: close * 1.001, low: close * .999, volume: 1 };
});
const config = { mode: 'boll_box', boll_period: 30, boll_multiplier: 2, boll_start: '000', lookback_start: '029' };
test('布林三轨按收盘总体标准差计算，预热不画线', () => {
  const band = calculateBollingerBands(rows, config);
  assert.equal(band.middle[28], null);
  assert.ok(Math.abs(band.middle[29] - 100) < 1e-10);
  assert.ok(Math.abs(band.upper[29] - (100 + 2 * Math.sqrt(2))) < 1e-10);
  assert.ok(Math.abs(band.lower[119] - (100 - 2 * Math.sqrt(2))) < 1e-10);
});
test('周期倍数可变，坏点与计算起点必须重置预热', () => {
  const band = calculateBollingerBands(rows, { ...config, boll_start: '020', boll_period: 10, boll_multiplier: 3 });
  assert.equal(band.middle[28], null);
  assert.notEqual(band.middle[29], null);
  const bad = rows.map(row => ({ ...row }));
  bad[70].volume = 0;
  const reset = calculateBollingerBands(bad, config);
  assert.equal(reset.middle[99], null);
  assert.notEqual(reset.middle[100], null);
});
test('微价标的不舍入成零', () => {
  const tiny = rows.map(row => ({ ...row, open: row.open * 1e-8, close: row.close * 1e-8, high: row.high * 1e-8, low: row.low * 1e-8 }));
  const band = calculateBollingerBands(tiny, config);
  assert.ok(band.upper[29] > band.middle[29]);
  assert.ok(Math.abs(band.upper[29] / 1e-8 - (100 + 2 * Math.sqrt(2))) < 1e-10);
});
test('只有布林模式替换默认均线，保留 K 线和成交量及原图配置', () => {
  const option = { legend: { top: 4 }, series: [{ name: 'K线', type: 'candlestick', markLine: { data: [{ yAxis: 110, label: { formatter: '参考' } }] } }, { name: 'MA30' }, { name: '成交量' }] };
  assert.equal(withBollingerBands(option, rows, null), option);
  const result = withBollingerBands(option, rows, config);
  assert.equal(result.series.filter(s => s.id?.startsWith('boll-')).length, 3);
  assert.ok(!result.series.some(s => s.name === 'MA30'));
  assert.ok(result.series.some(s => s.name === '成交量'));
  assert.equal(option.series.length, 3);
  assert.equal(result.series.find(s => s.name === 'K线').markLine.data[0].label.position, 'insideEndTop');
  assert.equal(result.series.find(s => s.name === 'K线').markArea.data[0][0].xAxis, '029');
  const compact = withBollingerBands(option, rows, config, false, 200);
  // 缩略图下方已有图例标出三轨颜色，右侧端标签会与水平线标签挤在一起，只在大图保留。
  assert.equal(compact.series.find(s => s.id === 'boll-upper').endLabel.show, false);
  assert.equal(result.series.find(s => s.id === 'boll-upper').endLabel.formatter, 'BOLL30 上轨');
  assert.equal(compact.xAxis.axisLabel.interval, 29);
});

test('首尾四点直接连成闭合轮廓，不能把斜边强制画平', () => {
  const points = { ...config, boll_geometry: 'endpoints_v1', lookback_start: '030', box_end: '119',
    head_upper: 103, head_lower: 97, tail_upper: 103.3, tail_lower: 97.2 };
  const option = { series: [{ name: 'K线', type: 'candlestick', markLine: { data: [{ yAxis: 103 }] } }] };
  const chart = withBollingerBands(option, rows, points);
  const outline = chart.series.find(s => s.id === 'boll-outline');
  assert.ok(outline, '缺少四点轮廓');
  assert.deepEqual(outline.data, [['030', 103], ['119', 103.3], ['119', 97.2], ['030', 97], ['030', 103]]);
  assert.equal(outline.smooth, false);
  assert.equal(chart.series[0].markLine.data.length, 0);
  assert.ok(chart.legend.data.includes('首尾四点'));
  // 旧历史没有四点，不凭空补画一个矩形。
  assert.ok(!withBollingerBands(option, rows, config).series.some(s => s.id === 'boll-outline'));
});

test('长区间四点框默认完整可见，缩放不能丢掉框外端点', () => {
  const longRows = Array.from({ length: 400 }, (_, i) => ({ ...rows[i % 120], date: String(i).padStart(3, '0') }));
  const points = { ...config, boll_geometry: 'endpoints_v1', lookback_start: '030', box_end: '399',
    box_bars: 370, head_upper: 103, head_lower: 97, tail_upper: 103.1, tail_lower: 97.1 };
  const option = { series: [{ name: 'K线', type: 'candlestick' }], dataZoom: [{ type: 'inside', start: 50, end: 100 }] };
  const compact = withBollingerBands(option, longRows, points, false, 200);
  assert.ok(compact.dataZoom[0].startValue <= 30);
  assert.equal(compact.dataZoom[0].filterMode, 'none');
  const full = withBollingerBands(option, longRows, points);
  assert.ok(full.dataZoom[0].start < 10);
  assert.equal(full.dataZoom[0].filterMode, 'none');
});

test('图表参数变更调用已有 setOptions，提示显示三轨精度', () => {
  for (const file of ['KlineChart.vue', 'FullKlineChart.vue']) {
    const source = readFileSync(new URL(file, import.meta.url), 'utf8');
    assert.match(source, /async function renderChart/);
    assert.match(source, /watch\(\[[^\n]+props.bollinger/);
  }
  const text = formatKlineTooltip([{ seriesName: 'K线', dataIndex: 29 },
    { seriesName: 'BOLL30 上轨', dataIndex: 29, value: 0.0000123456 }], rows);
  assert.match(text, /BOLL30 上轨/);
  assert.match(text, /0.0000123456/);
});
