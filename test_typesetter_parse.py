"""Exercise the typesetter parser without running the full build at import."""
import ast
import re
import unittest
from html import escape
from pathlib import Path
from poem_format import manuscript_sections, poem_body_html


def load_parser():
    tree = ast.parse(Path(__file__).with_name('build_v11_server.py').read_text())
    names = {'strip_fm', 'norm_quotes', 'absorb', 'reference_html', 'inline', 'split_title', 'add_dropcap', 'prose_body_html', 'parse'}
    definitions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    scope = {'re': re, 'escape': escape, 'manuscript_sections': manuscript_sections, 'poem_body_html': poem_body_html,
             'NUM_WORDS': {2: 'TWO'}, 'RESOURCES_URL': 'https://choosingallah.com/resources'}
    exec(compile(ast.Module(body=definitions, type_ignores=[]), 'typesetter-parser', 'exec'), scope)
    return scope['parse']


class TypesetterParseTests(unittest.TestCase):
    def test_invitation_after_credit_is_prose_and_qr_is_clickable(self):
        from companion_qr import COMPANION_MARKDOWN
        source = ('I have chosen to answer with a poem.\n\n'
                  + '\n\n'.join('One\nTwo\nThree\nFour' for _ in range(5))
                  + '\n\nInspired by another poem.\n\n'
                  + 'A closing invitation ' * 20 + '\n\n' + COMPANION_MARKDOWN)
        sections = manuscript_sections(source, infer_poem=True)
        self.assertEqual([kind for kind, _ in sections], ['prose', 'poem', 'prose'])
        self.assertNotIn('closing invitation', sections[1][1])
        html = load_parser()(source, '2. Why should you believe in Allah?')
        self.assertIn('class="companion-page"', html)
        self.assertIn('href="https://choosingallah.com/explore"', html)
        self.assertIn('data:image/svg+xml;base64,', html)
        self.assertNotIn('[![', html)

    def test_companion_follows_poem_and_keeps_credit_once(self):
        from companion_qr import COMPANION_MARKDOWN
        source = (':::poem\nFirst line\nSecond line\n\nFinal line\nLast line\n\n'
                  'Inspired by a poem.\n:::\n\nScan the code to keep exploring.\n\n' + COMPANION_MARKDOWN)
        html = load_parser()(source, '2. Why should you believe in Allah?')
        last_group = html[html.rfind('<div class="poem-bookend">'):]
        self.assertIn('Final line', last_group)
        self.assertIn('companion-page-code', last_group)
        self.assertIn('Look again', last_group)
        self.assertEqual(html.count('Inspired by a poem.'), 1)
        self.assertEqual(html.count('Scan the code to keep exploring.'), 1)
        self.assertEqual(html.count('class="poem-ornament'), 2)

    def test_long_prose_outro_stays_outside_poem(self):
        from companion_qr import COMPANION_MARKDOWN
        source = ':::poem\nOne\nTwo\n:::\n\nFirst paragraph.\n\nSecond paragraph.\n\n' + COMPANION_MARKDOWN
        html = load_parser()(source, '2. Why should you believe in Allah?')
        self.assertNotIn('companion-page-code', html)
        self.assertIn('class="companion-note"', html)

    def test_poem_is_explicit_safe_and_keeps_inline_references(self):
        html = load_parser()('---\nformat: poem\n---\nFirst\nSecond *word*\n\nA < B & C [^9]', '2. A question', 'a-2')
        self.assertIn('<span class="poem-line">Second <em>word</em></span>', html)
        self.assertEqual(html.count('class="poem-stanza"'), 2)
        self.assertEqual(html.count('class="poem-ornament'), 2)
        self.assertIn('A &lt; B &amp; C', html)
        self.assertIn('/resources/references#ref-9', html)
        self.assertNotIn('dropcap', html)
        self.assertNotIn('format: poem', html)

    def test_ordinary_prose_still_uses_original_paragraphs_and_dropcap(self):
        source = 'A paragraph long enough to have the same opening drop cap as it always did in the printed manuscript.\n\nAnother paragraph.'
        html = load_parser()(source, '2. A question', 'a-2')
        self.assertIn('<span class="dropcap">A</span>', html)
        self.assertIn('<p>Another paragraph.</p>', html)
        self.assertNotIn('poem-stanza', html)
        self.assertNotIn('<br>', html)

    def test_mixed_chapter_keeps_prose_and_native_or_legacy_references(self):
        source = ('An introduction long enough to receive the same drop capital as in the original printed chapter.\n\n'
                  ':::poem\nA verse with [^9].\nAnother with <sup>10</sup>.\n:::\n\nA prose ending.')
        html = load_parser()(source, '2. A question', 'a-2')
        self.assertEqual(html.count('class="dropcap"'), 1)
        self.assertIn('class="chapter chapter--mixed-poem"', html)
        self.assertEqual(html.count('class="poem"'), 1)
        self.assertIn('references#ref-9', html)
        self.assertIn('references#ref-10', html)
        self.assertIn('<p>A prose ending.</p>', html)
        self.assertNotIn(':::poem', html)
        self.assertNotIn('&lt;sup&gt;', html)

    def test_legacy_inference_is_scoped_to_belief_chapter(self):
        source = 'I have chosen to answer with a poem.\n\n' + '\n\n'.join('One\nTwo\nThree\nFour' for _ in range(5))
        parse = load_parser()
        belief_html = parse(source, '2. Why should you believe in Allah?')
        self.assertIn('class="chapter chapter--mixed-poem"', belief_html)
        self.assertIn('class="poem"', belief_html)
        self.assertNotIn('class="poem"', parse(source, '3. Another chapter'))


if __name__ == '__main__':
    unittest.main()
