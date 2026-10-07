import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
for (const [file, name, next] of [['CaseManager.vue','loadCases','openCase'],['CaseDetail.vue','loadCaseData','saveCase']]) {
 test(`${file} API errors stay visible without fabricated fallback data`, async () => {
  const source = readFileSync(new URL(file, import.meta.url),'utf8');
  const body = source.slice(source.indexOf(`const ${name} =`),source.indexOf(`const ${next} =`));
  const loading={value:false}, error={value:null}, cases={value:[]}, caseData={value:{}}, klineData={value:null}, analysisData={value:null}, editData={value:{}}, showFullKlineChart={value:false}, editMode={value:false};
  const load = new Function('axios','loading','error','cases','caseData','klineData','analysisData','editData','props','showFullKlineChart','editMode', `${body}; return ${name};`)({get:async()=>{throw new Error('offline');}},loading,error,cases,caseData,klineData,analysisData,editData,{caseId:'id'},showFullKlineChart,editMode);
  await load(); assert.equal(loading.value,false); assert.match(error.value,/加载案例/); assert.equal(klineData.value,null); assert.equal(analysisData.value,null);
  assert.doesNotMatch(body,/fetch\(|process.env|模拟/);
 });
}
