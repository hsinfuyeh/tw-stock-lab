import test from 'node:test';
import assert from 'node:assert/strict';
import {createCloudClient} from '../web/cloud.js';

test('cloud client starts the selected scope and resumes exact run without storing password',async()=>{
  const saved=new Map();const store={getItem:k=>saved.get(k),setItem:(k,v)=>saved.set(k,v),removeItem:k=>saved.delete(k)};
  let prompts=0;const calls=[];
  const client=createCloudClient('https://tw-stock-lab-update.demo.workers.dev',async()=>{prompts++;return 'private-password';},async(url,options)=>{
    calls.push({url,options});return {job:{id:'42',running:true,status:'queued'}};
  },store);
  assert.equal((await client.status()).status,'idle');assert.equal(calls.length,0);
  await client.start('social','24h');
  assert.deepEqual(JSON.parse(calls[0].options.body),{scope:'social',window:'24h'});
  assert.equal(calls[0].options.headers.Authorization,'Bearer private-password');
  assert.ok(!JSON.stringify([...saved]).includes('private-password'));
  const resumed=createCloudClient('https://tw-stock-lab-update.demo.workers.dev',async()=>assert.fail('no login for public status'),async url=>{assert.match(url,/id=42/);return {job:{id:'42',running:false,status:'success'}};},store);
  assert.equal((await resumed.status()).status,'success');assert.equal(prompts,1);
});
test('cloud endpoint requires HTTPS on workers.dev; cancelled login sends no update',async()=>{
  assert.throws(()=>createCloudClient('http://example.com',()=>{},()=>{}),/網址/);
  assert.throws(()=>createCloudClient('https://evil.example',()=>{},()=>{}),/網址/);
  let calls=0;const store={getItem:()=>null,setItem:()=>{}};
  const client=createCloudClient('https://update.demo.workers.dev',async()=>null,async()=>{calls++;},store);
  await assert.rejects(client.start('market','7d'),/取消/);assert.equal(calls,0);
});
test('temporary update error keeps in-memory password while unauthorized clears it',async()=>{
  let prompts=0,calls=0;
  const client=createCloudClient('https://update.demo.workers.dev',async()=>{prompts++;return 'password';},async()=>{
    calls++;
    if(calls===1)throw Object.assign(Error('timeout'),{status:503});
    if(calls===2)throw Object.assign(Error('bad key'),{status:401});
    return {job:{id:'42'}};
  });
  await assert.rejects(client.start('market','7d'),/timeout/);
  await assert.rejects(client.start('market','7d'),/bad key/);
  await client.start('market','7d');
  assert.equal(prompts,2);
});
