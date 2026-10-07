# -*- coding: utf-8 -*-
"""The markup page: every sheet of a house, and the means to write and draw
on it. Marks carry the sheet they were made on and are stored in metres,
so they stay put when a sheet is redrawn. Each sheet zooms by narrowing its
own viewBox, in and out, so a mark lands where it was drawn at any zoom.

And the page that is sent: the same sheets in one file that needs nothing
else, to be read and not drawn on."""
import base64
import json
import os
import re
import shutil
from urllib.parse import quote
from . import render, report

VARS = {'INK': 'var(--ink)', 'SOFT': 'var(--ink-soft)', 'FLOOR': 'var(--floor)',
        'FIT': 'var(--fit)', 'RED': 'var(--red)', 'BLUE': 'var(--blue)', 'GRID': 'var(--grid)'}

ASSETS = os.path.join(os.path.dirname(__file__), 'assets')


def asset(name):
    with open(os.path.join(ASSETS, name)) as fh:
        return fh.read()


SHARED = ('icon.svg', 'icon-180.png', 'icon-192.png', 'icon-512.png', 'icon-maskable-512.png',
          'manifest.webmanifest', 'fonts')      # what install() puts beside the index

FACES = ("@font-face{font-family:'Archivo';font-style:normal;font-weight:500 700;font-display:swap;"
         "src:url(%sfonts/archivo.woff2) format('woff2')}\n"
         "@font-face{font-family:'IBM Plex Mono';font-style:normal;font-weight:400;font-display:swap;"
         "src:url(%sfonts/plex-mono-400.woff2) format('woff2')}\n"
         "@font-face{font-family:'IBM Plex Mono';font-style:normal;font-weight:500;font-display:swap;"
         "src:url(%sfonts/plex-mono-500.woff2) format('woff2')}")


def fonts(root=None):
    """The two typefaces, from the copies install() puts beside the index —
    a page asks no other site for anything. With no `root` there is no such
    copy, and the page falls back to the system's own faces."""
    return '' if root is None else '<style>%s</style>' % (FACES % (root, root, root))


def fonts_inside():
    """The same two typefaces carried in the page itself, for a page that
    is sent on its own."""
    css = FACES % ('', '', '')
    for name in ('archivo', 'plex-mono-400', 'plex-mono-500'):
        with open(os.path.join(ASSETS, 'fonts', name + '.woff2'), 'rb') as fh:
            css = css.replace('fonts/%s.woff2' % name,
                              'data:font/woff2;base64,' + base64.b64encode(fh.read()).decode('ascii'))
    return css


def icon_uri():
    """The icon as a data URI: a plan with a door in it."""
    return 'data:image/svg+xml,' + quote(' '.join(asset('icon.svg').split()), safe=" =:/'(),;.-")


def icon(root=None):
    """The <head> lines for the icon. The SVG is carried in the page itself,
    so a page saved or published on its own still has it; with `root`, the
    path to where install() put the rest, the page can also go on a home
    screen or a dock."""
    out = ['<link rel="icon" type="image/svg+xml" href="%s">' % icon_uri()]
    if root is not None:
        out += ['<link rel="apple-touch-icon" href="%sicon-180.png">' % root,
                '<link rel="manifest" href="%smanifest.webmanifest">' % root,
                '<meta name="apple-mobile-web-app-title" content="Flawlessplan">',
                '<meta name="theme-color" content="#EDF1EF" media="(prefers-color-scheme: light)">',
                '<meta name="theme-color" content="#0F1513" media="(prefers-color-scheme: dark)">']
    return '\n'.join(out)


def install(out):
    """Copy the icons and the manifest into `out`, beside the index."""
    for name in SHARED:
        src, dest = os.path.join(ASSETS, name), os.path.join(out, name)
        if os.path.isdir(src):
            shutil.copytree(src, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns('*.txt'))
        else:
            shutil.copyfile(src, dest)


def _js(v):
    """A value as JSON that is safe inside a <script>: no tag can end it."""
    return json.dumps(v).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')


def _fill(template, parts):
    """A template with each `__NAME__` put in, once through: nothing put
    in is read again, so a room called __JS__ is a room called __JS__."""
    return re.sub('__([A-Z]+)__', lambda m: parts[m.group(1)], template)


def panel(key, info):
    """What is said about a sheet, as the panel beside it."""
    return '\n'.join(['<aside class="info" id="in-%s">' % key] + said(info) + ['</aside>'])


def said(info):
    """The lines of a sheet's panel."""
    e = render.esc
    out = ['<h2>%s</h2>' % e(info['title'])]
    if info['summary']:
        out.append('<p>%s</p>' % e(info['summary']))
    rows = ['<tr><td>%s</td><td>%s</td></tr>' % (e(a), e(b)) for a, b in info['figures']]
    if rows:
        out.append('<table>%s</table>' % ''.join(rows))
    if info['rooms']:
        out.append('<h3>Rooms, clear inside</h3><table>')
        for r in info['rooms']:
            shape = report.SHAPES.get(r['shape'])
            out.append('<tr><td>%s%s</td><td>%.2f × %.2f</td><td>%.1f m²</td></tr>'
                       % (e(r['name']), '<small>%s</small>' % shape if shape else '',
                          r['w'], r['h'], r['area']))
        out.append('</table>')
    for key, head, items in info['groups']:
        out.append('<h3 class="%s">%s</h3><ul>%s</ul>'
                   % (key, e(head), ''.join('<li>%s</li>' % e(t) for t in items)))
    return out


def markup(title, sheets, root=None, send=None, hidden=(), version=None):
    """The page for one house, from its sheets (solve.Sheet: id, tab, vb,
    lines, info). `root` is the path from the page to the index of houses:
    given, the page has a way back to it, its own fonts, and can be put on a
    home screen. `send` is the name of the file beside it that share()
    made: given, the page has a button that hands it over. `sheets` are
    the ones that show; `hidden` the ones that do not, listed in the menu
    that brings them back; `version` names the house file the page was
    drawn from, which the page gives back with any change it asks for."""
    movable = [s.id for s in sheets if getattr(s, 'kind', 'plan') == 'plan']     # the outline sheet is not in the file to be moved
    sheets = [(s.id, s.tab, s.vb, s.lines, s.info) for s in sheets]
    keys = [s[0] for s in sheets]
    tabs = '\n'.join(
        '    <button class="tab" role="tab" id="tab-%s" data-sheet="%s" aria-controls="cv-%s"'
        ' aria-selected="%s" tabindex="%s">%s<span class="n" hidden></span></button>'
        % (k, k, k, 'true' if i == 0 else 'false', 0 if i == 0 else -1, render.esc(label))
        for i, (k, label) in enumerate(s[:2] for s in sheets))
    stages = []
    for k, label, vb, lines, info in sheets:
        x, y, w, h = [render.n2(v) for v in vb]
        stages.append(
            '<div class="stage" id="cv-%s" role="tabpanel" aria-labelledby="tab-%s">'
            '<svg id="sv-%s" class="draw" viewBox="%s %s %s %s" role="img"'
            ' aria-label="%s sheet, with a drawing layer">\n'
            '    <rect class="hit" x="%s" y="%s" width="%s" height="%s"/>\n'
            '%s\n'
            '    <g id="mk-%s"></g>\n'
            '    <g id="gh-%s"></g>\n'
            '  </svg></div>' % (k, k, k, x, y, w, h, render.esc(label), x, y, w, h,
                               '\n'.join(lines), k, k))
    home = '' if root is None else (
        '  <a class="home" href="%sindex.html" aria-label="Flawlessplan: all houses" title="All houses">'
        '<img src="%s" alt="" width="26" height="26"></a>\n' % (root, icon_uri()))
    send = '' if send is None else (
        '  <a id="send" class="toggle" href="%s" download title="One file to send: every sheet, to be read and not drawn on">\n'
        '    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 15V3"/><path d="M8 7l4-4 4 4"/>'
        '<path d="M5 12v7a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-7"/></svg>\n'
        '    <span>Share</span>\n  </a>\n' % render.esc(quote(send)))
    js = {'VIEW': asset('view.js'), 'KEYS': _js(keys), 'LABELS': _js(dict(s[:2] for s in sheets)),
          'HIDDEN': _js([{'id': s.id, 'label': s.tab} for s in hidden]), 'MOVABLE': _js(movable), 'VERSION': _js(version)}
    parts = {'TITLE': render.esc(title), 'TABS': tabs, 'STAGES': '\n'.join(stages),
             'INFOS': '\n'.join(panel(s[0], s[4]) for s in sheets),
             'CSS': asset('page.css').replace('__DRAWING__', render.css(VARS, 'svg.draw')),
             'JS': _fill(asset('page.js'), js),
             'ICON': icon(root), 'FONTS': fonts(root), 'HOME': home, 'SEND': send}
    return ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '</head>\n<body>\n' + _fill(asset('page.html'), parts) + '\n</body>\n</html>\n')


def share(title, sheets):
    """One file to send: every sheet of a house (solve.Sheet) and what is
    said beside it, each drawn once and as the house file has it. It asks
    no other file or site for anything — the fonts and the icon are inside
    it — and saves nothing."""
    e = render.esc
    tabs, out = [], []
    for i, s in enumerate(sheets):
        tabs.append('    <button class="tab" role="tab" id="tab-%s" aria-controls="cv-%s" aria-selected="%s"'
                    ' tabindex="%s">%s</button>' % (s.id, s.id, 'true' if i == 0 else 'false', 0 if i == 0 else -1, e(s.tab)))
        x, y, w, h = [render.n2(v) for v in s.vb]
        out.append('<section class="sheet" id="cv-%s" role="tabpanel" aria-labelledby="tab-%s">\n'
                   '  <div class="stage">\n'
                   '    <svg id="sv-%s" class="draw" viewBox="%s %s %s %s" role="img" aria-label="%s sheet">\n'
                   '%s\n    </svg>\n  </div>\n'
                   '  <div class="infos">\n<aside class="info">\n%s\n</aside>\n  </div>\n</section>'
                   % (s.id, s.id, s.id, x, y, w, h, e(s.tab), '\n'.join(s.lines), '\n'.join(said(s.info))))
    parts = {'TITLE': e(title), 'ICON': icon(), 'TABS': '\n'.join(tabs), 'SHEETS': '\n'.join(out),
             'CSS': (fonts_inside() + asset('page.css').replace('__DRAWING__', render.css(VARS, 'svg.draw'))
                     + asset('share.css')),
             'JS': asset('share.js').replace('__VIEW__', asset('view.js')).replace('__KEYS__', _js([s.id for s in sheets]))}
    return _fill(asset('share.html'), parts)


def index(houses):
    """The page that lists the houses: for each (folder name, Solved) its
    first plan as a picture, its size, and its sheets — the ones that
    change another marked."""
    e = render.esc
    cards = []
    for name, s in houses:
        plans = [p for p in s.plans() if not p.hidden] or s.plans()     # the ones that show
        first = plans[0]
        x, y, w, h = [render.n2(v) for v in first.vb]
        levels = len(s.house['levels'])
        found = sum(1 for _, lv, _ in s.issues() if lv != 'info')
        cards.append(
            '    <li><a class="house" href="%s/index.html">\n'
            '      <div class="thumb"><svg class="draw" viewBox="%s %s %s %s" role="img" aria-label="%s">\n%s\n</svg></div>\n'
            '      <div class="body">\n        <h2>%s</h2>\n'
            '        <p class="figures">%s · %d sheet%s · %.1f m² gross</p>\n%s'
            '        <ul class="sheets">%s</ul>\n      </div>\n    </a></li>'
            % (e(quote(name)), x, y, w, h, e(first.title.title()), '\n'.join(first.lines), e(s.house['name']),
               '%d levels' % levels if levels > 1 else '1 level', len(plans), '' if len(plans) == 1 else 's',
               first.plan.gross,
               '        <p class="found">%d problem%s found</p>\n' % (found, '' if found == 1 else 's') if found else '',
               ''.join('<li%s>%s</li>' % (' class="changes"' if p.base else '', e(p.tab)) for p in plans)))
    tokens = asset('page.css').split('*{box-sizing')[0]         # the colours and faces, as the house pages have them
    count = '%d house%s' % (len(houses), '' if len(houses) == 1 else 's')
    return _fill(asset('index.html'), {'CSS': tokens + asset('index.css') + render.css(VARS, 'svg.draw'),
                                       'ICON': icon(''), 'FONTS': fonts(''), 'MARK': icon_uri(),
                                       'COUNT': count, 'HOUSES': '\n'.join(cards)})
