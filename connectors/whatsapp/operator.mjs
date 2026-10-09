// OPERATOR ONLY. Starting this file reads the explicit ignored session boundary.
import { readFile, lstat, readdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { Outbox, normalize, deliver } from './bridge.mjs';

const root=fileURLToPath(new URL('../../backend/private/whatsapp/v1/',import.meta.url));
let client,outbox,timer,draining=false;
try {
  // Check every ancestor before reading credentials or creating session files.
  for(let p=root;;p=path.dirname(p)) {
    const s=await lstat(p);
    if(s.isSymbolicLink()) throw new Error('LINKED_BOUNDARY');
    if(path.dirname(p)===p) break;
  }
  const configPath=path.join(root,'connector.json');
  const stat=await lstat(configPath);
  if(!stat.isFile()||stat.isSymbolicLink()||stat.size>65536||stat.nlink!==1) throw new Error('INVALID_CONFIG_FILE');
  const config=JSON.parse(await readFile(configPath,'utf8'));
  const keys=['backend_url','connector_token','source_id','group_id','sender_ids','browser_executable'];
  if(Object.keys(config).some(k=>!keys.includes(k))||keys.some(k=>!(k in config))||
      typeof config.source_id!=='string'||!config.source_id.trim()||typeof config.group_id!=='string'||!config.group_id.endsWith('@g.us')||!Array.isArray(config.sender_ids)||!config.sender_ids.length||
      config.sender_ids.some(x=>typeof x!=='string'||!x.trim())||typeof config.connector_token!=='string'||config.connector_token.length<32||
      !path.isAbsolute(config.browser_executable)) throw new Error('INVALID_CONFIG');
  if(JSON.stringify(config).includes('REPLACE_WITH_')) throw new Error('PLACEHOLDER_CONFIG');
  const url=new URL(config.backend_url);
  if(url.protocol!=='http:'||url.hostname!=='127.0.0.1'||url.username||url.password||url.pathname!=='/'||url.search||url.hash) throw new Error('INVALID_BACKEND');
  // Refuse linked files anywhere in the designated private session boundary.
  async function checkChildren(directory) {
    for(const name of await readdir(directory)) {
      const target=path.join(directory,name),s=await lstat(target);
      if(s.isSymbolicLink()||(s.isFile()&&s.nlink!==1)) throw new Error('LINKED_SESSION');
      if(s.isDirectory()) await checkChildren(target);
    }
  }
  await checkChildren(root);
  // Dynamic imports prevent fixture tests from loading a native/browser session.
  const {default:wweb}=await import('whatsapp-web.js');
  const {default:qrcode}=await import('qrcode');
  outbox=new Outbox(path.join(root,'outbox.sqlite3'));
  client=new wweb.Client({authStrategy:new wweb.LocalAuth({clientId:'nexusai-v1',dataPath:path.join(root,'auth')}),
    puppeteer:{headless:true,executablePath:config.browser_executable},webVersionCache:{type:'none'}});
  async function drain() {
    if(draining)return;draining=true;
    try {await outbox.drain(e=>deliver(e,config));} catch {process.stdout.write('DELIVERY_PENDING\n');}
    finally {draining=false;}
  }
  client.on('qr',async qr=>{
    try {await qrcode.toFile(path.join(root,'link-qr.png'),qr);process.stdout.write('LINK_REQUIRED_PRIVATE_QR\n');}
    catch {process.stdout.write('LINK_QR_FAILED\n');}
  });
  client.on('ready',()=>{process.stdout.write('CONNECTOR_READY_NOT_EXECUTION_PERMISSION\n');drain();});
  client.on('message',async message=>{
    try {const envelope=normalize(message,config);if(envelope){outbox.enqueue(envelope);await drain();}}
    catch {process.stdout.write('MESSAGE_QUARANTINED\n');}
  });
  client.on('disconnected',()=>process.stdout.write('CONNECTOR_DISCONNECTED\n'));
  client.on('auth_failure',()=>process.stdout.write('CONNECTOR_AUTH_FAILURE\n'));
  timer=setInterval(drain,5000);
  async function stop(){clearInterval(timer);await client.destroy();outbox.close();process.exit(0);}
  process.on('SIGINT',stop);process.on('SIGTERM',stop);
  await client.initialize();
} catch {
  clearInterval(timer);
  process.stderr.write('CONNECTOR_BLOCKED_CHECK_PRIVATE_SETUP\n');
  process.exitCode=2;
}
