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

export function hitMarks (hit, ruleId) {
  const match = hit.matches?.[ruleId || Object.keys(hit.matches || {})[0]];
  if (!match) return hit.mark_lines || [];
  return [{ type: 'horizontal', text: '箱体上轨', value: match.upper },
    { type: 'horizontal', text: '箱体下轨', value: match.lower }].filter(line => Number.isFinite(line.value));
}

export function cleanupPayload ({ mode, value, kind }) {
  const number = Number(value);
  if (!Number.isInteger(number) || number < 1) throw new Error('保留值须为正整数');
  const key = { count: 'keep_count', days: 'keep_days', size: 'max_kline_bytes' }[mode];
  if (!key) throw new Error('请选择清理方式');
  return { [key]: mode === 'size' ? number * 1024 * 1024 : number, ...(kind ? { kind } : {}), apply: false };
}

export const formatBytes = bytes => `${(Number(bytes || 0) / 1024 / 1024).toFixed(1)} MiB`;
export const frequencyLabel = value => ({ '60': '60 分钟', '1h': '1 小时', d: '日线' }[value] || value);
export const statusLabel = value => ({ completed: '完成', cancelled: '已停止 · 部分结果', failed: '失败' }[value] || value);
export const timestampLabel = value => value ? new Date(value * 1000).toLocaleString('zh-CN', { hour12: false }) : '—';
