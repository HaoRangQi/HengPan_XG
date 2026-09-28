import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const readView = name => readFile(new URL(`./${name}`, import.meta.url), 'utf8');

test('平台-U 复刻平台-A的工作台结构并替换为加密扫描范围', async () => {
  const [stockView, cryptoView] = await Promise.all([
    readView('ScanView.vue'),
    readView('CryptoScanView.vue'),
  ]);

  for (const section of ['基础条件', '功能开关', '参数设置', '扫描结果']) {
    assert.match(stockView, new RegExp(section));
    assert.match(cryptoView, new RegExp(section));
  }
  for (const className of ['base-conditions-primary', 'base-conditions-metrics', 'switch', 'seg-btn']) {
    assert.match(cryptoView, new RegExp(className));
  }
  assert.match(cryptoView, /扫描类别/);
  assert.match(cryptoView, /交易对（可选）/);
  assert.match(cryptoView, /24 小时成交额门槛/);
  assert.doesNotMatch(cryptoView, /板块过滤|基本面筛选|行业筛选/);
});

test('平台-U 暴露后端支持的类别阈值和共享分析开关', async () => {
  const source = await readView('CryptoScanView.vue');

  for (const key of [
    'box_threshold',
    'ma_diff_threshold',
    'volatility_threshold',
    'volume_change_threshold',
    'volume_stability_threshold',
  ]) assert.match(source, new RegExp(key));

  for (const key of [
    'use_box_detection',
    'use_volume_analysis',
    'use_breakthrough_prediction',
    'use_breakthrough_confirmation',
    'use_window_weights',
  ]) assert.match(source, new RegExp(key));
});

test('平台-U 与平台-A一样提供计时、历史、筛选、分页和双列结果卡', async () => {
  const source = await readView('CryptoScanView.vue');

  assert.match(source, /formatDuration/);
  assert.match(source, /loadHistory/);
  assert.match(source, /filteredResults/);
  assert.match(source, /pagedResults/);
  assert.match(source, /pageSize/);
  assert.match(source, /lg:grid-cols-2/);
  assert.match(source, /selection_reasons/);
});
