"""Verse-aware book layout. Source text and ordinary prose are never rewritten.

Use ``format: poem`` front matter for a whole poem, or a ``:::poem`` / ``:::``
block for verse within a prose chapter. Blank lines delimit stanzas; single
newlines delimit verse lines. An explicitly announced, stanza-shaped poem in
Chapter Two is also recognised for existing editor revisions without markers.
"""
import re
from html import escape

POEM_FORMAT_VERSION = 11
_FRONT = re.compile(r'^\ufeff?---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)')
_FENCE = re.compile(r'^[\t ]*:::poem[\t ]*$', re.I | re.M)
_CREDIT = re.compile(r'^[*_]*inspired by\s+', re.I)

POEM_CSS = r'''
@page poem-page { size: 5.5in 8.5in; margin: 0.8in 0.05in 0.85in 0.20in; }
.chapter--mixed-poem { page: poem-page; }
.chapter--mixed-poem > :not(.poem) {
  width: 4.35in; max-width: 100%; margin-left: auto; margin-right: auto;
  box-sizing: border-box;
}
/* Lists should sit inside the prose measure, not hang their bullets in the
   gutter. Keep the indent modest: marker near the prose edge, text just in. */
.chapter--mixed-poem > ul {
  width: 4.25in;
  margin: 0 auto .13in;
  padding-left: .18in;
  box-sizing: border-box;
}
.chapter--mixed-poem > ul > li {
  padding-left: .02in;
}
.poem {
  /* Match the book: Georgia at a fixed 11pt on every authored verse line. */
  font-family: Georgia, "Liberation Serif", serif; font-size: 11pt; font-weight: 400;
  font-kerning: normal; letter-spacing: normal; word-spacing: normal;
  width: auto; max-width: none; margin: .26in auto .22in;
  line-height: 1.34;
  text-align: center; text-indent: 0;
  hyphens: none; -webkit-hyphens: none;
}
.poem .poem-stanza {
  display: block; margin: 0 0 .18in; padding: 0; text-indent: 0;
  text-align: center; white-space: normal;
  font-size: inherit; line-height: inherit;
  break-inside: avoid; page-break-inside: avoid;
  hyphens: none; -webkit-hyphens: none;
}
.poem .poem-line {
  display: block; margin: 0; padding: 0; text-indent: 0;
  white-space: pre; text-align: center; text-wrap: nowrap;
  word-break: normal; overflow-wrap: normal;
  font-size: inherit; line-height: inherit;
  break-inside: avoid; page-break-inside: avoid;
  orphans: 2; widows: 2;
}
.poem .poem-line--quran {
  width: 4.55in; max-width: 88%; margin: .03in auto;
  white-space: normal; text-wrap: balance; overflow-wrap: normal;
  line-height: 1.34;
}
.poem-bookend { break-inside: avoid; page-break-inside: avoid; }
.poem-ornament {
  display: block; width: 1.2in; height: .24in;
  margin: 0 auto .21in; color: #555;
  break-after: avoid; page-break-after: avoid;
}
.poem-ornament svg { display: block; width: 100%; height: 100%; }
.poem-ornament--close {
  margin: .20in auto 0; transform: rotate(180deg);
  break-before: avoid; page-break-before: avoid;
  break-after: auto; page-break-after: auto;
}
.poem .poem-credit {
  font-family: Georgia, serif; font-variation-settings: normal;
  font-size: 8.5pt; line-height: 1.4; font-style: italic;
  text-align: center; margin: .16in 0 0;
  hyphens: none; -webkit-hyphens: none;
}
.poem .poem-bookend:last-child .poem-stanza { margin-bottom: 0; }
.poem .poem-stanza--long, .poem .poem-bookend--long {
  break-inside: auto; page-break-inside: auto;
}
'''


def _front(source):
    match = _FRONT.match(source)
    return (source[match.end():], match[1]) if match else (source, '')


def is_poem(source):
    """Backward-compatible explicit poem check (not a prose-length heuristic)."""
    body, front = _front(source)
    return bool(_FENCE.search(body.replace('\r\n', '\n')) or re.search(
        r'^format\s*:\s*[\"\']?poem[\"\']?\s*$', front, re.I | re.M))


def _implicit_sections(body):
    """Narrow compatibility path for the existing mixed Chapter Two.

    Called only for the belief chapter. Require a prose announcement of poetry,
    at least four multi-line stanzas and at least twelve short verse lines.
    Never infer stanza boundaries or use private manuscript quotations in code.
    An explicit ``format: prose`` opts out; fences always take precedence.
    """
    blocks = list(re.finditer(r'[^\n](?:[^\n]|\n(?![\t ]*\n))*', body))
    for index, match in enumerate(blocks):
        lines = match[0].strip().split('\n')
        if len(lines) < 2 or any(len(line) > 180 for line in lines):
            continue
        before = body[:match.start()]
        if not re.search(r'\bpoem\b|\bpoetry\b', before, re.I):
            continue
        tail = [block[0].strip().split('\n') for block in blocks[index:]]
        verse_lines = [line for stanza in tail for line in stanza if line.strip()]
        multiline = sum(len(stanza) > 1 for stanza in tail)
        if (multiline >= 4 and len(verse_lines) >= 12
                and sum(len(line) <= 180 for line in verse_lines) / len(verse_lines) >= .95
                and not any(re.match(r'^\s*(?:#{1,6}\s|[-+]\s|```|~~~)', line) for line in verse_lines)):
            return [('prose', before), ('poem', body[match.start():])]
    return [('prose', body)]


def manuscript_sections(source, infer_poem=False):
    """Return ordered (kind, text) segments without changing saved source."""
    body, front = _front(source)
    body = body.replace('\r\n', '\n')
    if _FENCE.search(body):
        sections, buffer, verse = [], [], False
        for line in body.split('\n'):
            marker = line.strip().lower()
            if marker == ':::poem':
                if verse:
                    raise ValueError('Poem blocks cannot be nested. Close the current block with :::.')
                if buffer:
                    sections.append(('prose', '\n'.join(buffer)))
                buffer, verse = [], True
            elif marker == ':::' and verse:
                sections.append(('poem', '\n'.join(buffer)))
                buffer, verse = [], False
            else:
                buffer.append(line)
        if verse:
            raise ValueError('Close the :::poem block with a line containing ::: before printing.')
        if buffer:
            sections.append(('prose', '\n'.join(buffer)))
        if verse:
            raise ValueError('Close the :::poem block before printing.')
        return [(kind, text) for kind, text in sections if text.strip() or kind == 'poem']
    if re.search(r'^format\s*:\s*[\"\']?poem[\"\']?\s*$', front, re.I | re.M):
        return [('poem', body)]
    if infer_poem and not re.search(r'^format\s*:\s*[\"\']?prose[\"\']?\s*$', front, re.I | re.M):
        return _implicit_sections(body)
    return [('prose', body)]


def _ornament(closing=False):
    modifier = ' poem-ornament--close' if closing else ''
    # Vector linework, not a font glyph or remotely fetched decoration.
    return ('<div class="poem-ornament%s" aria-hidden="true">'
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 32" '
            'fill="none" stroke="currentColor" stroke-width=".9" stroke-linecap="round">'
            '<path d="M6 16h24c10 0 13-9 23-9 7 0 11 5 11 9s-3 7-7 7c-3 0-5-2-5-4'
            'm102-3h-24c-10 0-13-9-23-9-7 0-11 5-11 9s3 7 7 7c3 0 5-2 5-4"/>'
            '<path d="M80 4l4 8 8 4-8 4-4 8-4-8-8-4 8-4z"/>'
            '<path d="M80 11l5 5-5 5-5-5z"/>'
            '<path d="M21 20h15m-10 3h8m90-3h-15m10 3h-8"/>'
            '</svg></div>') % modifier


def poem_body_html(body, inline, continue_from_prose=False):
    """One element per authored line; one unbreakable group per stanza."""
    body = body.replace('\r\n', '\n').strip('\n')
    stanzas = [stanza for stanza in re.split(r'\n[\t ]*\n+', body) if stanza.strip()]
    credit = ''
    # Only the final standalone attribution is treated as a credit.
    if stanzas and '\n' not in stanzas[-1].strip() and _CREDIT.match(stanzas[-1].strip()):
        credit = stanzas.pop().strip()
    if not stanzas:
        return ['<p class="poem-credit">%s</p>' % escape(credit)] if credit else []

    def format_line(line):
        # Older editor servers turn native numeric references into <sup>n</sup>
        # before sending mixed chapters. Restore only that narrow token before
        # escaping; all other literal HTML remains inert manuscript text.
        line = re.sub(r'<sup>(\d+)</sup>', r'[^\1]', line.rstrip())
        return re.sub(r'_([^_\n]+)_', r'<em>\1</em>', inline(escape(line, quote=True)))

    rendered = []
    quran_citation = re.compile(r'\(\s*\d{1,3}:\d{1,3}(?:\s*[,\)])')
    for stanza in stanzas:
        lines = ''.join('<span class="poem-line%s">%s</span>' %
                        (' poem-line--quran' if quran_citation.search(line) else '', format_line(line))
                        for line in stanza.split('\n'))
        rendered.append('<p class="poem-stanza">%s</p>' % lines)
    credit_html = '<p class="poem-credit">%s</p>' % format_line(credit) if credit else ''
    if len(rendered) == 1:
        groups = ['<div class="poem-bookend">' + _ornament() + rendered[0]
                  + credit_html + _ornament(True) + '</div>']
    else:
        groups = ['<div class="poem-bookend">' + _ornament() + rendered[0] + '</div>']
        groups.extend(rendered[1:-1])
        groups.append('<div class="poem-bookend">' + rendered[-1] + credit_html
                      + _ornament(True) + '</div>')
    return ['<div class="poem">' + '\n'.join(groups) + '</div>']
