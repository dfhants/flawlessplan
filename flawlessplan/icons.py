# -*- coding: utf-8 -*-
"""The icon as the PNGs a phone or a dock wants, made from assets/icon.svg.

    python3 -m flawlessplan.icons       # rewrites assets/icon-*.png

Run this again only when icon.svg changes.
"""
import os
import re

ASSETS = os.path.join(os.path.dirname(__file__), 'assets')
SIZES = (('icon-180.png', 180, False),              # apple-touch-icon
         ('icon-192.png', 192, False), ('icon-512.png', 512, False),
         ('icon-maskable-512.png', 512, True))      # full bleed, the drawing inside the safe middle


def maskable(svg):
    """The same drawing on a square tile with no corners, shrunk into the
    middle four fifths: a launcher may crop the rest to any shape."""
    head, tile, rest = re.match(r'(?s)(.*?)(<rect class="tile"[^>]*/>)(.*)</svg>', svg).groups()
    return (head + '<rect class="tile" width="64" height="64"/><g transform="translate(6.4 6.4) scale(0.8)">'
            + rest + '</g></svg>')


def make():
    import resvg_py
    with open(os.path.join(ASSETS, 'icon.svg')) as fh:
        svg = fh.read()
    for name, size, full in SIZES:
        with open(os.path.join(ASSETS, name), 'wb') as fh:
            fh.write(bytes(resvg_py.svg_to_bytes(svg_string=maskable(svg) if full else svg, width=size, height=size)))
        print(os.path.join(ASSETS, name))


if __name__ == '__main__':
    make()
