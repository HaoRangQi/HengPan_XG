import test from 'node:test';
import assert from 'node:assert/strict';
import { markDateIndex } from './markDateIndex.js';
test('date marks require a real visible candle including intraday time', () => {
  const dates=['2026-09-28 10:30:00','2026-09-28 11:30:00'];
  assert.equal(markDateIndex('2026-09-28 11:30:00',dates),1);
  assert.equal(markDateIndex('2026-09-28',dates),0);
  assert.equal(markDateIndex('2026-09-29',dates),-1);
  assert.equal(markDateIndex('2026-09-28 15:00:00',dates),-1);
  assert.equal(markDateIndex('2026-09-28',[]),-1);
});
