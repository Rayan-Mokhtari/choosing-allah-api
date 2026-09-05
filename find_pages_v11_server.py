# -*- coding: utf-8 -*-
"""Locate actual section openers in either a full-book or standalone PDF.

Hardened version: the full-book pass used to abort with
"MISSING anchors: [...]" whenever Chromium dropped the tiny white
[[PG:...]] markers from the PDF text layer, or whenever a manifest title
did not match the heading printed on the page (curly quotes, hyphenation
across a line break, a renamed chapter, punctuation differences).

Now matching is punctuation-insensitive, headings are looked for in the
opening block of a page first, and anything still not found falls back to
a sane page number instead of killing the build. Unresolved anchors are
reported on stderr so they can be fixed, but the PDF still ships.
"""
import fitz, json, re, sys
from build_v11_server import MANIFEST, EXPORT_FILE, PRELUDE_FILES, RESOURCE_FILES


def display(title):
    return re.sub(r'^\d+\.\s+', '', title)


def norm(value):
    """Whitespace/quote normalisation used for the raw page text."""
    value = (value.replace('\u2019', "'").replace('\u2018', "'")
                  .replace('\u201c', '"').replace('\u201d', '"')
                  .replace('\u2013', '-').replace('\u2014', '-')
                  .replace('\u00a0', ' '))
    value = ' '.join(value.split())
    return re.sub(r'(?<=\w)-\s+(?=\w)', '-', value)


def loose(value):
    """Letters and digits only - immune to quotes, dashes and spacing."""
    return re.sub(r'[^a-z0-9]+', '', norm(value).lower())


doc = fitz.open(sys.argv[1] if len(sys.argv) > 1 else './pass1.pdf')
pages = [norm(page.get_text()) for page in doc]
loose_pages = [loose(text) for text in pages]
# Chapter openers print their title near the top of the page.
loose_heads = [loose(text[:400]) for text in pages]


def marker(anchor):
    token = loose('[[PG:%s]]' % anchor)
    return next((index + 1 for index, text in enumerate(loose_pages) if token in text), None)


def heading(title, start=0):
    needle = loose(display(title))
    if not needle:
        return None
    for scope in (loose_heads, loose_pages):
        for index in range(start, len(pages)):
            if 'CONTENTS' in pages[index][:80].upper():
                continue
            if needle and needle in scope[index]:
                return index + 1
    return None


unresolved = []

if EXPORT_FILE == 'f_00_front_matter.md':
    # These three pages deliberately have no running heads or folios.
    result = {'_preface': len(doc) + 1}
elif EXPORT_FILE == 'f_00_preface_clean.md':
    result = {'_preface': marker('a-preface') or 1}
elif EXPORT_FILE in RESOURCE_FILES:
    result = {'_preface': 1, 'a-refs': marker('a-refs') or 1}
elif EXPORT_FILE and EXPORT_FILE != 'manifest.json':
    entry = MANIFEST[0]
    # Standalone exports contain only the selected section and deliberately
    # start it on page 1, so page 1 is the authoritative fallback.
    found = marker(entry['anchor']) or heading(entry['title']) or 1
    result = {'_preface': 1, entry['anchor']: found}
else:
    preface = marker('a-preface') or heading('Before we begin') or 1
    toc = marker('a-toc') or heading('Contents', preface) or preface
    result = {'_preface': preface, '_toc': toc}

    last = preface
    for entry in MANIFEST:
        anchor = entry.get('anchor')
        if not entry.get('file') or not anchor:
            continue
        if anchor in ('a-refs', 'a-gloss') or entry['file'] in PRELUDE_FILES:
            continue
        found = marker(anchor) or heading(entry['title'], last)
        if found is None:
            # Keep the map monotonic and usable rather than failing the build.
            found = last or 1
            unresolved.append(anchor)
        result[anchor] = found
        last = max(last or 0, found)

    refs = marker('a-refs') or heading('References', last)
    if refs is None:
        refs = last or 1
        unresolved.append('a-refs')
    result['a-refs'] = refs

if unresolved:
    print('WARNING: could not locate anchors %s - fell back to nearest page '
          '(%d pages total)' % (unresolved, len(doc)), file=sys.stderr)

with open('./page_map_v11.json', 'w', encoding='utf-8') as output:
    json.dump(result, output)
print(json.dumps(result, indent=1))
print('total pages:', len(doc))
doc.close()
