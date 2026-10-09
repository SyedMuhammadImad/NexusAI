import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import path from 'node:path';
import { linkOnly, pairingOptions } from './pair.mjs';

class FixtureClient extends EventEmitter {
  constructor(event,fail=false) { super(); this.event=event; this.fail=fail; this.destroyed=false; }
  async initialize() {
    assert.equal(this.listenerCount('message'),0);
    assert.equal(this.listenerCount('message_create'),0);
    this.emit('qr','FIXTURE_QR_MUST_NOT_BE_LOGGED');
    if (this.fail) throw new Error('FIXTURE_SECRET_MUST_NOT_BE_LOGGED');
    if (this.event) this.emit(this.event);
  }
  async destroy() { this.destroyed=true; }
}

test('login has a dedicated visible profile, not an existing browser profile',() => {
  const root=path.resolve('fixture-session-not-opened');
  const options=pairingOptions(path.resolve('fixture-browser-not-launched'),root);
  assert.equal(options.auth.clientId,'nexusai-v1');
  assert.equal(options.auth.dataPath,path.join(root,'auth'));
  assert.equal(options.puppeteer.headless,false);
  assert.ok(!options.puppeteer.args.includes('--no-sandbox'));
  assert.throws(() => pairingOptions('relative',root));
});

for (const [event,code] of [['ready',0],['auth_failure',2],['disconnected',2],[null,3]]) {
  test(`pairing ${event ?? 'timeout'} stops without message forwarding`,async () => {
    const client=new FixtureClient(event),output=[];
    assert.equal(await linkOnly(client,value=>output.push(value),10),code);
    assert.equal(client.destroyed,true);
    assert.equal(client.eventNames().length,0);
    assert.ok(!output.join('').includes('FIXTURE_QR'));
    assert.equal(output.includes('WHATSAPP_LINKED_EXECUTION_DISABLED'),code===0);
  });
}

test('initialization failure never logs provider error content',async () => {
  const client=new FixtureClient(null,true),output=[];
  assert.equal(await linkOnly(client,value=>output.push(value),50),2);
  assert.equal(client.destroyed,true);
  assert.ok(!output.join('').includes('FIXTURE_SECRET'));
});

for (const behavior of ['reject','hang']) {
  test(`uncertain browser stop (${behavior}) is not reported as clean exit`,async () => {
    const client=new FixtureClient('ready'),output=[];
    let kills=0;
    client.pupBrowser={process:() => ({kill:() => { kills++; }})};
    client.destroy=() => behavior==='reject'
      ? Promise.reject(new Error('FIXTURE_STOP_SECRET')) : new Promise(() => {});
    assert.equal(await linkOnly(client,value=>output.push(value),50,5),4);
    assert.equal(kills,1);
    assert.ok(output.includes('WHATSAPP_BROWSER_STOP_UNVERIFIED'));
    assert.ok(!output.join('').includes('FIXTURE_STOP_SECRET'));
  });
}

test('read-only ready callback completes before browser shutdown',async()=>{
  const client=new FixtureClient('ready'),output=[];
  let checked=false;
  const code=await linkOnly(client,value=>output.push(value),100,50,async()=>{
    assert.equal(client.destroyed,false); checked=true;
  });
  assert.equal(code,0);assert.equal(checked,true);assert.equal(client.destroyed,true);
});
test('read-only failure remains sanitized and stops client',async()=>{
  const client=new FixtureClient('ready'),output=[];
  const code=await linkOnly(client,value=>output.push(value),100,50,async()=>{
    throw new Error('FIXTURE_READ_SECRET');
  });
  assert.equal(code,2);assert.equal(client.destroyed,true);
  assert.ok(output.includes('WHATSAPP_READ_ONLY_CHECK_FAILED'));
  assert.ok(!output.join('').includes('FIXTURE_READ_SECRET'));
});
