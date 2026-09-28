export function latestBars (rows, count) {
  if (!Array.isArray(rows)) return [];

  const limit = Math.max(0, Math.floor(Number(count) || 0));
  if (!limit || rows.length <= limit) return rows;

  return rows.slice(-limit);
}

export function zoomStartForVisibleBars (total, visibleBars, fallback = 50) {
  const length = Math.max(0, Math.floor(Number(total) || 0));
  const visible = Math.max(0, Math.floor(Number(visibleBars) || 0));
  if (!length || !visible) return fallback;

  return Math.max(0, (1 - Math.min(visible, length) / length) * 100);
}
