# -*- coding: utf-8 -*-
"""Locate actual section openers in either a full-book or standalone PDF."""
import fitz, json, re, sys
from build_v11_server import MANIFEST, EXPORT_FILE, PRELUDE_FILES, RESOURCE_FILES

def display(title):
    return re.sub(r'^\d+\.\s+', '', title)

def norm(value):
    value = ' '.join(value.replace('\u2019', "'").replace('\u2018', "'").split())
    return re.sub(r'(?<=\w)-\s+(?=\w)', '-', value)

doc = fitz.open(sys.argv[1] if len(sys.argv) > 1 else './pass1.pdf')
pages = [norm(page.get_text()) for page in doc]

def marker(anchor):
    token = '[[PG:%s]]' % anchor
    return next((index + 1 for index, text in enumerate(pages) if token in text), None)

def heading(title, start=0):
    needle = norm(display(title)).upper()
    return next((index + 1 for index in range(start, len(pages))
                 if 'CONTENTS' not in pages[index][:80].upper() and needle in pages[index].upper()), None)

if EXPORT_FILE == 'f_00_front_matter.md':
    # These three pages deliberately have no running heads or folios.
    result = {'_preface': len(doc) + 1}
elif EXPORT_FILE == 'f_00_preface_clean.md':
    result = {'_preface': marker('a-preface')}
elif EXPORT_FILE in RESOURCE_FILES:
    result = {'_preface': 1, 'a-refs': marker('a-refs')}
elif EXPORT_FILE and EXPORT_FILE != 'manifest.json':
    entry = MANIFEST[0]
    # Standalone exports contain only the selected section and deliberately
    # start it on page 1. Chromium can omit the tiny white marker from PDF text
    # extraction (seen with the Introduction), so page 1 is the authoritative
    # fallback when neither the marker nor the displayed heading survives.
    found = marker(entry['anchor']) or heading(entry['title']) or (1 if len(doc) else None)
    result = {'_preface': 1, entry['anchor']: found}
else:
    preface = marker('a-preface') or heading('Before we begin')
    result = {'_preface': preface, '_toc': marker('a-toc'), 'a-refs': marker('a-refs')}
    last = preface or 0
    for entry in MANIFEST:
        if not entry.get('file') or entry['anchor'] in ('a-refs', 'a-gloss') or entry['file'] in PRELUDE_FILES:
            continue
        found = marker(entry['anchor']) or heading(entry['title'], last)
        result[entry['anchor']] = found
        if found: last = found

missing = [anchor for anchor, number in result.items() if number is None]
if missing:
    raise SystemExit('MISSING anchors: %s (%d pages)' % (missing, len(doc)))
with open('./page_map_v11.json', 'w', encoding='utf-8') as output:
    json.dump(result, output)
print(json.dumps(result, indent=1))
print('total pages:', len(doc))
doc.close()
