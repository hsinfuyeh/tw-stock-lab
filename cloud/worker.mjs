// GitHub credentials stay in Worker secrets; only fixed main workflows can run.
const workflow='market-pages.yml';
const activeStatuses=new Set(['queued','in_progress','waiting','pending','requested']);
function jobFor(run,scope,window){
  const running=activeStatuses.has(run.status);
  return {id:String(run.id),running,scope,window,status:running?run.status:run.conclusion==='success'?'success':'failed',
    started_at:run.created_at,finished_at:running?null:run.updated_at,
    message:running?'雲端工作執行中':run.conclusion==='success'?'更新完成，已發布':'雲端更新未完成，保留先前報告',
    error:!running&&run.conclusion!=='success'?'請查看 GitHub Actions 的失敗步驟。':null,
    url:`https://github.com/hsinfuyeh/tw-stock-lab/actions/runs/${run.id}`,sources:{}};
}
async function sameKey(supplied,expected){
  if(!expected||expected.length<24||!supplied)return false;
  const bytes=new TextEncoder();
  const [a,b]=await Promise.all([supplied,expected].map(s=>crypto.subtle.digest('SHA-256',bytes.encode(s))));
  let difference=0;const aa=new Uint8Array(a),bb=new Uint8Array(b);
  for(let i=0;i<aa.length;i++)difference|=aa[i]^bb[i];
  return difference===0;
}
export function createWorker(fetcher=fetch){
  return {async fetch(request,env){
    const origin=request.headers.get('Origin');
    const headers={'Content-Type':'application/json','Cache-Control':'no-store','Vary':'Origin'};
    const send=(status,data)=>Response.json(data,{status,headers});
    if(origin!==env.SITE_ORIGIN)return send(403,{error:'不接受此網站來源'});
    headers['Access-Control-Allow-Origin']=origin;
    if(request.method==='OPTIONS')return new Response(null,{status:204,headers:{...headers,'Access-Control-Allow-Methods':'GET, POST, OPTIONS','Access-Control-Allow-Headers':'Authorization, Content-Type','Access-Control-Max-Age':'600'}});
    const url=new URL(request.url);
    if(env.GITHUB_REPOSITORY!=='hsinfuyeh/tw-stock-lab'||!env.GITHUB_TOKEN)return send(503,{error:'雲端更新服務尚未設定完成'});
    const base=`https://api.github.com/repos/${env.GITHUB_REPOSITORY}/actions`;
    async function github(path,options={}){
      const response=await fetcher(base+path,{...options,signal:AbortSignal.timeout(12000),headers:{Accept:'application/vnd.github+json',Authorization:`Bearer ${env.GITHUB_TOKEN}`,'X-GitHub-Api-Version':'2026-03-10','User-Agent':'tw-stock-lab-cloud-update','Content-Type':'application/json'}});
      if(!response.ok)throw Error(`GitHub 更新服務回應 ${response.status}`);
      return response.status===204?null:response.json();
    }
    try{
      if(url.pathname==='/update'&&request.method==='POST'){
        if(!await sameKey(request.headers.get('Authorization')?.replace(/^Bearer /,''),env.UPDATE_KEY))return send(401,{error:'雲端更新密碼不正確'});
        if(request.headers.get('Content-Type')?.split(';')[0]!=='application/json')return send(415,{error:'需要 JSON'});
        const text=await request.text();if(text.length>1024)return send(400,{error:'請求過大'});
        let body;try{body=JSON.parse(text);}catch{return send(400,{error:'JSON 格式錯誤'});}
        if(!body||Array.isArray(body)||typeof body!=='object'||Object.keys(body).sort().join(',')!=='scope,window'||!['market','social','all'].includes(body.scope)||!['24h','7d'].includes(body.window))return send(400,{error:'更新類型或統計期間錯誤'});
        // Production dispatches are serialized by UpdateCoordinator below.
        const runs=await github(`/workflows/${workflow}/runs?branch=main&per_page=30`);
        const active=runs.workflow_runs.find(r=>activeStatuses.has(r.status));
        if(active){
          if(active.event!=='workflow_dispatch'||active.display_title!==`${body.scope} · ${body.window}`)
            return send(409,{error:'已有其他更新工作執行中，請等完成後重試本次更新。'});
          return send(202,{job:{...jobFor(active,body.scope,body.window),reused:true,message:'同一個雲端更新工作仍在執行'}});
        }
        const result=await github(`/workflows/${workflow}/dispatches`,{method:'POST',body:JSON.stringify({ref:'main',inputs:body})});
        if(!result?.workflow_run_id)throw Error('已送出更新要求，但未取得工作編號，請到 GitHub Actions 確認');
        return send(202,{job:{id:String(result.workflow_run_id),running:true,status:'queued',scope:body.scope,window:body.window,sources:{},message:'已排入雲端更新佇列'}});
      }
      if(url.pathname==='/job'&&request.method==='GET'){
        const id=url.searchParams.get('id');if(!/^\d{1,20}$/.test(id||''))return send(400,{error:'工作編號錯誤'});
        const run=await github(`/runs/${id}`);
        if(run.head_branch!=='main'||!run.path?.split('@')[0].endsWith(`/.github/workflows/${workflow}`)&&run.path?.split('@')[0]!==`.github/workflows/${workflow}`)return send(404,{error:'找不到此更新工作'});
        const job=jobFor(run,url.searchParams.get('scope')||'all',url.searchParams.get('window')||'7d');
        if(job.running){
          const {jobs}=await github(`/runs/${id}/jobs`);
          const step=jobs.flatMap(j=>j.steps||[]).find(s=>s.status==='in_progress');
          job.message=step?`雲端執行中：${step.name}`:'雲端排隊或等待發布中';
        }
        return send(200,{job});
      }
      return send(404,{error:'找不到操作'});
    }catch(error){return send(502,{error:error.name==='TimeoutError'?'雲端服務回應逾時，請確認工作狀態':error.message});}
  }};
}

// A single Durable Object serializes dispatches across browser tabs and instances.
export class UpdateCoordinator{
  constructor(ctx,env){this.ctx=ctx;this.env=env;}
  async fetch(request){return this.ctx.blockConcurrencyWhile(()=>createWorker().fetch(request,this.env));}
}
export default {async fetch(request,env){
  if(new URL(request.url).pathname==='/update'&&request.method==='POST'){
    const id=env.COORDINATOR.idFromName('market-pages-main');
    return env.COORDINATOR.get(id).fetch(request);
  }
  return createWorker().fetch(request,env);
}};
