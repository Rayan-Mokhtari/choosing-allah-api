// Both the API and local command use the same typesetter, in a private build folder.
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');
const { pathToFileURL, fileURLToPath } = require('url');

(async () => {
  const out = process.argv[2];
  if (!out || path.basename(out) !== out || !out.endsWith('.pdf')) {
    throw new Error('usage: node render.js <output.pdf>');
  }
  const base = path.resolve(process.env.BOOK_BUILD_DIR || __dirname);
  const assets = path.resolve(process.env.BOOK_ASSET_DIR || __dirname);
  const browser = await chromium.launch({
    ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}),
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage',
           '--disable-gpu', '--force-color-profile=srgb'],
  });
  try {
    // Manuscript HTML is a document, not an application. It must not execute
    // scripts or fetch arbitrary web/private files while the server prints it.
    const page = await browser.newPage({ javaScriptEnabled: false });
    await page.route('**/*', (route) => {
      const url = route.request().url();
      if (url.startsWith('data:')) return route.continue();
      if (url.startsWith('file:')) {
        try {
          const file = fs.realpathSync(fileURLToPath(url));
          const relative = path.relative(base, file);
          const font = path.relative(path.join(assets, 'fonts'), file);
          if ((!relative.startsWith('..') && !path.isAbsolute(relative)) ||
              (!font.startsWith('..') && !path.isAbsolute(font))) return route.continue();
        } catch {
          return route.abort();
        }
      }
      return route.abort();
    });
    await page.goto(pathToFileURL(path.join(base, 'interior.html')).href, {
      waitUntil: 'networkidle', timeout: 180000,
    });
    await page.evaluate(() => document.fonts.ready);
    const failedFonts = await page.evaluate(() =>
      Array.from(document.fonts).some((font) => font.status === 'error'));
    if (failedFonts) throw new Error('A book font could not load; refusing to use a substitute');
    const brokenImages = await page.evaluate(() =>
      Array.from(document.images).filter((image) => !image.complete || !image.naturalWidth).length);
    if (brokenImages) throw new Error('A PDF image could not load; refusing to export an incomplete book');
    await page.pdf({
      path: path.join(base, out), preferCSSPageSize: true, printBackground: true,
      displayHeaderFooter: false, timeout: 300000,
    });
    console.log('rendered', out);
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
