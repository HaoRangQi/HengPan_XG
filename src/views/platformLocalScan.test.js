import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { applyPlatformScanSource, PLATFORM_SCAN_SOURCES } from './platformScanSource.js';

const source = readFileSync(new URL('./ScanView.vue', import.meta.url), 'utf8');

test('平台期扫描默认使用本地数据并保留旧版联网入口', () => {
  assert.match(source, /data_source:\s*['"]local['"]/);
  assert.match(source, /本地行情库/);
  assert.match(source, /旧版联网/);
  assert.match(source, /扫描过程(?:中)?不联网/);
});

test('本地来源固定为60分钟并关闭联网基本面筛选', () => {
  const config = {
    data_source: 'baostock',
    frequency: 'd',
    use_fundamental_filter: true,
    markets: ['sz_gem', 'bj'],
  };
  applyPlatformScanSource(config, 'local');
  assert.deepEqual(config, {
    data_source: 'local',
    frequency: '60',
    use_fundamental_filter: false,
    markets: ['sz_gem'],
  });
  assert.deepEqual(PLATFORM_SCAN_SOURCES.map(item => item.value), ['local', 'baostock']);
});
