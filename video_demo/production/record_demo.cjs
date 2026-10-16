const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const ROOT = path.resolve(__dirname, '..', '..');
const OUT = path.join(__dirname, 'recordings');
const edge = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
fs.mkdirSync(OUT, { recursive: true });

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

(async () => {
  const browser = await chromium.launch({ executablePath: edge, headless: true });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1,
    recordVideo: { dir: OUT, size: { width: 1920, height: 1080 } },
  });
  const page = await context.newPage();
  await page.goto('http://127.0.0.1:8000/?mock=1', { waitUntil: 'networkidle' });
  await page.addStyleTag({ content: `
    #demo-cursor { position:fixed; z-index:99999; width:24px; height:24px; pointer-events:none;
      transform:translate(-3px,-3px); transition:left .32s ease,top .32s ease;
      filter:drop-shadow(0 1px 2px #000); }
    #demo-cursor:before { content:''; display:block; width:0;height:0;border-top:18px solid #fff;
      border-right:10px solid transparent; transform:rotate(-25deg); }
    #demo-cursor:after { content:''; position:absolute;left:7px;top:8px;width:8px;height:8px;border-radius:50%; background:#22d3ee; }
    .demo-focus { outline: 3px solid #22d3ee !important; outline-offset: 4px; box-shadow: 0 0 0 7px rgba(34,211,238,.18) !important; }
  ` });
  await page.evaluate(() => { const c=document.createElement('div');c.id='demo-cursor';c.style.left='960px';c.style.top='540px';document.body.append(c); });
  async function move(sel) {
    const box = await page.locator(sel).first().boundingBox(); if (!box) return;
    const x=box.x+box.width/2, y=box.y+Math.min(box.height/2,30);
    await page.evaluate(({x,y})=>{const c=document.querySelector('#demo-cursor');c.style.left=x+'px';c.style.top=y+'px';}, {x,y});
    await page.mouse.move(x,y,{steps:12}); await sleep(900);
  }
  async function focus(sel) { await page.locator(sel).first().evaluate(el=>el.classList.add('demo-focus')); await sleep(1800); await page.locator(sel).first().evaluate(el=>el.classList.remove('demo-focus')); }
  async function click(sel) { await move(sel); await page.locator(sel).first().click(); await sleep(1100); }

  // 0:00–0:10 — title card over the genuine app shell.
  await page.evaluate(() => { const e=document.createElement('div'); e.id='opening-card'; e.innerHTML='<div><p>AI-ASSISTED DRAIN INSPECTION</p><h1>AI URBAN<br>FLOOD SENTINEL</h1><span>Image insight · explainable prioritisation</span></div>'; Object.assign(e.style,{position:'fixed',inset:'0',zIndex:'90000',display:'grid',placeItems:'center',background:'linear-gradient(120deg,rgba(5,16,36,.98),rgba(8,65,86,.95))',color:'white',textAlign:'center',fontFamily:'Arial,sans-serif'}); e.querySelector('h1').style.cssText='font-size:72px;letter-spacing:5px;margin:18px 0';e.querySelector('p').style.cssText='color:#67e8f9;letter-spacing:4px;font-size:18px';e.querySelector('span').style.cssText='font-size:24px;color:#dbeafe';document.body.append(e); });
  await sleep(8500); await page.locator('#opening-card').evaluate(el=>el.remove()); await sleep(1500);

  // 0:10–0:25 overview.
  for (const s of ['#kpi-box-critical','#kpi-box-high','#kpi-box-inconclusive','#kpi-note']) { await move(s); await focus(s); }
  await sleep(4500);

  // 0:25–0:45 sample selection and metadata.
  await click('#sample-blocked'); await click('#drain-id'); await page.locator('#drain-id').fill('DEMO-1');
  await click('details.more summary'); await page.locator('#rainfall').fill('90'); await move('#submit-btn'); await focus('#submit-btn'); await sleep(4000);

  // 0:45–1:05 actual mock analysis control and its genuine rendered result.
  await click('#submit-btn'); await sleep(3500); await page.locator('#detail-body').scrollIntoViewIfNeeded(); await sleep(5000);

  // 1:05–1:30 result details.
  for (const s of ['#detail-body .score','#detail-body .callout','#detail-body .facts','#detail-body .warnings']) { if (await page.locator(s).count()) { await move(s); await focus(s); } }
  await sleep(4500);

  // 1:30–1:55 map and queue. Select an actual queue entry.
  await page.locator('.col-map').scrollIntoViewIfNeeded(); await move('#map'); await sleep(2000); await click('.queue-row'); await sleep(2500); await move('.queue-row:nth-of-type(2)'); await sleep(5000);

  // 1:55–2:15 another meaningful control: clear sample + inconclusive fixture.
  await page.locator('#upload-form').scrollIntoViewIfNeeded(); await click('#sample-clear'); await page.locator('#fixture-select').selectOption('inconclusive'); await sleep(1500); await move('#detail-body'); await sleep(5000); await page.locator('#fixture-select').selectOption('completed-critical'); await sleep(1500); await move('#alert-banner'); await sleep(4500);

  // Hold the authentic high-priority result long enough for the final explanation.
  await sleep(24000);

  // 2:15–2:30 close on a concise overlay above the real dashboard.
  await page.evaluate(() => { const e=document.createElement('div'); e.id='closing-card'; e.innerHTML='<div><p>AI URBAN FLOOD SENTINEL</p><h1>Smarter inspection.<br>Clearer priorities.</h1><span>Experimental decision support — not a flood forecast.</span></div>'; Object.assign(e.style,{position:'fixed',inset:'0',zIndex:'90000',display:'grid',placeItems:'center',background:'rgba(5,16,36,.92)',color:'white',textAlign:'center',fontFamily:'Arial,sans-serif'}); e.querySelector('p').style.cssText='color:#67e8f9;letter-spacing:4px;font-size:19px';e.querySelector('h1').style.cssText='font-size:56px;margin:18px';e.querySelector('span').style.cssText='font-size:18px;color:#dbeafe';document.body.append(e); });
  await sleep(15000);
  await context.close(); await browser.close();
})().catch(error => { console.error(error); process.exit(1); });
