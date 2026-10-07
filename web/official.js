const esc=value=>String(value??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=value=>typeof value==='number'&&Number.isFinite(value)?value.toLocaleString('zh-TW',{maximumFractionDigits:2}):'—';
const pct=value=>typeof value==='number'&&Number.isFinite(value)?`${num(value)}%`:'—';
const names={institution:'法人籌碼',margin:'融資／融券',revenue:'月營收',announcement:'公司公告',action:'除權息線索'};
const states={success:'取得成功',error:'更新失敗',not_collected:'尚未取得',available:'已有觀測',missing:'來源未涵蓋／尚未可用',stale:'保留舊觀測 · 更新失敗',not_applicable:'不適用'};
const dayStates={late_entry:'決策晚於進場開盤',before_definition:'早於實驗凍結',insufficient_features:'時點資料不足',missing_universe:'缺原始候選母體',pending:'交易未成熟',not_comparable:'缺行情／未成交',corporate_action:'公司行動窗口',comparable:'可比較'};
const table=(heads,rows)=>`<div class="research-table-wrap"><table class="research-table"><thead><tr>${heads.map(h=>`<th scope="col">${h}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
function sourceLink(row){
  try{const url=new URL(row.evidence?.url);if(url.protocol==='https:'&&['www.twse.com.tw','openapi.twse.com.tw'].includes(url.hostname))return `<a href="${esc(url.href)}" target="_blank" rel="noopener noreferrer">官方原始來源</a>`;}catch{}
  return '來源網址不可核對';
}
function provenance(row){return `<small>資料日 ${esc(row.data_date)} · 首次取得 ${esc(row.first_seen_at)} · 公布 ${esc(row.published_at)} · ${sourceLink(row)}</small>`;}

export function summaryMarkup(report){
  const summary=report?.summary||{},job=report?.job||{};
  return `<div class="official-header"><div><p class="section-kicker">本機官方研究 · 行情截至 ${esc(report?.as_of)}</p><h2>資料來源與覆蓋</h2></div><button class="button" type="button" data-official-update ${job.running?'disabled':''}>${job.running?'官方資料更新中…':'更新官方研究資料'}</button></div>
    <p class="research-muted">首次更新後，往後本機行情更新會一起收集官方研究資料。新資料只加入研究與影子實驗。</p>
    ${job.error?`<p class="research-warning">${esc(job.error)}</p>`:''}
    ${table(['來源','狀態','本快照覆蓋','最新資料日','最後檢查／問題'],Object.entries(summary.sources||{}).map(([key,r])=>`<tr><th scope="row">${names[key]||esc(key)}</th><td>${states[r.status]||esc(r.status)}</td><td>${num(r.covered_symbols)} 檔${r.universe_symbols!=null?` / ${num(r.universe_symbols)} 檔`:''}</td><td>${esc(r.latest_data_date)}</td><td>${esc(r.checked_at)}${r.error?`<small class="research-warning">${esc(r.error)}</small>`:''}</td></tr>`))}
    <p class="research-muted">${(summary.notes||[]).map(esc).join(' ')}</p>`;
}

export function detailMarkup(report){
  const sources=report?.detail?.sources||{},f=report?.current_features;
  return `<h3>官方籌碼／營收／事件</h3><p class="research-muted">以下為目前取得的回顧資料。原訊號決策時刻：${esc(report?.signal_cutoff)}；${report?.features?.eligible?'當時具備完整影子特徵':'當時影子特徵不足，不回填過去訊號'}。</p>
    ${f?`<p>回顧五日法人淨買：${num(f.institution_net_5)} 股 · 占同期成交股數 ${f.institution_ratio_5==null?'—':pct(f.institution_ratio_5*100)} · 連續買超 ${num(f.buy_streak)} 日</p>`:''}
    ${Object.entries(sources).map(([source,data])=>`<details class="method-details" ${source==='institution'||source==='revenue'?'open':''}><summary>${names[source]||esc(source)} · ${states[data.status]||esc(data.status)}</summary><div class="method-body">${data.error?`<p class="research-warning">${esc(data.error)}</p>`:''}${(data.rows||[]).map(row=>{
      const v=row.values||{};let body='';
      if(source==='institution')body=`<p>官方三大法人淨買 ${num(v.total_net)} 股；外陸資 ${num(v.foreign_net)}、投信 ${num(v.trust_net)}、自營商 ${num(v.dealer_net)} 股。外資自營商另列 ${num(v.foreign_dealer_net)} 股。</p>`;
      if(source==='margin')body=`<p>融資餘額 ${num(v.financing_current)}（前日 ${num(v.financing_previous)}）；融券餘額 ${num(v.short_current)}（前日 ${num(v.short_previous)}）。單位：交易單位。</p><p>註記 ${esc(v.note||'無')} 指向次一營業日；前日餘額可能含更帳，餘額變動不等於買賣超。</p>`;
      if(source==='revenue')body=`<p>營收資料期 ${esc(row.period)} · 官方月增 ${pct(v.mom_pct)} · 年增 ${pct(v.yoy_pct)}。出表日 ${esc(v.export_date)}。</p><p>${esc(v.remark||'無備註')}；原始金額单位尚未核對，未換算金額。</p>`;
      if(source==='announcement')body=`<p><strong>${esc(v.headline)}</strong> · 條款 ${esc(v.clause)}</p><p>事實日 ${esc(v.fact_date)} · 公布時刻${v.time_status==='verified'?'已核對':'未能核對'}</p><details><summary>原公告說明</summary><p class="official-announcement">${esc(v.description)}</p></details>`;
      if(source==='action')body=`<p>${esc(row.data_date)} · ${esc(v.type)} · 官方現金股利 ${num(v.cash_dividend)}</p><p>部分公司行動線索，未涵蓋拆併股、減資等全部事件。</p>`;
      return `<div class="official-observation">${body}${provenance(row)}<details><summary>證據與版本</summary><small>${esc(row.parser_version)} · ${esc(row.content_hash)} · 原始檔 ${esc(row.evidence?.file)} · 可用時刻 ${esc(row.available_at)}</small></details></div>`;
    }).join('')||'<p class="research-muted">沒有可呈現的觀測；缺值不補零。</p>'}</div></details>`).join('')}`;
}

export function shadowMarkup(report){
  const r=report||{},s=r.summary||{};
  return `<p class="section-kicker">${esc(r.version||'official-shadow-v1')} · 固定影子實驗</p><h2>新資訊是否改善原排名</h2>
    <p class="research-warning">${r.status==='ready'?esc(s.conclusion):'樣本不足，尚不能判斷新規則是否改善預測。'}</p>
    <div class="research-metrics"><div><small>保存／實驗期訊號日</small><b>${num(r.saved_signal_days)} / ${num(r.prospective_signal_days)}</b></div><div><small>有效測試日／門檻</small><b>${num(s.valid_test_days??0)} / ${num(s.minimum_test_days??30)}</b></div><div><small>成本後每日差值</small><b>${pct(s.mean_difference_pct)}</b></div><div><small>95% 區塊區間</small><b>${s.ci95_pct?s.ci95_pct.map(pct).join(' ～ '):'—'}</b></div></div>
    <details class="method-details"><summary>固定規則與可用時點</summary><div class="method-body"><p>同一原候選普通股母體，要求完整五日法人股數／成交股數與三個月內營收年增率。原排名、法人比率、營收年增的百分位权重分別 70%、20%、10%；同分依原排名及代號，各取前十。信用交易、公告供人工核對。</p><p>前 30 訊號日暖機，隔開 10 日，每區測試 10 日，測試日期不重複；固定規則不擬合參數。所有入選交易滿十交易日且可比較才計入，同日先平均再跨日等權。十日區塊、2000 次固定種子重抽樣，至少 30 個有效測試日才提供區間。</p><p>決策须早於下一交易日 09:00，資料须在原快照時已取得。無達標機率，不自動換正式排名。</p><small>定義凍結 ${esc(r.frozen_at)} · ${esc(r.definition_sha256)}</small></div></details>
    ${table(['訊號日','狀態','普通股／時點合格','基準／影子淨報酬','差值'],(r.days||[]).slice(-20).reverse().map(d=>`<tr><td>${esc(d.signal_date)}</td><td>${dayStates[d.status]||esc(d.status)}</td><td>${num(d.candidate_count)} / ${num(d.eligible_count)}</td><td>${pct(d.baseline_return_pct)} / ${pct(d.shadow_return_pct)}</td><td>${pct(d.difference_pct)}</td></tr>`))}
    <p class="research-muted">${(r.notes||[]).map(esc).join(' ')}</p>`;
}

export function initOfficial({fetchJSON,summaryContainer=null,shadowContainer=null,staticMode=false,setTimer=setTimeout}){
  let generation=0,detailGeneration=0,currentId=null,updating=false;
  async function load(id){
    currentId=id;const token=++generation;++detailGeneration;
    if(staticMode){if(summaryContainer)summaryContainer.hidden=true;if(shadowContainer)shadowContainer.innerHTML='<p class="research-muted">官方研究與影子比較限本機開發版。</p>';return;}
    const suffix=id?`?id=${encodeURIComponent(id)}`:'';
    const results=await Promise.allSettled([fetchJSON(`/api/official${suffix}`),fetchJSON(`/api/shadow${suffix}`)]);
    if(token!==generation)return;
    if(summaryContainer)summaryContainer.innerHTML=results[0].status==='fulfilled'?summaryMarkup(results[0].value):`<p class="research-warning">官方資料暫時無法讀取：${esc(results[0].reason?.message)}</p>`;
    if(shadowContainer)shadowContainer.innerHTML=results[1].status==='fulfilled'?shadowMarkup(results[1].value):`<p class="research-warning">影子比較暫時無法讀取：${esc(results[1].reason?.message)}</p>`;
    if(results[0].status==='fulfilled'&&results[0].value.job?.running&&!updating)poll();
  }
  async function detail(symbol,id,container){
    const token=++detailGeneration;
    if(staticMode){container.innerHTML='<p class="research-muted">官方研究資料限本機開發版。</p>';return;}
    container.innerHTML='<p class="research-muted">正在讀取官方研究資料…</p>';
    try{const report=await fetchJSON(`/api/official?symbol=${encodeURIComponent(symbol)}${id?`&id=${encodeURIComponent(id)}`:''}`);if(token===detailGeneration)container.innerHTML=detailMarkup(report);}
    catch(error){if(token===detailGeneration)container.innerHTML=`<p class="research-warning">官方資料讀取失敗：${esc(error.message)}</p>`;}
  }
  function poll(){
    updating=true;
    setTimer(async()=>{
      try{const {job}=await fetchJSON('/api/official/job');if(job?.running){await load(currentId);poll();}else{updating=false;await load(currentId);}}
      catch(error){updating=false;if(summaryContainer)summaryContainer.innerHTML=`<p class="research-warning">更新狀態讀取失敗：${esc(error.message)}；重新讀取頁面可恢復。</p>`;}
    },1500);
  }
  async function update(){
    if(staticMode||updating)return;
    updating=true;
    try{await fetchJSON('/api/official/update',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});await load(currentId);poll();}
    catch(error){updating=false;if(summaryContainer)summaryContainer.innerHTML=`<p class="research-warning">更新未啟動：${esc(error.message)}；請重新讀取後再試。</p>`;}
  }
  summaryContainer?.addEventListener('click',event=>{if(event.target.closest('[data-official-update]'))update();});
  return {load,detail,update};
}
