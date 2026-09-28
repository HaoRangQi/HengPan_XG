const fmtNum = (value, digits = 2) => (
  Number.isFinite(Number(value)) ? Number(value).toFixed(digits) : '—'
);

const fmtSignedPct = (value) => (
  Number.isFinite(value) ? `${value > 0 ? '+' : ''}${(value * 100).toFixed(2)}%` : '—'
);

const fmtPlainPct = (value) => (
  Number.isFinite(value) ? `${(value * 100).toFixed(2)}%` : '—'
);

const fmtVolume = (value) => {
  const shares = Number(value);
  if (!Number.isFinite(shares)) return '—';
  const lots = shares / 100;
  return lots >= 1e4
    ? `${(lots / 1e4).toFixed(2)} 万手`
    : `${Math.round(lots).toLocaleString('zh-CN')} 手`;
};

const fmtAmount = (value) => {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return '—';
  if (amount >= 1e8) return `${(amount / 1e8).toFixed(2)} 亿`;
  if (amount >= 1e4) return `${(amount / 1e4).toFixed(2)} 万`;
  return amount.toLocaleString('zh-CN', { maximumFractionDigits: 2 });
};

export const calculateBarMetrics = (rows, index) => {
  const row = rows[index];
  if (!row) return { change: null, amplitude: null, prevClose: null };

  const previous = index > 0 ? Number(rows[index - 1]?.close) : Number(row.open);
  const changeBase = Number.isFinite(previous) && previous > 0 ? previous : null;
  const close = Number(row.close);
  const amplitudeBase = Number.isFinite(close) && close > 0 ? close : null;

  return {
    prevClose: index > 0 ? changeBase : null,
    change: changeBase ? (close - changeBase) / changeBase : null,
    amplitude: amplitudeBase ? (Number(row.high) - Number(row.low)) / amplitudeBase : null,
  };
};

export const formatKlineTooltip = (params, rows, options = {}) => {
  const list = Array.isArray(params) ? params : [params];
  const bar = list.find(item => item.seriesName === 'K线') || list[0];
  const row = bar ? rows[bar.dataIndex] : null;
  if (!bar || !row) return '';

  const { change, amplitude, prevClose } = calculateBarMetrics(rows, bar.dataIndex);
  const isDarkMode = Boolean(options.isDarkMode);
  const tone = !Number.isFinite(change) || change === 0
    ? (isDarkMode ? '#bbb' : '#666')
    : change > 0
      ? (options.riseColor || (isDarkMode ? '#ff6b6b' : '#d93a3a'))
      : (options.fallColor || (isDarkMode ? '#3ecf8e' : '#1b9e5a'));
  const muted = isDarkMode ? '#aeb4bd' : '#666';
  const cell = (label, value, color) => (
    `<div style="display:flex;justify-content:space-between;gap:16px">` +
      `<span style="color:${muted}">${label}</span>` +
      `<strong style="color:${color || 'inherit'};font-variant-numeric:tabular-nums">${value}</strong>` +
    `</div>`
  );
  const averages = list
    .filter(item => item.seriesName?.startsWith('MA') && item.value != null)
    .map(item => cell(item.seriesName, fmtNum(item.value)));

  return [
    `<div style="min-width:240px;max-width:320px">`,
    `<div style="font-weight:600;margin-bottom:8px">${row.date}</div>`,
    `<div style="display:grid;grid-template-columns:1fr 1fr;gap:4px 18px">`,
    cell('开盘', fmtNum(row.open)),
    cell('收盘', fmtNum(row.close), tone),
    cell('最高', fmtNum(row.high)),
    cell('最低', fmtNum(row.low)),
    cell('涨跌幅', fmtSignedPct(change), tone),
    cell('振幅', fmtPlainPct(amplitude)),
    prevClose != null ? cell('前收', fmtNum(prevClose)) : '',
    row.volume != null ? cell('成交量', fmtVolume(row.volume)) : '',
    row.amount != null ? cell('成交额', fmtAmount(row.amount)) : '',
    row.turn != null && Number.isFinite(Number(row.turn))
      ? cell('换手率', `${fmtNum(row.turn)}%`)
      : '',
    averages.length ? `<div style="grid-column:1/-1;display:grid;gap:4px">${averages.join('')}</div>` : '',
    `</div>`,
    `</div>`,
  ].join('');
};
