import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

// Import/API compatibility only: never initialize a browser or read operator auth.
test('Node 24 CommonJS adapter loads overridden Puppeteer APIs', async () => {
  const require = createRequire(import.meta.url);
  const wweb = require('whatsapp-web.js');
  const puppeteer = require('puppeteer');
  assert.equal(typeof puppeteer.launch, 'function');
  assert.equal(typeof puppeteer.connect, 'function');
  assert.equal(require('puppeteer/package.json').version, '25.12.0');
  const directory = mkdtempSync(path.join(tmpdir(), 'nexus-wa-compat-'));
  try {
    const client = new wweb.Client({
      authStrategy: new wweb.LocalAuth({clientId:'fixture', dataPath:directory}),
      puppeteer:{headless:true, executablePath:'fixture-browser-not-launched'},
      webVersionCache:{type:'none'},
    });
    await client.authStrategy.beforeBrowserInitialized();
    assert.equal(client.options.puppeteer.userDataDir, path.join(directory,'session-fixture'));
    assert.equal(client.options.puppeteer.executablePath,'fixture-browser-not-launched');
    assert.equal(client.pupBrowser, null);
  } finally { rmSync(directory,{recursive:true,force:true}); }
});
