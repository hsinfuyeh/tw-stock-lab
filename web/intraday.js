// Presentation only until a real intraday provider is configured.
export const INTRADAY_RANKS={
  gainers:{label:'上市股票漲幅',note:'上市普通股的當日漲幅排行，依行情來源的當日參考價計算。'},
  losers:{label:'上市股票跌幅',note:'上市普通股的當日跌幅排行，依行情來源的當日參考價計算。'},
  'etf-gainers':{label:'ETF 漲幅',note:'ETF 當日漲幅獨立排行，與普通股分開觀察。'},
  'etf-losers':{label:'ETF 跌幅',note:'ETF 當日跌幅獨立排行，與普通股分開觀察。'},
  amount:{label:'成交金額',note:'依盤中累計成交金額排序，並顯示各標的行情時間。'},
  volume:{label:'成交量',note:'依盤中累計成交量排序，單位與交易類別依實際行情來源標示。'},
  'gap-up':{label:'開高排行',note:'比較正式開盤價與當日參考價，列出開高標的。'},
  'gap-down':{label:'開低排行',note:'比較正式開盤價與當日參考價，列出開低標的。'},
  'from-open-up':{label:'開盤後漲幅',note:'比較最新正式成交價與開盤價，觀察開盤後的上漲幅度。'},
  'from-open-down':{label:'開盤後跌幅',note:'比較最新正式成交價與開盤價，觀察開盤後的下跌幅度。'},
  opening:{label:'開盤狀況分析',note:'觀察正式開盤與前 5／15／30 分鐘量價變化，試撮不視為正式成交。'},
  watchlist:{label:'入場觀察名單',note:'需取得盤中資料並完成策略驗證，才能提供有依據的入場觀察。'}
};

export function intradayMarkup(selected='gainers'){
  const key=Object.hasOwn(INTRADAY_RANKS,selected)?selected:'gainers',rank=INTRADAY_RANKS[key];
  const columns=key==='opening'?['標的','開盤價','開盤變化','前 5 分鐘','前 15 分鐘','前 30 分鐘','行情時間']:
    key==='watchlist'?['標的','觀察條件','入選理由','風險提示','訊號時間']:
    ['排序','標的','最新成交價','當日漲跌幅','開盤後漲跌幅','成交量','成交金額','行情時間'];
  return `<div class="intraday-connection" role="status"><strong>行情來源尚未連線</strong><span>尚未接入盤中行情，以下不顯示盤後數據或模擬報價。</span></div>
    <div class="intraday-meta"><div><small>行情來源</small><b>未設定</b></div><div><small>交易狀態</small><b>未連線</b></div><div><small>行情日期</small><b>—</b></div><div><small>最後行情時間</small><b>—</b></div></div>
    <div class="rankings-layout"><nav class="rank-nav" aria-label="盤中排行分類">${Object.entries(INTRADAY_RANKS).map(([id,r])=>`<button type="button" data-intraday-rank="${id}" aria-pressed="${id===key}">${r.label}</button>`).join('')}</nav>
      <div class="rank-content"><h3>${rank.label}</h3><p class="search-hint">${rank.note}</p>
        <p class="explore-summary">等待行情來源連線 · 未開始自動更新</p>
        ${key==='watchlist'?'<p class="intraday-notice">盤中策略尚未啟用，目前不產生買進建議或入場名單。</p>':''}
        <div class="research-table-wrap"><table class="research-table intraday-table"><thead><tr>${columns.map(c=>`<th scope="col">${c}</th>`).join('')}</tr></thead><tbody><tr><td colspan="${columns.length}" class="intraday-empty">${key==='watchlist'?'等待盤中資料及策略驗證後顯示觀察名單。':'連接即時行情後，這裡會顯示此分類的盤中排行。'}</td></tr></tbody></table></div>
        <p class="ranking-footnote">盤中行情與盤後研究分開呈現。正式成交、試撮、停牌與行情中斷須分別標示；資料未到或已過期時，不列為可交易訊號。</p>
      </div></div>`;
}

export function createIntradayView(root){
  let selected='gainers';
  const render=()=>{root.innerHTML=intradayMarkup(selected);};
  root.addEventListener('click',event=>{
    const key=event.target.closest('[data-intraday-rank]')?.dataset.intradayRank;
    if(!Object.hasOwn(INTRADAY_RANKS,key))return;
    const scrollLeft=root.querySelector?.('.rank-nav')?.scrollLeft??0;
    selected=key;render();
    const nav=root.querySelector?.('.rank-nav');
    if(nav)nav.scrollLeft=scrollLeft;
    root.querySelector?.(`[data-intraday-rank="${key}"]`)?.focus({preventScroll:true});
  });
  render();return {render};
}
