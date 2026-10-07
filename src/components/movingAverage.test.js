import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { calculateMovingAverage, withSelectedMA } from './movingAverage.js';

const candles = prices => prices.map(price => [price, price, price, price]);

test('均线预热为 N−1 根，第 N 根开始有值', () => {
  assert.deepEqual(calculateMovingAverage(3, candles([1, 2, 3, 4, 5])), [null, null, 2, 3, 4]);
});

test('小面值加密价格不能被固定小数位舍入成零', () => {
  const values = calculateMovingAverage(2, candles([0.000001, 0.000002, 0.000003]));
  assert.ok(Math.abs(values[1] - 0.0000015) < 1e-18);
  assert.ok(Math.abs(values[2] - 0.0000025) < 1e-18);
});

test('无效价格只使包含它的均线窗口失效，不跨过缺失值计算', () => {
  assert.deepEqual(calculateMovingAverage(2, candles([1, null, 3, 5])), [null, null, null, 4]);
});

test('新模式只突出实际配置的均线，不与默认均线重名', () => {
  const option = { legend: { data: ['K线', 'MA10', 'MA30'] }, series: [
    { name: 'K线', type: 'candlestick' },
    { name: 'MA10', type: 'line' },
    { name: 'MA30', type: 'line', lineStyle: { color: '#6b7280', opacity: 0.6 } },
    { name: '成交量', type: 'bar' },
  ] };
  assert.equal(withSelectedMA(option, [], null), option);
  for (const period of [10, 17, 30, 60]) {
    const selected = withSelectedMA(option, candles(Array(80).fill(0.000001)), period);
    assert.deepEqual(selected.legend.data, ['K线', `MA${period}`]);
    assert.equal(selected.legend.selected[`MA${period}`], true);
    const averages = selected.series.filter(series => series.name.startsWith('MA'));
    assert.equal(averages.length, 1);
    assert.equal(averages[0].name, `MA${period}`);
    assert.equal(averages[0].data[period - 2], null);
    assert.ok(averages[0].data[period - 1] > 0);
    assert.equal(averages[0].smooth, false);
    assert.equal(averages[0].itemStyle.color, averages[0].lineStyle.color);
    assert.equal(selected.series.some(series => series.name === '成交量'), true);
  }
  assert.equal(option.series.length, 4);
});

test('缩略图限制初始可见根数但用完整历史计算均线', () => {
  const option = { legend: {}, xAxis: { data: Array.from({ length: 800 }, (_, i) => String(i)), axisLabel: {} },
    series: [{ name: 'K线', type: 'candlestick' }, { name: 'MA30', type: 'line' }] };
  const selected = withSelectedMA(option, candles(Array(800).fill(100)), 45, 200);
  assert.equal(selected.dataZoom[0].startValue, 600);
  assert.equal(selected.dataZoom[0].endValue, 799);
  assert.ok(selected.xAxis.axisLabel.interval >= 49);
  assert.equal(selected.series.at(-1).data.length, 800);
  assert.equal(selected.series.at(-1).data[600], 100);
});

test('均线区间上下沿标签放在绘图区内，避免长价格被右侧裁切', () => {
  const mark = { yAxis: 2749.17, label: { position: 'end', formatter: '区间最高: 2749.17' } };
  const option = { legend: {}, series: [
    { name: 'K线', type: 'candlestick', markLine: { data: [mark] } },
    { name: 'MA30', type: 'line' },
  ] };
  const result = withSelectedMA(option, candles([100, 100]), 2);
  assert.equal(result.series[0].markLine.data[0].label.position, 'insideEndTop');
  assert.equal(mark.label.position, 'end');
});

for (const file of ['KlineChart.vue', 'FullKlineChart.vue']) {
  test(`${file} 接受均线周期并在周期或标线切换时刷新`, async () => {
    const source = await readFile(new URL(file, import.meta.url), 'utf8');
    assert.match(source, /maPeriod:\s*\{/);
    assert.match(source, /withSelectedMA\(option, (?:values|data.values), props.maPeriod(?:, 200)?\)/);
    assert.match(source, /watch\(\[\(\) => props.maPeriod, \(\) => props.markLines, \(\) => props.bollinger\]/);
    assert.match(source, /replaceMerge: \['series'(?:, 'dataZoom')?\]/);
  });
}
