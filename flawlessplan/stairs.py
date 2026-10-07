# -*- coding: utf-8 -*-
"""A stair is a walking line with a width.

`path` runs from the foot to the head; each leg of it is a flight, each
corner a landing or a fan of winders. Counting along the path every tread
is one riser, a landing is one, n winders are n, and the last riser lands
on the floor above.

A leg with no treads is level. It is drawn as its own piece of landing
unless the winders after it `reach` back over it, when it is part of the
lowest winder: the width of a banister between two flights is not a step.

A plan is cut at waist height, so a floor shows the stair only up to
`cut_risers` (`show: below`) and the floor above shows the rest (`show:
above`). The cut end IS the zigzag: the flight's outline is closed on it,
half a tread past a nosing so the two never coincide.
"""
import math
from shapely.geometry import Polygon
from shapely.ops import unary_union

BREAK_AMP = 0.075        # how far the zigzag swings either side of the cut


def _add(a, b, k=1.0):
    return (a[0]+b[0]*k, a[1]+b[1]*k)


def build(st):
    """Polygons, tread lines, walking line and labels for one stair."""
    P, W, turns = st['path'], st['width'], st['turns']
    legs = len(P) - 1
    reach = st.get('reach') or [False]*(legs - 1)
    back = {}                                       # corner -> level run its first winder takes in
    D, L = [], []
    for a, b in zip(P, P[1:]):
        d = (b[0]-a[0], b[1]-a[1])
        ln = math.hypot(*d)
        if ln < 1e-9:
            raise ValueError('%s: two path points coincide' % st['where'])
        D.append((d[0]/ln, d[1]/ln))
        L.append(ln)

    # units, in walking order: ('tread', leg, i, n, s, e) and ('corner', j, k)
    units, flats, spans = [], [], []
    for i in range(legs):
        s = _add(P[i], D[i], W[i-1]/2.0 if i > 0 else 0.0)
        e = _add(P[i+1], D[i], -(W[i+1]/2.0 if i < legs-1 else 0.0))
        run = math.hypot(e[0]-s[0], e[1]-s[1])
        if (e[0]-s[0])*D[i][0] + (e[1]-s[1])*D[i][1] < -1e-6:
            raise ValueError('%s: leg %d is shorter than the corners at its ends' % (st['where'], i))
        n = st['treads'][i]
        if n is None:
            n = int(round(run / st['going']))
        spans.append((s, e, n))
        if n == 0:
            if run > 1e-6:
                flats.append((i, s, e))             # a level stretch: part of the landing
        else:
            units.extend(('tread', i, k, n) for k in range(n))
        if i < legs - 1:
            units.extend(('corner', i+1, k) for k in range(max(1, turns[i])))

    cut, show = st['cut'], st['show']
    at = None                                       # unit index the cut falls in
    if cut is not None and show != 'all':
        at = int(math.floor(cut + 0.5))
        if at >= len(units):                        # cut above its head, both sheets would show the whole flight
            raise ValueError('%s.cut_risers: %g is past the top of the stair, which has %d risers'
                             % (st['where'], cut, len(units) + 1))
        while at < len(units) and units[at][0] != 'tread':
            at += 1
        if at >= len(units):
            at = None
    keep = (lambda k: True) if at is None else (
        (lambda k: k < at) if show == 'below' else (lambda k: k > at))

    polys, lines = [], []

    def quad(i, s, e):
        n = (-D[i][1]*W[i]/2.0, D[i][0]*W[i]/2.0)
        return [_add(s, n), _add(e, n), _add(e, n, -1), _add(s, n, -1)]

    def zig(i, c, teeth=2):
        """Jagged cut across leg i at c, from its left edge to its right."""
        n = (-D[i][1], D[i][0])
        m = teeth*2
        out = []
        for k in range(m+1):
            p = _add(c, n, W[i]*(0.5 - k/float(m)))
            if k not in (0, m):
                p = _add(p, D[i], BREAK_AMP if k % 2 else -BREAK_AMP)
            out.append(p)
        return out

    drawn = set(k for k in range(len(units)) if keep(k))
    cutpt = None
    for i in range(legs):
        s, e, n = spans[i]
        idx = [k for k, u in enumerate(units) if u[0] == 'tread' and u[1] == i]
        if not idx:
            continue
        step = math.hypot(e[0]-s[0], e[1]-s[1]) / float(n)
        lo = [k for k in idx if k in drawn]
        has_cut = at in idx
        if not lo and not has_cut:
            continue
        a = (min(lo) - idx[0]) if lo else (at - idx[0])
        b = (max(lo) - idx[0] + 1) if lo else (at - idx[0] + 1)
        pa, pb = _add(s, D[i], a*step), _add(s, D[i], b*step)
        if has_cut:
            c = _add(s, D[i], (at - idx[0] + 0.5)*step)
            cutpt = (i, c)
            z = zig(i, c)                           # left edge to right edge
            pa, pb = (pa, c) if show == 'below' else (c, pb)
            q = quad(i, pa, pb)
            polys.append([q[0]] + z + [q[3]] if show == 'below' else z + [q[2], q[1]])
        else:
            polys.append(quad(i, pa, pb))
        for k in range(n + 1):                      # nosings inside what is drawn
            p = _add(s, D[i], k*step)
            t = (p[0]-pa[0])*D[i][0] + (p[1]-pa[1])*D[i][1]
            if 1e-6 < t < math.hypot(pb[0]-pa[0], pb[1]-pa[1]) - 1e-6:
                q = quad(i, p, p)
                lines.append((q[0], q[3]))
    for i, s, e in flats:
        if i < legs - 1 and reach[i] and turns[i] > 1:
            back[i+1] = math.hypot(e[0]-s[0], e[1]-s[1])
            continue
        near = [k for k, u in enumerate(units) if u[0] == 'corner' and u[1] in (i, i+1)]
        if not near or any(k in drawn for k in near):
            polys.append(quad(i, s, e))
    for j in range(1, legs):
        idx = [k for k, u in enumerate(units) if u[0] == 'corner' and u[1] == j]
        if not all(k in drawn for k in idx):
            continue
        a, b = D[j-1], D[j]
        c = P[j]
        ha, hb = W[j]/2.0, W[j-1]/2.0               # half extents along a and along b
        polys.append([_add(_add(c, a, sa*ha - (back.get(j, 0.0) if sa < 0 else 0.0)), b, sb*hb)
                      for sa, sb in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
        n = turns[j-1]
        if n > 1:                                   # fan from the inside of the turn
            o = _add(_add(c, a, -ha), b, hb)
            for k in range(1, n):
                th = math.radians(90.0*k/n)
                ca, sn = math.cos(th), math.sin(th)
                t = min(2*hb/ca if ca > 1e-9 else 1e9, 2*ha/sn if sn > 1e-9 else 1e9)
                lines.append((o, _add(_add(o, b, -ca*t), a, sn*t)))

    # walking line: from the foot to the cut going up, from the head to it going down
    walk, head = [], None
    gap = BREAK_AMP + 0.03
    if cutpt is None:
        walk = list(P)
        if len(walk) >= 2:
            head = (walk[-1], D[-1])
            walk[-1] = _add(walk[-1], D[-1], -0.18)
    elif show == 'below':
        i, c = cutpt
        tip = _add(c, D[i], -gap)
        walk = list(P[:i+1]) + [_add(tip, D[i], -0.18)]
        head = (tip, D[i])
    else:
        i, c = cutpt
        tip = _add(c, D[i], gap)
        back = (-D[i][0], -D[i][1])
        walk = [_add(P[-1], D[-1], -0.30)] + list(P[i+1:-1][::-1]) + [_add(tip, back, -0.18)]
        head = (tip, back)
    if st['label'] == 'DN' or show == 'above':
        label = (_add(_add(P[-1], D[-1], -0.62), (-D[-1][1], D[-1][0]), 0.18), st['label'])
    else:
        foot = _add(P[0], D[0], -0.28)              # clear of the bottom riser
        label = ((foot[0], foot[1] + 0.08), st['label'])
    shapes = [Polygon(p) for p in polys if len(p) >= 3]
    return {'polys': polys, 'lines': lines, 'walk': walk, 'head': head, 'label': label,
            'risers': len(units) + 1,
            'block': unary_union([s.buffer(0) for s in shapes]) if shapes else None}
