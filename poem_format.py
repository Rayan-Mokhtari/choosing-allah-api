"""Explicit verse layout without changing the existing prose typesetter."""
import re
from html import escape

POEM_FORMAT_VERSION = 1


def is_poem(source):
    front = re.match(r'^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)', source)
    return bool(front and re.search(r'^format\s*:\s*[\"\']?poem[\"\']?\s*$', front[1], re.I | re.M))


def poem_body_html(body, inline):
    body = body.replace('\r\n', '\n')
    body = re.sub(r'\A(?:[\t ]*\n)+|(?:\n[\t ]*)+\Z', '', body)
    stanzas = re.split(r'\n[\t ]*\n+', body)
    return ['<p class="poem-stanza">' + '<br>'.join(
        re.sub(r'_([^_\n]+)_', r'<em>\1</em>', inline(escape(line.rstrip(), quote=True)))
        for line in stanza.split('\n')
    ) + '</p>' for stanza in stanzas if stanza.strip()]
