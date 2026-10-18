const groups={foreign:'外資',trust:'投信',dealer:'自營商'};
const metrics={net_buy:'買超',net_sell:'賣超',buy:'買進總量',sell:'賣出總量'};
const esc=value=>String(value??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const finite=value=>typeof value==='number'&&Number.isFinite(value);
const num=value=>finite(value)?value.toLocaleString('zh-TW',{maximumFractionDigits:2}):'—';
const options=(values,selected)=>Object.entries(values).map(([key,label])=>`<option value="${key}" ${key===String(selected)?'selected':''}>${label}</option>`).join('');

export function rankInstitutions(rows,group,metric,kind='all'){
  if(!Object.hasOwn(groups,group)||!Object.hasOwn(metrics,metric)||!['all','stock','etf'].includes(kind))return [];
  const key=metric.startsWith('net_')?'net':metric;
  return rows.filter(row=>{
    const value=row.groups?.[group]?.[key];
    return (kind==='all'||row.kind===kind)&&finite(value)&&(metric==='net_sell'?value<0:value>0);
  }).sort((a,b)=>(metric==='net_sell'?1:-1)*(a.groups[group][key]-b.groups[group][key])||String(a.symbol).localeCompare(String(b.symbol)));
}

export function institutionMarkup(report,state={},context={}){
  const {group='foreign',metric='net_buy',kind='all',page=1,sessions=1}=state;
  const r=report||{},ranked=rankInstitutions(r.rows||[],group,metric,kind),pages=Math.max(1,Math.ceil(ranked.length/10));
  const selectedPage=Math.max(1,Math.min(pages,page)),start=(selectedPage-1)*10;
  const mode=metric.startsWith('net_')?'net':'gross',direction=metric.endsWith('sell')?'sell':'buy';
  const column=mode==='net'?'net':metric;
  const quantityLabels={buy:'買進總量',sell:'賣出總量',net:'淨買賣'};
  const columns=[column,...Object.keys(quantityLabels).filter(key=>key!==column)];
  const dates=(r.dates||[]).map(esc).join('、');
  const acquired=(r.rows||[]).flatMap(row=>(row.evidence||[]).map(e=>e.first_seen_at)).filter(Boolean).sort().at(-1);
  return `<div class="institution-controls">
    <label>法人<select data-institution-group>${options(groups,group)}</select></label>
    <label>計算方式<select data-institution-mode>${options({net:'買超／賣超（淨額）',gross:'買進／賣出總量'},mode)}</select></label>
    <label>排行<select data-institution-direction>${options(mode==='net'?{buy:'買超',sell:'賣超'}:{buy:'買進總量',sell:'賣出總量'},direction)}</select></label>
    <label>期間<select data-institution-sessions>${options({1:'單日',5:'近五個交易日'},sessions)}</select></label>
    <label>標的<select data-institution-kind>${options({all:'股票與 ETF',stock:'普通股',etf:'股票型 ETF'},kind)}</select></label>
    <button class="button button-quiet" data-institution-refresh ${context.loading||context.staticMode?'disabled':''}>重新讀取法人資料</button></div>
    <h3>${groups[group]} · ${metrics[metric]}排行</h3>
    ${context.staticMode?'<p class="research-muted">法人排行目前限本機開發版，靜態頁面未發布此研究資料。</p>':''}
    ${context.loading?'<p class="explore-summary" role="status">正在讀取法人排行…</p>':''}
    ${context.error?`<p class="research-warning" role="alert">讀取失敗：${esc(context.error)}，可按重新讀取再試。</p>`:''}
    <p class="explore-summary">資料日 ${esc(r.as_of)} · ${sessions===5?'五日累計':'單日'} · ${ranked.length} 檔符合本榜 · 完整資料 ${num(r.coverage?.complete_symbols)} / ${num(r.coverage?.universe_symbols)} 檔 · 單位：股</p>
    <p class="research-muted">交易日：${dates||'尚無資料'}。最近首次觀測 ${esc(acquired)}；來源檢查 ${esc(r.health?.checked_at)}。回顧排行採目前保存的官方版本，不代表原訊號當時已知。</p>
    ${r.health?.status==='error'?`<p class="research-warning">來源更新失敗，保留已保存的回顧資料：${esc(r.health.error)}</p>`:''}
    ${!context.loading&&!context.staticMode&&r.status==='insufficient_data'?'<p class="research-warning">此期間資料不足；五日累計必須具備完整五個實際交易日，不補零或改用較短窗口。</p>':''}
    ${ranked.length?`<div class="research-table-wrap"><table class="research-table institution-table"><thead><tr><th>排序</th><th>標的</th>${columns.map(key=>`<th class="${column===key?'institution-selected':''}">${quantityLabels[key]}（股）</th>`).join('')}<th>盤後收盤／漲跌</th><th>個股資訊</th></tr></thead><tbody>${ranked.slice(start,start+10).map((row,i)=>{
      const g=row.groups[group];return `<tr><td>${start+i+1}</td><th scope="row"><b>${esc(row.symbol)}</b><small>${esc(row.name)} · ${row.kind==='etf'?'ETF':'股票'}</small></th>${columns.map(key=>`<td class="${column===key?'institution-selected':''}">${num(g[key])}</td>`).join('')}<td>${num(row.close)} ${esc(row.currency||'TWD')}<small>${finite(row.change_pct)?`${num(row.change_pct)}%`:'—'}</small></td><td><button class="button button-quiet" data-detail-symbol="${esc(row.symbol)}">個股詳情</button></td></tr>`;
    }).join('')}</tbody></table></div>`:!context.loading&&!context.error&&!context.staticMode?'<p class="explore-empty">沒有符合本榜的有效非零資料；未涵蓋與零值不當成買超或賣超。</p>':''}
    <div class="pagination" ${!ranked.length?'hidden':''}><button class="button button-quiet" data-institution-prev ${selectedPage===1?'disabled':''}>上一頁</button><span>第 ${selectedPage} / ${pages} 頁</span><button class="button button-quiet" data-institution-next ${selectedPage===pages?'disabled':''}>下一頁</button></div>
    <details class="method-details"><summary>法人計算口徑與來源</summary><div class="method-body"><p>買超／賣超依官方淨買賣股數排序；買進／賣出總量分開依成交股數排序。同分以代號固定順序，零值與缺值不列入該榜。</p><p>${(r.notes||[]).map(esc).join(' ')}</p><p>外資為外陸資（不含外資自營商）。自營商買進與賣出各合併自行買賣及避險，淨額保留官方合計。股數排行不等於投入金額，股票與 ETF 可分開篩選。</p></div></details>`;
}

export function createInstitutionView(root,fetcher,staticMode=false){
  let generation=0,snapshotId=null,report=null,loading=false,error='';
  const state={group:'foreign',metric:'net_buy',kind:'all',page:1,sessions:1};
  const render=()=>{root.innerHTML=institutionMarkup(report,state,{loading,error,staticMode});};
  async function load(id,sessions=state.sessions){
    snapshotId=id;state.sessions=sessions;state.page=1;const token=++generation;
    report=null;error='';loading=!staticMode;render();if(staticMode)return;
    try{const data=await fetcher(`/api/institutions?sessions=${sessions}${id?`&id=${encodeURIComponent(id)}`:''}`);if(token!==generation)return;report=data;}
    catch(cause){if(token!==generation)return;error=cause.message||'服務暫時無法讀取';}
    loading=false;render();
  }
  root.addEventListener('change',event=>{
    const target=event.target;
    if(target.matches('[data-institution-group]'))state.group=target.value;
    else if(target.matches('[data-institution-kind]'))state.kind=target.value;
    else if(target.matches('[data-institution-mode]'))state.metric=(target.value==='net'?'net_':'')+(state.metric.endsWith('sell')?'sell':'buy');
    else if(target.matches('[data-institution-direction]'))state.metric=(state.metric.startsWith('net_')?'net_':'')+target.value;
    else if(target.matches('[data-institution-sessions]')){load(snapshotId,Number(target.value));return;}
    else return;
    state.page=1;render();
  });
  root.addEventListener('click',event=>{
    const button=event.target.closest('button');if(!button)return;
    if(button.hasAttribute('data-institution-refresh')){load(snapshotId);return;}
    if(button.hasAttribute('data-institution-prev'))state.page--;
    else if(button.hasAttribute('data-institution-next'))state.page++;
    else return;
    const pages=Math.max(1,Math.ceil(rankInstitutions(report?.rows||[],state.group,state.metric,state.kind).length/10));
    state.page=Math.min(pages,Math.max(1,state.page));render();
  });
  return {load};
}
