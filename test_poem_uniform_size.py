"""Keep every verse line at one real 11pt size, including long outliers."""
import os
import unittest
import test_poem_pdf as pipeline


@unittest.skipUnless(os.environ.get('BOOK_PDF_TESTS') == '1', 'opt-in Chromium tests')
class UniformPoemSizeTests(unittest.TestCase):
    def test_long_and_short_lines_use_identical_size_and_font(self):
        lines = [
            'A quiet evening settles over the rooftops while the last of the daylight fades behind the hills.',
            'A shorter line stays here.',
            'The final line keeps its size.',
        ]
        doc, _ = pipeline.PoemPdfTests.render(self, ':::poem\n' + '\n'.join(lines) + '\n:::')
        self.addCleanup(doc.close)
        found = []
        for page in doc:
            self.assertEqual(tuple(page.rect)[2:], (396.0, 612.0))
            for block in page.get_text('dict')['blocks']:
                for line in block.get('lines', []):
                    text = ''.join(span['text'] for span in line['spans'])
                    if text not in lines:
                        continue
                    found.append(text)
                    for span in line['spans']:
                        self.assertAlmostEqual(span['size'], 11, delta=.02)
                        self.assertIn('Imbue', span['font'])
                    self.assertGreater(line['bbox'][0], 30)
                    self.assertLess(line['bbox'][2], 366)
        self.assertEqual(found, lines)

    def test_prose_and_poem_do_not_share_the_new_typeface(self):
        prose = 'Ordinary prose retains Georgia and its original size.'
        verse = 'The verse retains eleven points.'
        doc, _ = pipeline.PoemPdfTests.render(self, prose + '\n\n:::poem\n' + verse + '\n:::')
        self.addCleanup(doc.close)
        found = {}
        for page in doc:
            for block in page.get_text('dict')['blocks']:
                for line in block.get('lines', []):
                    text = ''.join(span['text'] for span in line['spans'])
                    if text in (prose, verse):
                        found[text] = line['spans']
        self.assertEqual(set(found), {prose, verse})
        self.assertTrue(all('Georgia' in span['font'] for span in found[prose]))
        self.assertTrue(all('Imbue' in span['font'] for span in found[verse]))
        for spans in found.values():
            for span in spans:
                self.assertAlmostEqual(span['size'], 11, delta=.02)


if __name__ == '__main__':
    unittest.main()
