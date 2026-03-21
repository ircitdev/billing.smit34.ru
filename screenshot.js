const puppeteer = require('puppeteer');
const path = require('path');

const DIR = path.join(__dirname, 'slides');
const BASE = 'https://demo.billing.smit34.ru';

const pages = [
  { name: '06_dashboard', url: '/admin/welcome/', wait: 3000 },
  { name: '04_abonents_list', url: '/admin/Abonents/9001/', wait: 3000 },
  { name: '04_abonent_card', url: '/admin/Abonents/5391/', wait: 3000 },
  { name: '06_debtors', url: '/admin/debtors/', wait: 3000 },
  { name: '05_tariffs', url: '/admin/dictionaries/Tarif/', wait: 3000 },
  { name: '10_send_message', url: '/admin/Abonents/5391/send_message/', wait: 3000 },
  { name: '09_integrations', url: '/admin/settings/integrations/?tab=tvip', wait: 3000 },
  { name: '09_payment_settings', url: '/admin/settings/payment/', wait: 3000 },
  { name: '09_iptv_mappings', url: '/admin/settings/iptv_mappings/', wait: 3000 },
  { name: '11_nas', url: '/admin/equipment/Nas/', wait: 3000 },
  { name: '12_sorm', url: '/admin/equipment/sorm_list/', wait: 3000 },
  { name: '07_lk_main', url: '/lk/', wait: 3000, lk: true },
  { name: '07_lk_pay', url: '/lk/payments/pay/', wait: 3000, lk: true },
];

async function login(page, url, fields) {
  await page.goto(url, { waitUntil: 'networkidle2', timeout: 20000 });
  for (const [name, value] of Object.entries(fields)) {
    await page.type(`input[name="${name}"]`, value);
  }
  await page.evaluate(() => {
    const forms = document.querySelectorAll('form[method="post"]');
    if (forms.length) forms[forms.length - 1].submit();
  });
  await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 20000 });
}

(async () => {
  const browser = await puppeteer.launch({
    headless: 'new',
    protocolTimeout: 120000,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu', '--window-size=1440,900'],
    defaultViewport: { width: 1440, height: 900 },
  });

  // ─── Admin login ───
  const adminPage = await browser.newPage();
  await login(adminPage, `${BASE}/admin/login/`, { username: 'admin', password: 'admin' });
  const adminUrl = adminPage.url();
  console.log('Admin logged in:', adminUrl);
  if (adminUrl.includes('login')) {
    console.error('ERROR: Admin login failed! Still on login page.');
    await browser.close();
    process.exit(1);
  }

  // ─── LK login ───
  const lkPage = await browser.newPage();
  await login(lkPage, `${BASE}/lk/login/`, { login: '7777', password: '7777' });
  const lkUrl = lkPage.url();
  console.log('LK logged in:', lkUrl);
  if (lkUrl.includes('login')) {
    console.error('WARNING: LK login may have failed.');
  }

  // ─── Take screenshots ───
  for (const p of pages) {
    const page = p.lk ? lkPage : adminPage;
    try {
      await page.goto(`${BASE}${p.url}`, { waitUntil: 'networkidle2', timeout: 30000 });
      await new Promise(r => setTimeout(r, p.wait || 2000));

      // Verify we're not on login page
      const currentUrl = page.url();
      if (currentUrl.includes('login')) {
        console.log(`SKIP: ${p.name} — redirected to login (${currentUrl})`);
        continue;
      }

      const file = path.join(DIR, `${p.name}.png`);
      await page.screenshot({ path: file, fullPage: false });
      console.log(`OK: ${p.name} (${currentUrl})`);
    } catch (e) {
      console.log(`FAIL: ${p.name} — ${e.message.substring(0, 100)}`);
    }
  }

  await browser.close();
  console.log('Done!');
})();
