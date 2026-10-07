import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { hitMarks, hitMaPeriod } from '../views/historyPresentation.js';
import {
  BOX_MODES, DEFAULT_RULES, RULE_FIELDS, fieldRangeError, fieldsForMode, sameRule,
  ruleToPayload, payloadToRule, formatRuleSummary, formatTailState,
} from './ruleModes.js';

const rule = { box_type: 'ma_flat', ma_period: 30, min_flat_bars: 30, ma_pct: 1, max_efficiency_ratio: 0.5 };

test('均线走平注册为独立模式，默认均线周期和最少根数均为 30', () => {
  assert.equal(BOX_MODES.ma_flat?.label, '均线走平');
  assert.deepEqual(DEFAULT_RULES.ma_flat, rule);
  assert.deepEqual(fieldsForMode('ma_flat'), ['ma_period', 'min_flat_bars', 'ma_pct', 'max_efficiency_ratio']);
});

test('自定义均线周期、极小容差和 ER 在请求与历史中无损往返', () => {
  const custom = { ...rule, ma_period: 17, min_flat_bars: 45, ma_pct: 0.00001, max_efficiency_ratio: 0.35 };
  const payload = ruleToPayload(custom);
  assert.deepEqual(payload, { box_type: 'ma_flat', ma_period: 17, min_flat_bars: 45,
    ma_tolerance: 0.00001 / 100, max_efficiency_ratio: 0.35 });
  const restored = payloadToRule(payload);
  assert.equal(restored.ma_period, 17);
  assert.equal(restored.min_flat_bars, 45);
  assert.ok(Math.abs(restored.ma_pct - custom.ma_pct) < 1e-14);
  assert.equal(restored.max_efficiency_ratio, 0.35);
  assert.match(formatRuleSummary(restored), /MA17/);
  assert.match(formatRuleSummary(restored), /至少 45 根/);
});

test('均线规则判重不受旧箱体参数影响', () => {
  assert.equal(sameRule(rule, { ...rule, box_pct: 20, lookback: 80, max_breach: 20 }), true);
  for (const [key, value] of Object.entries({ ma_period: 20, min_flat_bars: 60, ma_pct: 2, max_efficiency_ratio: 1 })) {
    assert.equal(sameRule(rule, { ...rule, [key]: value }), false);
  }
});

test('末端状态只描述相对位置，不把脱离写成确认突破', () => {
  assert.equal(formatTailState({ tail_state: 'inside', tail_bars: 0 }), '区间内');
  assert.equal(formatTailState({ tail_state: 'above', tail_bars: 2 }), '疑似向上脱离 · 2 根');
  assert.equal(formatTailState({ tail_state: 'below', tail_bars: 1 }), '疑似向下脱离 · 1 根');
});

test('统一历史按命中规则恢复均线周期和走平起点', () => {
  const hit = { matches: {
    '1': { mode: 'ma_flat', ma_period: 17, lower: 90, upper: 110, lookback_start: '2026-09-01 14:00:00' },
    '2': { mode: 'ma_flat', ma_period: 45, lower: 95, upper: 105 },
  } };
  assert.equal(hitMaPeriod(hit), 17);
  assert.equal(hitMaPeriod(hit, '2'), 45);
  assert.equal(hitMaPeriod({ matches: { '1': { mode: 'fixed' } } }), null);
  const marks = hitMarks(hit, '1');
  assert.equal(marks[0].text, '区间最高');
  assert.equal(marks[2].date, hit.matches['1'].lookback_start);
  assert.equal(marks[2].text, '走平起点');
});

test('统一历史和案例大小图都传入实际均线周期', async () => {
  const history = await readFile(new URL('../views/HistoryView.vue', import.meta.url), 'utf8');
  assert.match(history, /:ma-period="chart.maPeriod"/);
  assert.match(history, /maPeriod: hitMaPeriod\(hit, ruleId\)/);
  const detail = await readFile(new URL('../components/case-management/CaseDetail.vue', import.meta.url), 'utf8');
  assert.equal((detail.match(/:ma-period="analysisData\?\.parameters\?\.ma_period"/g) || []).length, 2);
  assert.ok(detail.includes("analysisData.parameters.ma_period ? '根 K 线' : '天'"));
});

for (const page of ['HengpanScanView.vue', 'CryptoHengpanScanView.vue']) {
  test(`${page} 允许均线独立参数并拒绝小数周期`, async () => {
    const source = await readFile(new URL(page, import.meta.url), 'utf8');
    const validate = source.match(/function validate \(\) \{[\s\S]*?\n\}/)[0];
    const run = new Function('config', 'fieldsForMode', 'RULE_FIELDS', 'sameRule', 'today', 'fieldRangeError', `${validate}; return validate();`);
    const config = { rules: [{ ...rule }], scan_date: '', min_quote_wan: 0 };
    assert.equal(run(config, fieldsForMode, RULE_FIELDS, sameRule, '2099-01-01', fieldRangeError), '');
    for (const key of ['ma_period', 'min_flat_bars']) {
      config.rules = [{ ...rule, [key]: 30.5 }];
      assert.match(run(config, fieldsForMode, RULE_FIELDS, sameRule, '2099-01-01', fieldRangeError), /整数/);
    }
    config.rules = [{ ...rule, max_efficiency_ratio: 1.1 }];
    assert.notEqual(run(config, fieldsForMode, RULE_FIELDS, sameRule, '2099-01-01', fieldRangeError), '');
  });

  test(`${page} 表单按字段注册表生成，图表使用命中结果中的均线周期`, async () => {
    const source = await readFile(new URL(page, import.meta.url), 'utf8');
    assert.match(source, /<RuleEditorTable[^>]*:fields="activeRuleFields"/);
    assert.match(source, /fieldEntriesForMode\(activeBoxType\.value\)/);
    assert.match(source, /:ma-period="(?:stock|item)\.match\.ma_period"/);
    assert.match(source, /:ma-period="chart(?:Stock|Symbol)\?\.match\?\.ma_period"/);
    assert.match(source, /history_limited/);
    assert.match(source, /flat_bars/);
    assert.match(source, /efficiency_ratio/);
  });
}
