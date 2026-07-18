# -*- coding: utf-8 -*-
# v11 interior build, manifest-driven. Full layout overhaul.
import re, os, sys, json

D = './src16/'

def strip_fm(t):
    if t.lstrip().startswith('---'):
        parts = t.split('---', 2)
        if len(parts) >= 3: return parts[2]
    return t

def norm_quotes(s):
    out = []
    for i, ch in enumerate(s):
        if ch == '"':
            prev = s[i-1] if i > 0 else ' '
            out.append('\u201d' if (prev.isalnum() or prev in ".,!?%)'\u2019") else '\u201c')
        else:
            out.append(ch)
    return ''.join(out)

def absorb(s):
    for c in ('\u02f9','\u02fa','\u2e28','\u2e29'):
        s = s.replace(c, '')
    s = s.replace('  ', ' ')
    if '(Surah' in s or s.startswith('>'):
        s = re.sub(r'\\\[(.*?)\\\]', r'\1', s)
    else:
        s = re.sub(r'\\\[(.*?)\\\]', r'[\1]', s)
    return s

def inline(s):
    s = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', s)
    s = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', s)
    s = re.sub(r'\[\[FN(\d+)\]\]', r'<sup class="fn">\1</sup>', s)
    # merge adjacent reference markers into one superscript: 20,21 (not 2021)
    s = s.replace('</sup><sup class="fn">', ',')
    return s

NUM_WORDS = {1:'ONE',2:'TWO',3:'THREE',4:'FOUR',5:'FIVE',6:'SIX',7:'SEVEN',8:'EIGHT',
             9:'NINE',10:'TEN',11:'ELEVEN',12:'TWELVE',13:'THIRTEEN',14:'FOURTEEN',
             15:'FIFTEEN',16:'SIXTEEN',17:'SEVENTEEN',18:'EIGHTEEN'}

def split_title(title):
    m = re.match(r'^(\d+)\.\s+(.*)$', title)
    if m:
        n = int(m.group(1))
        return ('CHAPTER ' + NUM_WORDS.get(n, str(n)), m.group(2))
    return (None, title)

def add_dropcap(p_html):
    m = re.match(r'^<p>([A-Za-z])(.*)$', p_html, re.S)
    if not m: return p_html
    return '<p><span class="dropcap">%s</span>%s' % (m.group(1), m.group(2))

def clean_cell(s):
    s = re.sub(r'<[^>]+>', '', s)
    s = s.replace('**','').replace('*','')
    return ' '.join(s.split())

def load_glossary():
    t = open(D + 'glossary.md', encoding='utf-8').read()
    rows = re.findall(r'<tr>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*</tr>', t, re.S)
    terms = []
    for term, defn, first in rows:
        term, defn = clean_cell(term), clean_cell(defn)
        if not term or term.lower() == 'term': continue
        alts = [a.strip() for a in term.split('/') if a.strip()]
        pats = [r'(?<![A-Za-z])' + re.escape(a) + r'(?![A-Za-z])' for a in alts]
        rx = re.compile('|'.join(pats), re.IGNORECASE)
        terms.append({'term': term, 'defn': defn, 'rx': rx, 'done': False, 'num': None})
    return terms

GLOSSARY = load_glossary()
FN_COUNTER = [0]

def parse(md, chapter_title, anchor_id=None, footnotes=True):
    if md is None: return ''
    md = strip_fm(md)
    lines = [l.strip() for l in md.split('\n')]
    body = []
    idx = 0
    while idx < len(lines) and not lines[idx]: idx += 1
    if idx < len(lines):
        l = lines[idx]
        if l.startswith('*') and l.endswith('*') and l.count('*') == 2: idx += 1
    in_ul = False
    for l in lines[idx:]:
        if not l: continue
        if l.startswith('<page') or l.startswith('<empty-block'): continue
        raw = l
        l = norm_quotes(absorb(l))
        if re.match(r'^-{3,}$', raw):
            body.append('<p class="break">*&nbsp;&nbsp;&nbsp;*&nbsp;&nbsp;&nbsp;*</p>'); continue
        if raw.startswith('- '):
            if not in_ul: body.append('<ul>'); in_ul = True
            body.append('<li>%s</li>' % l[2:].strip()); continue
        if in_ul: body.append('</ul>'); in_ul = False
        if raw.startswith('## '):
            body.append('<h2>%s</h2>' % l[3:].strip()); continue
        if raw.startswith('> '):
            body.append('<p class="bq">%s</p>' % l[2:].strip()); continue
        if l.startswith('\u201c') and ('Surah' in raw or 'surah' in raw or re.search(r'\b[Aa]yas? \d', raw)):
            body.append('<p class="trans">%s</p>' % l); continue
        body.append('<p>%s</p>' % l)
    if in_ul: body.append('</ul>')
    while body and body[-1].startswith('<p class="break"'): body.pop()
    out = []
    for el in body:
        m2 = re.match(r'^(<[^>]+>)(.*?)(</[a-z0-9]+>)$', el, re.S)
        if m2:
            out.append(m2.group(1) + inline(m2.group(2)) + m2.group(3))
        else:
            out.append(el)
    body = out
    for i, el in enumerate(body):
        if el.startswith('<p>'):
            if len(re.sub(r'<[^>]+>', '', el)) >= 70:
                body[i] = add_dropcap(el); break
            continue  # short opener line: the cap belongs on the next full paragraph
        if not el.startswith('<h2>'): break
    eyebrow, display = split_title(chapter_title)
    anchor = '<a id="%s"></a>' % anchor_id if anchor_id else ''
    if eyebrow:
        head = '%s<section class="chapter"><div class="eyebrow">%s</div><h1 class="chap">%s</h1>' % (anchor, eyebrow, display)
    else:
        head = '%s<section class="chapter"><h1 class="chap nonum">%s</h1>' % (anchor, display)
    return head + '\n'.join(body) + '</section>'

MANIFEST = json.load(open(D + 'manifest.json', encoding='utf-8'))

def load(fp):
    p = D + fp
    if not os.path.exists(p): raise SystemExit('Missing: ' + p)
    return open(p, encoding='utf-8').read()

def toc_case(title):
    return title

def build_toc_html(page_map):
    rows = []
    for e in MANIFEST:
        # a-gloss has no printed page; a-refs (Online resources) is the single
        # QR page right after the preface and stays out of the Contents by design.
        if e['anchor'] in ('a-gloss', 'a-refs'): continue
        num = page_map.get(e['anchor'],'') if page_map else ''
        rows.append('<div class="toc-row"><span class="toc-title">%s</span><span class="toc-dots"></span><span class="toc-num">%s</span></div>' % (toc_case(e['title']), num if num else ''))
    return '<section class="chapter toc"><h1 class="chap nonum">Contents</h1><div class="toc-body">' + '\n'.join(rows) + '</div></section>'

def front_matter():
    t = strip_fm(load('f_00_front_matter.md'))
    t = t.replace('\\[','[').replace('\\]',']')
    def grab(label):
        m = re.search(r'\*\*' + label + r':?\*\*:?\s*(.*?)(?=\n\s*\*\*|\Z)', t, re.S)
        return ' '.join(m.group(1).split()) if m else None
    # Pull every field from the file. The file may or may not have
    # **Label:** prefixes; handle both layouts.
    cop = grab('Copyright page') or ''

    # Dedication: try the label first; if absent, use everything before
    # the first **-prefixed label (or before copyright) as the dedication.
    ded_raw = grab('Dedication')
    if not ded_raw:
        # No label: the whole file (minus copyright block) is the dedication.
        ded_raw = re.sub(r'\*\*[^*]+\*\*:?.*', '', t, flags=re.S).strip()
    ded = norm_quotes(ded_raw) if ded_raw else 'I don’t know your name.<br>But I thought about you on every single page.'

    # Epigraph: try the label first; fall back to hardcoded original.
    eq = '“Did He not find you unaware of the right path, and then guided you?”'
    esrc = 'Surah Ad-Duha, aya 7'
    epi_raw = grab('Epigraph')
    if epi_raw:
        if '—' in epi_raw:
            eq, esrc = [s.strip() for s in epi_raw.rsplit('—', 1)]
        elif '–' in epi_raw:
            eq, esrc = [s.strip() for s in epi_raw.rsplit('–', 1)]
        else:
            eq = epi_raw.strip()
        eq = norm_quotes(eq)
    cop = re.sub(r'\s*\(placeholder[^)]*\)', '', cop)
    cop_lines = [s.strip() for s in re.split(r'(?<=[.\]])\s+(?=[A-Z])', cop) if s.strip()]
    return ded, eq, esrc, cop_lines

def menu_section(anchor):
    url = 'https://choosingallah.com/resources'
    qr_tag = '<img class="qr-img" src="qr_refs.png">'
    try:
        import urllib.request, base64
        qr_url = 'https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=' + url
        with urllib.request.urlopen(qr_url, timeout=8) as r:
            b64 = base64.b64encode(r.read()).decode()
        qr_tag = '<img class="qr-img" src="data:image/png;base64,%s">' % b64
    except Exception:
        pass
    # No text on this page by design. Everything it needs to say lives in the
    # preface. Just the heading and the QR code, centered on the page.
    return ('<a id="%s"></a><section class="chapter" style="height:6.8in; display:flex; flex-direction:column;">'
            '<h1 class="chap nonum">Online resources</h1>'
            '<div style="flex:1; display:flex; align-items:center; justify-content:center;">%s</div>'
            '</section>') % (anchor, qr_tag)

CSS = (
    '@page { size: 5.5in 8.5in; margin: 0.8in 0.5in 0.85in 0.65in; }\n'
    '@page cover-page { size: 5.5in 8.5in; margin: 0; }\n'
    '.pg-cover { page: cover-page; width: 5.5in; height: 8.5in; page-break-after: always; overflow: hidden; display: block; }\n'
    '.pg-cover img { width: 100%; height: 100%; object-fit: cover; display: block; }\n'
    'body { font-family: Georgia, "Liberation Serif", serif; font-size: 11pt; line-height: 1.52;'
    '       color: #111; margin: 0; padding: 0; text-align: justify; hyphens: auto; orphans: 2; widows: 2; }\n'
    'p { margin: 0 0 0.13in 0; text-indent: 0; }\n'
    # Front matter pages
    '.pg-half { display:flex; flex-direction:column; justify-content:center;'
    '           align-items:center; height:6.8in; page-break-after:always; text-align:center; }\n'
    '.halftitle { font-size:14pt; letter-spacing:5px; text-transform:uppercase; margin:0; }\n'
    '.pg-title { display:flex; flex-direction:column; justify-content:center;'
    '            align-items:center; height:6.8in; page-break-after:always; text-align:center; }\n'
    '.pg-title h1 { font-family:Georgia,serif; font-size:26pt; font-weight:400; letter-spacing:6px;'
    '               text-transform:uppercase; margin:0; color:#111; line-height:1.5; }\n'
    '.tp-author { margin-top:1.1in; font-size:11.5pt; letter-spacing:3px; text-transform:uppercase; }\n'
    '.pg-copyright { display:flex; flex-direction:column; justify-content:flex-end;'
    '                min-height:6.7in; page-break-after:always; padding-bottom:0.1in; }\n'
    '.pg-copyright p { font-size:8.5pt; line-height:1.8; text-align:left; margin:0; }\n'
    '.pg-epigraph { display:flex; flex-direction:column; justify-content:center;'
    '               align-items:center; min-height:6.8in; page-break-after:always; text-align:center; }\n'
    '.epi-quote { font-style:italic; font-size:11.5pt; margin:0 0 0.22in 0;'
    '             max-width:4.0in; line-height:1.65; }\n'
    '.epi-src { font-size:9pt; color:#444; font-style:normal; margin:0; }\n'
    '.pg-dedication { display:flex; flex-direction:column; justify-content:center;'
    '                 align-items:center; min-height:6.8in; page-break-after:always; text-align:center; }\n'
    '.ded-line { font-style:italic; font-size:11.5pt; margin:0; padding:0.2in 0 0 0; }\n'
    '.ded-line:first-child { padding-top:0; }\n'
    # Chapters
    '.chapter { page-break-before:always; }\n'
    'h1.chap { text-align:center; font-size:16.5pt; font-weight:400; letter-spacing:3px;'
    '          text-transform:uppercase; margin:0 0 0.42in 0; color:#111; }\n'
    'h1.chap.nonum { margin-top:0.55in; }\n'
    '.preface h1.chap.nonum { margin:0.3in 0 0.32in 0; }\n'
    '.preface p { margin:0 0 0.10in 0; }\n'
    '.eyebrow { text-align:center; font-size:9pt; letter-spacing:4px; text-transform:uppercase;'
    '            margin:0.3in 0 0.14in 0; color:#333; }\n'
    'h2 { font-size:11pt; font-weight:bold; margin:0.158in 0 0.155in 0; page-break-after:avoid; }\n'
    '.bq { font-style:italic; margin:0 0 0.13in 0; }\n'
    '.trans { font-style:italic; margin:0 0 0.13in 0; }\n'
    '.break { text-align:center; margin:0.16in 0 0.29in 0; }\n'
    'ul { margin:0 0 0.13in 0.3in; padding:0; }\n'
    'li { margin:0 0 0.05in 0; }\n'
    'sup.fn { font-size:7.5pt; vertical-align:baseline; position:relative; top:-0.5em; line-height:0; }\n'
    # Drop cap: 2-line float
    '.dropcap { float:left; font-size:34.81pt; line-height:0.85; padding:0 0.09em 0 0; color:#111; position:relative; top:1.65pt; }\n'
    # QR pages
    '.qr-note { font-size:10.5pt; line-height:1.55; margin:0 0 0.4in 0; }\n'
    '.qr-img { display:block; margin:0 auto 0.1in auto; width:1.7in; height:1.7in; }\n'
    '.qr-url { font-size:8.5pt; text-align:center; font-family:Georgia,serif; color:#444; margin:0; }\n'
    # TOC
    '.toc h1.chap.nonum { margin:0.35in 0 0.3in 0; }\n'
    '.toc-body { margin-top:0.05in; }\n'
    '.toc-row { display:flex; align-items:baseline; margin:0 0 0.048in 0; font-size:9.5pt; }\n'
    '.toc-title { flex:0 1 auto; text-align:left; }\n'
    '.toc-dots { flex:1 1 auto; border-bottom:1px dotted #666; margin:0 0.08in 0.055in 0.08in; }\n'
    '.toc-num { flex:0 0 auto; }\n'
)


REFS_MAP = []
if os.path.exists('./refs_map.json'):
    with open('./refs_map.json') as _f:
        REFS_MAP = json.load(_f)

def inject_refs(md, fname):
    """Insert [[FNn]] reference markers after the sentence containing each mapped needle."""
    if md is None: return md
    entries = [e for e in REFS_MAP if e['file'] == fname]
    # process needles in order of position so numbers ascend at shared sentence ends
    entries.sort(key=lambda e: md.find(e['find']))
    for e in entries:
        i = md.find(e['find'])
        if i < 0: continue
        m = re.compile(r'[.!?][\u201d\u2019\'")\]]*').search(md, i + len(e['find']) - 1)
        if not m: continue
        pos = m.end()
        # skip past any markers already inserted at this point
        while True:
            fm = re.compile(r'\[\[FN\d+\]\]').match(md, pos)
            if fm: pos = fm.end()
            else: break
        md = md[:pos] + ('[[FN%d]]' % e['n']) + md[pos:]
    return md

def build_html(page_map=None):
    # The single online-resources page sits right after the preface (not in
    # the back matter), so readers meet it before the table of contents.
    resources_html = menu_section('a-refs')
    preface_html = parse(load('f_00_preface_clean.md'), 'Before we begin')
    preface_html = preface_html.replace('<section class="chapter">', '<section class="chapter preface">', 1)
    body = ''
    for e in MANIFEST:
        if e['anchor'] in ('a-refs','a-gloss'): continue
        body += parse(inject_refs(load(e['file']), e['file']), e['title'], anchor_id=e['anchor'])
    toc_html = build_toc_html(page_map or {})
    ded, eq, esrc, cop_lines = front_matter()
    ded_lines = [l.strip() for l in ded.split('<br>') if l.strip()]
    ded_html = ''.join('<p class="ded-line">%s</p>' % l for l in ded_lines)
    # Cover page: full bleed, no margins, page 1 if a cover URL was synced.
    cover_page = ''
    for _cuf in (D + 'f_cover_url.md', D + '__cover_url.txt'):
        if not os.path.exists(_cuf): continue
        _raw = open(_cuf, encoding='utf-8').read().strip()
        if not _raw: break
        try:
            import json as _json
            cu = _json.loads(_raw).get('content', '') if _raw.startswith('{') else _raw
        except Exception:
            cu = _raw
        if cu:
            try:
                import urllib.request, base64 as _b64
                req = urllib.request.Request(cu, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=20) as resp:
                    img_bytes = resp.read()
                    ct = resp.headers.get_content_type() or 'image/jpeg'
                b64str = _b64.b64encode(img_bytes).decode('ascii')
                cover_page = ('<div class="pg-cover">'
                              '<img src="data:%s;base64,%s" alt="Front cover">'
                              '</div>') % (ct, b64str)
            except Exception as _e:
                print('Cover image download failed:', _e)
        break

    h = '<!DOCTYPE html><html lang="en" dir="ltr"><head><meta charset="UTF-8"><style>' + CSS + '</style></head><body>'
    h += cover_page
    h += '<div class="pg-half"><p class="halftitle">Choosing Allah</p></div>'
    h += '<div class="pg-title"><h1>Choosing<br>Allah</h1><p class="tp-author">Rayan Mokhtari</p></div>'
    h += '<div class="pg-copyright">' + ''.join('<p>%s</p>' % c for c in cop_lines) + '</div>'
    h += '<div class="pg-epigraph"><p class="epi-quote">%s</p><p class="epi-src">%s</p></div>' % (eq, esrc)
    h += '<div class="pg-dedication">' + ded_html + '</div>'
    # blank verso so the preface opens on a recto (p7), matching print convention
    h += '<div style="height:6.8in; page-break-after:always;"></div>'
    h += preface_html
    # The online-resources page fills the verso after the preface (p8), so the
    # Contents still opens on a recto (p9), matching print convention.
    h += resources_html
    h += toc_html + body + '</body></html>'
    return h

if __name__ == '__main__':
    page_map = None
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        with open(sys.argv[1]) as f: page_map = json.load(f)
    html = build_html(page_map)
    with open('./interior.html', 'w', encoding='utf-8') as f:
        f.write(html)
    fns = {str(g['num']): {'term': g['term'], 'defn': g['defn']} for g in GLOSSARY if g['done']}
    with open('./footnotes.json', 'w', encoding='utf-8') as f:
        json.dump(fns, f, ensure_ascii=False)
    missed = [g['term'] for g in GLOSSARY if not g['done']]
    print('interior.html written;', 'page numbers ON' if page_map else 'pass 1')
    if missed: print('glossary terms never found:', missed)
