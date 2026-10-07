export const HISTORY_KINDS = {
  hengpan_a: { label: '横盘-A', market: 'a', path: '/' },
  hengpan_u: { label: '横盘-U', market: 'crypto', path: '/platform' },
  platform_a: { label: '平台-A', market: 'a', path: '/crypto-a' },
  platform_u: { label: '平台-U', market: 'crypto', path: '/crypto-u' },
};

export function historyQuery (filters = {}, page = 1) {
  const query = { market: filters.market || 'a', view: filters.view || 'symbols',
    intraday: (filters.period || 'intraday') === 'intraday', page, page_size: 20 };
  if (filters.period && !['all', 'intraday'].includes(filters.period)) query.frequency = filters.period;
  for (const key of ['kind', 'status', 'date_from', 'date_to', 'code']) {
    if (filters[key]?.trim()) query[key] = filters[key].trim();
  }
  return query;
}

export function historyLink (kind) {
  return `#/history?market=${HISTORY_KINDS[kind].market}&kind=${kind}`;
}

export function hitIdentity (hit) {
  return { code: hit.code || hit.symbol, name: hit.name || hit.base_asset || hit.code || hit.symbol };
}

export function hitMaPeriod (hit, ruleId) {
  const match = hit.matches?.[ruleId || Object.keys(hit.matches || {})[0]];
  return match?.mode === 'ma_flat' ? match.ma_period : null;
}

export function hitBollinger (hit, ruleId) {
  const match = hit.matches?.[ruleId || Object.keys(hit.matches || {})[0]];
  return match?.mode === 'boll_box' ? match : null;
}

export function hitMarks (hit, ruleId) {
  const match = hit.matches?.[ruleId || Object.keys(hit.matches || {})[0]];
  if (!match) return hit.mark_lines || [];
  if (match.boll_geometry === 'endpoints_v1') return [
    { date: match.lookback_start, text: '四点起点' },
    { date: match.box_end, text: '四点终点' },
  ];
  if (match.mode === 'boll_box') return [
    { type: 'horizontal', text: '上轨中位参考', value: match.upper },
    { type: 'horizontal', text: '下轨中位参考', value: match.lower },
    ...(match.lookback_start ? [{ date: match.lookback_start, text: '矩形起点' }] : []),
  ];
  const maFlat = match.mode === 'ma_flat';
  const marks = [{ type: 'horizontal', text: maFlat ? '区间最高' : '箱体上轨', value: match.upper },
    { type: 'horizontal', text: maFlat ? '区间最低' : '箱体下轨', value: match.lower }]
    .filter(line => Number.isFinite(line.value));
  if (maFlat && match.lookback_start) marks.push({ date: match.lookback_start, text: '走平起点' });
  return marks;
}

export function cleanupPayload ({ mode, value, kind }) {
  const key = { count: 'keep_count', days: 'keep_days', size: 'max_kline_bytes' }[mode];
  if (!key) throw new Error('请选择清理方式');
  if (value == null || typeof value === 'boolean' || String(value).trim() === '') throw new Error('请输入保留值');
  const number = Number(value);
  if (!Number.isInteger(number) || number < 0) {
    throw new Error('保留值须为 0 或正整数');
  }
  return { [key]: mode === 'size' ? number * 1024 * 1024 : number, ...(kind ? { kind } : {}), apply: false };
}

export const formatBytes = bytes => `${(Number(bytes || 0) / 1024 / 1024).toFixed(1)} MiB`;
export const frequencyLabel = value => ({ '60': '60 分钟', '1h': '1 小时', d: '日线' }[value] || value);
export const statusLabel = value => ({ completed: '完成', cancelled: '已停止 · 部分结果', failed: '失败' }[value] || value);
export const timestampLabel = value => value ? new Date(value * 1000).toLocaleString('zh-CN', { hour12: false }) : '—';
