import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { DEFAULT_RULES, RULE_FIELDS, fieldsForMode, sameRule, ruleToPayload, payloadToRule } from './ruleModes.js';

for (const page of ['HengpanScanView.vue', 'CryptoHengpanScanView.vue']) {
  test(`${page} 的箱体宽度不限制在 0.5% 至 30%`, async () => {
    const source = await readFile(new URL(page, import.meta.url), 'utf8');
    const validate = source.match(/function validate \(\) \{[\s\S]*?\n\}/)[0];
    const run = new Function('config', 'fieldsForMode', 'RULE_FIELDS', 'sameRule', 'today', `${validate}; return validate();`);
    for (const box_type of ['fixed', 'tolerant']) {
      for (const box_pct of [0, 0.000001, 0.1, 0.49, 31.125, 150, 1000]) {
        const config = { rules: [{ ...DEFAULT_RULES[box_type], box_pct }], scan_date: '', min_quote_wan: 0 };
        assert.equal(run(config, fieldsForMode, RULE_FIELDS, sameRule, '2099-01-01'), '', `${box_type}: ${box_pct}%`);
      }
    }
    const config = { rules: [{ ...DEFAULT_RULES.tolerant, box_pct: -1 }], scan_date: '', min_quote_wan: 0 };
    assert.match(run(config, fieldsForMode, RULE_FIELDS, sameRule, '2099-01-01'), /不能为负数/);
  });
}

test('宽度输入不设上限、不强制半个百分点步进', () => {
  assert.equal(RULE_FIELDS.box_pct.min, 0);
  assert.equal(RULE_FIELDS.box_pct.max, undefined);
  assert.equal(RULE_FIELDS.box_pct.step, 'any');
});

test('细小的自定义宽度往返不被四位小数截成零', () => {
  for (const box_pct of [0.000001, 0.003, 0.1, 31.125, 150]) {
    const payload = ruleToPayload({ ...DEFAULT_RULES.tolerant, box_pct });
    assert.equal(payload.box_height, box_pct / 100);
    assert.ok(Math.abs(payloadToRule(payload).box_pct - box_pct) < Math.max(1e-14, box_pct * 1e-12));
  }
});
