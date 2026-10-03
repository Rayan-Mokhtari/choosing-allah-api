"""Regressions for mixed chapters and deliberately empty verse blocks."""
import unittest
from poem_format import is_poem, manuscript_sections, poem_body_html
from test_typesetter_parse import load_parser


class PoemEdgeCases(unittest.TestCase):
    def test_windows_newlines_enable_fenced_verse(self):
        self.assertTrue(is_poem('Intro\r\n\r\n:::poem\r\nOne\r\nTwo\r\n:::'))

    def test_empty_poem_does_not_print_its_markers(self):
        html = load_parser()(':::poem\n\n:::', '2. A question')
        self.assertNotIn(':::', html)
        self.assertNotIn('poem-ornament', html)

    def test_empty_poem_does_not_discard_following_italic_prose(self):
        html = load_parser()(':::poem\n\n:::\n\n*A closing note.*', '2. A question')
        self.assertIn('<em>A closing note.</em>', html)
        self.assertNotIn(':::', html)

    def test_italic_prose_after_poem_is_not_a_discarded_subtitle(self):
        html = load_parser()(':::poem\nOne\nTwo\n:::\n\n*A closing note.*', '2. A question')
        self.assertIn('<p><em>A closing note.</em></p>', html)
        self.assertEqual(html.count('class="poem-line"'), 2)

    def test_final_verse_starting_by_is_not_an_attribution(self):
        html = ''.join(poem_body_html('First\nSecond\n\nBy the water I stand.', lambda text: text))
        self.assertEqual(html.count('class="poem-stanza"'), 2)
        self.assertNotIn('class="poem-credit"', html)


if __name__ == '__main__':
    unittest.main()
