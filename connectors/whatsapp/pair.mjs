// OPERATOR ONLY: links the dedicated session; never reads chats or sends proposals.
import { lstat, mkdir, readdir, open, unlink } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

export function pairingOptions(browser, root) {
  if (!path.isAbsolute(browser) || !path.isAbsolute(root)) throw new Error('ABSOLUTE_PATH_REQUIRED');
  return {
    auth: {clientId:'nexusai-v1', dataPath:path.join(root,'auth')},
    puppeteer: {headless:false, executablePath:browser, args:['--disable-extensions']},
    webVersionCache: {type:'none'},
  };
}

export async function linkOnly(client, report, timeoutMs=600000, stopTimeoutMs=30000, onReady=async()=>{}) {
  let finish, timer, code, stopTimer, readyStarted=false;
  const completed=new Promise(resolve => { finish=resolve; });
  // No message, chat, outbox, HTTP delivery or broker handler is registered.
  const handlers={
    qr: () => report('SCAN_QR_IN_DEDICATED_BROWSER'),
    ready: () => {
      if (readyStarted) return;
      readyStarted=true;
      report('WHATSAPP_LINKED_EXECUTION_DISABLED');
      Promise.resolve().then(onReady).then(() => finish(0)).catch(() => {
        report('WHATSAPP_READ_ONLY_CHECK_FAILED'); finish(2);
      });
    },
    auth_failure: () => { report('WHATSAPP_LINK_FAILED'); finish(2); },
    disconnected: () => { report('WHATSAPP_LINK_DISCONNECTED'); finish(2); },
  };
  for (const [event,handler] of Object.entries(handlers)) client.on(event,handler);
  const interrupted=() => finish(130);
  process.on('SIGINT',interrupted);
  process.on('SIGTERM',interrupted);
  timer=setTimeout(() => { report('WHATSAPP_LINK_TIMEOUT'); finish(3); },timeoutMs);
  try {
    code=await Promise.race([
      Promise.resolve().then(() => client.initialize()).then(() => completed)
        .catch(() => { report('WHATSAPP_LINK_FAILED'); return 2; }),
      completed,
    ]);
  } finally {
    clearTimeout(timer);
    process.removeListener('SIGINT',interrupted);
    process.removeListener('SIGTERM',interrupted);
    for (const [event,handler] of Object.entries(handlers)) client.removeListener(event,handler);
    try {
      await Promise.race([
        Promise.resolve().then(() => client.destroy()),
        new Promise((_,reject) => {
          stopTimer=setTimeout(() => reject(new Error('STOP_TIMEOUT')),stopTimeoutMs);
        }),
      ]);
    } catch {
      // Only the child handle owned by this dedicated client may be stopped.
      try { client.pupBrowser?.process()?.kill(); } catch { /* Stop remains unverified. */ }
      report('WHATSAPP_BROWSER_STOP_UNVERIFIED');
      code=4;
    } finally { clearTimeout(stopTimer); }
  }
  return code;
}

export async function safeDirectories(root) {
  const pending=[];
  for (let p=root;;p=path.dirname(p)) {
    try {
      const stat=await lstat(p);
      if (!stat.isDirectory() || stat.isSymbolicLink()) throw new Error('UNSAFE_BOUNDARY');
    } catch (error) {
      if (error.code!=='ENOENT') throw error;
      pending.push(p);
    }
    if (path.dirname(p)===p) break;
  }
  for (const directory of pending.reverse()) await mkdir(directory);
  async function check(directory) {
    for (const name of await readdir(directory)) {
      const target=path.join(directory,name),stat=await lstat(target);
      if (stat.isSymbolicLink() || (stat.isFile() && stat.nlink!==1)) throw new Error('LINKED_SESSION');
      if (stat.isDirectory()) await check(target);
    }
  }
  await check(root);
}

export async function findBrowser(explicit=[]) {
  const candidates=explicit.length ? explicit : [
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  ];
  if (explicit.length>1) throw new Error('ONE_BROWSER_PATH_ONLY');
  let browser;
  for (const candidate of candidates) {
    if (!path.isAbsolute(candidate)) throw new Error('ABSOLUTE_BROWSER_REQUIRED');
    try {
      const stat=await lstat(candidate);
      if (stat.isFile() && !stat.isSymbolicLink() && stat.nlink===1) { browser=candidate; break; }
    } catch (error) { if (error.code!=='ENOENT') throw error; }
  }
  if (!browser) throw new Error('BROWSER_NOT_AVAILABLE');
  return browser;
}

async function operatorMain() {
  const root=fileURLToPath(new URL('../../backend/private/whatsapp/v1/',import.meta.url));
  const browser=await findBrowser(process.argv.slice(2));
  await safeDirectories(root);
  const lockPath=path.join(root,'link-only.lock');
  const lock=await open(lockPath,'wx');
  try {
    const {default:wweb}=await import('whatsapp-web.js');
    const options=pairingOptions(browser,root);
    const client=new wweb.Client({
      authStrategy:new wweb.LocalAuth(options.auth),
      puppeteer:options.puppeteer,
      webVersionCache:options.webVersionCache,
    });
    process.exitCode=await linkOnly(client,status => process.stdout.write(status+'\n'));
  } finally {
    await lock.close();
    await unlink(lockPath);
  }
}

if (process.argv[1] && path.resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  operatorMain().then(() => process.exit(process.exitCode ?? 0)).catch(() => {
    process.stderr.write('WHATSAPP_PAIRING_BLOCKED_CHECK_OPERATOR_SETUP\n');
    process.exit(2);
  });
}
