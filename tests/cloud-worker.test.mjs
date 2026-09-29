import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorker} from '../cloud/worker.mjs';

const env={SITE_ORIGIN:'https://hsinfuyeh.github.io',GITHUB_REPOSITORY:'hsinfuyeh/tw-stock-lab',GITHUB_TOKEN:'private-github-token',UPDATE_KEY:'a-long-private-update-password'};
const request=(body,key=env.UPDATE_KEY,origin=env.SITE_ORIGIN)=>new Request('https://update.example.com/update',{method:'POST',headers:{Origin:origin,Authorization:`Bearer ${key}`,'Content-Type':'application/json'},body:JSON.stringify(body)});
test('cloud trigger rejects missing authorization and foreign origins without touching GitHub',async()=>{
  let calls=0;const worker=createWorker(async()=>{calls++;throw Error('unexpected');});
  assert.equal((await worker.fetch(request({scope:'social',window:'24h'},'bad'),env)).status,401);
  assert.equal((await worker.fetch(request({scope:'social',window:'24h'},env.UPDATE_KEY,'https://other.example'),env)).status,403);
  assert.equal(calls,0);
});
test('cloud trigger validates scope, dispatches fixed main workflow and returns exact run ID',async()=>{
  const calls=[];const worker=createWorker(async(url,options)=>{
    calls.push({url,options});
    if(url.includes('/dispatches'))return Response.json({workflow_run_id:42});
    return Response.json({workflow_runs:[]});
  });
  assert.equal((await worker.fetch(request({scope:'unknown',window:'24h'}),env)).status,400);
  const response=await worker.fetch(request({scope:'social',window:'24h'}),env);
  assert.equal(response.status,202);
  const data=await response.json();assert.equal(data.job.id,'42');assert.equal(data.job.running,true);
  const dispatched=calls.find(c=>c.url.includes('/dispatches'));
  assert.deepEqual(JSON.parse(dispatched.options.body),{ref:'main',inputs:{scope:'social',window:'24h'}});
  assert.equal(dispatched.options.headers.Authorization,`Bearer ${env.GITHUB_TOKEN}`);
  assert.ok(!JSON.stringify(data).includes(env.GITHUB_TOKEN));
});
test('matching active cloud run is reused and failed deployment is never described as published',async()=>{
  let dispatches=0;const run={id:9,head_branch:'main',event:'workflow_dispatch',status:'in_progress',path:'.github/workflows/market-pages.yml',display_title:'social · 24h',created_at:'2026-09-30T00:00:00Z'};
  const worker=createWorker(async url=>{
    if(url.includes('/dispatches')){dispatches++;throw Error('unexpected');}
    if(url.includes('/workflows/'))return Response.json({workflow_runs:[run]});
    if(url.endsWith('/jobs'))return Response.json({jobs:[]});
    return Response.json({...run,status:'completed',conclusion:'failure'});
  });
  assert.equal((await(await worker.fetch(request({scope:'social',window:'24h'}),env)).json()).job.id,'9');assert.equal(dispatches,0);
  const response=await worker.fetch(new Request('https://update.example.com/job?id=9',{headers:{Origin:env.SITE_ORIGIN}}),env);
  const {job}=await response.json();assert.equal(job.running,false);assert.equal(job.status,'failed');assert.ok(job.error);
});
test('a market-only active run cannot masquerade as a social collection',async()=>{
  const worker=createWorker(async url=>{
    if(url.includes('/dispatches'))assert.fail('cannot queue behind active run');
    return Response.json({workflow_runs:[{id:10,event:'workflow_dispatch',status:'in_progress',display_title:'market · 7d'}]});
  });
  const response=await worker.fetch(request({scope:'social',window:'24h'}),env);
  assert.equal(response.status,409);
  assert.match((await response.json()).error,/其他更新工作/);
});
test('job lookup refuses other workflows and request bodies cannot choose a repository',async()=>{
  const worker=createWorker(async()=>Response.json({id:2,head_branch:'main',path:'.github/workflows/other.yml',status:'completed',conclusion:'success'}));
  assert.equal((await worker.fetch(request({scope:'social',window:'24h',repository:'evil/repo'}),env)).status,400);
  assert.equal((await worker.fetch(new Request('https://update.example.com/job?id=2',{headers:{Origin:env.SITE_ORIGIN}}),env)).status,404);
});
