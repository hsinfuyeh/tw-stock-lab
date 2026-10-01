import test from 'node:test';
import assert from 'node:assert/strict';
import {createCloudClient} from '../web/cloud.js';

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
