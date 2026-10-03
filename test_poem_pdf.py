"""Opt-in Chromium integration tests using synthetic, non-manuscript text.

Run with BOOK_PDF_TESTS=1 after installing the normal renderer dependencies.
The actual HTML builder, Chromium renderer, page mapper and stamper are used.
Every test builds in its own temporary directory; no saved chapter is edited.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

BASE = Path(__file__).resolve().parent


def normal(text):
    return ' '.join(text.split())


@unittest.skipUnless(os.environ.get('BOOK_PDF_TESTS') == '1', 'opt-in Chromium tests')
class PoemPdfTests(unittest.TestCase):
    def render(self, source, book=False):
        import fitz
        with tempfile.TemporaryDirectory(prefix='poem-layout-test-') as folder:
            job = Path(folder)
            (job / 'src16').mkdir()
            files = {
                'f_02.md': source,
                'f_03.md': 'Following prose remains a normal paragraph, with the same typography used throughout the rest of the book. This is test text, not a manuscript revision.',
                'f_00_preface_clean.md': 'This prefatory paragraph exists only in automated layout tests.',
                'f_00_front_matter.md': '**Copyright page:** Layout test fixture.\n**Dedication:** A layout test.\n**Epigraph:** Test typography.',
                'manifest.json': json.dumps([
                    {'file': 'f_02.md', 'title': '2. Why should you believe in Allah?', 'anchor': 'a-2'},
                    {'file': 'f_03.md', 'title': '3. Following chapter', 'anchor': 'a-3'},
                ]),
            }
            for filename, text in files.items():
                (job / 'src16' / filename).write_text(text, encoding='utf-8')
            before = {name: hashlib.sha256((job / 'src16' / name).read_bytes()).hexdigest() for name in files}
            env = {**os.environ, 'BOOK_BUILD_DIR': str(job), 'BOOK_ASSET_DIR': str(BASE),
                   'BOOK_EXPORT_FILE': '' if book else 'f_02.md', 'BOOK_EXPORT_TITLE': ''}

            def run(*args):
                result = subprocess.run(args, cwd=BASE, env=env, text=True,
                                        capture_output=True, timeout=180)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            run(sys.executable, str(BASE / 'build_v11_server.py'))
            run('node', str(BASE / 'render.js'), 'pass1.pdf')
            run(sys.executable, str(BASE / 'find_pages_v11_server.py'), str(job / 'pass1.pdf'))
            if book:
                run(sys.executable, str(BASE / 'build_v11_server.py'), str(job / 'page_map_v11.json'))
                run('node', str(BASE / 'render.js'), 'pass2.pdf')
            run(sys.executable, str(BASE / 'stamp_v11_server.py'), str(job / ('pass2.pdf' if book else 'pass1.pdf')))
            after = {name: hashlib.sha256((job / 'src16' / name).read_bytes()).hexdigest() for name in files}
            self.assertEqual(before, after, 'Printing must not modify the source snapshot')
            html = (job / 'interior.html').read_text(encoding='utf-8')
            document = fitz.open(stream=(job / 'interior.pdf').read_bytes(), filetype='pdf')
        return document, html

    def test_centred_stanzas_stay_intact_in_chapter_export(self):
        stanzas = ['\n'.join(f'Verse {i:02d}-{j}: a line kept within its stanza.' for j in range(4))
                   for i in range(18)]
        source = ('An introduction stays ordinary prose before the following poem is printed.\n\n'
                  ':::poem\n' + '\n\n'.join(stanzas) + '\n\nInspired by a test fixture.\n:::')
        doc, html = self.render(source)
        self.addCleanup(doc.close)
        self.assertGreater(len(doc), 2)
        self.assertEqual(html.count('class="poem-ornament'), 2)
        pages = [normal(page.get_text()) for page in doc]
        for stanza in stanzas:
            self.assertEqual(sum(normal(stanza) in page for page in pages), 1)
        centres = []
        for number, page in enumerate(doc, 1):
            self.assertEqual(tuple(page.rect)[2:], (396.0, 612.0))
            expected_centre = (36.0 if number % 2 == 0 else 46.8) + 156.6
            for block in page.get_text('dict')['blocks']:
                for line in block.get('lines', []):
                    text = ''.join(span['text'] for span in line['spans'])
                    if not text.startswith('Verse '):
                        continue
                    x0, y0, x1, y1 = line['bbox']
                    centres.append(abs((x0 + x1) / 2 - expected_centre))
                    self.assertGreaterEqual(y0, 55)
                    self.assertLessEqual(y1, 554)
        self.assertEqual(len(centres), 72)
        self.assertLess(max(centres), 1.5)
        self.assertIn('Inspired by a test fixture.', doc[-1].get_text())
        self.assertGreater(len(doc[0].get_drawings()), 0)
        self.assertGreater(len(doc[-1].get_drawings()), 0)

    def test_stanza_taller_than_a_page_is_not_clipped(self):
        lines = [f'Long stanza line {i:03d} continues safely.' for i in range(90)]
        doc, _ = self.render('---\nformat: poem\n---\n' + '\n'.join(lines))
        self.addCleanup(doc.close)
        text = normal(' '.join(page.get_text() for page in doc))
        for line in lines:
            self.assertEqual(text.count(line), 1)
        self.assertGreater(len(doc), 2)
        self.assertLess(len(doc), 6)

    def test_full_book_keeps_following_prose_and_reference_links(self):
        source = ('A normal introduction before a verse passage in the full-book export.\n\n'
                  ':::poem\nThe first line is kept.\nThe reference stays linked. [^9]\n\n'
                  'The last stanza remains here.\nIts final line stays here too.\n:::\n\n*An italic closing note.*')
        doc, html = self.render(source, book=True)
        self.addCleanup(doc.close)
        self.assertIn('<p><em>An italic closing note.</em></p>', html)
        self.assertEqual(html.count('class="poem"'), 1)
        text = normal(' '.join(page.get_text() for page in doc))
        self.assertIn('the same typography used throughout the rest of the book.', text)
        self.assertTrue(any(link.get('uri', '').endswith('/references#ref-9')
                            for page in doc for link in page.get_links()))
        following = next(entry for entry in doc.get_toc() if entry[1] == '3. Following chapter')
        self.assertIn('FOLLOWINGCHAPTER', ''.join(doc[following[2] - 1].get_text().split()))

    def test_every_authored_line_is_one_pdf_line_even_the_longest(self):
        # Every line must fit in normal Georgia without any automatic resizing.
        lines = [f'Short verse {i:02d} stays at the common size.' for i in range(30)]
        lines.insert(9, 'This longer verse line still fits within the printed page.')
        lines.insert(21, 'Every word in this longer verse stays on one baseline.')
        source = ':::poem\n' + '\n\n'.join('\n'.join(lines[i:i + 4]) for i in range(0, len(lines), 4)) + '\n:::'
        doc, _ = self.render(source)
        self.addCleanup(doc.close)
        found = []
        for number, page in enumerate(doc, 1):
            left = (36.0 if number % 2 == 0 else 46.8) - 28.8
            for block in page.get_text('dict')['blocks']:
                for line in block.get('lines', []):
                    text = ''.join(span['text'] for span in line['spans'])
                    if text not in lines:
                        continue
                    found.append(text)
                    x0, _, x1, _ = line['bbox']
                    self.assertGreaterEqual(x0, left - 1)
                    self.assertLessEqual(x1, left + 370.8 + 1)
                    self.assertLess(abs((x0 + x1) / 2 - (left + 185.4)), 1.5)
        self.assertEqual(found, lines, 'A verse line wrapped, clipped, disappeared, or changed order')

    def test_impossibly_long_line_stops_export_instead_of_wrapping(self):
        with self.assertRaisesRegex(AssertionError, r'Poem line 1 is too long to fit on one line'):
            self.render(':::poem\n' + ('Unbroken words ' * 150) + '\n:::')


if __name__ == '__main__':
    unittest.main()
