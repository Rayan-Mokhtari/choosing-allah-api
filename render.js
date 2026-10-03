// Both the API and local command use the same typesetter, in a private build folder.
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');
const { pathToFileURL, fileURLToPath } = require('url');

// One fixed point size and one type design across the entire poem. Measure only:
// never change a line's font size, tracking, horizontal scale or authored words.
function preparePoemLayout() {
  const pageHeight = 6.85 * 96;
  const expectedPixels = 11 * 96 / 72;
  for (const poem of document.querySelectorAll('.poem')) {
    const lines = Array.from(poem.querySelectorAll('.poem-line'));
    const available = poem.getBoundingClientRect().width;
    if (!(available > 0)) throw new Error('The poem has no printable text width.');
    for (const [index, line] of lines.entries()) {
      const style = getComputedStyle(line);
      if (Math.abs(parseFloat(style.fontSize) - expectedPixels) > .01) {
        throw new Error(`Poem line ${index + 1} does not use the fixed 11pt type size.`);
      }
      const range = document.createRange();
      range.selectNodeContents(line);
      // Retain the original margins and a little overhang/rounding clearance.
      if (range.getBoundingClientRect().width > available - 1.5) {
        throw new Error(`Poem line ${index + 1} is too long to fit on one line at ` +
          'the fixed 11pt size. The line was not shrunk, wrapped or clipped. ' +
          'Use a wider print layout for this manuscript.');
      }
      line.dataset.poemFont = '11';
    }
    for (const stanza of poem.querySelectorAll('.poem-stanza')) {
      stanza.classList.toggle('poem-stanza--long', stanza.getBoundingClientRect().height > pageHeight - 1);
    }
    for (const bookend of poem.querySelectorAll('.poem-bookend')) {
      bookend.classList.toggle('poem-bookend--long', bookend.getBoundingClientRect().height > pageHeight - 1);
    }
    poem.dataset.poemLayout = '4';
    poem.dataset.poemFont = '11';
  }
}

(async () => {
  const out = process.argv[2];
  if (!out || path.basename(out) !== out || !out.endsWith('.pdf')) {
    throw new Error('usage: node render.js <output.pdf>');
  }
  const base = path.resolve(process.env.BOOK_BUILD_DIR || __dirname);
  const assets = path.resolve(process.env.BOOK_ASSET_DIR || __dirname);
  let printInput = path.join(base, 'interior.html');
  const html = fs.readFileSync(printInput, 'utf8');
  if (html.includes('<div class="poem">')) {
    const fontPath = path.join(assets, 'fonts', 'Imbue.ttf');
    if (!fs.existsSync(fontPath)) {
      throw new Error('The poem typeface is missing. Run python prepare_poem_fonts.py before printing.');
    }
    // Fonts belong in the document before navigation. addStyleTag may wait
    // indefinitely for a load event when document JavaScript is disabled.
    // This is a generated build file, never a saved manuscript or source file.
    const encoded = fs.readFileSync(fontPath).toString('base64');
    const face = '<style>@font-face { font-family: "Poem Serif"; ' +
      'src: url("data:font/ttf;base64,' + encoded + '") format("truetype"); ' +
      'font-weight: 100 900; font-style: normal; }</style>';
    if (!html.includes('</head>')) throw new Error('The typeset document has no HTML head.');
    printInput = path.join(base, 'interior.print.html');
    fs.writeFileSync(printInput, html.replace('</head>', face + '</head>'), 'utf8');
  }
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
    await page.goto(pathToFileURL(printInput).href, {
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
