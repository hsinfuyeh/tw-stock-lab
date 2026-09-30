const names={ptt:'PTT',dcard:'Dcard',threads:'Threads'};
const statuses={success:'已取得',partial:'部分取樣',failed:'收集失敗',not_configured:'尚未授權',disabled:'暫緩收集',unavailable:'來源未接通',queued:'等待收集',collecting:'收集中'};
const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const date=value=>value?new Intl.DateTimeFormat('zh-TW',{timeZone:'Asia/Taipei',dateStyle:'short',timeStyle:'short'}).format(new Date(value)):'尚未收集';

export function socialPage(report,windowKey,source,page=1){
  const rows=(report?.windows?.[windowKey]||[]).filter(r=>source==='all'||(r.counts?.[source]??0)>0)
    .slice().sort((a,b)=>(source==='all'?b.total-a.total:b.counts[source]-a.counts[source])||String(a.symbol).localeCompare(String(b.symbol)));
  const pages=Math.max(1,Math.ceil(rows.length/10));
  page=Math.max(1,Math.min(pages,page));
  return {rows:rows.slice((page-1)*10,page*10),total:rows.length,pages,page,start:(page-1)*10};
}

function safeLink(value,source){
  try{
    const url=new URL(value);
    const allowed={ptt:['www.ptt.cc'],dcard:['www.dcard.tw'],threads:['www.threads.com','www.threads.net','threads.com','threads.net']};
    return url.protocol==='https:'&&allowed[source]?.includes(url.hostname)?url.href:'';
  }catch{return '';}
}

export function createSocialUpdater(api,onJob,onDone,onError,schedule=setTimeout){
  let busy=false,retries=0;
  async function accept(job){
    onJob(job);
    if(job.running){schedule(poll,api.pollDelay||1500);return;}
    busy=false;await onDone();
  }
  async function poll(){
    try{const job=await api.status();retries=0;await accept(job);}
    catch(error){if(++retries<=3)schedule(poll,api.pollDelay||3000);else{busy=false;onJob({running:false,status:'failed'});onError(error.message||'無法確認收集狀態，請重新連線後再次讀取進度。');}}
  }
  return {async start(window){
    if(busy)return;busy=true;retries=0;onJob({running:true,status:'starting',sources:{}});
    try{await accept(await api.start(window));}
    catch(error){busy=false;onJob({running:false,status:'failed'});onError(error.message||'無法啟動收集，請確認更新服務仍在執行。');}
  },async resume(){
    if(busy)return;
    try{const job=await api.status();onJob(job);if(job.running){busy=true;schedule(poll,api.pollDelay||1500);}}
    catch(error){onError(error.message||'無法讀取社群收集狀態。');}
  }};
}

export function createSocialView(root,fetcher,api=null){
  let report=null,error='',loading=false,windowKey='24h',source='all',page=1,generation=0,job={running:false,status:'idle'};
  const $=selector=>root.querySelector(selector);
  const updater=api?createSocialUpdater(api,value=>{job=value;if(job.running&&['24h','7d'].includes(job.window)){windowKey=job.window;$('[data-social-window]').value=windowKey;}render();},async()=>{page=1;await load();},value=>{error=value;render();}):null;
  function render(){
    $('[data-social-status]').innerHTML=Object.entries(names).map(([key,name])=>{
      const s=report?.sources?.[key];
      const status=`${escape(statuses[s?.status]||'尚未收集')}${s?.error?` · ${escape(s.error)}`:''}`;
      const scope=escape(s?.scope||'尚無來源記錄');
      const checked=`檢查：${escape(date(s?.checked_at))} · 掃描 ${s?.scanned??'—'} 篇`;
      return `<div class="social-source social-source-desktop"><strong>${name}</strong><span>${status}</span><p>${scope}</p><small>${checked}</small></div>
        <details class="social-source social-source-mobile"><summary><strong>${name}</strong><span>${status}</span></summary><div class="social-source-details"><p>${scope}</p><small>${checked}</small></div></details>`;
    }).join('');
    const data=socialPage(report,windowKey,source,page);page=data.page;
    const available=source==='all'?Object.values(report?.sources||{}).some(s=>['success','partial'].includes(s.status)):['success','partial'].includes(report?.sources?.[source]?.status);
    $('[data-social-summary]').textContent=error||(loading?'正在讀取社群資料…':`收集時間：${date(report?.collected_at)} · ${windowKey==='24h'?'近 24 小時':'近 7 天'} · 依${source==='all'?'已取得來源合計':names[source]}篇數排序 · ${available?`${data.total} 檔有觀察到提及`:'來源尚未取得有效資料'}${report?.coverage_note?` · ${report.coverage_note}`:''}`);
    $('[data-social-results]').innerHTML=data.rows.length?`<div class="table-shell"><table class="social-table"><thead><tr><th>排序</th><th>標的</th><th>已取得來源合計</th><th>PTT</th><th>Dcard</th><th>Threads</th><th>原文依據</th></tr></thead><tbody>${data.rows.map((r,i)=>`<tr><td data-label="排序">${data.start+i+1}</td><td data-label="標的"><b>${escape(r.symbol)}</b><br>${escape(r.name)}</td><td data-label="已取得來源合計">${r.total} 篇</td>${Object.keys(names).map(s=>`<td data-label="${names[s]}">${r.counts[s]===null?'—':`${r.counts[s]} 篇`}</td>`).join('')}<td data-label="原文依據"><button class="button button-quiet" data-social-evidence="${escape(r.symbol)}">查看貼文</button><button class="social-detail" data-detail-symbol="${escape(r.symbol)}">個股詳情</button></td></tr>`).join('')}</tbody></table></div>`:`<p class="social-empty">${available?'本次觀察範圍內沒有符合這個期間／來源的貼文。':'尚未取得可用的社群資料；此狀態不代表沒有討論。'}</p>`;
    $('[data-social-page]').textContent=`第 ${page} / ${data.pages} 頁`;
    $('[data-social-pager]').hidden=!data.total;
    $('[data-social-prev]').disabled=page===1;
    $('[data-social-next]').disabled=page===data.pages;
    $('[data-social-evidence-panel]').hidden=true;
    const collected=report?.collected_at?new Date(report.collected_at).getTime():0;
    $('[data-social-stale]').hidden=!collected||Date.now()-collected<30*3600000;
    const button=$('[data-social-update]');
    button.disabled=!updater||job.running;
    button.textContent=job.running?'正在收集…':!updater?'雲端更新待設定':api.cloud?'雲端更新社群':'立即更新社群';
    $('[data-social-window]').disabled=job.running;
    const progress=$('[data-social-job]');
    progress.textContent=!updater?'雲端觸發服務尚未接通，目前由每日排程更新；也可使用下方「執行更新／查看進度」至 GitHub 手動啟動。':
      job.running?`${job.window==='7d'?'近 7 天':job.window==='24h'?'近 24 小時':'正在啟動'} · ${job.message||Object.entries(job.sources||{}).map(([key,s])=>`${names[key]}：${statuses[s.status]||s.status}`).join(' · ')}`:
      job.finished_at?`${job.status==='failed'?'收集未完成，保留先前結果':'收集完成'} · ${date(job.finished_at)}${job.status==='partial'?' · 部分來源未取得完整資料，請查看各平台狀態':''}${job.status==='failed'?` · ${Object.entries(job.sources||{}).map(([key,s])=>`${names[key]}：${statuses[s.status]||s.status}${s.error?`（${s.error}）`:''}`).join(' · ')}`:''}${job.error?` · ${job.error}`:''}`:
      api.cloud?'按下後啟動雲端收集與發布，可關閉電腦；完成後自動讀取新排行。Dcard 可能拒絕請求，Threads 公開搜尋尚未接通。':'按下後立即向來源收集所選期間；可能需要數分鐘。Dcard 重新嘗試公開 API，Threads 不使用個人帳號。';
  }
  root.addEventListener('change',event=>{
    if(event.target.matches('[data-social-window]')) windowKey=event.target.value;
    else if(event.target.matches('[data-social-source]')) source=event.target.value;
    else return;
    page=1;render();
  });
  root.addEventListener('click',event=>{
    const target=event.target.closest('button');if(!target)return;
    if(target.hasAttribute('data-social-update')&&updater){error='';updater.start(windowKey);}
    if(target.hasAttribute('data-social-prev')){page--;render();}
    if(target.hasAttribute('data-social-next')){page++;render();}
    if(target.hasAttribute('data-social-close')) $('[data-social-evidence-panel]').hidden=true;
    if(target.dataset.socialEvidence){
      const row=(report?.windows?.[windowKey]||[]).find(r=>r.symbol===target.dataset.socialEvidence);if(!row)return;
      const panel=$('[data-social-evidence-panel]');
      $('[data-social-evidence-title]').textContent=`${row.symbol} ${row.name} · 貼文依據`;
      $('[data-social-evidence-list]').innerHTML=row.evidence.filter(p=>source==='all'||p.source===source).map(p=>{
        const link=safeLink(p.url,p.source);
        return `<li><small>${names[p.source]} · ${escape(date(p.published_at))}</small><br>${link?`<a href="${escape(link)}" target="_blank" rel="noopener noreferrer">${escape(p.title||'查看原文')}</a>`:escape(p.title||'連結不可用')}</li>`;
      }).join('');
      panel.hidden=false;panel.scrollIntoView({behavior:'smooth',block:'start'});
    }
  });
  async function load(){
    const version=++generation;loading=true;error='';render();
    try{const result=await fetcher();if(version!==generation)return;report=result;}
    catch{if(version!==generation)return;error='社群資料讀取失敗，請稍後重新讀取。';}
    if(version===generation){loading=false;render();}
  }
  return {async load(){await load();if(updater)await updater.resume();},render};
}
