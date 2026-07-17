# -*- coding: utf-8 -*-
# v11 post-render furniture, three jobs in one pass:
# 1. MIRRORED MARGINS: pages are rendered with left=gutter(0.65in)/right=outer(0.5in).
#    Versos (even page numbers) are shifted left by 0.15in so the gutter faces the spine.
# 2. RUNNING HEADS + FOLIOS: body pages get a centered-on-text-block running head with
#    the folio at the outer edge of the head line. Opener pages get a bottom-center folio.
#    Front matter (before the preface) stays clean.
# 3. GLOSSARY FOOTNOTES: superscript markers (6.5pt digits) are located per page and the
#    matching 'term: definition' lines are stamped at the bottom of that page, above a rule.
import fitz, json, sys

GEORGIA = '/usr/share/fonts/msttcore/georgia.ttf'
GEORGIA_I = '/usr/share/fonts/msttcore/georgiai.ttf'
import os
if not os.path.exists(GEORGIA_I): GEORGIA_I = GEORGIA

with open('/data/book/page_map_v11.json') as f:
    pm = json.load(f)
with open('/data/book/footnotes.json') as f:
    FN = json.load(f)

preface = pm.pop('_preface')
openers = set(pm.values()) | {preface}

# recto running heads carry the current chapter title; versos carry the book title
MAN = json.load(open('/data/book/src16/manifest.json'))
TITLES = {}
for e in MAN:
    if e['anchor'] == 'a-refs':
        # The online-resources page is a single opener right after the preface;
        # it must not become a running head for the pages that follow it.
        continue
    t = e['title']
    if '. ' in t and t.split('. ', 1)[0].isdigit():
        t = t.split('. ', 1)[1]
    TITLES[e['anchor']] = t.upper()
CHAP_STARTS = sorted((pg, TITLES[a]) for a, pg in pm.items() if a in TITLES)

def chapter_for(pageno):
    t = None
    for pg, title in CHAP_STARTS:
        if pg <= pageno:
            t = title
        else:
            break
    return t

raw_path = sys.argv[1] if len(sys.argv) > 1 else '/data/book/interior_v11_raw.pdf'
src = fitz.open(raw_path)
font = fitz.Font(fontfile=GEORGIA)
font_i = fitz.Font(fontfile=GEORGIA_I)

W, H = 396.0, 612.0          # 5.5x8.5in
SHIFT = 0.15 * 72            # gutter minus outer
GUTTER, OUTER = 0.65 * 72, 0.5 * 72
BLOCK_W = W - GUTTER - OUTER # 313.2
HEAD = 'CHOOSING ALLAH'
HEAD_SIZE, FOLIO_SIZE = 7.0, 9.0
FN_SIZE, FN_LEAD = 7.5, 9.2
TEXT_BOTTOM = H - 0.95 * 72  # 543.6

# ---- collect footnote markers per page from the RAW pdf (before shifting) ----
page_fns = {}
for i in range(len(src)):
    pageno = i + 1
    if pageno < preface: continue
    nums = []
    for b in src[i].get_text('dict')['blocks']:
        for l in b.get('lines', []):
            for s in l.get('spans', []):
                txt = s['text'].strip()
                if txt.isdigit() and 5.5 <= s['size'] <= 7.5 and txt in FN:
                    if int(txt) not in nums: nums.append(int(txt))
    if nums: page_fns[pageno] = sorted(nums)

# ---- rebuild with mirrored versos ----
out = fitz.open()
for i in range(len(src)):
    pageno = i + 1
    p = out.new_page(width=W, height=H)
    dx = -SHIFT if pageno % 2 == 0 else 0.0
    p.show_pdf_page(fitz.Rect(dx, 0, W + dx, H), src, i)

def block_left(pageno):
    return OUTER if pageno % 2 == 0 else GUTTER

def wrap(text, fnt, size, width):
    words = text.split()
    lines, cur = [], ''
    for w2 in words:
        t = (cur + ' ' + w2).strip()
        if fnt.text_length(t, size) <= width: cur = t
        else:
            if cur: lines.append(cur)
            cur = w2
    if cur: lines.append(cur)
    return lines

for i in range(len(out)):
    pageno = i + 1
    if pageno < preface: continue
    if not src[i].get_text().strip():
        continue  # blank versos stay completely clean
    page = out[i]
    bl = block_left(pageno)
    bc = bl + BLOCK_W / 2
    is_opener = pageno in openers
    label = str(pageno)
    if is_opener:
        w = font.text_length(label, FOLIO_SIZE)
        page.insert_text(fitz.Point(bc - w / 2, H - 26), label,
                         fontsize=FOLIO_SIZE, fontfile=GEORGIA, fontname='Georgia', color=(0.07, 0.07, 0.07))
    else:
        if pageno % 2 == 0:
            head_txt, hs = ' '.join(HEAD), HEAD_SIZE
        else:
            head_txt, hs = (chapter_for(pageno) or ' '.join(HEAD)), HEAD_SIZE
            while font.text_length(head_txt, hs) > BLOCK_W * 0.95 and hs > 5.5:
                hs -= 0.25
        w2 = font.text_length(head_txt, hs)
        page.insert_text(fitz.Point(bc - w2 / 2, 34), head_txt,
                         fontsize=hs, fontfile=GEORGIA, fontname='Georgia', color=(0.2, 0.2, 0.2))
        # folio bottom-center for body pages
        wl = font.text_length(label, FOLIO_SIZE)
        page.insert_text(fitz.Point(bc - wl / 2, H - 26), label,
                         fontsize=FOLIO_SIZE, fontfile=GEORGIA, fontname='Georgia', color=(0.07, 0.07, 0.07))
        wl = font.text_length(label, FOLIO_SIZE)
    # footnotes
    nums = page_fns.get(pageno)
    if not nums: continue
    entries = []
    for n in nums:
        e = FN[str(n)]
        entries.append((str(n), e['term'], e['defn']))
    # build wrapped lines: '<n> <term(i)>: <defn>'
    all_lines = []
    for n, term, defn in entries:
        full = '%s %s: %s' % (n, term, defn)
        all_lines.extend(wrap(full, font, FN_SIZE, BLOCK_W))
    size, lead = FN_SIZE, FN_LEAD
    if len(all_lines) > 4:
        size, lead = 7.0, 8.4
        all_lines = []
        for n, term, defn in entries:
            all_lines.extend(wrap('%s %s: %s' % (n, term, defn), font, size, BLOCK_W))
    y0 = 552 if is_opener else 554
    max_lines = 5 if not is_opener else 4
    if len(all_lines) > max_lines:
        print('WARN page %d: %d footnote lines (max %d)' % (pageno, len(all_lines), max_lines))
    # rule
    page.draw_line(fitz.Point(bl, y0 - 8), fitz.Point(bl + 72, y0 - 8), color=(0.25, 0.25, 0.25), width=0.5)
    y = y0
    for ln in all_lines:
        page.insert_text(fitz.Point(bl, y), ln, fontsize=size, fontfile=GEORGIA,
                         fontname='Georgia', color=(0.12, 0.12, 0.12))
        y += lead

out.save('/data/book/interior.pdf', garbage=3, deflate=True)
print('stamped ->', '/data/book/interior.pdf', 'pages:', len(out), 'footnote pages:', len(page_fns))
