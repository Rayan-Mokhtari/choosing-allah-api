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


def find_marker(anchor):
    # Primary detection: each chapter section embeds an invisible
    # '[[PG:<anchor>]]' token (see build_v11*.py). Unlike title text, the
    # token cannot recur in body text, wrap oddly, or drift when a title
    # is edited, so detection is exact.
    tag = '[[PG:%s]]' % anchor
    for i, t in enumerate(pages):
        if tag in t:
            return i + 1
    return None


# The online-resources page (a-refs) sits right after the preface and renders
# the heading ONLINE RESOURCES, so its fallback is located separately. Every
# other anchor appears after the preface in manifest order.
last = preface_page + 1
for e in MAN:
    if e['anchor'] == 'a-gloss': continue
    found = find_marker(e['anchor'])
    if found is None and e['anchor'] == 'a-refs':
        for i in range(preface_page + 1, len(doc)):
            pu = pages[i].upper()
            if 'CONTENTS' in pu[:40]:
                continue
            if 'ONLINE RESOURCES' in pu:
                found = i + 1
                break
        result[e['anchor']] = found
        continue
    if found is None:
        # Fallback for PDFs built without markers: old title-text search.
        needle = norm(display(e['title'])).upper()
        for i in range(last, len(doc)):
            pu = pages[i].upper()
            # skip the Contents page itself (it lists every title)
            if 'CONTENTS' in pu[:40]:
                continue
            if needle in pu:
                found = i + 1
                break
    if found is not None and e['anchor'] != 'a-refs':
        last = max(last, found)
    result[e['anchor']] = found

result['_preface'] = preface_page + 1
missing = [a for a, v in result.items() if v is None]
print('preface page:', preface_page + 1)
print(json.dumps(result, indent=1))
if missing:
    raise SystemExit('MISSING anchors: %s (pass1.pdf has %d pages; found: %s)'
                     % (missing, len(doc), {k: v for k, v in result.items() if v}))
with open('./page_map_v11.json', 'w') as f:
    json.dump(result, f)
print('total pages:', len(doc))
