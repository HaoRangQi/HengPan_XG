import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { BOX_MODES, DEFAULT_RULES, RULE_FIELDS, fieldRangeError, fieldsForMode, ruleToPayload, payloadToRule, sameRule, formatRuleSummary } from './ruleModes.js';
import * as history from '../views/historyPresentation.js';

const rule = { box_type: 'boll_box', boll_period: 30, boll_multiplier: 2, min_box_bars: 80, rectangle_pct: 20 };
test('布林矩形有独立默认值和参数', () => {
  assert.equal(BOX_MODES.boll_box?.label, '布林矩形');
  assert.deepEqual(DEFAULT_RULES.boll_box, rule);
  assert.deepEqual(fieldsForMode('boll_box'), ['boll_period', 'boll_multiplier', 'min_box_bars', 'rectangle_pct']);
});
test('布林规则说明解释标准差倍数及其与矩形容差的区别', () => {
  const help = BOX_MODES.boll_box.help.join('\n');
  assert.match(help, /标准差倍数默认 2/);
  assert.match(help, /BOLL30\(×2\)/);
  assert.match(help, /上轨 = 中轨 \+ 标准差倍数 × 标准差/);
  assert.match(help, /下轨 = 中轨 − 标准差倍数 × 标准差/);
  assert.match(help, /10\.4 元.*9\.6 元/);
  assert.match(help, /倍数越大.*越宽.*越小.*越窄/);
  assert.match(help, /不是「矩形偏差容差」/);
});

test('参数往返与有效字段去重不受旧模式影响', () => {
  const custom = { ...rule, boll_period: 17, boll_multiplier: 2.5, min_box_bars: 130, rectangle_pct: .125 };
  const payload = ruleToPayload(custom);
  assert.deepEqual(payload, { box_type: 'boll_box', boll_period: 17, boll_multiplier: 2.5,
    min_box_bars: 130, rectangle_tolerance: .00125 });
  assert.deepEqual(payloadToRule(payload), custom);
  assert.ok(sameRule(rule, { ...rule, lookback: 10, ma_period: 90 }));
  for (const field of fieldsForMode('boll_box')) assert.ok(!sameRule(rule, { ...rule, [field]: rule[field] + 1 }));
  assert.match(formatRuleSummary(custom), /BOLL17/);
  assert.match(formatRuleSummary(custom), /130/);
});
test('历史按所选规则回显布林周期与计算起点', () => {
  const match = { mode: 'boll_box', boll_period: 17, boll_multiplier: 2.5, boll_start: '2026-08-01', lookback_start: '2026-09-01', upper: 110, lower: 90 };
  const hit = { matches: { '1': match, '2': { mode: 'ma_flat', ma_period: 30 } } };
  assert.equal(history.hitBollinger(hit, '1'), match);
  assert.equal(history.hitBollinger(hit, '2'), null);
  assert.ok(history.hitMarks(hit, '1').some(mark => mark.text === '矩形起点'));
});
test('最少矩形根数下限为 30，不设上限的字段不能提示 undefined', () => {
  assert.equal(RULE_FIELDS.min_box_bars.min, 30);
  assert.equal(RULE_FIELDS.min_box_bars.max, undefined);
  // 不设上限的字段：只报下限，不能出现 undefined
  assert.equal(fieldRangeError('min_box_bars', 30), '');
  assert.equal(fieldRangeError('min_box_bars', 500), '');
  assert.equal(fieldRangeError('min_box_bars', 29), '「最少矩形根数」不能小于 30 根');
  assert.equal(fieldRangeError('bandwidth_pct', 1e4), '');
  assert.equal(fieldRangeError('bandwidth_pct', -1), '「带宽变化容差」不能小于 0 %');
  // 有上限的字段仍然报区间
  assert.equal(fieldRangeError('boll_period', 501), '「布林周期」应在 2 到 500 根之间');
  assert.equal(fieldRangeError('boll_period', 30), '');
  for (const file of ['HengpanScanView.vue', 'CryptoHengpanScanView.vue']) {
    const source = readFileSync(new URL(file, import.meta.url), 'utf8');
    assert.match(source, /fieldRangeError/);
    assert.doesNotMatch(source, /应在 \$\{field\.min\} 到 \$\{field\.max\}/);
  }
});

test('双页面传递布林参数、显示持续长度并保存案例', () => {
  for (const file of ['HengpanScanView.vue', 'CryptoHengpanScanView.vue']) {
    const source = readFileSync(new URL(file, import.meta.url), 'utf8');
    assert.ok((source.match(/:bollinger=/g) || []).length >= 2);
    assert.match(source, /match\.box_bars/);
    assert.match(source, /match\.rectangle_error/);
    assert.match(source, /bollinger:.*match/);
  }
});

test('首尾四点历史不能被画成水平中位参考线', () => {
  const match = { mode: 'boll_box', boll_geometry: 'endpoints_v1',
    head_upper: 110, head_lower: 90, tail_upper: 111, tail_lower: 91,
    upper: 111, lower: 91, lookback_start: '2026-09-01', box_end: '2026-09-30' };
  const marks = history.hitMarks({ matches: { '1': match } }, '1');
  assert.equal(marks.filter(mark => mark.type === 'horizontal').length, 0);
  assert.ok(marks.some(mark => mark.date === '2026-09-01'));
});
