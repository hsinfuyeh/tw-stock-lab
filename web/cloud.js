// Only non-secret run references are stored for progress after a reload.
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
    async status(){
      if(!reference)return {running:false,status:'idle',sources:{}};
      const query=new URLSearchParams(reference);
      const {job}=await fetcher(`${base}/job?${query}`);
      return job;
    }
  };
}
