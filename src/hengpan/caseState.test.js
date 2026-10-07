import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

for (const file of ['HengpanScanView.vue', 'CryptoHengpanScanView.vue']) {
  const source = readFileSync(new URL(file, import.meta.url), 'utf8');
  const stateCode = source.slice(source.indexOf('const caseState ='), source.indexOf('\nonActivated(loadHistories);', source.indexOf('const caseState =')));

  function setup () {
    const requests = [];
    const factory = new Function('reactive', 'activeRuleId', 'activeRule', 'MODES', 'fmtPrice', 'fmtPct', 'scan', 'buildPayload', 'axios', 'notify', 'fullRows', `${stateCode}\nreturn { caseState, caseKey, resetCaseState, saveToCases };`);
    const state = factory(value => value, { value: '1' }, { value: { params: { lookback: 30 } } }, { tolerant: { label: '容刺箱体' } }, String, String, { params: {} }, () => ({}), {
      post: () => new Promise((resolve, reject) => requests.push({ resolve, reject })),
    }, () => {}, async () => []);
    const item = { code: 'test', symbol: 'test', name: '测试', base_asset: '测试', match: { mode: 'tolerant', lower: 1, upper: 2, actual_range: 0.1 } };
    return { ...state, requests, item };
  }

  test(`${file} 重扫和历史载入均重置案例状态`, () => {
    assert.match(source, /async function startScan[\s\S]*?resetCaseState\(\)/);
    assert.match(source, /function applySnapshot[\s\S]*?resetCaseState\(\)/);
    const state = setup();
    state.caseState[state.caseKey(state.item)] = 'saved';
    state.resetCaseState();
    assert.deepEqual(state.caseState, {});
  });

  for (const failed of [false, true]) {
    test(`${file} 旧请求${failed ? '失败' : '成功'}不覆盖新请求`, async () => {
      const state = setup();
      const key = state.caseKey(state.item);
      const oldSave = state.saveToCases(state.item);
      await Promise.resolve();
      state.resetCaseState();
      const newSave = state.saveToCases(state.item);
      await Promise.resolve();
      if (failed) state.requests[0].reject(new Error('test'));
      else state.requests[0].resolve({});
      await oldSave;
      assert.equal(state.caseState[key], 'saving');
      state.requests[1].resolve({});
      await newSave;
      assert.equal(state.caseState[key], 'saved');
    });
  }
}
