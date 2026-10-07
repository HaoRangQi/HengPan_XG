import test from 'node:test';
import assert from 'node:assert/strict';
import { stStatus, matchesStFilter, normalizePlatformParams, hasLegacyUnits } from './semantics.js';
test('missing ST provenance is unknown, and hiding ST does not hide unknown', () => {
 for (const item of [{}, {is_st:false}, {is_st:true}, {is_st:null,st_status_source:'daily'}]) {
  assert.equal(stStatus(item), null); assert.equal(matchesStFilter(item, true, false), true); assert.equal(matchesStFilter(item, false, true), false);
 }
 assert.equal(matchesStFilter({is_st:true,st_status_source:'daily'}, true, false), false);
 assert.equal(matchesStFilter({is_st:false,st_status_source:'daily'}, true, true), true);
});
test('legacy parameter units normalize without mutating archived data', () => {
 const old = {high_point_lookback_days:365,rapid_decline_days:30,breakthrough_confirmation_days:2,decline_period_days:180};
 const normalized = normalizePlatformParams(old);
 assert.deepEqual(normalized,{high_point_lookback_bars:365,rapid_decline_bars:30,breakthrough_confirmation_bars:2,decline_period_days:180});
 assert.equal(old.rapid_decline_days,30); assert.equal(hasLegacyUnits(old),true);
 assert.equal(normalizePlatformParams({...old,rapid_decline_bars:8}).rapid_decline_bars,8);
 assert.equal(hasLegacyUnits({params_semantics_version:2}),false);
});
test('platform form payloads and help use explicit bar aliases and preserve calendar days', async () => {
 const { readFile } = await import('node:fs/promises');
 for (const file of ['../views/ScanView.vue','../views/CryptoScanView.vue','../views/LegacyScanView.vue']) {
  const text = await readFile(new URL(file,import.meta.url),'utf8');
  assert.match(text,/params_semantics_version: 2/);
  assert.match(text,/breakthrough_confirmation_bars/);
  assert.doesNotMatch(text,/high_point_lookback_days|rapid_decline_days|breakthrough_confirmation_days/);
 }
 const help = await readFile(new URL('../data/parameterHelp.js',import.meta.url),'utf8');
 assert.match(help,/以日历天为单位/); assert.match(help,/以 K 线根数为单位/);
});

test('thin and full result changes use fractions consistently', async () => {
  const { lastChangeRatio } = await import('./semantics.js');
  assert.equal(lastChangeRatio({ last_change_ratio: 0.01, kline_data: [] }), 0.01);
  assert.equal(lastChangeRatio({ kline_data: [{ close: 100 }, { close: 101 }] }), 0.01);
  assert.equal(lastChangeRatio({ kline_data: [] }), null);
});
