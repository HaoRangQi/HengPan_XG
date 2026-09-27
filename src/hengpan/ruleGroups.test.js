import test from 'node:test';
import assert from 'node:assert/strict';

import {
  createDefaultHengpanConfig,
  deleteRuleGroup,
  loadRuleGroups,
  saveRuleGroup,
} from './ruleGroups.js';

const DEFAULT_RULE = { doji_pct: 0.5, box_pct: 4, lookback: 80, max_breach: 2 };

class MemoryStorage {
  constructor () {
    this.values = new Map();
  }

  getItem (key) {
    return this.values.has(key) ? this.values.get(key) : null;
  }

  setItem (key, value) {
    this.values.set(key, String(value));
  }
}

test('new hengpan scans default to 60-minute bars and Shanghai main board', () => {
  const config = createDefaultHengpanConfig(DEFAULT_RULE);
  assert.equal(config.frequency, '60');
  assert.deepEqual(config.markets, ['sh_main']);
  assert.deepEqual(config.rules, [DEFAULT_RULE]);
  assert.notEqual(config.rules[0], DEFAULT_RULE);
});

test('saved rule groups use sequential default names and clone rule values', () => {
  const storage = new MemoryStorage();
  const first = saveRuleGroup(storage, [], [DEFAULT_RULE]);
  assert.equal(first.saved.name, '规则组1');

  const changedRule = { ...DEFAULT_RULE, box_pct: 8 };
  const second = saveRuleGroup(storage, first.groups, [changedRule]);
  assert.equal(second.saved.name, '规则组2');
  changedRule.box_pct = 10;

  const loaded = loadRuleGroups(storage);
  assert.deepEqual(loaded.map(group => group.name), ['规则组1', '规则组2']);
  assert.equal(loaded[1].rules[0].box_pct, 8);
});

test('deleting a group persists and the next name remains monotonic', () => {
  const storage = new MemoryStorage();
  const first = saveRuleGroup(storage, [], [DEFAULT_RULE]);
  const second = saveRuleGroup(storage, first.groups, [DEFAULT_RULE]);
  const remaining = deleteRuleGroup(storage, second.groups, first.saved.id);
  assert.deepEqual(remaining.map(group => group.name), ['规则组2']);

  const third = saveRuleGroup(storage, remaining, [DEFAULT_RULE]);
  assert.equal(third.saved.name, '规则组3');
});

test('corrupt saved data is treated as no saved groups', () => {
  const storage = new MemoryStorage();
  storage.setItem('hengpan.rule-groups.v1', '{not json');
  assert.deepEqual(loadRuleGroups(storage), []);
});
