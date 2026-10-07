// 与后端一致：收盘价、总体标准差、不跨无效数据，预热不计入矩形长度。
export function calculateBollingerBands (rows, config) {
  const result = { upper: [], middle: [], lower: [] };
  const period = config.boll_period;
  const multiplier = config.boll_multiplier;
  let start = 0;
  for (let i = 0; i < rows.length; i++) {
    const row = rows[i];
    const prices = ['open', 'close', 'low', 'high'].map(key => Number(row[key]));
    const invalid = prices.some(price => !Number.isFinite(price) || price <= 0) ||
      prices[2] > Math.min(prices[0], prices[1]) || prices[3] < Math.max(prices[0], prices[1]) ||
      (row.volume != null && (!Number.isFinite(Number(row.volume)) || Number(row.volume) <= 0));
    if (invalid || (config.boll_start && row.date < config.boll_start)) start = i + 1;
    if (i - start + 1 < period) {
      for (const values of Object.values(result)) values.push(null);
      continue;
    }
    const scale = Number(row.close);
    const window = rows.slice(i - period + 1, i + 1).map(item => Number(item.close) / scale - 1);
    const mean = window.reduce((sum, value) => sum + value, 0) / period;
    const sigma = Math.sqrt(window.reduce((sum, value) => sum + (value - mean) ** 2, 0) / period);
    result.middle.push((mean + 1) * scale);
    result.upper.push((mean + 1 + multiplier * sigma) * scale);
    result.lower.push((mean + 1 - multiplier * sigma) * scale);
  }
  return result;
}

export function withBollingerBands (option, rows, config, dark = false, visibleBars = null) {
  if (config?.mode !== 'boll_box' || !Number.isInteger(config.boll_period) || config.boll_period < 2 ||
      !Number.isFinite(config.boll_multiplier) || config.boll_multiplier <= 0) return option;
  const bands = calculateBollingerBands(rows, config);
  const endpoints = config.boll_geometry === 'endpoints_v1' && config.lookback_start && config.box_end &&
    ['head_upper', 'head_lower', 'tail_upper', 'tail_lower'].every(key => Number.isFinite(config[key]));
  const colors = dark ? ['#3987e5', '#d95926', '#199e70'] : ['#2a78d6', '#eb6834', '#1baf7a'];
  const ink = dark ? '#e5e7eb' : '#374151';
  const names = ['上轨', '中轨', '下轨'].map(label => `BOLL${config.boll_period} ${label}`);
  const base = option.series.filter(series => !/^MA\d+$/.test(series.name) && !series.id?.startsWith('boll-'))
    .map(series => {
      if (series.type !== 'candlestick' || !config.lookback_start || !rows.length) return series;
      return { ...series,
        markLine: { ...series.markLine, data: (series.markLine?.data || []).filter(mark => !endpoints || !Number.isFinite(mark.yAxis)).map(mark =>
          Number.isFinite(mark.yAxis) ? { ...mark, label: { ...mark.label, color: ink,
            position: 'insideEndTop', fontSize: 10 } } : mark) },
        markArea: { silent: true,
        itemStyle: { color: dark ? 'rgba(57,135,229,0.10)' : 'rgba(42,120,214,0.07)' },
        label: { show: true, position: 'insideTopLeft', color: ink, fontSize: 10 },
        data: [[{ name: endpoints ? '首尾四点区间' : '旧版布林矩形区间', xAxis: config.lookback_start }, { xAxis: config.box_end || rows.at(-1).date }]] } };
    });
  const lines = ['upper', 'middle', 'lower'].map((key, index) => ({
    id: `boll-${key}`, name: names[index], type: 'line', data: bands[key],
    xAxisIndex: 0, yAxisIndex: 0, smooth: false, showSymbol: false, connectNulls: false,
    lineStyle: { width: endpoints ? 1 : 2, opacity: endpoints ? 0.65 : 1, color: colors[index], type: ['solid', 'dashed', 'dotted'][index] },
    itemStyle: { color: colors[index] },
    endLabel: { show: !visibleBars, formatter: names[index], color: ink, fontSize: 10 },
    labelLayout: { moveOverlap: 'shiftY' }, emphasis: { focus: 'series' },
  }));
  const outline = endpoints ? [{
    id: 'boll-outline', name: '首尾四点', type: 'line', smooth: false,
    xAxisIndex: 0, yAxisIndex: 0, dimensions: ['time', 'price'], encode: { x: 'time', y: 'price' },
    data: [[config.lookback_start, config.head_upper], [config.box_end, config.tail_upper],
      [config.box_end, config.tail_lower], [config.lookback_start, config.head_lower],
      [config.lookback_start, config.head_upper]],
    showSymbol: true, symbol: 'circle', symbolSize: 8, z: 6,
    lineStyle: { width: 2, color: ink },
    itemStyle: { color: ink, borderColor: dark ? '#1e293b' : '#fff', borderWidth: 2 },
  }] : [];
  const legendNames = ['K线', ...names, ...(endpoints ? ['首尾四点'] : [])];
  const result = { ...option,
    legend: { ...option.legend, data: legendNames, selected: Object.fromEntries(legendNames.map(name => [name, true])) },
    series: [...base, ...lines, ...outline] };
  const headIndex = endpoints ? rows.findIndex(row => row.date === config.lookback_start) : -1;
  const frameStart = Math.max(0, headIndex - 5);
  if (endpoints && Array.isArray(result.dataZoom)) result.dataZoom = result.dataZoom.map(zoom => ({
    ...zoom, start: frameStart / Math.max(1, rows.length - 1) * 100, end: 100, filterMode: 'none',
  }));
  if (visibleBars && rows.length) {
    const start = endpoints ? Math.min(Math.max(0, rows.length - visibleBars), frameStart) : Math.max(0, rows.length - visibleBars);
    const count = rows.length - start;
    result.xAxis = { ...option.xAxis, axisLabel: { ...option.xAxis?.axisLabel,
      interval: Math.max(0, Math.ceil(count / 4) - 1), showMaxLabel: true } };
    result.dataZoom = [{ type: 'inside', disabled: true, xAxisIndex: 0,
      ...(endpoints ? { filterMode: 'none' } : {}), startValue: start, endValue: rows.length - 1 }];
  }
  return result;
}
