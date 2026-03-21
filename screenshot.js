const puppeteer = require('puppeteer');
const path = require('path');

const DIR = path.join(__dirname, 'slides');
const BASE = 'https://demo.billing.smit34.ru';

const pages = [
  { name: '04_abonents_list', url: '/admin/Abonents/9001/', w: 1440, h: 900 },
  { name: '04_abonent_card', url: '/admin/Abonents/Abonents/5391/', w: 1440, h: 900 },
  { name: '05_tariffs', url: '/admin/Tarif/', w: 1440, h: 900 },
  { name: '06_dashboard', url: '/admin/welcome/', w: 1440, h: 900 },
  { name: '06_debtors', url: '/admin/debtors/', w: 1440, h: 900 },
  { name: '07_lk_main', url: '/lk/', w: 1440, h: 900, lk: true },
  { name: '07_lk_pay', url: '/lk/payments/pay/', w: 1440, h: 900, lk: true },
  { name: '09_integrations', url: '/admin/settings/integrations/?tab=tvip', w: 1440, h: 900 },
  { name: '09_payment_settings', url: '/admin/settings/payment/', w: 1440, h: 900 },
  { name: '09_iptv_mappings', url: '/admin/settings/iptv_mappings/', w: 1440, h: 900 },
  { name: '10_send_message', url: '/admin/Abonents/5391/send_message/', w: 1440, h: 900 },
  { name: '11_nas', url: '/admin/Nas/', w: 1440, h: 900 },
  { name: '12_sorm', url: '/admin/equipment/sorm_list/', w: 1440, h: 900 },
];

(async () => {
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--window-size=1440,900'],
    defaultViewport: { width: 1440, height: 900 },
  });

  // Admin login
  const adminPage = await browser.newPage();
  await adminPage.goto(`${BASE}/admin/login/`, { waitUntil: 'networkidle2' });
  await adminPage.type('input[name="username"]', 'admin');
  await adminPage.type('input[name="password"]', 'admin');
  await adminPage.evaluate(() => document.querySelector('form').submit());
  await adminPage.waitForNavigation({ waitUntil: 'networkidle2' });
  console.log('Admin logged in');

  // LK login — find correct field names
  const lkPage = await browser.newPage();
  await lkPage.goto(`${BASE}/lk/login/`, { waitUntil: 'networkidle2' });
  const lkFields = await lkPage.evaluate(() =>
    Array.from(document.querySelectorAll('input')).map(i => i.name || i.type)
  );
  console.log('LK fields:', lkFields);
  // Try typing into first two text inputs
  await lkPage.type('input[name="login"]', '0828');
  await lkPage.type('input[name="password"]', '2006374');
  await lkPage.evaluate(() => document.querySelector('form').submit());
  await lkPage.waitForNavigation({ waitUntil: 'networkidle2' });
  console.log('LK logged in at:', lkPage.url());

  for (const p of pages) {
    const page = p.lk ? lkPage : adminPage;
    try {
      await page.setViewport({ width: p.w, height: p.h });
      await page.goto(`${BASE}${p.url}`, { waitUntil: 'networkidle2', timeout: 30000 });
      await new Promise(r => setTimeout(r, 1500)); // wait for JS
      const file = path.join(DIR, `${p.name}.png`);
      await page.screenshot({ path: file, fullPage: false });
      console.log(`OK: ${p.name}`);
    } catch (e) {
      console.log(`FAIL: ${p.name} — ${e.message}`);
    }
  }

  await browser.close();
  console.log('Done');
})();
