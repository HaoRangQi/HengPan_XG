export const BOX_MODES = {
  tolerant: { label: '容刺箱体', description: '用实体中心价寻找主体箱体，允许少量离散刺破' },
  boll_box: {
    label: '布林矩形',
    description: '先检查最近最少根数区间的首尾四点，再用中点复核左右两个矩形；通过后逐根向前扩展，遇到不合格即停止。中点只检查第一次。',
    help: [
      '布林周期 n 决定每个端点用最近多少根收盘价计算，默认 30 根。中轨 = 这 n 根收盘价的平均值；标准差衡量这些收盘价的波动大小，使用总体标准差（ddof=0）。',
      '标准差倍数默认 2，即 BOLL30(×2) 中的 ×2。上轨 = 中轨 + 标准差倍数 × 标准差；下轨 = 中轨 − 标准差倍数 × 标准差。周期和倍数均可调整。',
      '例如均价 10 元、标准差 0.2 元，取 2 倍时，上轨为 10.4 元、下轨为 9.6 元。倍数越大布林带越宽，越小越窄。',
      '标准差倍数改变首尾四点的位置，会影响筛选结果；它不是「矩形偏差容差」，后者才规定四点连线偏离水平矩形的允许程度。',
      '例如最少 50 根、周期 20，先准备 70 根数据，前 20 根只作预热。BOLL 包含当前根，预热最老一根是余量。',
      '先检查最近 B 根（最少矩形根数）的头上、头下、尾上、尾下四个点；整体矩形不合格就淘汰，不尝试更长区间挽救。',
      '整体通过后，取初始 B 根的中间 K 线（偶数长度取靠左中点），增加上下轨两个点；左半和右半矩形必须分别通过同一容差。中点只检查第一次，扩展时不重新检查；取样复核不代表中途每根 K 线都没有波动。',
      '矩形偏差 = 上下边首尾高度差的较大值 ÷ 首尾平均箱高。容差 20% 表示高度差不超过平均箱高的五分之一；是可调试用值。',
      '最少根数下限 30、默认 80。初始检查通过后，末端固定，起点逐根向历史移动，只检查新起点与末端的四点矩形；首次失败即停止，保留上一次合格的起点，不跳过失败位置。本地不设长度上限，联网日线受取数范围限制。',
      '图中轮廓是实际参与判断的首尾四点连线；布林三轨只作背景参考。仅使用有效连续、已收盘数据，不跨缺失数据或零成交，零箱高不算矩形。',
      '历史记录保留当时的判定结果，不自动重算；重新扫描采用当前的一次中点复核与向前遇坏即停规则。旧版整段轨道规则未设置矩形容差时，重扫使用默认矩形容差，请按需调整。',
    ],
  },
  fixed: { label: '末端定高', description: '用末端 K 线位置锚定固定高度箱体' },
  amplitude: { label: '末端振幅', description: '按末端 K 线振幅动态扩展箱体' },
  ma_flat: {
    label: '均线走平',
    description: '从已收盘尾部向前寻找均线水平区间，用价格方向效率过滤单边走势；不预设价格箱宽',
    help: [
      '均线周期可调，默认 MA30；最少连续根数是独立条件，默认 30 根，不包含均线预热。',
      '均线波动 =（区间均线最大值 − 最小值）÷ 最新均线值；向前延伸到容差边界，不固定最终长度。',
      'ER = 价格净位移 ÷ 逐根涨跌的绝对值之和。越接近 1 越单边；上限设为 1 可关闭方向过滤。',
      '仅使用已收盘 K 线，不跨缺失数据；本地 A/U 使用全部已存历史，联网日线使用有限的取数日期范围。',
      '末端脱离只提示，不单独淘汰；触及可用历史边界时显示“至少”。均线走平不等于价格窄幅横盘。',
    ],
  },
};

export const DEFAULT_BOX_MODE = 'tolerant';

export const RULE_FIELDS = {
  boll_period: { label: '布林周期', unit: '根', step: 1, min: 2, max: 500, integer: true },
  boll_multiplier: { label: '标准差倍数', unit: '倍', step: 0.1, min: 0.1, max: 10 },
  min_box_bars: { label: '最少矩形根数', unit: '根', step: 1, min: 30, integer: true },
  rectangle_pct: { label: '矩形偏差容差', unit: '%', step: 'any', min: 0 },
  rail_pct: { label: '轨道摆动容差', unit: '%', step: 'any', min: 0, max: 100 },
  bandwidth_pct: { label: '带宽变化容差', unit: '%', step: 'any', min: 0 },
  doji_pct: { label: '十字星振幅上限', unit: '%', step: 0.1, min: 0.1, max: 5 },
  box_pct: { label: '箱体宽度上限', unit: '%', step: 'any', min: 0 },
  amp_multiple: { label: '振幅倍数', unit: '倍', step: 0.1, min: 0.1, max: 20 },
  max_amp_pct: { label: '振幅上限', unit: '%', step: 0.5, min: 0.1, max: 100, optional: true, placeholder: '不限' },
  lookback: { label: '回验根数', unit: '根', step: 1, min: 10, max: 250, integer: true },
  max_breach: { label: '允许刺破', unit: '根', step: 1, min: 0, max: 20, integer: true },
  max_consecutive_breach: { label: '连续刺破上限', unit: '根', step: 1, min: 1, max: 20, integer: true },
  ma_period: { label: '均线周期', unit: '根', step: 1, min: 2, max: 500, integer: true },
  min_flat_bars: { label: '最少连续走平', unit: '根', step: 1, min: 2, max: 1000, integer: true },
  ma_pct: { label: '均线波动容差', unit: '%', step: 'any', min: 0, max: 100 },
  max_efficiency_ratio: { label: '方向效率 ER 上限', unit: '0–1', step: 'any', min: 0, max: 1 },
};

const MODE_FIELDS = {
  boll_box: ['boll_period', 'boll_multiplier', 'min_box_bars', 'rectangle_pct'],
  fixed: ['doji_pct', 'box_pct', 'lookback', 'max_breach'],
  amplitude: ['amp_multiple', 'max_amp_pct', 'lookback', 'max_breach'],
  tolerant: ['box_pct', 'lookback', 'max_breach', 'max_consecutive_breach'],
  ma_flat: ['ma_period', 'min_flat_bars', 'ma_pct', 'max_efficiency_ratio'],
};

export const DEFAULT_RULES = {
  boll_box: { box_type: 'boll_box', boll_period: 30, boll_multiplier: 2, min_box_bars: 80, rectangle_pct: 20 },
  fixed: { box_type: 'fixed', doji_pct: 0.5, box_pct: 4, lookback: 80, max_breach: 2 },
  amplitude: { box_type: 'amplitude', amp_multiple: 1, max_amp_pct: null, lookback: 80, max_breach: 2 },
  tolerant: { box_type: 'tolerant', box_pct: 4, lookback: 80, max_breach: 4, max_consecutive_breach: 1 },
  ma_flat: { box_type: 'ma_flat', ma_period: 30, min_flat_bars: 30, ma_pct: 1, max_efficiency_ratio: 0.5 },
};

export const PRESET_RULES = {
  boll_box: [{ rectangle_pct: 10 }, { rectangle_pct: 20 }, { rectangle_pct: 30 }],
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
  ma_flat: [
    { ma_pct: 1, min_flat_bars: 30, max_efficiency_ratio: 0.5 },
    { ma_pct: 1.5, min_flat_bars: 30, max_efficiency_ratio: 0.5 },
    { ma_pct: 1, min_flat_bars: 50, max_efficiency_ratio: 0.3 },
  ],
  tolerant: [
    { box_pct: 3, lookback: 80, max_breach: 3, max_consecutive_breach: 1 },
    { box_pct: 4, lookback: 80, max_breach: 4, max_consecutive_breach: 1 },
    { box_pct: 5, lookback: 80, max_breach: 5, max_consecutive_breach: 1 },
  ],
};

const trim = (value) => Number(Number(value).toFixed(4));
const validMode = (mode) => (BOX_MODES[mode] ? mode : 'fixed');

// 取值范围提示。部分字段（最少矩形根数、带宽变化容差、箱体宽度）刻意不设上限，
// 这时只报下限，不能把 undefined 拼进文案。返回空串表示取值合法。
export function fieldRangeError (key, value) {
  const field = RULE_FIELDS[key];
  if (!field) return '';
  const hasMax = Number.isFinite(field.max);
  if (value < field.min) {
    return hasMax
      ? `「${field.label}」应在 ${field.min} 到 ${field.max} ${field.unit}之间`
      : `「${field.label}」不能小于 ${field.min} ${field.unit}`;
  }
  return hasMax && value > field.max
    ? `「${field.label}」应在 ${field.min} 到 ${field.max} ${field.unit}之间` : '';
}

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
  if (normalized.box_type === 'boll_box') {
    return { box_type: 'boll_box', boll_period: normalized.boll_period,
      boll_multiplier: normalized.boll_multiplier, min_box_bars: normalized.min_box_bars,
      rectangle_tolerance: normalized.rectangle_pct / 100 };
  }
  if (normalized.box_type === 'ma_flat') {
    return {
      box_type: 'ma_flat',
      ma_period: normalized.ma_period,
      min_flat_bars: normalized.min_flat_bars,
      ma_tolerance: normalized.ma_pct / 100,
      max_efficiency_ratio: normalized.max_efficiency_ratio,
    };
  }
  return {
    box_type: normalized.box_type,
    doji_amplitude: trim((normalized.doji_pct ?? DEFAULT_RULES.fixed.doji_pct) / 100),
    box_height: (normalized.box_pct ?? DEFAULT_RULES.fixed.box_pct) / 100,
    amp_multiple: trim(normalized.amp_multiple ?? DEFAULT_RULES.amplitude.amp_multiple),
    max_amplitude: normalized.box_type === 'amplitude' && Number(normalized.max_amp_pct) > 0
      ? trim(normalized.max_amp_pct / 100) : null,
    lookback: normalized.lookback,
    max_breach: normalized.max_breach,
    max_consecutive_breach: normalized.max_consecutive_breach ?? DEFAULT_RULES.tolerant.max_consecutive_breach,
  };
}

export function payloadToRule (params = {}) {
  if (params.box_type === 'boll_box') return normalizeRule({ box_type: 'boll_box',
    boll_period: params.boll_period ?? 30, boll_multiplier: params.boll_multiplier ?? 2,
    min_box_bars: params.min_box_bars ?? 80,
    rectangle_pct: Number(((params.rectangle_tolerance ?? 0.2) * 100).toPrecision(15)) });
  if (params.box_type === 'ma_flat') {
    return normalizeRule({
      box_type: 'ma_flat',
      ma_period: params.ma_period ?? 30,
      min_flat_bars: params.min_flat_bars ?? 30,
      ma_pct: Number(((params.ma_tolerance ?? 0.01) * 100).toPrecision(15)),
      max_efficiency_ratio: params.max_efficiency_ratio ?? 0.5,
    });
  }
  return normalizeRule({
    box_type: params.box_type || 'fixed',
    doji_pct: trim((params.doji_amplitude ?? 0.005) * 100),
    box_pct: Number(((params.box_height ?? 0.04) * 100).toPrecision(15)),
    max_amp_pct: params.max_amplitude ? trim(params.max_amplitude * 100) : null,
    amp_multiple: params.amp_multiple ?? 1,
    lookback: params.lookback ?? 80,
    max_breach: params.max_breach ?? 2,
    max_consecutive_breach: params.max_consecutive_breach ?? 1,
  });
}

export function formatTailState (match) {
  const labels = { inside: '区间内', above: '疑似向上脱离', below: '疑似向下脱离' };
  const label = labels[match.tail_state] || '状态未知';
  return match.tail_bars ? `${label} · ${match.tail_bars} 根` : label;
}

export function formatRuleSummary (rule) {
  const normalized = normalizeRule(rule);
  if (normalized.box_type === 'boll_box') return `BOLL${normalized.boll_period}(×${normalized.boll_multiplier}) / 至少 ${normalized.min_box_bars} 根 / 矩形偏差 ≤ ${normalized.rectangle_pct}%`;
  if (normalized.box_type === 'ma_flat') {
    return `MA${normalized.ma_period} / 至少 ${normalized.min_flat_bars} 根 / 波动 ≤ ${normalized.ma_pct}% / ER ≤ ${normalized.max_efficiency_ratio}`;
  }
  if (normalized.box_type === 'amplitude') {
    return `振幅 x${trim(normalized.amp_multiple)} / ${normalized.lookback} 根`;
  }
  if (normalized.box_type === 'tolerant') {
    return `容刺 ${trim(normalized.box_pct)}% / ${normalized.lookback} 根 / 最多 ${normalized.max_breach} 刺`;
  }
  return `定高 ${trim(normalized.box_pct)}% / ${normalized.lookback} 根`;
}

// 历史摘要必须保留当时的算法口径，不能把旧极差阈值当成新的四点容差。
export function formatPayloadRuleSummary (params = {}) {
  if (params.box_type === 'boll_box' && params.rectangle_tolerance == null) {
    return `旧版 BOLL${params.boll_period ?? 30}(×${params.boll_multiplier ?? 2}) / 至少 ${params.min_box_bars ?? 80} 根 / 整段轨摆 ≤ ${trim((params.rail_tolerance ?? 0.05) * 100)}% / 带宽变化 ≤ ${trim((params.bandwidth_tolerance ?? 1.5) * 100)}%`;
  }
  return formatRuleSummary(payloadToRule(params));
}
