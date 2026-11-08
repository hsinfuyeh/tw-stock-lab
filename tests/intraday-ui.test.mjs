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
