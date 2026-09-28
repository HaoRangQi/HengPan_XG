import test from 'node:test';
import assert from 'node:assert/strict';

import {
  DEFAULT_RULES,
  DEFAULT_BOX_MODE,
  BOX_MODES,
  fieldsForMode,
  normalizeRule,
  ruleToPayload,
} from './ruleModes.js';

test('tolerant mode is the first option and the default for new scans', () => {
  assert.equal(Object.keys(BOX_MODES)[0], 'tolerant');
  assert.equal(DEFAULT_BOX_MODE, 'tolerant');
});

test('tolerant mode defaults to 80 bars, four percent, four spikes and no consecutive pair', () => {
  assert.deepEqual(DEFAULT_RULES.tolerant, {
    box_type: 'tolerant',
    box_pct: 4,
    lookback: 80,
    max_breach: 4,
    max_consecutive_breach: 1,
  });
});

test('each mode exposes only its own editor fields', () => {
  assert.deepEqual(fieldsForMode('fixed'), ['doji_pct', 'box_pct', 'lookback', 'max_breach']);
  assert.deepEqual(fieldsForMode('amplitude'), ['amp_multiple', 'max_amp_pct', 'lookback', 'max_breach']);
  assert.deepEqual(fieldsForMode('tolerant'), ['box_pct', 'lookback', 'max_breach', 'max_consecutive_breach']);
});

test('old rules without box_type remain fixed and receive compatible defaults', () => {
  const normalized = normalizeRule({ box_pct: 6, lookback: 40 });
  assert.equal(normalized.box_type, 'fixed');
  assert.equal(normalized.box_pct, 6);
  assert.equal(normalized.max_breach, 2);
});

test('tolerant payload converts percentages and includes consecutive spike limit', () => {
  assert.deepEqual(ruleToPayload({ ...DEFAULT_RULES.tolerant, box_pct: 4.5 }), {
    box_type: 'tolerant',
    doji_amplitude: 0.005,
    box_height: 0.045,
    amp_multiple: 1,
    max_amplitude: null,
    lookback: 80,
    max_breach: 4,
    max_consecutive_breach: 1,
  });
});
