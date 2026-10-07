import test from 'node:test';
import assert from 'node:assert/strict';
import { createHistoryPersistence } from './historyPersistence.js';
const tick = () => new Promise(resolve => setImmediate(resolve));
test('terminal pending history gets one confirmation only', async () => {
 let callback, reads=0; const state={};
 const controller=createHistoryPersistence(state,{get:async()=>{reads++;return {data:{history_pending:true}};},post:async()=>({data:{saved:true}})},()=>{},fn=>{callback=fn;return 1;},()=>{});
 controller.observe('task',{history_pending:true});assert.equal(state.status,'pending');
 callback();await tick();assert.equal(reads,1);assert.equal(state.status,'pending');assert.equal(state.busy,false);
 await controller.retry();assert.equal(state.status,'saved');
});
test('history errors remain visible and successful retry refreshes history', async () => {
 const state={};let refreshed=0;
 const controller=createHistoryPersistence(state,{post:async()=>({data:{saved:true}})},()=>{refreshed++;});
 controller.observe('task',{history_error:'disk full'});assert.equal(state.error,'disk full');
 await controller.retry();assert.equal(state.status,'saved');assert.equal(refreshed,1);
});
test('old retry cannot mutate a newly selected task', async () => {
 let resolve;const state={};const controller=createHistoryPersistence(state,{post:()=>new Promise(r=>{resolve=r;})});
 controller.observe('old',{history_error:'failed'});const promise=controller.retry();controller.reset();resolve({data:{saved:true}});await promise;
 assert.equal(state.status,'idle');
});
test('all modern scan pages render save warning and retry integration', async () => {
 const {readFile}=await import('node:fs/promises');
 for (const file of ['views/ScanView.vue','views/CryptoScanView.vue','hengpan/HengpanScanView.vue','hengpan/CryptoHengpanScanView.vue']) {
  const source=await readFile(new URL(`../${file}`,import.meta.url),'utf8');
  assert.match(source,/<HistorySaveStatus :state="historyPersistence.state" @retry="historyPersistence.retry"/);
  assert.match(source,/historyPersistence.observe\(taskId, data\)/);
 }
 const source=await readFile(new URL('../hengpan/HengpanScanView.vue',import.meta.url),'utf8');
 assert.doesNotMatch(source,/盘中可能尚未完成|上证指数最新|不会错选/);
});
