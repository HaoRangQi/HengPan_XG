// ECharts K 线格式为 [open, close, low, high]，计算保留原精度，显示层再格式化。
export function calculateMovingAverage (period, values) {
  const closes = values.map(row => row[1] == null ? NaN : Number(row[1]));
  let sum = 0;
  let invalid = 0;
  return closes.map((close, index) => {
    if (Number.isFinite(close) && close > 0) sum += close;
    else invalid++;
    if (index >= period) {
      const previous = closes[index - period];
      if (Number.isFinite(previous) && previous > 0) sum -= previous;
      else invalid--;
    }
    return index >= period - 1 && invalid === 0 ? sum / period : null;
  });
}

export function withSelectedMA (option, values, period, visibleBars = null) {
  if (!Number.isInteger(period) || period < 2) return option;
  const name = `MA${period}`;
  const template = option.series.find(series => series.name === 'MA30');
  const selected = {
    ...template,
    id: 'selected-ma',
    name,
    type: 'line',
    data: calculateMovingAverage(period, values),
    smooth: false,
    showSymbol: false,
    itemStyle: { ...template?.itemStyle, color: template?.lineStyle?.color },
    lineStyle: { ...template?.lineStyle, width: 2, opacity: 1 },
  };
  const baseSeries = option.series.filter(series => !/^MA\d+$/.test(series.name)).map(series => {
    if (!series.markLine?.data) return series;
    return { ...series, markLine: { ...series.markLine, data: series.markLine.data.map(mark =>
      Number.isFinite(mark.yAxis)
        ? { ...mark, label: { ...mark.label, position: 'insideEndTop' } } : mark) } };
  });
  const result = {
    ...option,
    legend: { ...option.legend, data: ['K线', name], selected: { K线: true, [name]: true } },
    series: [...baseSeries, selected],
  };
  if (visibleBars && values.length) {
    const count = Math.min(values.length, visibleBars);
    result.dataZoom = [{ type: 'inside', disabled: true, xAxisIndex: 0,
      startValue: values.length - count, endValue: values.length - 1 }];
    result.xAxis = { ...option.xAxis, axisLabel: { ...option.xAxis?.axisLabel,
      interval: Math.max(0, Math.ceil(count / 4) - 1), showMaxLabel: true } };
  }
  return result;
}
