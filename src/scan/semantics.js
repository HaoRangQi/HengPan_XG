const BAR_ALIASES = {
  high_point_lookback_days: 'high_point_lookback_bars',
  rapid_decline_days: 'rapid_decline_bars',
  breakthrough_confirmation_days: 'breakthrough_confirmation_bars',
};
export function normalizePlatformParams (params = {}) {
  const result = { ...params };
  for (const [oldKey, newKey] of Object.entries(BAR_ALIASES)) {
    if (result[newKey] === undefined && result[oldKey] !== undefined) result[newKey] = result[oldKey];
    delete result[oldKey];
  }
  return result;
}
export const hasLegacyUnits = params => Number(params?.params_semantics_version || 0) < 2;
export function stStatus (item) {
  return item?.st_status_source && typeof item.is_st === 'boolean' ? item.is_st : null;
}
export function matchesStFilter (item, hideSt, onlyConfirmedNonSt) {
  const status = stStatus(item);
  return (!hideSt || status !== true) && (!onlyConfirmedNonSt || status === false);
}

export function lastChangeRatio (item) {
  if (Number.isFinite(item?.last_change_ratio)) return item.last_change_ratio;
  const rows = item?.kline_data;
  if (!Array.isArray(rows) || rows.length < 2) return null;
  const previous = Number(rows.at(-2).close), current = Number(rows.at(-1).close);
  return previous > 0 && Number.isFinite(current) ? (current - previous) / previous : null;
}
