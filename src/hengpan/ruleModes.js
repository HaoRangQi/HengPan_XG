export const BOX_MODES = {
  fixed: { label: '末端定高', description: '用末端 K 线位置锚定固定高度箱体' },
  amplitude: { label: '末端振幅', description: '按末端 K 线振幅动态扩展箱体' },
  tolerant: { label: '容刺箱体', description: '用实体中心价寻找主体箱体，允许少量离散刺破' },
};

export const RULE_FIELDS = {
  doji_pct: { label: '十字星振幅上限', unit: '%', step: 0.1, min: 0.1, max: 5 },
  box_pct: { label: '箱体宽度上限', unit: '%', step: 0.5, min: 0.5, max: 30 },
  amp_multiple: { label: '振幅倍数', unit: '倍', step: 0.1, min: 0.1, max: 20 },
  max_amp_pct: { label: '振幅上限', unit: '%', step: 0.5, min: 0.1, max: 100, optional: true, placeholder: '不限' },
  lookback: { label: '回验根数', unit: '根', step: 1, min: 10, max: 250 },
  max_breach: { label: '允许刺破', unit: '根', step: 1, min: 0, max: 20 },
  max_consecutive_breach: { label: '连续刺破上限', unit: '根', step: 1, min: 1, max: 20 },
};

const MODE_FIELDS = {
  fixed: ['doji_pct', 'box_pct', 'lookback', 'max_breach'],
  amplitude: ['amp_multiple', 'max_amp_pct', 'lookback', 'max_breach'],
  tolerant: ['box_pct', 'lookback', 'max_breach', 'max_consecutive_breach'],
};

export const DEFAULT_RULES = {
  fixed: { box_type: 'fixed', doji_pct: 0.5, box_pct: 4, lookback: 80, max_breach: 2 },
  amplitude: { box_type: 'amplitude', amp_multiple: 1, max_amp_pct: null, lookback: 80, max_breach: 2 },
  tolerant: { box_type: 'tolerant', box_pct: 4, lookback: 80, max_breach: 4, max_consecutive_breach: 1 },
};

export const PRESET_RULES = {
  fixed: [
    { box_pct: 4, lookback: 80, max_breach: 2 },
    { box_pct: 6, lookback: 40, max_breach: 2 },
    { box_pct: 8, lookback: 40, max_breach: 2 },
    { box_pct: 10, lookback: 40, max_breach: 2 },
  ],
  amplitude: [
    { amp_multiple: 0.8, lookback: 80, max_breach: 2 },
    { amp_multiple: 1, lookback: 80, max_breach: 2 },
    { amp_multiple: 1.2, lookback: 80, max_breach: 2 },
  ],
  tolerant: [
    { box_pct: 3, lookback: 80, max_breach: 3, max_consecutive_breach: 1 },
    { box_pct: 4, lookback: 80, max_breach: 4, max_consecutive_breach: 1 },
    { box_pct: 5, lookback: 80, max_breach: 5, max_consecutive_breach: 1 },
  ],
};

const trim = (value) => Number(Number(value).toFixed(4));
const validMode = (mode) => (BOX_MODES[mode] ? mode : 'fixed');

export const fieldsForMode = (mode) => [...MODE_FIELDS[validMode(mode)]];
export const fieldEntriesForMode = (mode) => fieldsForMode(mode).map(key => [key, RULE_FIELDS[key]]);

export function normalizeRule (rule = {}, forcedMode) {
  const mode = validMode(forcedMode || rule.box_type);
  return { ...DEFAULT_RULES[mode], ...rule, box_type: mode };
}

export function rulesForMode (mode, partials = [{}]) {
  return partials.map(rule => normalizeRule(rule, mode));
}

export function sameRule (left, right) {
  const a = normalizeRule(left);
  const b = normalizeRule(right);
  return a.box_type === b.box_type && fieldsForMode(a.box_type).every(key => a[key] === b[key]);
}

export function ruleToPayload (rule) {
  const normalized = normalizeRule(rule);
  return {
    box_type: normalized.box_type,
    doji_amplitude: trim((normalized.doji_pct ?? DEFAULT_RULES.fixed.doji_pct) / 100),
    box_height: trim((normalized.box_pct ?? DEFAULT_RULES.fixed.box_pct) / 100),
    amp_multiple: trim(normalized.amp_multiple ?? DEFAULT_RULES.amplitude.amp_multiple),
    max_amplitude: normalized.box_type === 'amplitude' && Number(normalized.max_amp_pct) > 0
      ? trim(normalized.max_amp_pct / 100) : null,
    lookback: normalized.lookback,
    max_breach: normalized.max_breach,
    max_consecutive_breach: normalized.max_consecutive_breach ?? DEFAULT_RULES.tolerant.max_consecutive_breach,
  };
}

export function payloadToRule (params = {}) {
  return normalizeRule({
    box_type: params.box_type || 'fixed',
    doji_pct: trim((params.doji_amplitude ?? 0.005) * 100),
    box_pct: trim((params.box_height ?? 0.04) * 100),
    max_amp_pct: params.max_amplitude ? trim(params.max_amplitude * 100) : null,
    amp_multiple: params.amp_multiple ?? 1,
    lookback: params.lookback ?? 80,
    max_breach: params.max_breach ?? 2,
    max_consecutive_breach: params.max_consecutive_breach ?? 1,
  });
}

export function formatRuleSummary (rule) {
  const normalized = normalizeRule(rule);
  if (normalized.box_type === 'amplitude') {
    return `振幅 x${trim(normalized.amp_multiple)} / ${normalized.lookback} 根`;
  }
  if (normalized.box_type === 'tolerant') {
    return `容刺 ${trim(normalized.box_pct)}% / ${normalized.lookback} 根 / 最多 ${normalized.max_breach} 刺`;
  }
  return `定高 ${trim(normalized.box_pct)}% / ${normalized.lookback} 根`;
}
