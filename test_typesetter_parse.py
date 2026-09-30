"""Exercise the typesetter parser without running the full build at import."""
import ast
import re
import unittest
from html import escape
from pathlib import Path
from poem_format import is_poem, poem_body_html


def load_parser():
    tree = ast.parse(Path(__file__).with_name('build_v11_server.py').read_text())
    names = {'strip_fm', 'norm_quotes', 'absorb', 'reference_html', 'inline', 'split_title', 'add_dropcap', 'parse'}
    definitions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    scope = {'re': re, 'escape': escape, 'is_poem': is_poem, 'poem_body_html': poem_body_html,
             'NUM_WORDS': {2: 'TWO'}, 'RESOURCES_URL': 'https://choosingallah.com/resources'}
    exec(compile(ast.Module(body=definitions, type_ignores=[]), 'typesetter-parser', 'exec'), scope)
    return scope['parse']


class TypesetterParseTests(unittest.TestCase):
    def test_poem_is_explicit_safe_and_keeps_inline_references(self):
        html = load_parser()('---\nformat: poem\n---\nFirst\nSecond *word*\n\nA < B & C [^9]', '2. A question', 'a-2')
        self.assertIn('First<br>Second <em>word</em>', html)
        self.assertEqual(html.count('class="poem-stanza"'), 2)
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


if __name__ == '__main__':
    unittest.main()
