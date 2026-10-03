// Both the API and local command use the same typesetter, in a private build folder.
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');
const { pathToFileURL, fileURLToPath } = require('url');

// Runs through Playwright, not manuscript scripts. Measure the actual embedded
// font at the book's fixed text measure, after fonts load, on both PDF passes.
function preparePoemLayout() {
  const pageHeight = 6.85 * 96; // 8.5in minus the existing .8in/.85in margins.
  for (const poem of document.querySelectorAll('.poem')) {
    const lines = Array.from(poem.querySelectorAll('.poem-line'));
    if (!lines.length) continue;
    const available = poem.getBoundingClientRect().width;
    const base = parseFloat(getComputedStyle(poem).fontSize);
    const probe = document.createElement('span');
    Object.assign(probe.style, {
      position: 'fixed', left: '-100000px', top: '0', visibility: 'hidden',
      display: 'inline-block', width: 'max-content', maxWidth: 'none',
      whiteSpace: 'pre', overflowWrap: 'normal', textWrap: 'nowrap',
    });
    probe.setAttribute('aria-hidden', 'true');
    poem.appendChild(probe);
    const widths = lines.map((line) => {
      probe.replaceChildren(...Array.from(line.childNodes, (node) => node.cloneNode(true)));
      return probe.getBoundingClientRect().width;
    }).sort((a, b) => a - b);
    probe.remove();
    // One size for the whole poem, never a tiny size on an individual long line.
    // Fit the 90th percentile; genuinely long lines get balanced continuations.
    const target = widths[Math.min(widths.length - 1, Math.ceil(widths.length * .9) - 1)];
    const points = target > 0 ? (base * .75 * available * .985 / target) : 11;
    const size = Math.max(10.25, Math.min(11, Math.floor(points * 20) / 20));
    poem.style.setProperty('--poem-font-size', `${size}pt`);
    // A stanza taller than an entire page must be allowed to flow. Its authored
    // lines still remain atomic; ordinary stanzas and bookends stay together.
    for (const stanza of poem.querySelectorAll('.poem-stanza')) {
      stanza.classList.toggle('poem-stanza--long', stanza.getBoundingClientRect().height > pageHeight - 1);
    }
    for (const bookend of poem.querySelectorAll('.poem-bookend')) {
      bookend.classList.toggle('poem-bookend--long', bookend.getBoundingClientRect().height > pageHeight - 1);
    }
    poem.dataset.poemLayout = '2';
    poem.dataset.poemFont = String(size);
  }
}

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
    await page.emulateMedia({ media: 'print' });
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
    await page.evaluate(preparePoemLayout);
    await page.pdf({
      path: path.join(base, out), preferCSSPageSize: true, printBackground: true,
      displayHeaderFooter: false, timeout: 300000,
    });
    console.log('rendered', out);
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
