import assert from 'node:assert/strict';
import test from 'node:test';

import { latestBars, zoomStartForVisibleBars } from './klineWindow.js';
import * as windowOptions from './klineWindow.js';

const fullOption = () => ({
  legend: { data: ['K线', 'BOLL30 上轨', 'BOLL30 中轨', 'BOLL30 下轨', '首尾四点'], selected: {} },
  dataZoom: [{ type: 'inside', start: 5, end: 100, filterMode: 'none' }, { type: 'slider', start: 5, end: 100 }],
  series: [{ name: 'K线' }, { id: 'boll-upper', name: 'BOLL30 上轨' },
    { id: 'boll-middle', name: 'BOLL30 中轨' }, { id: 'boll-lower', name: 'BOLL30 下轨' },
    { id: 'boll-outline', name: '首尾四点' }, { name: '成交量' }],
});

test('大图默认精确显示末端 200 根，布林三轨默认关闭但保留四点轮廓', () => {
  assert.equal(typeof windowOptions.applyFullKlineDisplay, 'function');
  const option = fullOption();
  const result = windowOptions.applyFullKlineDisplay(option, 500);
  for (const zoom of result.dataZoom) {
    assert.equal(zoom.startValue, 300);
    assert.equal(zoom.endValue, 499);
    assert.equal(zoom.start, undefined);
    assert.equal(zoom.end, undefined);
    assert.deepEqual(zoom.rangeMode, ['value', 'value']);
  }
  assert.deepEqual(result.legend.data, ['K线', '首尾四点']);
  assert.deepEqual(result.series.map(series => series.name), ['K线', '首尾四点', '成交量']);
  assert.equal(option.series.length, 6);
  assert.equal(option.dataZoom[0].start, 5);
});

test('大图根数可调整，开启布林线不能覆盖指定窗口', () => {
  assert.equal(typeof windowOptions.applyFullKlineDisplay, 'function');
  const result = windowOptions.applyFullKlineDisplay(fullOption(), 500, 100, true);
  assert.equal(result.dataZoom[0].startValue, 400);
  assert.equal(result.dataZoom[0].endValue, 499);
  assert.equal(result.series.length, 6);
  assert.equal(result.legend.data.length, 5);
});

test('大图数据不足时显示全部，无效根数回退到 200', () => {
  assert.equal(typeof windowOptions.applyFullKlineDisplay, 'function');
  assert.equal(windowOptions.applyFullKlineDisplay(fullOption(), 80, 200).dataZoom[0].startValue, 0);
  for (const count of [0, -1, NaN, Infinity]) {
    assert.equal(windowOptions.applyFullKlineDisplay(fullOption(), 500, count).dataZoom[0].startValue, 300);
  }
  const empty = windowOptions.applyFullKlineDisplay(fullOption(), 0);
  assert.equal(empty.dataZoom[0].startValue, 0);
  assert.equal(empty.dataZoom[0].endValue, 0);
});

test('latestBars 只保留最后指定数量的 K 线', () => {
  const rows = Array.from({ length: 500 }, (_, index) => index);

  assert.deepEqual(latestBars(rows, 160), rows.slice(-160));
});

test('latestBars 在数据不足时保留原数组', () => {
  const rows = Array.from({ length: 120 }, (_, index) => index);

  assert.equal(latestBars(rows, 160), rows);
});

test('zoomStartForVisibleBars 按可见数量计算大图起点', () => {
  assert.equal(zoomStartForVisibleBars(1440, 360), 75);
  assert.equal(zoomStartForVisibleBars(300, 360), 0);
});

test('zoomStartForVisibleBars 在参数无效时沿用原来的半屏窗口', () => {
  assert.equal(zoomStartForVisibleBars(1440, 0), 50);
  assert.equal(zoomStartForVisibleBars(0, 360), 50);
});
