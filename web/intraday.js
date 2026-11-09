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
  opening:{label:'開盤狀況分析',note:'觀察可確認參考價的標的開高、開低與平盤家數，以及開盤後漲跌。'},
  watchlist:{label:'入場觀察名單',note:'需取得盤中資料並完成策略驗證，才能提供有依據的入場觀察。'}
};

const statusText={
  unconfigured:['行情來源尚未連線','尚未接入盤中行情，以下不顯示盤後數據或模擬報價。'],
  live:['盤中快照','本機頁面開啟時，會定期檢查行情。'],
  closed:['已離開一般交易時段','顯示當日來源快照。'],
  outside_session:['目前不在盤中','開盤時段開始後會查詢。'],
  stale:['行情日期或時間已過期','已暫停顯示排行，等待有效快照。'],
  no_catalog:['缺少上市分類清單','請先完成一次本機市場資料更新。'],
  no_trades:['暫無可用成交','等待當日有效成交與行情時間。'],
  unauthorized:['行情授權未通過','請確認本機 API 金鑰及快照方案權限。'],
  rate_limited:['行情查詢達到頻率限制','稍後會再次檢查。'],
  unavailable:['暫時無法取得行情','稍後會再次檢查。'],
};
const rankRules={
  gainers:['day_pct',1,'stock'],losers:['day_pct',-1,'stock'],
  'etf-gainers':['day_pct',1,'etf'],'etf-losers':['day_pct',-1,'etf'],
  amount:['amount',1],volume:['volume',1],
  'gap-up':['gap_pct',1],'gap-down':['gap_pct',-1],
  'from-open-up':['from_open_pct',1],'from-open-down':['from_open_pct',-1],
};
const escapeHtml=value=>String(value??'—').replace(/[&<>"']/g,character=>({
  '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;',
})[character]);
const numeric=new Intl.NumberFormat('zh-TW',{maximumFractionDigits:4});
const number=value=>Number.isFinite(value)?numeric.format(value):'—';
const percent=value=>Number.isFinite(value)?`${value>0?'+':''}${value.toFixed(2)}%`:'—';
const quoteTime=value=>escapeHtml(value?.slice(11,19));

function rankedRows(key,rows){
  if(key==='opening')return rows.filter(row=>Number.isFinite(row.gap_pct))
    .sort((left,right)=>Math.abs(right.gap_pct)-Math.abs(left.gap_pct)||left.symbol.localeCompare(right.symbol));
  if(!Object.hasOwn(rankRules,key))return [];
  const [metric,direction,kind]=rankRules[key];
  return rows.filter(row=>(!kind||row.kind===kind)&&Number.isFinite(row[metric])&&row[metric]*direction>0)
    .sort((left,right)=>(right[metric]-left[metric])*direction||left.symbol.localeCompare(right.symbol));
}

export function intradayMarkup(selected='gainers',report={}){
  const key=Object.hasOwn(INTRADAY_RANKS,selected)?selected:'gainers',rank=INTRADAY_RANKS[key];
  const status=report.status||'unconfigured';
  const [label,note]=Object.hasOwn(statusText,status)?statusText[status]:statusText.unavailable;
  const usable=status==='live'||status==='closed';
  const watchlist=report.scope==='watchlist';
  const rows=rankedRows(key,usable?report.rows||[]:[]);
  const columns=key==='opening'?['標的','開盤價','開盤變化','開盤後漲跌幅','行情時間']:
    key==='watchlist'?['標的','觀察條件','入選理由','風險提示','訊號時間']:
    ['排序','標的','成交價','當日漲跌幅','開盤變化','開盤後漲跌幅','成交量（張）','成交金額（元）','行情時間'];
  const count=sign=>rows.filter(row=>Math.sign(row.gap_pct)===sign).length;
  const openingSummary=key==='opening'&&rows.length?
    `開高 ${count(1)} 檔 · 開低 ${count(-1)} 檔 · 平盤 ${count(0)} 檔。依開盤變化絕對值排序。`:'';
  const rowMarkup=rows.slice(0,50).map((row,index)=>{
    const security=`${escapeHtml(row.symbol)} ${escapeHtml(row.name)}${row.trial?' · 試撮中':''}`;
    const data=key==='opening'?[security,number(row.opening),percent(row.gap_pct),percent(row.from_open_pct),quoteTime(row.updated_at)]:
      [index+1,security,number(row.price),percent(row.day_pct),percent(row.gap_pct),
        percent(row.from_open_pct),number(row.volume),number(row.amount),quoteTime(row.updated_at)];
    return `<tr>${data.map(value=>`<td>${value}</td>`).join('')}</tr>`;
  }).join('');
  let empty=usable?'本分類目前沒有符合條件的成交資料。':'等待可用的盤中行情。';
  if(key==='watchlist')empty='等待盤中資料及策略驗證後顯示觀察名單。';
  if(watchlist&&key==='amount')empty='此來源未提供累計成交金額。';
  return `<div class="intraday-connection" role="status"><strong>${label}</strong><span>${note}</span></div>
    <div class="intraday-meta"><div><small>行情來源</small><b>${escapeHtml(report.source||'未設定')}</b></div><div><small>交易狀態</small><b>${label}</b></div><div><small>行情日期</small><b>${escapeHtml(report.snapshot_at?.slice(0,10))}</b></div><div><small>${watchlist?'最新成交時間':'快照時間'}（台灣）</small><b>${quoteTime(report.snapshot_at)}</b></div></div>
    <div class="rankings-layout"><nav class="rank-nav" aria-label="盤中排行分類">${Object.entries(INTRADAY_RANKS).map(([id,r])=>`<button type="button" data-intraday-rank="${id}" aria-pressed="${id===key}">${r.label}</button>`).join('')}</nav>
      <div class="rank-content"><h3>${rank.label}</h3><p class="search-hint">${rank.note}</p>
        ${usable?`<p class="explore-summary">${watchlist?'自選清單 · ':''}有成交資料 ${number(report.coverage)}／${number(report.universe_count)} 檔 · 本分類 ${rows.length} 檔，最多顯示前 50 檔。</p>`:''}
        ${openingSummary?`<p class="explore-summary">${openingSummary}</p>`:''}
        ${key==='watchlist'?'<p class="intraday-notice">盤中策略尚未啟用，目前不產生買進建議或入場名單。</p>':''}
        <div class="research-table-wrap"><table class="research-table intraday-table"><thead><tr>${columns.map(c=>`<th scope="col">${c}</th>`).join('')}</tr></thead><tbody>${rowMarkup||`<tr><td colspan="${columns.length}" class="intraday-empty">${empty}</td></tr>`}</tbody></table></div>
        <p class="ranking-footnote">${watchlist?'排名限自選清單。漲跌幅以 MIS 回傳的昨收欄位計算，請核對除權息日的參考價。行情時間依各標的回傳時間。':'涵蓋本機清單中的上市普通股與股票型原型 ETF。行情時間為各標的快照時間。參考價無法核對時，對應漲跌幅留空。'}</p>
      </div></div>`;
}

export function createIntradayView(root,fetchReport){
  let selected='gainers';
  let report, timer, generation=0, active=false;
  const render=(focus=false)=>{
    const scrollLeft=root.querySelector?.('.rank-nav')?.scrollLeft??0;
    const tableScroll=root.querySelector?.('.research-table-wrap')?.scrollLeft??0;
    root.innerHTML=intradayMarkup(selected,report);
    const nav=root.querySelector?.('.rank-nav');
    const table=root.querySelector?.('.research-table-wrap');
    if(nav)nav.scrollLeft=scrollLeft;
    if(table)table.scrollLeft=tableScroll;
    if(focus)root.querySelector?.(`[data-intraday-rank="${selected}"]`)?.focus({preventScroll:true});
  };
  async function refresh(run){
    if(!document.hidden){
      let next;
      try{next=await fetchReport();}
      catch{next={status:'unavailable'};}
      if(run!==generation)return;
      report=next;
      render(Boolean(root.contains(document.activeElement)));
    }
    if(run===generation&&report?.status!=='unconfigured'){
      timer=setTimeout(()=>refresh(run),15000);
    }
  }
  function setActive(visible){
    if(visible===active)return;
    active=visible;
    generation++;
    clearTimeout(timer);
    if(active&&fetchReport)refresh(generation);
    if(!active&&report){
      report=undefined;
      render();
    }
  }
  root.addEventListener('click',event=>{
    const key=event.target.closest('[data-intraday-rank]')?.dataset.intradayRank;
    if(!Object.hasOwn(INTRADAY_RANKS,key))return;
    selected=key;
    render(true);
  });
  render();return {render,setActive};
}
