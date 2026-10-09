// Browser checks use the local token without recording it in screenshots or logs.
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const root = path.resolve(__dirname, '..');
  const token = fs.readFileSync(path.join(root, 'backend/private/control_token.txt'), 'utf8').trim();
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const results = [];
  try {
    for (const viewport of [{width:1440,height:1000},{width:390,height:844}]) {
      const page = await browser.newPage({ viewport });
      const errors = [];
      page.on('pageerror', e => errors.push(e.message));
      await page.goto('http://127.0.0.1:5173');
      await page.getByLabel('Local control token').fill(token);
      await page.getByRole('button', {name:'Unlock workspace'}).click();
      await page.getByRole('heading', {name:'NexusAI Core'}).waitFor();
      if (!(await page.getByText('HALTED', {exact:true}).isVisible())) throw new Error('Halt not displayed');
      await page.screenshot({path:path.join(root,`logs/rebuild-${viewport.width}.png`),fullPage:true});
      await page.getByRole('link', {name:'Historical review'}).click();
      await page.getByText('784', {exact:true}).waitFor();
      await page.locator('.chat-message').first().click();
      const attachedImage = page.locator('.chat-detail img').first();
      await attachedImage.waitFor({state:'visible'});
      await attachedImage.evaluate(img => img.complete ? Promise.resolve() : new Promise(resolve => {img.onload=resolve; img.onerror=resolve;}));
      await page.screenshot({path:path.join(root,`logs/rebuild-history-${viewport.width}.png`),fullPage:true});
      const metrics = await page.evaluate(() => ({
        overflow: document.documentElement.scrollWidth > window.innerWidth,
        images: [...document.querySelectorAll('.chat-detail img')].map(i => i.naturalWidth),
      }));
      if (metrics.overflow || errors.length || metrics.images.some(w => !w)) throw new Error(JSON.stringify({metrics,errors}));
      results.push({viewport, ...metrics, errors});
      await page.close();
    }
    console.log(JSON.stringify({passed:true,results}));
  } finally { await browser.close(); }
})().catch(e => {console.error(e.message); process.exitCode=1;});
