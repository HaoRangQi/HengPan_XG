export const PLATFORM_SCAN_SOURCES = [
  { value: 'local', label: '本地行情库' },
  { value: 'baostock', label: '旧版联网' },
];

export const applyPlatformScanSource = (config, source) => {
  config.data_source = source;
  if (source === 'local') {
    config.frequency = '60';
    config.use_fundamental_filter = false;
    config.markets = config.markets.filter(market => market !== 'bj');
  }
  return config;
};
