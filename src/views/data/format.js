/** 数据页用到的格式化小工具。 */

export function formatBytes (bytes) {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) { value /= 1024; index += 1; }
  return `${value.toFixed(index ? 1 : 0)} ${units[index]}`;
}

export function formatCount (value) {
  if (value === null || value === undefined || value === '') return '—';
  return Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 });
}

/** 大数字压缩成「亿 / 万」，成交额一眼能看出量级 */
export function formatCompact (value) {
  if (value === null || value === undefined || value === '' || Number.isNaN(Number(value))) return '—';
  const n = Number(value);
  if (Math.abs(n) >= 1e8) return `${(n / 1e8).toFixed(2)} 亿`;
  if (Math.abs(n) >= 1e4) return `${(n / 1e4).toFixed(1)} 万`;
  return n.toLocaleString('zh-CN', { maximumFractionDigits: 2 });
}

/**
 * 价格。digits 给定时固定小数位（A 股按分计价，复权价的浮点尾巴也一并收掉）；
 * 不给时按量级自适应（币价可能是 0.00001234）
 */
export function formatPrice (value, digits = null) {
  if (value === null || value === undefined || value === '') return '—';
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  if (digits !== null) return n.toFixed(digits);
  const abs = Math.abs(n);
  const places = abs >= 1000 ? 2 : abs >= 1 ? 4 : abs >= 0.01 ? 5 : 8;
  return Number(n.toFixed(places)).toString();
}

export function formatPercent (value) {
  if (value === null || value === undefined || value === '') return '—';
  const n = Number(value);
  return `${n > 0 ? '+' : ''}${n.toFixed(2)}%`;
}

/** Date → <input type="date"> 需要的 YYYY-MM-DD（按本地时区，避免 UTC 偏移） */
export function toDateInput (date) {
  const pad = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** 生成并下载 CSV。前缀 BOM，Excel 打开中文不乱码 */
export function downloadCsv (filename, columns, rows) {
  const cell = (value) => {
    if (value === null || value === undefined) return '';
    const text = String(value);
    return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  const lines = [columns.map((col) => cell(col.label)).join(',')];
  for (const row of rows) lines.push(columns.map((col) => cell(row[col.key])).join(','));
  const blob = new Blob([`﻿${lines.join('\n')}`], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
