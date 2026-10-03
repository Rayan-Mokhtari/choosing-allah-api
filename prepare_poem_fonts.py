"""Install the pinned OFL poem typeface at image-build time, never during printing.

Run once for local builds: python prepare_poem_fonts.py
The official variable font is used unmodified. CSS fixes its optical design;
no font files, glyph outlines or text are condensed by the renderer.
"""
from pathlib import Path
import hashlib
import urllib.request

REVISION = '0b58fb370093f9a9f4ff785d94405710b79de67c'
BASE_URL = f'https://raw.githubusercontent.com/google/fonts/{REVISION}/ofl/imbue/'
SHA256 = 'bf45ff1dc01974acedf4f11bcbfa7365053d97f4d598ddafe189d238ac80a534'


def install(destination=None):
    destination = Path(destination) if destination else Path(__file__).resolve().parent / 'fonts'
    destination.mkdir(parents=True, exist_ok=True)
    font = destination / 'Imbue.ttf'
    if not font.exists() or hashlib.sha256(font.read_bytes()).hexdigest() != SHA256:
        with urllib.request.urlopen(BASE_URL + 'Imbue%5Bopsz,wght%5D.ttf', timeout=30) as response:
            data = response.read(2_000_001)
        if len(data) > 2_000_000 or hashlib.sha256(data).hexdigest() != SHA256:
            raise RuntimeError('The poem typeface did not match the pinned checksum.')
        temporary = destination / '.Imbue.ttf.tmp'
        temporary.write_bytes(data)
        temporary.replace(font)
    license_path = destination / 'Imbue-OFL.txt'
    if not license_path.exists():
        with urllib.request.urlopen(BASE_URL + 'OFL.txt', timeout=30) as response:
            data = response.read(20_001)
        if len(data) > 20_000 or b'SIL OPEN FONT LICENSE' not in data:
            raise RuntimeError('The poem typeface license could not be verified.')
        license_path.write_bytes(data)
    print('Pinned Imbue poem typeface and OFL license ready.')


if __name__ == '__main__':
    install()
