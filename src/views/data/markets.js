/**
 * 两个本地行情库的配置。A 股和加密货币各用各的接口、各存各的库，
 * 数据页用同一个面板组件（LocalStorePanel）按这里的配置渲染，界面一致、数据不混。
 */
import { formatCompact, formatCount, formatPercent, formatPrice } from './format.js';

export const ASHARE = {
  key: 'ashare',
  api: '/api/store',
  sourceName: 'Baostock',
  intervalLabel: '60 分钟线',
  itemName: '股票',
  unit: '只',
  groupParam: 'boards',
  groups: [
    { key: 'sh_main', label: '沪市主板', icon: 'account_balance', on: true },
    { key: 'sz_main', label: '深市主板', icon: 'location_city', on: true },
    { key: 'sz_gem', label: '创业板', icon: 'rocket_launch', on: true },
    { key: 'sh_star', label: '科创板', icon: 'science', on: false },
  ],
  // overview 接口里每个板块的统计，统一成 {key, rows, items, pool, first, last}
  groupStats: (overview) => (overview?.boards || []).map((b) => ({
    key: b.board, rows: b.rows, items: b.codes, pool: b.pool_codes, first: b.first_date, last: b.last_date,
  })),
  overviewFacts: (o) => [
    { icon: 'inventory_2', label: '股票池', value: `${formatCount(o.stock_count)} 只` },
    { icon: 'event_available', label: '交易日历', value: `${formatCount(o.trade_days)} 天` },
  ],
  clearPath: (group) => `/api/store/board/${group}`,
  syncBody: ({ groups, start, end }) => ({ boards: groups, frequency: '60', start, end, force_metadata: false, workers: 3 }),
  syncHint: '起始日期留空 = 按本地进度增量（已是最新的股票不发请求）；填了则补这个区间的历史。',
  list: { path: '/api/store/stocks', field: 'stocks', idKey: 'code' },
  sorts: [{ key: 'code', label: '代码' }, { key: 'bars', label: '根数' }],
  defaultSort: 'code',
  search: (item, keyword) => item.code.toLowerCase().includes(keyword) || (item.name || '').toLowerCase().includes(keyword),
  itemTitle: (item) => item.code,
  itemLabel: (item) => item.name,
  itemMeta: (item) => item.industry || '未知行业',
  itemAvatar: (item) => (item.name || item.code).slice(0, 1),
  itemRange: (item) => (item.first_date ? { first: item.first_date, last: item.last_date } : null),
  itemFacts: () => [],
  detail: {
    path: '/api/store/kline',
    idParam: 'code',
    adjust: true,
    priceDigits: 2,
    timeNote: '',
    columns: [
      { key: 'date', label: '时间', kind: 'time' },
      { key: 'open', label: '开', kind: 'price' },
      { key: 'high', label: '高', kind: 'price' },
      { key: 'low', label: '低', kind: 'price' },
      { key: 'close', label: '收', kind: 'close' },
      { key: 'volume', label: '成交量（股）', kind: 'count' },
      { key: 'amount', label: '成交额（元）', kind: 'compact' },
    ],
  },
  refetchBody: (id, start, end) => ({ code: id, start, end }),
  deleteParams: (id, start, end) => ({ code: id, start, end }),
  keepDaysHint: '60 分钟线默认保留 60 天（约 160 根）',
};

export const CRYPTO = {
  key: 'crypto',
  api: '/api/crypto',
  sourceName: 'Binance 永续',
  intervalLabel: '1 小时线',
  itemName: '交易对',
  unit: '个',
  groupParam: 'categories',
  groups: [
    { key: 'perpetual', label: '加密永续', icon: 'currency_bitcoin', on: true },
    { key: 'tradifi', label: 'TradFi 永续', icon: 'monitoring', on: true },
  ],
  groupStats: (overview) => (overview?.categories || []).map((c) => ({
    key: c.category, rows: c.rows, items: c.symbols, pool: c.pool_symbols, first: c.first_time, last: c.last_time,
  })),
  overviewFacts: (o) => [
    { icon: 'token', label: '正在交易', value: `${formatCount(o.symbol_count)} 个` },
    { icon: 'update', label: '行情快照', value: o.ticker_updated_at ? o.ticker_updated_at.replace('T', ' ').slice(5, 16) : '未同步' },
  ],
  clearPath: (group) => `/api/crypto/category/${group}`,
  syncBody: ({ groups, start, end, minQuoteVolume }) => ({
    categories: groups, interval: '1h', start, end, min_quote_volume: minQuoteVolume || 0,
  }),
  syncHint: '时间按北京时间。起始日期留空 = 增量同步（已是最新的交易对不发请求）；最后一根未走完的 K 线会自动截掉。',
  // 24 小时成交额下限：TradFi 整体流动性偏低，过滤后更干净
  volumeFilters: [
    { value: 0, label: '不限' },
    { value: 1e6, label: '≥ 100 万' },
    { value: 1e7, label: '≥ 1000 万' },
  ],
  ping: '/api/crypto/ping',
  list: { path: '/api/crypto/symbols', field: 'symbols', idKey: 'symbol' },
  sorts: [{ key: 'quoteVolume', label: '成交额' }, { key: 'symbol', label: '代码' }, { key: 'change', label: '涨跌' }],
  defaultSort: 'quoteVolume',
  search: (item, keyword) => item.symbol.toLowerCase().includes(keyword) || (item.baseAsset || '').toLowerCase().includes(keyword),
  itemTitle: (item) => item.symbol,
  itemLabel: (item) => item.baseAsset,
  itemMeta: (item) => `24h 成交额 ${formatCompact(item.quoteVolume)} USDT`,
  itemAvatar: (item) => (item.baseAsset || item.symbol).slice(0, 1),
  itemRange: (item) => (item.first_time ? { first: item.first_time, last: item.last_time } : null),
  itemFacts: (item) => [
    { label: '最新价', value: formatPrice(item.lastPrice) },
    { label: '24h', value: formatPercent(item.priceChangePercent), tone: Number(item.priceChangePercent) >= 0 ? 'rise' : 'fall' },
  ],
  detail: {
    path: '/api/crypto/kline',
    idParam: 'symbol',
    adjust: false,
    priceDigits: null,
    timeNote: '北京时间',
    columns: [
      { key: 'date', label: '开盘时间', kind: 'time' },
      { key: 'open', label: '开', kind: 'price' },
      { key: 'high', label: '高', kind: 'price' },
      { key: 'low', label: '低', kind: 'price' },
      { key: 'close', label: '收', kind: 'close' },
      { key: 'volume', label: '成交量（币）', kind: 'count' },
      { key: 'quote_asset_volume', label: '成交额（USDT）', kind: 'compact' },
      { key: 'number_of_trades', label: '笔数', kind: 'count' },
    ],
  },
  refetchBody: (id, start, end) => ({ symbol: id, start, end }),
  deleteParams: (id, start, end) => ({ symbol: id, start, end }),
  keepDaysHint: '1 小时线默认保留 60 天（1440 根）',
};
