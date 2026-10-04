import unittest
from poem_format import is_poem, manuscript_sections, poem_body_html


class PoemFormatTests(unittest.TestCase):
    def render(self, source):
        return ''.join(poem_body_html(source, lambda value: value))

    def test_stanzas_and_special_characters(self):
        source = '---\nformat: poem\n---\nFirst\nSecond\n\nA < B & C\nLast'
        self.assertTrue(is_poem(source))
        rendered = self.render('First\nSecond\n\nA < B & C\nLast')
        self.assertEqual(rendered.count('class="poem-stanza"'), 2)
        self.assertEqual(rendered.count('class="poem-line"'), 4)
        self.assertIn('<span class="poem-line">First</span><span class="poem-line">Second</span>', rendered)
        self.assertIn('A &lt; B &amp; C', rendered)
        self.assertEqual(rendered.count('class="poem-ornament'), 2)
        self.assertNotIn('<br>', rendered)

    def test_only_explicit_markers_enable_general_verse(self):
        self.assertFalse(is_poem('The phrase format: poem inside prose'))
        self.assertFalse(is_poem('---\nformat: prose\n---\nText'))
        self.assertTrue(is_poem('---\r\nformat: "poem"\r\n---\r\nText'))
        self.assertTrue(is_poem('Prose\n:::poem\nVerse\n:::'))

    def test_markdown_block_syntax_and_indentation_are_literal_verse(self):
        rendered = self.render('\n  1. First\n2. Second\n---\n# A verse\n> Another\n  Last\n')
        for text in ('  1. First', '2. Second', '---', '# A verse', '&gt; Another', '  Last'):
            self.assertIn('<span class="poem-line">' + text + '</span>', rendered)
        self.assertEqual(rendered.count('class="poem-stanza"'), 1)
        self.assertEqual(rendered.count('class="poem-bookend"'), 1)

    def test_mixed_prose_and_multiple_poems(self):
        source = 'Intro\n\n:::poem\nOne\nTwo\n:::\n\nBridge\n:::poem\nThree\n:::\nEnding'
        sections = manuscript_sections(source)
        self.assertEqual([kind for kind, _ in sections], ['prose', 'poem', 'prose', 'poem', 'prose'])
        self.assertEqual(sections[1][1], 'One\nTwo')
        self.assertEqual(sections[-1][1], 'Ending')

    def test_crlf_and_bom(self):
        sections = manuscript_sections('\ufeff---\r\nformat: "poem"\r\n---\r\nOne\r\nTwo')
        self.assertEqual(sections, [('poem', 'One\nTwo')])

    def test_invalid_fences_fail_without_guessing(self):
        for source in (':::poem\nOne', ':::poem\n:::poem\nTwo\n:::'):
            with self.assertRaises(ValueError):
                manuscript_sections(source)

    def test_announced_poem_inference_is_opt_in_and_respects_source_gaps(self):
        intro = 'I have chosen to answer with a poem.\n\n'
        verse = '\n\n'.join('\n'.join('Stanza %s line %s.' % (i, j) for j in range(4)) for i in range(5))
        self.assertEqual(manuscript_sections(intro + verse), [('prose', intro + verse)])
        self.assertEqual(manuscript_sections(intro + verse, infer_poem=True), [('prose', intro), ('poem', verse)])
        self.assertEqual(manuscript_sections('---\nformat: prose\n---\n' + intro + verse, True), [('prose', intro + verse)])
        self.assertEqual(self.render(verse.replace('\n\n', '\n  \n')).count('class="poem-stanza"'), 5)

    def test_short_prose_and_unannounced_lines_are_not_inferred(self):
        self.assertEqual(manuscript_sections('A poem is mentioned.\n\nShort\nLines', True)[0][0], 'prose')
        self.assertEqual(manuscript_sections(('Line one\nLine two\n\n' * 10), True)[0][0], 'prose')

    def test_mixed_poem_can_start_on_prose_page_then_switch_wide(self):
        rendered = ''.join(poem_body_html(
            'First line\nSecond line\n\nLater stanza\nFinal line',
            lambda value: value, continue_from_prose=True))
        self.assertIn('class="poem poem--lead"', rendered)
        self.assertIn('class="poem poem--wide"', rendered)
        self.assertLess(rendered.index('First line'), rendered.index('Later stanza'))
        self.assertEqual(rendered.count('class="poem-ornament'), 2)

    def test_credit_stays_with_last_stanza_and_closing_ornament(self):
        rendered = self.render('First\nSecond\n\nLast\n\nInspired by an author.')
        self.assertEqual(rendered.count('class="poem-credit"'), 1)
        self.assertEqual(rendered.count('class="poem-stanza"'), 2)
        self.assertLess(rendered.index('Last'), rendered.index('Inspired by'))
        self.assertLess(rendered.index('Inspired by'), rendered.index('poem-ornament--close'))
        self.assertIn('font-size', __import__('poem_format').POEM_CSS)

    def test_html_is_inert_and_emphasis_is_retained(self):
        rendered = self.render('<script>alert(1)</script>\nA _quiet_ line.')
        self.assertNotIn('<script>', rendered)
        self.assertIn('&lt;script&gt;', rendered)
        self.assertIn('<em>quiet</em>', rendered)


if __name__ == '__main__':
    unittest.main()
