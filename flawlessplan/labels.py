# -*- coding: utf-8 -*-
"""Where a room's label goes: the largest layout that fits, inside the
room, off door swings, stairs, fittings and other text. Solving a sheet
places every label, so a label with nowhere to go is a problem the checks
report, not something found out when the sheet is drawn.
"""
from shapely.geometry import LineString, Point, box
from shapely.prepared import prep

# Glyph advance in metres at each label size, measured off a render. They
# keep a label inside the room it names; remeasure if a font or size changes.
CH = {'rmname': 0.333, 'rmname small': 0.251, 'rmname mini': 0.215, 'rmname tiny': 0.172,
      'rmdim': 0.180, 'rmarea': 0.168, 'rmarea sm': 0.135, 'note': 0.168, 'zonelabel': 0.301}
# `zonelabel` was measured against `rmname` in the same render (0.903 of its width) and scaled from it.
NAMES = ['rmname', 'rmname small', 'rmname mini', 'rmname tiny']


def tw(s, cls):
    return len(s)*CH[cls]


def _name_cls(name, avail, start=0):
    for cls in NAMES[start:]:
        if tw(name, cls) <= avail:
            return cls
    return None


def layouts(r, W, H):
    """Ways of setting a room's label, best first: (items, box w, box h).
    An item is (dx, dy, text, class, rot), offsets in metres from the centre."""
    name, small = r['name'], r.get('size') == 'small'
    dims = '%.2f × %.2f m' % (r['w'], r['h'])
    area = '%.1f m²' % r['area']
    if r.get('zone'):                               # not laid out yet: what it is for, and how much there is
        items = [(0, -0.36, name, 'zonelabel', None)]
        if r['sub']:
            items.append((0, 0.14, r['sub'], 'rmarea sm', None))
        items.append((0, 0.54 if r['sub'] else 0.14, area, 'rmarea sm', None))
        return [(items, max(tw(t, c) for _, _, t, c, _ in items), 1.20 if r['sub'] else 0.80)]
    note = area if r['sub'] is None else r['sub']
    plain = not r['dims']
    out = []
    flat, turned = r['rot'] is None, r['rot'] is not None or H > W
    if flat and not plain and not small:
        cls = _name_cls(name, W - 0.20)
        if cls:
            ncls = 'rmarea' if tw(note, 'rmarea') <= W - 0.20 else 'rmarea sm'
            items = [(0, -0.30, name, cls, None), (0, 0.14, dims, 'rmdim', None)]
            if note:
                items.append((0, 0.54, note, ncls, None))
            out.append((items, max(tw(name, cls), tw(dims, 'rmdim'), tw(note, ncls)), 1.20))
    if flat and not plain:
        cls = _name_cls(name, W - 0.20, 1)
        line2 = dims if r['sub'] is None else (r['sub'] or dims)
        if cls:
            out.append(([(0, -0.14, name, cls, None), (0, 0.28, line2, 'rmarea sm', None)],
                        max(tw(name, cls), tw(line2, 'rmarea sm')), 0.70))
            out.append(([(0, -0.22, name, cls, None), (0, 0.18, '%.2f ×' % r['w'], 'rmarea sm', None),
                         (0, 0.52, '%.2f m' % r['h'], 'rmarea sm', None)],
                        max(tw(name, cls), 0.80), 1.05))
    if turned and not plain:
        cls = _name_cls(name, H - 0.20, 1)
        if cls:
            out.append(([(-0.14, 0, name, cls, -90), (0.32, 0, dims, 'rmarea sm', -90)],
                        0.72, max(tw(name, cls), tw(dims, 'rmarea sm'))))
    if flat:
        cls = _name_cls(name, W - 0.20, 0 if plain and not small else 1) or 'rmname tiny'
        out.append(([(0, 0.10, name, cls, None)], tw(name, cls), 0.34))
    if turned or not out:
        cls = _name_cls(name, H - 0.20, 1) or 'rmname tiny'
        thin = cls == 'rmname tiny'                 # a cupboard: the smallest name needs less room
        out.append(([(0.07 if thin else 0.10, 0, name, cls, -90)], 0.26 if thin else 0.34, tw(name, cls)))
    return out


# where a label is tried, as steps off the middle of its room: nearest first
STEPS = sorted([(a*0.1, b*0.1) for a in range(-40, 41) for b in range(-40, 41)],
               key=lambda s: s[0]*s[0] + s[1]*s[1])


def place(r, blocked):
    """Pick a layout and a spot for it: inside the room, off the door swings.
    Returns (items, x, y, found); with nowhere clear the smallest layout
    goes in the middle and `found` is False."""
    x0, y0, x1, y1 = r['rect']
    W, H = x1 - x0, y1 - y0
    cx, cy = (x0+x1)/2.0, (y0+y1)/2.0
    if r['shape'] == 'near':                        # a chamfer or a nib: use the whole room
        bx0, by0, bx1, by1 = r['face'].bounds
        W, H = bx1 - bx0, by1 - by0
    opts = layouts(r, W, H)
    if r['dx'] or r['dy']:
        return opts[0][0], cx + r['dx'], cy + r['dy'], True
    opts = [o for o in opts if o[1] <= W - 0.16 and o[2] <= H - 0.10] or opts[-1:]
    room = prep(r['face'].buffer(-0.07))
    for items, bw, bh in opts:
        for dx, dy in STEPS:
            if abs(dx) > W/2.0 or abs(dy) > H/2.0:
                continue
            b = box(cx+dx-bw/2.0, cy+dy-bh/2.0, cx+dx+bw/2.0, cy+dy+bh/2.0)
            if room.contains(b) and not blocked.intersects(b):
                return items, cx+dx, cy+dy, True
    return opts[-1][0], cx, cy, False


def text_box(at, text, cls, rot=None):
    """The space a line of free text takes, for room labels to keep off."""
    w, h = tw(text, cls if cls in CH else 'rmarea sm'), 0.30
    if rot is not None:
        w, h = h, w
    return box(at[0]-w/2.0, at[1]-h/2.0, at[0]+w/2.0, at[1]+h/2.0)


OUT = {'west': (-1, 0), 'east': (1, 0), 'north': (0, -1), 'south': (0, 1)}


def outside(r, side, envelope, front=False):
    """A room's label set in the margin on one side of the building, level
    with the room: (items, x, y, leader). The leader is a line from the
    label to just inside the room. On the `front` side it steps out past
    the caption written there, where the two would meet."""
    dx, dy = OUT[side]
    x0, y0, x1, y1 = r['face'].bounds
    cx, cy = (x0+x1)/2.0, (y0+y1)/2.0
    ex0, ey0, ex1, ey1 = envelope.bounds
    reach = LineString([(cx, cy), (cx + dx*(ex1-ex0+1), cy + dy*(ey1-ey0+1))]).intersection(envelope)
    bx0, by0, bx1, by1 = reach.bounds                   # how far the building runs on, that way
    edge = (bx0 if dx < 0 else bx1 if dx > 0 else cx, by0 if dy < 0 else by1 if dy > 0 else cy)
    out = (ex0, ey0, ex1, ey1)[(0, 1, 2, 3)[('west', 'north', 'east', 'south').index(side)]]
    clear = 0.75 if front and abs((edge[0] if dx else edge[1]) - out) < 0.45 else 0.0   # the caption stands off the outermost face
    second = r['sub'] or ('%.1f m²' % r['area'] if r.get('zone') or not r['dims']
                          else '%.2f × %.2f m' % (r['w'], r['h']))
    name = 'zonelabel' if r.get('zone') else 'rmname small'
    rot = {'west': -90, 'east': 90}.get(side)
    near, far = 0.30 + clear, 0.62 + clear              # the second line sits nearer the building
    if side == 'south':
        near, far = 0.72 + clear, 0.40 + clear          # ... except below it, where text reads down
    items = [(dx*far, dy*far, r['name'], name, rot), (dx*near, dy*near, second, 'rmarea sm', rot)]
    face = r['face'].representative_point() if not r['face'].contains(Point(cx, cy)) else Point(cx, cy)
    inside = LineString([(cx, cy), edge]).intersection(r['face'])
    tip = (face.x, face.y) if inside.is_empty else (
        (inside.bounds[0] if dx < 0 else inside.bounds[2] if dx > 0 else cx) - dx*0.25,
        (inside.bounds[1] if dy < 0 else inside.bounds[3] if dy > 0 else cy) - dy*0.25)
    return items, edge[0], edge[1], ((edge[0] + dx*0.14, edge[1] + dy*0.14), tip)


def spread(marks, gap=0.12):
    """Labels in the same margin moved along it until none is over the
    next. Each is (side, x, y, items); they come back as (x, y), moved no
    further than they must be and still in the order of their rooms.
    Labels on faces more than a label's depth apart are not neighbours."""
    out = [(x, y) for _, x, y, _ in marks]
    for side, (dx, dy) in OUT.items():
        k = 1 if dx else 0                              # the way the margin runs: down the page, or across it
        mine = sorted((i for i, m in enumerate(marks) if m[0] == side), key=lambda i: marks[i][2 - k])
        rows, last = [], None
        for i in mine:                                  # those standing off the same face, near enough
            if last is None or marks[i][2 - k] - last > 0.8:
                rows.append([])
            rows[-1].append(i)
            last = marks[i][2 - k]
        for row in rows:
            row.sort(key=lambda i: marks[i][1 + k])
            half = dict((i, max(tw(t, cls) for _, _, t, cls, _ in marks[i][3])/2.0 + gap/2.0) for i in row)
            groups = []                                 # each: its labels, and where its first one starts
            for i in row:
                groups.append([[i], marks[i][1 + k] - half[i]])
                while len(groups) > 1 and groups[-2][1] + 2*sum(half[j] for j in groups[-2][0]) > groups[-1][1]:
                    b = groups.pop()
                    a = groups[-1]
                    a[0] += b[0]
                    at, starts = 0.0, []                # where each would start the group, were it where it wants to be
                    for j in a[0]:
                        starts.append(marks[j][1 + k] - half[j] - at)
                        at += 2*half[j]
                    a[1] = sum(starts)/len(starts)
            for members, at in groups:
                for j in members:
                    out[j] = (out[j][0], at + half[j]) if k else (at + half[j], out[j][1])
                    at += 2*half[j]
    return out
