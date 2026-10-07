import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const code=await readFile(new URL('../web/official.js',import.meta.url),'utf8');
const {summaryMarkup,detailMarkup,shadowMarkup,initOfficial}=await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);

test('summary distinguishes stale, zero and missing and escapes errors',()=>{
  const html=summaryMarkup({summary:{sources:{institution:{status:'error',covered_symbols:0,error:'<img onerror=evil>'}}},job:{}});
  assert.match(html,/0 檔/);assert.match(html,/失敗/);assert.ok(!html.includes('<img'));
});
test('detail shows official units, N/A, zero, safe sources and time provenance',()=>{
  const html=detailMarkup({signal_cutoff:'2026-10-07T19:00:00+08:00',features:{eligible:false},
    detail:{sources:{revenue:{status:'not_applicable',rows:[]},institution:{status:'stale',rows:[{
      values:{total_net:0},data_date:'2026-10-07',first_seen_at:'today',evidence:{url:'javascript:evil'}}]}}}});
  assert.match(html,/不適用/);assert.match(html,/0 股/);assert.match(html,/保留舊觀測/);
  assert.ok(!html.includes('href="javascript:'));assert.match(html,/首次取得/);
});
test('shadow insufficient never displays an improvement or probability',()=>{
  const html=shadowMarkup({status:'insufficient_data',summary:{valid_test_days:2,ci95_pct:null},days:[]});
  assert.match(html,/樣本不足/);assert.match(html,/—/);assert.ok(!html.includes('準確率提升'));
});
test('static mode performs no requests',async()=>{
  let calls=0;const box={innerHTML:'',addEventListener(){}};
  const ctl=initOfficial({staticMode:true,fetchJSON:async()=>{calls++;},summaryContainer:box,shadowContainer:box});
  await ctl.load('x');await ctl.detail('2330','x',box);await ctl.update();assert.equal(calls,0);
});
test('detail request generation prevents stale overwrite',async()=>{
  const pending=[];const box={innerHTML:'',addEventListener(){}};
  const ctl=initOfficial({fetchJSON:()=>new Promise(resolve=>pending.push(resolve))});
  const first=ctl.detail('2330','one',box);const second=ctl.detail('2317','one',box);
  pending[1]({detail:{sources:{}},signal_cutoff:'new'});await second;
  pending[0]({detail:{sources:{}},signal_cutoff:'old'});await first;
  assert.match(box.innerHTML,/new/);assert.ok(!box.innerHTML.includes('old'));
});
test('summary and shadow failures are independent and old load cannot replace new',async()=>{
  const resolvers=[];const summary={innerHTML:'',addEventListener(){}};const shadow={innerHTML:''};
  const ctl=initOfficial({fetchJSON:()=>new Promise((resolve,reject)=>resolvers.push({resolve,reject})),summaryContainer:summary,shadowContainer:shadow});
  const first=ctl.load('one');const second=ctl.load('two');
  resolvers[2].resolve({summary:{sources:{}},job:{},as_of:'new'});resolvers[3].reject(Error('<bad>'));await second;
  resolvers[0].resolve({summary:{sources:{}},as_of:'old'});resolvers[1].resolve({});await first;
  assert.match(summary.innerHTML,/new/);assert.ok(!summary.innerHTML.includes('old'));assert.ok(!shadow.innerHTML.includes('<bad>'));
});
test('same snapshot polling does not invalidate an outstanding detail',async()=>{
  let resolveDetail;const box={innerHTML:''};
  const ctl=initOfficial({fetchJSON:url=>url.includes('symbol=')?new Promise(resolve=>resolveDetail=resolve):Promise.resolve({summary:{sources:{}},job:{},days:[]})});
  await ctl.load('one');const detail=ctl.detail('2330','one',box);
  await ctl.load('one');resolveDetail({detail:{sources:{}},signal_cutoff:'retained'});await detail;
  assert.match(box.innerHTML,/retained/);assert.ok(!box.innerHTML.includes('正在讀取'));
});
test('compacted unknown inputs are not described as originally missing features',()=>{
  const html=detailMarkup({features_status:'unavailable_inputs',features:null,detail:{sources:{}}});
  assert.match(html,/無法重新核對/);assert.ok(!html.includes('當時影子特徵不足'));
});
