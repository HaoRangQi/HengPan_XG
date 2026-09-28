import assert from 'node:assert/strict';
import test from 'node:test';

import { latestBars, zoomStartForVisibleBars } from './klineWindow.js';

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
