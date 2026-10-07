# -*- coding: utf-8 -*-
"""One solved sheet as SVG. 100 user units = 1 metre, north up.

Nothing is worked out here: the plan, the stairs and where each label goes
come solved (solve.Sheet), and this writes them down.
"""
import math
from . import geom, fittings
from .labels import tw

U = 100.0
ZONE_IN = 0.15           # a zone's outline sits this far inside the wall faces

# An area's style, by what the area is: whether it is painted over the walls
# or under them, and the class of its label.
AREAS = {'outdoor': (False, 'outdoorlabel'),        # roofed or paved, outside the walls
         'below': (False, 'rmname small muted'),    # a lower roof or storey seen from this one
         'new': (False, 'rmname small muted'),      # floor gained, where a sheet says so by hand
         'zone': (True, 'rmname small muted'),      # a region marked out, where no one room is it
         'fitting': (True, 'rmname small muted')}   # worktops and the like: labels keep off them
# What free text may be set in, by what it is for.
TEXT = {'name': 'rmname', 'small': 'rmname small', 'mini': 'rmname mini', 'note': 'rmarea sm',
        'zone': 'zonelabel'}

STYLE = """
.floor{fill:FLOOR}
.wall{fill:INK;stroke:none;fill-rule:evenodd}
.below{fill:FIT;fill-opacity:.5;stroke:SOFT;stroke-width:5;stroke-dasharray:16 11}
.outdoor{fill:none;stroke:BLUE;stroke-width:8;stroke-dasharray:20 12}
.new{fill:BLUE;fill-opacity:.10;stroke:none}
.zone{fill:none;stroke:BLUE;stroke-width:6;stroke-dasharray:24 15}
.fitting{fill:FIT;stroke:SOFT;stroke-width:4}
.fitline{fill:none;stroke:SOFT;stroke-width:3}
.rooflight{fill:none;stroke:SOFT;stroke-width:4;stroke-dasharray:14 9}
.gone{fill:none;stroke:RED;stroke-width:5;stroke-dasharray:16 11}
.dr{stroke:INK;stroke-width:6;fill:none}
.win{stroke:INK;stroke-width:5}
.swing{fill:none;stroke:RED;stroke-width:4;stroke-dasharray:10 7}
.fold{fill:none;stroke:INK;stroke-width:6}
.stair{fill:FIT;stroke:SOFT;stroke-width:4}
.well{fill:SOFT;fill-opacity:.3;stroke:none}
.rail{fill:none;stroke:INK;stroke-width:5;stroke-linejoin:miter}
.edge{fill:none;stroke:SOFT;stroke-width:4}
.stairline{stroke:SOFT;stroke-width:3}
.arrow{fill:none;stroke:SOFT;stroke-width:5}
.arrowhead{fill:SOFT}
.compass{fill:none;stroke:SOFT;stroke-width:4}
.northarrow{fill:INK}
.dimline{stroke:SOFT;stroke-width:2}
.leader{stroke:BLUE;stroke-width:3}
.grid{stroke:GRID;stroke-width:1.4}
.grid5{stroke:GRID;stroke-width:3}
.env{fill:none;stroke:INK;stroke-width:7}
text{font-family:Archivo,Helvetica,sans-serif;fill:INK}
.rmname{font-size:38px;font-weight:600;letter-spacing:2px}
.rmname.small{font-size:28px}
.rmname.mini{font-size:24px}
.rmname.tiny{font-size:20px;letter-spacing:1px}
.rmname.muted{fill:SOFT}
.rmdim{font-family:monospace;font-size:30px}
.rmarea{font-family:monospace;font-size:28px;fill:SOFT}
.rmarea.sm{font-size:22px}
.zonelabel{font-size:34px;font-weight:700;letter-spacing:2px;fill:BLUE}
.outdoorlabel{font-family:monospace;font-size:30px;font-weight:600;fill:BLUE}
.front{font-size:30px;font-weight:600;letter-spacing:2.5px;fill:BLUE}
.note{font-family:monospace;font-size:28px;fill:SOFT}
.dimtext{font-family:monospace;font-size:26px;fill:SOFT}
.dimtext.soft{fill:RED}
.dimtext.calc{fill:BLUE}
.sheetname{font-size:30px;font-weight:700;letter-spacing:2px}
.caption{font-family:monospace;font-size:23px;fill:SOFT}
.figure{font-family:monospace;font-size:30px;font-weight:600}
"""
TOKENS = ('INK', 'SOFT', 'FLOOR', 'FIT', 'RED', 'BLUE', 'GRID')
HEX = {'INK': '#131A18', 'SOFT': '#5C6D67', 'FLOOR': '#E3E9E6', 'FIT': '#DCE4E0',
       'RED': '#A6402F', 'BLUE': '#276A80', 'GRID': '#C2CDC7'}


def css(colours=HEX, prefix=''):
    """The drawing styles: fixed colours for a standalone sheet, or the
    page's own variables — `prefix` scopes every rule to the page's sheets."""
    out = STYLE
    for t in TOKENS:
        out = out.replace(t, colours[t])
    if prefix:
        out = '\n'.join(prefix + ' ' + ln if ln.strip() else ln for ln in out.split('\n'))
    return out


CSS = css()


def esc(t):
    return (str(t).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;').replace("'", '&#39;'))        # text goes into attributes too


def n2(v):
    return ('%.2f' % v).rstrip('0').rstrip('.') if v else '0'


def path(pts, close=True):
    return 'M ' + ' L '.join('%s %s' % (n2(x*U), n2(y*U)) for x, y in pts) + (' Z' if close else '')


def geom_path(g):
    out = []
    for p in geom._polys(g):
        out.append(path(list(p.exterior.coords)[:-1]))
        out.extend(path(list(r.coords)[:-1]) for r in p.interiors)
    return ' '.join(out)


class Canvas(object):
    """The lines of a drawing, in the order they are painted."""

    def __init__(self):
        self.buf = []

    def out(self, s):
        self.buf.append(s)

    def line(self, a, b, cls):
        self.out('<line x1="%s" y1="%s" x2="%s" y2="%s" class="%s"/>'
                 % (n2(a[0]*U), n2(a[1]*U), n2(b[0]*U), n2(b[1]*U), cls))

    def text(self, p, s, cls, anchor='middle', rot=None):
        x, y = n2(p[0]*U), n2(p[1]*U)
        tr = ' transform="rotate(%s %s %s)"' % (n2(float(rot)), x, y) if rot is not None else ''
        self.out('<text x="%s" y="%s" class="%s" text-anchor="%s"%s>%s</text>'
                 % (x, y, cls, anchor, tr, esc(s)))


def draw(sheet):
    """One sheet: the lines of its drawing, and the viewBox round them."""
    plan, house = sheet.plan, sheet.house
    fl, sh = plan.spec, Canvas()

    sh.out('<path d="%s" class="floor"/>' % geom_path(plan.E))
    for a in fl['areas']:
        if not AREAS[a['style']][0]:
            sh.out('<path d="%s" class="%s"/>' % (path(a['pts']), a['style']))
    if sheet.gained is not None:
        sh.out('<path d="%s" class="new"/>' % geom_path(sheet.gained))
    for g in fl['gone']:
        sh.out('<path d="%s" class="gone"/>' % path(g, close=False))
    if sheet.demolition is not None:
        sh.out('<path d="%s" class="gone"/>' % geom_path(sheet.demolition))
    sh.out('<path d="%s" class="wall"/>' % geom_path(plan.walls))
    for h in plan.env_hosts:
        if h.open:                                  # where the floor ends and no wall stands
            run(sh, h.run(0.0, h.L), 'edge')
    for a in fl['areas']:
        if AREAS[a['style']][0]:
            sh.out('<path d="%s" class="%s"/>' % (path(a['pts']), a['style']))
    for f in sorted(plan.fittings, key=lambda f: (fittings.ORDER + (f['kind'],)).index(f['kind'])):
        at = lambda p: geom._add(geom._add(f['o'], f['u'], p[0]), f['n'], p[1])
        for part in fittings.symbol(f['kind'], f['w'], f['d'], f['label']):
            if part[0] == 'text':
                sh.text(geom._add(at(part[1]), (0, 0.07)), part[2], 'rmarea sm')
            else:
                sh.out('<path d="%s" class="%s"/>' % (path([at(p) for p in part[1]], close=part[0] == 'fill' or part[2]),
                                                     'fitting' if part[0] == 'fill' else 'fitline'))
    for z in plan.zones:                            # each one's outline, a little inside the wall faces
        sh.out('<path d="%s" class="zone"/>' % geom_path(z['face'].buffer(-ZONE_IN, join_style=2)))

    for g in sheet.stairs:
        if g['void'] is not None:                   # the well the rest of the flight is in: not floor
            sh.out('<path d="%s" class="well"/>' % geom_path(g['void']))
        for p in g['polys']:
            sh.out('<path d="%s" class="stair"/>' % path(p))
        for a, b in g['lines']:
            sh.line(a, b, 'stairline')
        if len(g['walk']) >= 2:
            sh.out('<path d="%s" class="arrow"/>' % path(g['walk'], close=False))
        if g['head']:
            (tx, ty), (dx, dy) = g['head']
            base = (tx - dx*0.18, ty - dy*0.18)
            pts = [(tx, ty), (base[0] - dy*0.09, base[1] + dx*0.09),
                   (base[0] + dy*0.09, base[1] - dx*0.09)]
            sh.out('<path d="%s" class="arrowhead"/>' % path(pts))
        if g['label'][1]:
            sh.text(g['label'][0], g['label'][1], 'rmarea sm')
        for pts in g['rail']:                       # the balustrade, over the stair's own edge
            sh.out('<path d="%s" class="rail"/>' % path(pts, close=False))

    for o in plan.openings:
        h = o['host']
        if o['style'] == 'window':
            for off in (-h.t/2.0, 0.0, h.t/2.0):    # two reveals and the glass
                run(sh, h.run(o['s0'], o['s1'], off), 'win')
        elif o['style'] == 'frame':
            # A frame beside a door is in the door's plane, on the face the
            # leaf is hung on (`face:` on the door, else the one it opens
            # to); on the centreline the two do not meet and the door reads
            # as hanging in a gap.
            off = 0.0
            for d in plan.openings:
                if d['host'] is h and d.get('leaves') and (
                        abs(d['s0'] - o['s1']) < 0.01 or abs(d['s1'] - o['s0']) < 0.01):
                    u = d['frame'][0]
                    off = geom._dot(d['hung'], (-u[1], u[0]))*h.t/2.0
            run(sh, h.run(o['s0'], o['s1'], off), 'dr')
        elif o['style'] == 'slide':
            mid = (o['s0'] + o['s1'])/2.0
            run(sh, h.run(o['s0'], mid + 0.05, h.t/2.0 + 0.04), 'dr')
            run(sh, h.run(mid - 0.05, o['s1'], h.t/2.0 + 0.10), 'dr')
        elif o['style'] == 'fold':
            u, inward = o['frame']
            n, side = 4, (1.0 if inward is None else
                          (1.0 if geom._dot(inward, (-u[1], u[0])) > 0 else -1.0))
            pts = [h.at(o['s0'] + (o['s1']-o['s0'])*i/float(n),
                        side*(-h.t/2.0 + (0.22 if i % 2 else 0.0))) for i in range(n+1)]
            sh.out('<path d="%s" class="fold"/>' % path(pts, close=False))
        for hinge, shut, side, w in o.get('leaves', []):
            tip, sweep, _ = geom.leaf_shape(hinge, shut, side, w)
            sh.line(hinge, tip, 'dr')
            sh.out('<path d="M %s %s A %s %s 0 0 %d %s %s" class="swing"/>'
                   % (n2((hinge[0]+w*shut[0])*U), n2((hinge[1]+w*shut[1])*U),
                      n2(w*U), n2(w*U), sweep, n2(tip[0]*U), n2(tip[1]*U)))

    for r in plan.rooflights:                       # overhead, so dashed and over everything on the floor: its outline, and a cross corner to corner
        a, b, c, d = r['pts']
        sh.out('<path d="%s" class="rooflight"/>' % path(r['pts']))
        sh.out('<path d="%s %s" class="rooflight"/>' % (path([a, c], close=False), path([b, d], close=False)))
        if r['label']:
            sh.text(rooflight_label(r), r['label'], TEXT['note'])
    for lb in fl['labels']:
        sh.text(lb['at'], lb['text'], TEXT[lb['style']], rot=lb['rot'])
    for a in fl['areas']:
        xs, ys = [p[0] for p in a['pts']], [p[1] for p in a['pts']]
        cx, cy = (min(xs)+max(xs))/2.0, (min(ys)+max(ys))/2.0
        cls = AREAS[a['style']][1]
        if a['label'] and a['rot'] is not None:
            sh.text((cx - (0.12 if a['sub'] else 0), cy), a['label'],
                    cls, rot=a['rot'])
            if a['sub']:
                sh.text((cx + 0.30, cy), a['sub'], 'rmarea sm', rot=a['rot'])
        elif a['label']:
            sh.text((cx, cy - 0.20), a['label'], cls)
            if a['sub']:
                sh.text((cx, cy + 0.28), a['sub'], 'rmarea sm')

    for a, b in sheet.leaders:
        sh.line(a, b, 'leader')
    for items, cx, cy in sheet.labels:
        for dx, dy, s, cls, rot in items:
            sh.text((cx+dx, cy+dy), s, cls, rot=rot)

    for d in fl['dims']:
        dim(sh, d['a'], d['b'], d['text'], d['style'])

    # ---- the sheet round the plan
    beyond = [p for a in fl['areas'] for p in a['pts']] + [p for g in sheet.stairs for q in g['polys'] for p in q]
    xs = [p[0] for p in fl['envelope']['pts'] + beyond]         # a flight may run off the floor's open edge
    ys = [p[1] for p in fl['envelope']['pts'] + beyond]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    dx0 = min([x0] + [min(d['a'][0], d['b'][0]) for d in fl['dims']])
    dx1 = max([x1] + [max(d['a'][0], d['b'][0]) for d in fl['dims']])
    dy1 = max([y1] + [max(d['a'][1], d['b'][1]) for d in fl['dims']])
    north = x1 + 0.58                               # the compass, top right, clear of the building
    if plan.E.intersects(geom.Point(north, y0 + 0.95).buffer(0.80)):
        north = x1 + 1.05
    cx, cy = north*U, (y0 + 0.95)*U
    sh.out('<circle cx="%s" cy="%s" r="72" class="compass"/>' % (n2(cx), n2(cy)))
    sh.out('<path d="M %s %s l -22 92 l 22 -20 l 22 20 Z" class="northarrow"/>' % (n2(cx), n2(cy-58)))
    sh.text((north, y0 + 2.03), 'N', 'rmname small')
    front, drop = house.get('front'), 0.0
    if front:
        word = 'FRONT (%s)' % front.upper()
        if house.get('front_note'):
            word += ' — ' + house['front_note']
        if front == 'west':
            sh.text((x0 - 0.70, (y0+y1)/2.0), word, 'front', rot=-90)
        elif front == 'east':
            sh.text((x1 + 0.70, (y0+y1)/2.0 + 1.5), word, 'front', rot=90)
        elif front == 'north':
            sh.text(((x0+x1)/2.0, y0 - 0.55), word, 'front')
        else:
            sh.text(((x0+x1)/2.0, y1 + 0.75), word, 'front')
            drop = 0.60
    # the one line that is drawn: what the sheet is. Everything else said
    # about it is in report.info(), beside the drawing and not in it.
    title = '%s · %.1f m² gross' % (fl['title'], plan.gross)
    sh.text((x0, dy1 + 0.85 + drop), title, 'note', anchor='start')

    left = 2.6 if front == 'west' else 1.2
    vx, vy = min(x0 - left, dx0 - 0.5), y0 - 1.7
    vw = max(max(north + 1.42, dx1 + 0.5) - vx, tw(title, 'note') + (x0 - vx) + 0.4)
    vh = (dy1 - y0) + 1.7 + 0.85 + drop + 0.80
    return sh.buf, (vx*U, vy*U, vw*U, vh*U)


def rooflight_label(r):
    """Where a rooflight's label is written: under it, clear of its cross."""
    return (r['at'][0], max(p[1] for p in r['pts']) + 0.28)


def run(sh, pts, cls):
    """A line along a wall: one stroke where the wall is straight."""
    if len(pts) == 2:
        sh.line(pts[0], pts[1], cls)
    else:
        sh.out('<path d="%s" class="%s" fill="none"/>' % (path(pts, close=False), cls))


def dim(sh, a, b, label, style=''):
    """A dimension line with a tick at each end and its figure alongside."""
    d = (b[0]-a[0], b[1]-a[1])
    L = math.hypot(*d) or 1.0
    n = (-d[1]/L*0.13, d[0]/L*0.13)
    sh.line(a, b, 'dimline')
    for p in (a, b):
        sh.line((p[0]-n[0], p[1]-n[1]), (p[0]+n[0], p[1]+n[1]), 'dimline')
    cls = ('dimtext ' + style).strip()
    mid = ((a[0]+b[0])/2.0, (a[1]+b[1])/2.0)
    if abs(d[1]) > abs(d[0]):
        sh.text(mid, label, cls, rot=-90)
    else:
        sh.text((mid[0], mid[1] - 0.18), label, cls)


def standalone(lines, vb, scale=1.5):
    """Wrap a drawing as an SVG file with its own styles."""
    x, y, w, h = [n2(v) for v in vb]
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="%s %s %s %s" width="%d" height="%d">'
            '<style>%s</style><rect x="%s" y="%s" width="%s" height="%s" fill="#F8FAF9"/>\n%s\n</svg>'
            % (x, y, w, h, round(vb[2]/scale), round(vb[3]/scale), CSS, x, y, w, h, '\n'.join(lines)))
