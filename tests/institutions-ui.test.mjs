import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const code=await readFile(new URL('../web/institutions.js',import.meta.url),'utf8');
const {rankInstitutions,institutionMarkup,createInstitutionView}=await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
const rows=[
  {symbol:'2330',name:'台積電',kind:'stock',groups:{foreign:{buy:100,sell:40,net:60}}},
  {symbol:'2317',name:'鴻海',kind:'stock',groups:{foreign:{buy:200,sell:300,net:-100}}},
  {symbol:'0050',name:'ETF',kind:'etf',groups:{foreign:{buy:0,sell:0,net:0}}},
  {symbol:'9999',name:'missing',kind:'stock',groups:{foreign:{buy:null,sell:null,net:null}}},
];
test('net buy/sell differ from gross buy/sell; zeros and missing excluded',()=>{
  assert.deepEqual(rankInstitutions(rows,'foreign','net_buy').map(r=>r.symbol),['2330']);
  assert.deepEqual(rankInstitutions(rows,'foreign','net_sell').map(r=>r.symbol),['2317']);
  assert.deepEqual(rankInstitutions(rows,'foreign','buy').map(r=>r.symbol),['2317','2330']);
  assert.deepEqual(rankInstitutions(rows,'foreign','sell').map(r=>r.symbol),['2317','2330']);
  assert.deepEqual(rankInstitutions(rows,'foreign','buy','etf'),[]);
  assert.deepEqual(rankInstitutions(rows,'foreign','bogus'),[]);
});
test('every institution supports all four rankings with deterministic ties',()=>{
  for(const group of ['foreign','trust','dealer']){
    const data=[{symbol:'2330',groups:{[group]:{buy:20,sell:30,net:-10}}},{symbol:'2317',groups:{[group]:{buy:20,sell:30,net:-10}}}];
    for(const metric of ['buy','sell','net_sell'])assert.equal(rankInstitutions(data,group,metric)[0].symbol,'2317');
    assert.deepEqual(rankInstitutions(data,group,'net_buy'),[]);
  }
});
test('markup distinguishes quantity, data date, collection date and source failure',()=>{
  const html=institutionMarkup({as_of:'2026-10-16',sessions:5,dates:['2026-10-12','2026-10-16'],rows,
    coverage:{universe_symbols:4,complete_symbols:2},health:{status:'error',error:'<img onerror=bad>',checked_at:'check'},notes:['foreign rule']},
    {group:'foreign',metric:'buy',kind:'all',page:1});
  assert.match(html,/買進總量/);assert.match(html,/股/);assert.match(html,/2026-10-16/);assert.match(html,/check/);
  assert.match(html,/保留已保存/);assert.ok(!html.includes('<img'));assert.match(html,/data-detail-symbol="2317"/);
});
test('pagination never loses global rank and missing rows stay out',()=>{
  const data=Array.from({length:21},(_,i)=>({symbol:String(i),kind:'stock',groups:{trust:{buy:100-i,sell:1,net:99-i}}}));
  const html=institutionMarkup({rows:data,dates:[],coverage:{},health:{}},{group:'trust',metric:'buy',kind:'all',page:2});
  assert.match(html,/第 2 \/ 3 頁/);assert.match(html,/data-detail-symbol="10"/);assert.ok(!html.includes('data-detail-symbol="0"'));
});
test('selected quantity is the first metric column, including narrow screens',()=>{
  for(const [metric,label] of [['net_buy','淨買賣'],['net_sell','淨買賣'],['sell','賣出總量']]){
    const html=institutionMarkup({rows,dates:[],coverage:{},health:{}},{group:'foreign',metric});
    const header=html.match(/<thead>(.*?)<\/thead>/s)?.[1];
    assert.ok(header.indexOf(label+'（股）')<header.indexOf('買進總量（股）'));
  }
});
test('static view never requests local API',async()=>{
  let calls=0;const root={innerHTML:'',addEventListener(){}};
  const ctl=createInstitutionView(root,()=>{calls++;},true);
  await ctl.load('one');assert.equal(calls,0);assert.match(root.innerHTML,/本機/);
});
test('snapshot and period request generations prevent stale overwrite',async()=>{
  const pending=[];const root={innerHTML:'',addEventListener(){}};
  const ctl=createInstitutionView(root,url=>new Promise(resolve=>pending.push({url,resolve})));
  const first=ctl.load('one');const second=ctl.load('two',5);
  assert.match(pending[1].url,/sessions=5/);pending[1].resolve({as_of:'new',rows:[],dates:[],coverage:{},health:{}});await second;
  pending[0].resolve({as_of:'old',rows:[],dates:[],coverage:{},health:{}});await first;
  assert.match(root.innerHTML,/new/);assert.ok(!root.innerHTML.includes('old'));
});
