// Only non-secret run references are stored for progress after a reload.
export function reconcilePublishedJob(job,publication){
  const instant=value=>{
    const parts=typeof value==='string'&&/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.exec(value);
    if(!parts)return NaN;
    const [year,month,day,hour,minute,second]=parts.slice(1).map(Number);
    const leap=year%4===0&&(year%100!==0||year%400===0);
    const days=[31,leap?29:28,31,30,31,30,31,31,30,31,30,31];
    if(month<1||month>12||day<1||day>days[month-1]||hour>23||minute>59||second>59)return NaN;
    return Date.parse(value);
  };
  if(!job||job.running||!job.error||!['market','all'].includes(job.scope))return job;
  const published=instant(publication?.checked_at),failed=instant(job.finished_at);
  if(!Number.isFinite(published)||!Number.isFinite(failed)||published<=failed)return job;
  return {...job,status:'superseded',phase:'行情已由後續工作更新',error:null,previous_error:job.error,
    publication_checked_at:publication.checked_at,
    message:'先前手動工作未完成；後續已成功發布行情。原工作失敗紀錄仍保留，這不代表其他來源已恢復。'};
}

export function createCloudClient(endpoint,fetcher,storage){
  const url=new URL(endpoint);
  if(url.protocol!=='https:'||!url.hostname.endsWith('.workers.dev')||url.username||url.password||url.search||url.hash||url.pathname!=='/')throw Error('雲端服務網址必須是 HTTPS workers.dev 網址');
  const base=url.origin;
  let reference;
  const storageKey='tw-stock-cloud-job';
  try{reference=JSON.parse(storage?.getItem(storageKey)||'null');}catch{}
  if(!reference||!/^\d{1,20}$/.test(reference.id||'')||!['market','social','all'].includes(reference.scope)||!['24h','7d'].includes(reference.window))reference=null;
  return {
    pollDelay:15000,
    async start(scope,window){
      const payload=await fetcher(`${base}/update`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scope,window})});
      reference={id:payload.job.id,scope,window};
      try{storage?.setItem(storageKey,JSON.stringify(reference));}catch{}
      return {...payload.job,scope,window};
    },
    async status(publication){
      if(!reference)return {running:false,status:'idle',sources:{}};
      const query=new URLSearchParams(reference);
      const {job}=await fetcher(`${base}/job?${query}`);
      return reconcilePublishedJob(job,publication);
    }
  };
}
