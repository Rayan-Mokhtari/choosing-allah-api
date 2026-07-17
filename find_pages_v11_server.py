# -*- coding: utf-8 -*-
# Pass-1 page detection for v11: manifest-driven. Titles render in CAPS via CSS,
# may wrap, so match normalized uppercase title text in raw page text.
import fitz, json, re

MAN = json.load(open('./src16/manifest.json'))

def display(title):
    m = re.match(r'^(\d+)\.\s+(.*)$', title)
    return m.group(2) if m else title

def norm(s):
    s = s.replace('\u2019', "'").replace('\u2018', "'")
    return ' '.join(s.split())

doc = fitz.open('./pass1.pdf')
pages = [norm(doc[i].get_text()) for i in range(len(doc))]

preface_page = None
for i, t in enumerate(pages):
    if 'BEFORE WE BEGIN' in t.upper():
        preface_page = i
        break
if preface_page is None:
    raise SystemExit('BEFORE WE BEGIN heading not found')

result = {}

# All anchors (including References and Glossary, now at the back of the book)
# appear after the preface, in manifest order.
last = preface_page + 1
for e in MAN:
    if e['anchor'] == 'a-gloss': continue  # not printed in PDF — skip
    needle = norm(display(e['title'])).upper()
    found = None
    for i in range(last, len(doc)):
        pu = pages[i].upper()
        # skip the Contents page itself (it lists every title)
        if 'CONTENTS' in pu[:40]:
            continue
        if needle in pu:
            found = i + 1
            last = i + 1
            break
    result[e['anchor']] = found

result['_preface'] = preface_page + 1
missing = [a for a, v in result.items() if v is None]
print('preface page:', preface_page + 1)
print(json.dumps(result, indent=1))
if missing:
    raise SystemExit('MISSING anchors: %s' % missing)
with open('./page_map_v11.json', 'w') as f:
    json.dump(result, f)
print('total pages:', len(doc))
