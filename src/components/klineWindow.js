export function latestBars (rows, count) {
  if (!Array.isArray(rows)) return [];

  const limit = Math.max(0, Math.floor(Number(count) || 0));
  if (!limit || rows.length <= limit) return rows;

  return rows.slice(-limit);
}

export function applyFullKlineDisplay (option, totalBars, visibleBars = 200, showBollinger = false) {
  const count = Number.isFinite(visibleBars) && visibleBars >= 1 ? Math.floor(visibleBars) : 200;
  const startValue = Math.max(0, totalBars - count);
  const endValue = Math.max(0, totalBars - 1);
  const hiddenNames = new Set(option.series
    .filter(series => ['boll-upper', 'boll-middle', 'boll-lower'].includes(series.id))
    .map(series => series.name));
  const series = showBollinger ? option.series : option.series.filter(item => !hiddenNames.has(item.name));
  const volumeIndex = series.findIndex(item => item.name === '成交量');
  return {
    ...option,
    legend: { ...option.legend, data: option.legend.data.filter(name => showBollinger || !hiddenNames.has(name)) },
    series,
    ...(option.visualMap && volumeIndex >= 0 ? { visualMap: { ...option.visualMap, seriesIndex: volumeIndex } } : {}),
    // 大图以用户指定根数为准，不让布林轮廓的自动取景覆盖窗口。
    dataZoom: option.dataZoom.map(({ start, end, ...zoom }) => ({
      ...zoom, startValue, endValue, rangeMode: ['value', 'value'],
    })),
  };
}

export function zoomStartForVisibleBars (total, visibleBars, fallback = 50) {
  const length = Math.max(0, Math.floor(Number(total) || 0));
  const visible = Math.max(0, Math.floor(Number(visibleBars) || 0));
  if (!length || !visible) return fallback;

  return Math.max(0, (1 - Math.min(visible, length) / length) * 100);
}
