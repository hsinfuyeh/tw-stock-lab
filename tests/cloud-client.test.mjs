import test from 'node:test';
import assert from 'node:assert/strict';
import {createCloudClient,reconcilePublishedJob} from '../web/cloud.js';

test('newer successful publication supersedes an old market failure, retaining history',()=>{
  const failed={id:'42',scope:'market',running:false,status:'failed',error:'old failure',finished_at:'2026-11-02T15:01:34Z',url:'https://github.com/example/run'};
  const result=reconcilePublishedJob(failed,{checked_at:'2026-11-08T00:55:00+08:00'});
  assert.equal(result.status,'superseded');assert.equal(result.error,null);
  assert.equal(result.previous_error,'old failure');assert.equal(result.url,failed.url);
  assert.equal(failed.error,'old failure');
});
test('new failures, active work, social jobs and ambiguous times remain visible',()=>{
  const failed={scope:'market',running:false,error:'error',finished_at:'2026-11-08T00:55:00+08:00'};
  const publication={checked_at:'2026-11-08T00:55:00+08:00'};
  for(const [job,pub] of [[failed,publication],[{...failed,running:true},{checked_at:'2026-11-09T00:00:00Z'}],
    [{...failed,scope:'social'},{checked_at:'2026-11-09T00:00:00Z'}],[failed,{}],
    [failed,{checked_at:'2026-11-09T00:00:00'}],[{...failed,finished_at:null},{checked_at:'2026-11-09T00:00:00Z'}]]){
    assert.equal(reconcilePublishedJob(job,pub),job);
  }
});
test('resumed status can reconcile against publication without deleting cloud reference',async()=>{
  const saved=new Map([['tw-stock-cloud-job',JSON.stringify({id:'42',scope:'market',window:'7d'})]]);
  const client=createCloudClient('https://update.demo.workers.dev',async()=>({job:{id:'42',scope:'market',running:false,error:'old',finished_at:'2026-11-02T00:00:00Z'}}),{getItem:k=>saved.get(k)});
  assert.equal((await client.status({checked_at:'2026-11-08T00:00:00Z'})).status,'superseded');
  assert.ok(saved.get('tw-stock-cloud-job'));
});

test('cloud client starts a public update without a password and resumes the run',async()=>{
  const saved=new Map();const store={getItem:k=>saved.get(k),setItem:(k,v)=>saved.set(k,v),removeItem:k=>saved.delete(k)};
  const calls=[];
  const client=createCloudClient('https://tw-stock-lab-update.demo.workers.dev',async(url,options)=>{
    calls.push({url,options});return {job:{id:'42',running:true,status:'queued'}};
  },store);
  assert.equal((await client.status()).status,'idle');assert.equal(calls.length,0);
  await client.start('social','24h');
  assert.deepEqual(JSON.parse(calls[0].options.body),{scope:'social',window:'24h'});
  assert.equal(calls[0].options.headers.Authorization,undefined);
  const resumed=createCloudClient('https://tw-stock-lab-update.demo.workers.dev',async url=>{assert.match(url,/id=42/);return {job:{id:'42',running:false,status:'success'}};},store);
  assert.equal((await resumed.status()).status,'success');
});
test('cloud endpoint requires HTTPS on workers.dev',async()=>{
  assert.throws(()=>createCloudClient('http://example.com',()=>{}),/網址/);
  assert.throws(()=>createCloudClient('https://evil.example',()=>{}),/網址/);
});
test('temporary update errors can be retried without a password prompt',async()=>{
  let calls=0;
  const client=createCloudClient('https://update.demo.workers.dev',async()=>{
    calls++;if(calls<3)throw Object.assign(Error('timeout'),{status:503});
    return {job:{id:'42'}};
  });
  await assert.rejects(client.start('market','7d'),/timeout/);
  await assert.rejects(client.start('market','7d'),/timeout/);
  await client.start('market','7d');
  assert.equal(calls,3);
});
