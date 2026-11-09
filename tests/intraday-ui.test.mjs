import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const html=await readFile(new URL('../web/index.html',import.meta.url),'utf8');

test('primary navigation follows the five requested tabs exactly',()=>{
  const nav=html.match(/<nav class="main-nav"[\s\S]*?<\/nav>/)?.[0];
  assert.deepEqual([...nav.matchAll(/<a\b[^>]*>([^<]+)<\/a>/g)].map(m=>m[1]),
    ['首頁','建議名單','盤中排行','其他排行','社群聲量']);
  assert.match(html,/<title>台股研究台<\/title>/);
  assert.match(html,/<h1 id="pageTitle">台股研究台<\/h1>/);
  assert.match(html,/data-view="intraday"/);
  assert.match(html,/id="socialView"[^>]*data-view="social"/);
  assert.match(html,/href="#research"/);
});

test('intraday categories present a sidebar and honest disconnected details',async()=>{
  const {INTRADAY_RANKS,intradayMarkup}=await import('../web/intraday.js');
  for(const label of ['上市股票漲幅','上市股票跌幅','ETF 漲幅','ETF 跌幅','成交金額','成交量','開高排行','開低排行','開盤後漲幅','開盤後跌幅','開盤狀況分析','入場觀察名單']){
    assert.ok(Object.values(INTRADAY_RANKS).some(r=>r.label===label),label);
  }
  for(const key of Object.keys(INTRADAY_RANKS)){
    const markup=intradayMarkup(key);
    assert.match(markup,/class="rank-nav"/);assert.match(markup,/class="rank-content"/);
    assert.match(markup,/行情來源尚未連線/);assert.match(markup,/尚未接入/);
    assert.ok(!markup.includes('2026-10-16'));
    assert.equal((markup.match(/aria-pressed="true"/g)||[]).length,1);
  }
});

test('switching intraday categories never fetches or invents quotes',async()=>{
  const {createIntradayView}=await import('../web/intraday.js');
  let click;const root={innerHTML:'',addEventListener:(event,handler)=>{if(event==='click')click=handler;}};
  const view=createIntradayView(root);view.render();
  click({target:{closest:()=>({dataset:{intradayRank:'etf-losers'}})}});
  assert.match(root.innerHTML,/ETF 跌幅/);assert.match(root.innerHTML,/行情來源尚未連線/);
  click({target:{closest:()=>({dataset:{intradayRank:'__proto__'}})}});
  assert.match(root.innerHTML,/行情來源尚未連線/);
});
test('category selection preserves keyboard focus and mobile sidebar scroll',async()=>{
  const {createIntradayView}=await import('../web/intraday.js');
  let click,focused=false,nav={scrollLeft:0},markup='';
  const root={
    get innerHTML(){return markup;},
    set innerHTML(value){markup=value;focused=false;nav={scrollLeft:0};},
    addEventListener(event,handler){if(event==='click')click=handler;},
    querySelector(selector){return selector==='.rank-nav'?nav:{focus(){focused=true;}};}
  };
  createIntradayView(root);nav.scrollLeft=280;
  click({target:{closest:()=>({dataset:{intradayRank:'opening'}})}});
  assert.equal(focused,true);assert.equal(nav.scrollLeft,280);
  assert.match(markup,/data-intraday-rank="opening" aria-pressed="true"/);
});

test('live ranking separates ETFs, filters losers and escapes source text',async()=>{
  const {intradayMarkup}=await import('../web/intraday.js');
  const report={status:'live',coverage:3,universe_count:4,snapshot_at:'2026-11-09T09:10:10+08:00',rows:[
    {symbol:'2330',name:'台積電',kind:'stock',day_pct:-2},
    {symbol:'0050',name:'<ETF>',kind:'etf',day_pct:-1.2},
    {symbol:'0056',name:'高股息',kind:'etf',day_pct:1.5}
  ]};
  const markup=intradayMarkup('etf-losers',report);
  assert.match(markup,/0050/);
  assert.match(markup,/&lt;ETF&gt;/);
  assert.match(markup,/-1\.20%/);
  assert.doesNotMatch(markup,/2330|0056|行情來源尚未連線/);
  assert.doesNotMatch(intradayMarkup('watchlist',report),/0050|2330/);
});

test('market rankings show results beyond the first 50 and identify partial batches',async()=>{
  const {intradayMarkup}=await import('../web/intraday.js');
  const rows=Array.from({length:53},(_,index)=>({
    symbol:String(2000+index),name:'測試',kind:'stock',day_pct:53-index,
  }));
  const report={status:'live',scope:'market',rows,batch_count:3,batches_ok:2,
    coverage:53,universe_count:120,returned_count:80};
  const page=intradayMarkup('gainers',report,2);
  assert.match(page,/第 2／2 頁/);
  assert.match(page,/2052/);
  assert.doesNotMatch(page,/>2000 測試/);
  assert.match(page,/部分批次/);
  assert.match(page,/來源回傳 80 檔/);
});
