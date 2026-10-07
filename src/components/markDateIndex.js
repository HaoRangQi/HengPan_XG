// Mark only an actual visible candle. Never invent a midpoint or another month.
export function markDateIndex (target, dates) {
  if (!target) return -1;
  const normalized = String(target).replace('T', ' ').replace(/\.\d+(Z)?$/, '').replace(/Z$/, '');
  const exact = dates.findIndex(date => String(date).replace('T', ' ').replace(/\.\d+(Z)?$/, '').replace(/Z$/, '') === normalized);
  if (exact >= 0 || normalized.length > 10) return exact;
  return dates.findIndex(date => String(date).slice(0, 10) === normalized);
}
