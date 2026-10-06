const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=(v,suffix='',scale=1)=>typeof v==='number'&&Number.isFinite(v)?`${(v*scale).toFixed(2)}${suffix}`:'—';
const pct=v=>num(v,'%');
const ratio=v=>num(v,'%',100);
const status={pending:'等待到期',evaluated:'已評估',not_filled:'未成交',not_comparable:'不可比較'};
const labels={stock:'股票',passive_etf:'被動 ETF',active_etf:'主動 ETF'};
const table=(heads,rows)=>`<div class="research-table-wrap"><table class="research-table"><thead><tr>${heads.map(h=>`<th scope="col">${h}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`;

export function marketMarkup(summary){
  if(!summary)return '<p class="research-muted">尚無市場摘要資料。</p>';
  const m=summary.market||{},c=summary.coverage||{};
  const coverage=key=>`${c[key]?.eligible??0}/${c[key]?.total??0} 檔`;
  const cards=[['漲／跌／平',`${m.advancers??'—'} / ${m.decliners??'—'} / ${m.unchanged??'—'}`,coverage('daily_return')],['股票日等權',pct(m.equal_weight_return_pct),coverage('daily_return')],['站上 20 日均線',ratio(m.above_ma20_ratio),coverage('ma20')],['成交值／前 20 日',num(m.turnover_ratio_20,' 倍'),coverage('turnover_ratio_20')]];
  return `<div class="section-heading"><div><p class="section-kicker">市場背景 · ${esc(summary.as_of)}</p><h2>市場與產業</h2></div></div>
    <div class="research-metrics">${cards.map(([label,value,denom])=>`<div><span>${label}</span><strong>${value}</strong><small>有效 ${denom}</small></div>`).join('')}</div>
    <p class="research-muted">只計上市普通股；各指標使用自己的有效集合。產業未記錄 ${esc(summary.classification_missing??0)} 檔。</p>
    <p class="research-muted">分類來源與取得時間：${(summary.classification_sources||[]).map(r=>`${esc(r.url)} · ${esc(r.retrieved_at)}`).join('；')||'未記錄'}。抓取時間不等於公告時間。</p>
    <details class="method-details"><summary>產業明細與資料覆蓋</summary>${table(['官方產業別','有效日報酬','日報酬中位數','上漲比例','成交值占比','20 日中位數','候選數'],(summary.industries||[]).map(r=>`<tr><th scope="row">${esc(r.industry)}${r.small_sample?'<small class="research-warning">樣本偏少</small>':''}</th><td>${r.valid_count??0}/${r.total??0}</td><td>${pct(r.median_return_pct)}</td><td>${ratio(r.advancing_ratio)}</td><td>${ratio(r.turnover_share)}<small>${r.turnover_count??0}/${r.total??0} 檔 · 缺 ${(r.total??0)-(r.turnover_count??0)} 檔</small>${r.turnover_small_sample?'<small class="research-warning">成交值樣本偏少</small>':''}</td><td>${pct(r.median_20_return_pct)}<small>${r.momentum20_count??0}/${r.total??0} 檔 · 缺 ${(r.total??0)-(r.momentum20_count??0)} 檔</small>${r.momentum20_small_sample?'<small class="research-warning">20 日樣本偏少</small>':''}</td><td>${r.candidate_count??0}</td></tr>`))}
      <p class="research-muted">產業別保留官方代碼；舊快照不回填今天的分類。有效樣本少於五檔，不作強弱判斷。缺值顯示 —。</p></details>`;
}

export function researchMarkup(report){
  if(!report||report.status==='insufficient_data')return '<p class="research-muted">尚無已保存快照，無法產製績效與追蹤報告。</p>';
  const rows=[];
  for(const [key,group] of Object.entries(report.performance||{})){
    for(const [which,label] of [['top10','前十名'],['baseline','同日全部合格']]){
      const r=group[which]||{},counts=r.counts||{};
      rows.push(`<tr><th scope="row">${labels[key]||esc(key)} · ${label}</th><td>${r.mature_signal_dates??0} / ${r.comparable_signal_dates??0}</td><td>${counts.evaluated??0} / ${counts.pending??0}</td><td>${counts.not_filled??0} / ${counts.not_comparable??0}</td><td>${pct(r.mean_net_return_pct)}</td><td>${pct(r.median_net_return_pct)}</td><td>${ratio(r.target_fill_rate)}</td><td>${pct(r.average_gain_pct)} / ${pct(r.average_loss_pct)}</td><td>${num(r.profit_factor)}</td><td>${ratio(r.top5_gain_share)}</td><td>${which==='top10'?pct(group.paired_difference_pct):'—'}<small>${which==='top10'?`${group.paired_dates??0} 配對日`:''}</small></td></tr>`);
    }
  }
  const tracking=(report.tracking||[]).filter(r=>r.rank>=1&&r.rank<=10);
  return `<p class="section-kicker">${esc(report.policy_version||'trade-policy-v1')} · ${esc(report.as_of)} · 本機研究</p><h2>成本後績效</h2>
    <p class="research-muted">訊號日等權：同日先平均，再跨日等權。重疊候選實驗不是固定資金投資組合；尚未滿十日不納入完成績效。</p>
    ${table(['組別／集合','成熟／可比較日','評估／等待筆','未成交／缺漏筆','平均淨報酬','中位淨報酬','保守目標比例','平均盈／虧','獲利因子','前五筆獲利占比','相對基準差額'],rows)}
    ${report.baseline_missing_records?`<p class="research-warning">${esc(report.baseline_missing_records)} 筆缺完整合格集合，僅追蹤、不納入基準比較。</p>`:''}
    ${report.local_import?.missing_snapshots?.length?`<p class="research-warning">匯入來源缺 ${report.local_import.missing_snapshots.length} 份歷史快照，未納入績效。已保存的最新快照可正常追蹤。</p>`:''}
    ${report.local_import?.note?`<p class="research-muted">${esc(report.local_import.note)}</p>`:''}
    <details class="method-details"><summary>固定規則與統計說明</summary><div class="method-body"><p>次一實際交易日開盤進場，進場日算第一日，最多十日，無停損。目標是按跳動單位向上取整的毛 +5%，不是淨 +5%。後續開盤達目標以開盤模擬出場；日高須高於目標至少一檔才以目標模擬出場，僅觸及不視為成交；否則第十日收盤出場。</p><p>股票賣出稅 0.3%、ETF 0.1%；雙邊手續費各 0.1425%、滑價各 0.05%。均屬日線假設，不能證明實際成交。獲利因子無虧損時不計；前五筆獲利占比使用按日權重後的正報酬贡献。中位數為各日中位數的跨日中位數。</p><p>不利變動只計出場日前的最低價；出場当日盤中先後未知。缺日與已辨識公司行動排除；未還原行情仍可能漏掉未標示公司行動。</p></div></details>
    <h2 class="research-tracking-title">原候選追蹤 <small>前十名 · ${tracking.length} 筆</small></h2>
    ${table(['原訊號／順位','標的','狀態／經過交易日','原理由','進場／目標','出場／原因','淨報酬','出場日前不利變動'],tracking.map(r=>`<tr><td>${esc(r.signal_date)}<small>第 ${r.rank} 名 · ${esc(r.snapshot_id)}</small></td><th scope="row"><button class="button button-quiet" data-research-symbol="${esc(r.symbol)}">${esc(r.symbol)} ${esc(r.name)}</button></th><td>${status[r.status]||esc(r.status)}<small>${r.elapsed_sessions??0} / 10 日</small></td><td>${esc((r.reasons||[]).join('、')||'未記錄')}</td><td>${num(r.entry_price)} / ${num(r.target_price)}<small>${esc(r.entry_date||'—')}</small></td><td>${num(r.exit_price)}<small>${esc(r.exit_date||'—')} · ${esc(({expiry_close:'十日收盤',gap_open:'開盤達標',conservative_target:'高過目標一檔'})[r.reason]||r.reason||'—')}</small></td><td>${pct(r.net_return_pct)}</td><td>${pct(r.adverse_before_exit_pct)}</td></tr>`))}
    ${tracking.length?'':'<p class="research-muted">此版本尚無封存候選。</p>'}`;
}

export function initResearch({fetchReport,openSecurity=()=>{},staticMode=false,marketContainer=null,reportContainer=null}){
  let generation=0;
  reportContainer?.addEventListener('click',e=>{const button=e.target.closest('[data-research-symbol]');if(button)openSecurity(button.dataset.researchSymbol);});
  return {async load(id){
    const current=++generation;
    if(staticMode){if(reportContainer)reportContainer.innerHTML='<p class="research-muted">此靜態版本尚未產製成本後報告，請在本機開發版查看。</p>';return;}
    try{
      const report=await fetchReport(id);if(current!==generation)return;
      if(marketContainer)marketContainer.innerHTML=marketMarkup(report.market_summary);
      if(reportContainer)reportContainer.innerHTML=researchMarkup(report);
    }catch(error){if(current!==generation)return;for(const element of [marketContainer,reportContainer])if(element)element.innerHTML=`<p role="alert">研究報告載入失敗：${esc(error.message)}</p>`;}
  }};
}
