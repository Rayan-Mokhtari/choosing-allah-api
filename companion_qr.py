"""Stable, locally rendered Chapter Two companion link for print and screen."""
import base64
from pathlib import Path

COMPANION_URL = 'https://choosingallah.com/explore'
COMPANION_MARKDOWN = '[![Explore nature and space](https://choosingallah.com/qr/chapter2.svg)](https://choosingallah.com/explore)'


def companion_qr_html():
    svg = Path(__file__).with_name('chapter2-qr.svg').read_bytes()
    encoded = base64.b64encode(svg).decode('ascii')
    return ('<div class="companion-qr" style="text-align:center;break-inside:avoid;'
            'page-break-inside:avoid;margin:.2in auto .1in">'
            '<a href="%s" aria-label="Explore nature and space">'
            '<img src="data:image/svg+xml;base64,%s" alt="Explore nature and space QR code" '
            'style="display:block;width:1.05in;height:1.05in;margin:0 auto .07in"></a>'
            '<a href="%s" style="font-size:8.5pt;color:#333;text-decoration:none">'
            'choosingallah.com/explore</a></div>') % (COMPANION_URL, encoded, COMPANION_URL)
