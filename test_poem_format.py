import unittest
from poem_format import is_poem, poem_body_html


class PoemFormatTests(unittest.TestCase):
    def test_stanzas_and_special_characters(self):
        source = '---\nformat: poem\n---\nFirst\nSecond\n\nA < B & C\nLast'
        self.assertTrue(is_poem(source))
        stanzas = poem_body_html('First\nSecond\n\nA < B & C\nLast', lambda value: value)
        self.assertEqual(stanzas, [
            '<p class="poem-stanza">First<br>Second</p>',
            '<p class="poem-stanza">A &lt; B &amp; C<br>Last</p>',
        ])

    def test_only_explicit_front_matter_enables_verse(self):
        self.assertFalse(is_poem('The phrase format: poem inside prose'))
        self.assertFalse(is_poem('---\nformat: prose\n---\nText'))
        self.assertTrue(is_poem('---\r\nformat: "poem"\r\n---\r\nText'))

    def test_markdown_block_syntax_and_indentation_are_literal_verse(self):
        html = poem_body_html('\n  1. First\n2. Second\n---\n# A verse\n> Another\n  Last\n', lambda value: value)
        self.assertEqual(html, ['<p class="poem-stanza">  1. First<br>2. Second<br>---<br># A verse<br>&gt; Another<br>  Last</p>'])


if __name__ == '__main__':
    unittest.main()
