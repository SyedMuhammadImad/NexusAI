import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { normalize,Outbox,deliver } from './bridge.mjs';
const config={source_id:'synthetic-source',group_id:'fixture@g.us',sender_ids:['teacher@c.us'],backend_url:'http://127.0.0.1:8000/',connector_token:'fixture-not-a-secret'};
const message={fromMe:false,type:'chat',from:'fixture@g.us',author:'teacher@c.us',id:{_serialized:'fixture-message'},timestamp:1800000000,body:'GOLD BUY SL 100 TP 140'};
test('trusted message fields and no media/auth leakage',()=>{
 const e=normalize({...message,mediaKey:'excluded'},config);assert.equal(e.source_type,'WHATSAPP_HUMAN');assert.equal(e.sender_id,message.author);assert.equal(e.original_timestamp,new Date(message.timestamp*1000).toISOString());assert.ok(!JSON.stringify(e).includes('mediaKey'));
 for(const patch of [{from:'other@g.us'},{author:'other@c.us'},{fromMe:true},{type:'image'}])assert.equal(normalize({...message,...patch},config),null);
});
test('durable reconnect replay and ambiguous HTTP delivery',async()=>{
 const file=path.join(mkdtempSync(path.join(tmpdir(),'nexus-wa-test-')),'outbox.sqlite3');let q=new Outbox(file);const e=normalize(message,config);
 q.enqueue(e);q.enqueue(e);let calls=0;await q.drain(async()=>{calls++;throw new Error('fixture timeout');}).catch(()=>{});q.close();q=new Outbox(file);
 await q.drain(async same=>{calls++;assert.deepEqual(same,e);return 'DELIVERED';});q.enqueue(e);await q.drain(async()=>{throw new Error('duplicate delivery');});assert.equal(calls,2);assert.equal(q.counts()[0].count,1);q.close();
});
test('conflicting message retained and never delivered',async()=>{
 const q=new Outbox(':memory:');const e=normalize(message,config);q.enqueue(e);assert.equal(q.enqueue({...e,raw_text:'revision'}),'CONFLICT');await q.drain(async()=>{throw new Error('conflict sent');});assert.equal(q.db.prepare('SELECT count(*) n FROM conflicts').get().n,1);q.close();
});
test('delivery restricts loopback and follows no redirects',async()=>{
 await assert.rejects(deliver({}, {...config,backend_url:'https://external.invalid/'}));
 const result=await deliver({},config,async(url,opt)=>{assert.equal(opt.redirect,'error');assert.equal(url.pathname,'/api/core/operations/whatsapp');return {ok:true};});assert.equal(result,'DELIVERED');
});
