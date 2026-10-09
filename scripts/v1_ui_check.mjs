// Runs only against the separately started credential-free v1_preview.py.
import {createRequire} from 'node:module';
import path from 'node:path';
import {mkdir} from 'node:fs/promises';
import assert from 'node:assert/strict';
const require=createRequire(path.join(process.env.PLAYWRIGHT_ROOT,'package.json'));
const {chromium}=require('playwright');
const browser=await chromium.launch({channel:process.env.V1_TEST_BROWSER || 'chrome',headless:true});
const output=path.resolve('tmp/v1-ui');
await mkdir(output,{recursive:true});
const errors=[],checks=[];
try {
  for(const [name,width,height] of [['desktop',1440,1000],['mobile',390,844]]) {
    const context=await browser.newContext({viewport:{width,height}});
    const page=await context.newPage();
    page.on('pageerror',e=>errors.push(e.message));
    await page.goto('http://127.0.0.1:5173/');
    await page.getByLabel('Local control token').fill('v1-fixture-preview');
    await page.getByRole('button',{name:'Unlock workspace'}).click();
    await page.getByText('FIXTURE PREVIEW',{exact:true}).waitFor();
    for(const [route,title] of [['dashboard','Dashboard'],['trade','New trade'],['positions','Positions / execution'],
       ['safety','Safety / risk'],['whatsapp','WhatsApp'],['strategies','Automated strategies'],['monitoring','Monitoring / alerts']]) {
      await page.goto(`http://127.0.0.1:5173/#/${route}`);
      await page.getByRole('heading',{name:title,exact:true}).waitFor();
      await page.waitForFunction(()=>!!document.querySelector('.op-footer'));
      if(route==='monitoring' && process.env.P8_RESEARCH_PREVIEW==='1') {
        await page.getByRole('heading',{name:'Intelligence research',exact:true}).waitFor();
        const evidence=await page.evaluate(async()=>{
          const r=await fetch('/api/core/operations/snapshot',{headers:{'X-Control-Token':'v1-fixture-preview'}});return r.json();
        });
        assert.equal(evidence.p8.scope,'RESEARCH_ONLY');
        assert.equal(evidence.p8.ml_filter,'PASS_THROUGH');
        assert.equal(evidence.p8.execution_eligible,false);
        assert.equal(evidence.broker_execution,'HARD_DISABLED');
      }
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,`${name} ${route} overflow`);
      await page.screenshot({path:path.join(output,`${name}-${route}.png`),fullPage:true});
    }
    await page.goto('http://127.0.0.1:5173/#/trade');
    await page.getByLabel('Stop loss',{exact:true}).fill('90');
    await page.getByLabel('Take profit(s)',{exact:true}).fill('140');
    await page.getByRole('button',{name:'Evaluate proposal'}).click();
    await page.getByText('P2 REJECTED',{exact:true}).waitFor();
    await page.getByText('HALTED',{exact:true}).first().waitFor();
    const snapshot=await page.evaluate(async()=>{
      const r=await fetch('/api/core/operations/snapshot',{headers:{'X-Control-Token':'v1-fixture-preview'}});return r.json();
    });
    assert.equal(snapshot.scope,'FIXTURE');
    assert.equal(snapshot.execution.attempts.length,0);
    assert.equal(snapshot.broker_execution,'HARD_DISABLED');
    await page.goto('http://127.0.0.1:5173/#/strategies');
    await page.getByRole('button',{name:'Register disabled'}).click();
    await page.getByRole('switch',{name:'Enable p6-01'}).waitFor();
    await page.getByRole('button',{name:'HALT',exact:true}).click();
    await page.getByRole('button',{name:'Export evidence'}).click();
    await page.goto('http://127.0.0.1:5173/#/tournament');
    await page.getByRole('heading',{name:/Tournament/}).first().waitFor();
    await page.goto('http://127.0.0.1:5173/#/');
    await page.getByRole('button',{name:'Lock workspace'}).click();
    await page.getByRole('button',{name:'Unlock workspace'}).waitFor();
    checks.push(`${name}: seven pages, overflow, manual HALT rejection, zero attempts, disabled registry, export, Arena, lock`);
    await context.close();
  }
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({checks,browser_errors:errors,screenshots:output}));
} finally {await browser.close();}
