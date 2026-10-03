// Both the API and local command use the same typesetter, in a private build folder.
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');
const { pathToFileURL, fileURLToPath } = require('url');

// Runs through Playwright, not manuscript scripts. Measure the actual embedded
// font at the book's fixed text measure, after fonts load, on both PDF passes.
function preparePoemLayout() {
  const pageHeight = 6.85 * 96; // 8.5in minus the existing .8in/.85in margins.
  const maxFont = 11;
  const minCommonFont = 9.5;
  const minLineFont = 7;
  const roundDown = (size) => Math.floor((size + 1e-8) * 20) / 20;
  const textWidth = (line) => {
    const range = document.createRange();
    range.selectNodeContents(line);
    return range.getBoundingClientRect().width;
  };

  for (const poem of document.querySelectorAll('.poem')) {
    const lines = Array.from(poem.querySelectorAll('.poem-line'));
    if (!lines.length) continue;
    // Reset before measuring, so repeated preparation is deterministic.
    poem.style.setProperty('--poem-font-size', `${maxFont}pt`);
    for (const line of lines) line.style.removeProperty('--poem-line-font-size');
    const available = poem.getBoundingClientRect().width;
    if (!(available > 0)) throw new Error('The poem has no printable text width.');
    const safeWidth = available * .985; // Reserve room for glyph overhang/rounding.
    const widest = lines.reduce((width, line) => Math.max(width, textWidth(line)), 0);
    const fitted = widest > 0 ? maxFont * safeWidth / widest : maxFont;
    // Use one common size wherever possible. A single exceptionally long line
    // must not force every other line down to small print. Only those outliers
    // get a smaller actual font, with the SAME baseline rhythm and no distortion.
    const commonSize = Math.max(minCommonFont, roundDown(Math.min(maxFont, fitted)));
    poem.style.setProperty('--poem-font-size', `${commonSize}pt`);
    let smallestSize = commonSize;
    for (const [index, line] of lines.entries()) {
      let size = commonSize;
      const width = textWidth(line);
      if (width > safeWidth) {
        size = roundDown(commonSize * safeWidth / width);
        // Re-measure the real styled text: references can have a fixed font size
        // and do not necessarily shrink proportionally with the surrounding verse.
        while (size >= minLineFont) {
          line.style.setProperty('--poem-line-font-size', `${size}pt`);
          if (textWidth(line) <= safeWidth) break;
          size = roundDown(size - .05);
        }
        if (size < minLineFont) {
          throw new Error(`Poem line ${index + 1} is too long to fit on one line at ` +
            `${minLineFont}pt in this book size. Use a wider print layout or shorten ` +
            'that authored line. No wrapped or clipped PDF was exported.');
        }
      }
      // Fail closed rather than quietly wrapping, clipping or losing any words.
      if (textWidth(line) > available) {
        throw new Error(`Poem line ${index + 1} exceeds its print margins.`);
      }
      line.dataset.poemFont = String(size);
      smallestSize = Math.min(smallestSize, size);
    }
    // Stanzas taller than a page can flow; ordinary stanzas and bookends remain
    // together. Authored lines cannot break horizontally or across two pages.
    for (const stanza of poem.querySelectorAll('.poem-stanza')) {
      stanza.classList.toggle('poem-stanza--long', stanza.getBoundingClientRect().height > pageHeight - 1);
    }
    for (const bookend of poem.querySelectorAll('.poem-bookend')) {
      bookend.classList.toggle('poem-bookend--long', bookend.getBoundingClientRect().height > pageHeight - 1);
    }
    poem.dataset.poemLayout = '3';
    poem.dataset.poemFont = String(commonSize);
    poem.dataset.poemSmallestFont = String(smallestSize);
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
