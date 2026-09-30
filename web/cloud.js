// Only non-secret run references are stored. Update password stays in memory.
export function createCloudClient(endpoint,getKey,fetcher,storage){
  const url=new URL(endpoint);
  if(url.protocol!=='https:'||!url.hostname.endsWith('.workers.dev')||url.username||url.password||url.search||url.hash||url.pathname!=='/')throw Error('雲端服務網址必須是 HTTPS workers.dev 網址');
  const base=url.origin;
  let key='',reference;
  const storageKey='tw-stock-cloud-job';
  try{reference=JSON.parse(storage?.getItem(storageKey)||'null');}catch{}
  if(!reference||!/^\d{1,20}$/.test(reference.id||'')||!['market','social','all'].includes(reference.scope)||!['24h','7d'].includes(reference.window))reference=null;
  return {
    pollDelay:15000,
    async start(scope,window){
      if(!key)key=await getKey();
      if(!key)throw Error('已取消雲端更新');
      let payload;
      try{payload=await fetcher(`${base}/update`,{method:'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${key}`},body:JSON.stringify({scope,window})});}
      catch(error){if(error.status===401)key='';throw error;}
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
