# -*- coding: utf-8 -*-
"""The geometry of one sheet: walls as real polygons, rooms as what is left.

The envelope is given by its outer faces and each external wall is drawn
inward from there, so the outside dimensions stay true. Partitions sit on
their centrelines. Every opening is cut out of the one wall it sits in and
no wider, and a room is whichever face of the plan its seed point falls in
— its clear size and area are measured, never written down.
"""
import math
import warnings
import numpy as np
import shapely
from shapely.affinity import rotate
from shapely.geometry import Polygon, Point, LineString, box
from shapely.ops import unary_union
from shapely.prepared import prep
from .fittings import KINDS

TOL = 0.002              # 2 mm: near enough to be the same point
NEAR = 0.05              # a room within 50 mm of the size it was given has that size
AREA_NEAR = 0.5          # m²
OPEN = 60.0              # leaves are drawn 60 degrees open
COMPASS = {'n': (0.0, -1.0), 's': (0.0, 1.0), 'e': (1.0, 0.0), 'w': (-1.0, 0.0)}


def _sub(a, b):
    return (a[0]-b[0], a[1]-b[1])


def _add(a, b, k=1.0):
    return (a[0]+b[0]*k, a[1]+b[1]*k)


def _dot(a, b):
    return a[0]*b[0] + a[1]*b[1]


def _cross(a, b):
    return a[0]*b[1] - a[1]*b[0]


def _unit(a, b):
    d = _sub(b, a)
    L = math.hypot(d[0], d[1])
    if L < 1e-9:
        raise ValueError('zero-length run at (%.3f, %.3f)' % a)
    return (d[0]/L, d[1]/L), L


def _polys(g):
    """Every polygon in a geometry, whatever shapely has wrapped it in."""
    if g is None or g.is_empty:
        return []
    if g.geom_type == 'Polygon':
        return [g]
    return [p for x in getattr(g, 'geoms', []) for p in _polys(x)]


def key(r):
    """What a room or zone is called in a note: its id, or its name, as a name."""
    return ''.join(c if c.isalnum() else '_' for c in str(r['id'] or r['name'])).strip('_')


def signed_area(pts):
    return sum(a[0]*b[1] - b[0]*a[1] for a, b in zip(pts, pts[1:] + pts[:1])) / 2.0


def inner_ring(pts, ts):
    """Inner faces of the external walls: each edge moved in by its own
    thickness, and neighbours joined where the moved lines cross."""
    s = 1.0 if signed_area(pts) > 0 else -1.0
    n = len(pts)
    dirs = [_unit(pts[i], pts[(i+1) % n])[0] for i in range(n)]
    norms = [(-d[1]*s, d[0]*s) for d in dirs]
    out = []
    for i in range(n):
        k = (i-1) % n
        p1, d1 = _add(pts[i], norms[k], ts[k]), dirs[k]
        p2, d2 = _add(pts[i], norms[i], ts[i]), dirs[i]
        c = _cross(d1, d2)
        if abs(c) < 1e-9:                       # runs straight on: a step in thickness
            out.append(p1)
            if math.hypot(p2[0]-p1[0], p2[1]-p1[1]) > 1e-9:
                out.append(p2)
        else:
            out.append(_add(p1, d1, _cross(_sub(p2, p1), d2)/c))
    return out, norms


def strip(a, b, t, ea=0.0, eb=0.0):
    """A wall body: the run a-b on its centreline, t thick, run on at each end."""
    u, _ = _unit(a, b)
    n = (-u[1]*t/2.0, u[0]*t/2.0)
    a, b = _add(a, u, -ea), _add(b, u, eb)
    return Polygon([_add(a, n), _add(b, n), _add(b, n, -1), _add(a, n, -1)])


FACET = 5.0              # degrees of arc drawn as one straight piece


def arc(a, b, via):
    """The arc from a to b through `via`, as points — both ends and enough
    between that no piece turns more than FACET degrees — and its radius."""
    (ax, ay), (bx, by), (cx, cy) = a, b, via
    d = 2.0*(ax*(by-cy) + bx*(cy-ay) + cx*(ay-by))
    if abs(d) < 1e-9:
        raise ValueError('an arc from (%.2f, %.2f) to (%.2f, %.2f) cannot run straight through (%.2f, %.2f)'
                         % (ax, ay, bx, by, cx, cy))
    ox = ((ax*ax+ay*ay)*(by-cy) + (bx*bx+by*by)*(cy-ay) + (cx*cx+cy*cy)*(ay-by)) / d
    oy = ((ax*ax+ay*ay)*(cx-bx) + (bx*bx+by*by)*(ax-cx) + (cx*cx+cy*cy)*(bx-ax)) / d
    r = math.hypot(ax-ox, ay-oy)
    at = lambda p: math.atan2(p[1]-oy, p[0]-ox)
    full = 2*math.pi
    sweep = (at(b) - at(a)) % full
    if (at(via) - at(a)) % full > sweep:            # the other way round passes through it
        sweep -= full
    n = max(2, int(math.ceil(abs(math.degrees(sweep)) / FACET)))
    mid = [(ox + r*math.cos(at(a) + sweep*i/n), oy + r*math.sin(at(a) + sweep*i/n)) for i in range(1, n)]
    return [a] + mid + [b], r


class Host(object):
    """Something an opening can sit in: a partition or one external wall.
    Its line is a run of points — two for a straight wall, more for a
    curved one — and a place in it is a distance along that line."""

    def __init__(self, hid, pts, t, inward=None, face=None, arc=None):
        self.id, self.pts, self.t = hid, list(pts), t           # pts is the centreline
        self.a, self.b = self.pts[0], self.pts[-1]
        self.name = hid
        self.segs, s = [], 0.0                                  # (where it starts, its start, direction, length)
        for p, q in zip(self.pts, self.pts[1:]):
            u, L = _unit(p, q)
            self.segs.append((s, p, u, L))
            s += L
        self.L = s
        self.u = _unit(self.a, self.b)[0]                       # end to end
        self.arc = arc                                          # {'r': radius, 'rise': how far it stands off its chord}
        # external walls only: which way is in — `inward` is that of its first piece
        self.turn = None if inward is None else (1.0 if _dot(inward, self._left(self.segs[0][2])) > 0 else -1.0)
        self.inward = inward if inward is None or len(self.pts) == 2 else self.frame(0.0, self.L)[1]
        self.face = face or (self.a, self.b)                    # the measured line
        self.cuts = []                                          # (s0, s1, where)

    @staticmethod
    def _left(u):
        return (u[1], -u[0])

    def _seg(self, s):
        for k, (s0, p, u, L) in enumerate(self.segs):
            if s <= s0 + L or k == len(self.segs) - 1:
                return s0, p, u, L

    def project(self, p):
        """How far along the wall a point is, and how far off it."""
        best, last = None, len(self.segs) - 1
        for k, (s0, a, u, L) in enumerate(self.segs):
            s = _dot(_sub(p, a), u)
            if k > 0:
                s = max(s, 0.0)
            if k < last:
                s = min(s, L)
            q = _add(a, u, s)
            d = math.hypot(p[0]-q[0], p[1]-q[1])
            if best is None or d < best[1] - 1e-12:
                best = (s0 + s, d)
        return best

    def at(self, s, off=0.0):
        s0, p, u, _ = self._seg(s)
        return _add(_add(p, u, s - s0), (-u[1], u[0]), off)

    def run(self, s0, s1, off=0.0):
        """The wall's line from s0 to s1, `off` to one side of it."""
        out = [self.at(s0, off)]
        for (_, _, u, _), (s, p, v, _) in zip(self.segs, self.segs[1:]):
            if s0 + TOL < s < s1 - TOL:
                n = (-(u[1]+v[1]), u[0]+v[0])
                out.append(_add(p, n, off / (1.0 + _dot(u, v))))
        return out + [self.at(s1, off)]

    def frame(self, s0, s1):
        """Along the wall and into the building, for the stretch s0 to s1."""
        if len(self.pts) == 2:
            return self.u, self.inward
        u = _unit(self.at(s0), self.at(s1))[0]
        return u, None if self.turn is None else _add((0.0, 0.0), self._left(u), self.turn)

    def hole(self, s0, s1):
        """What an opening from s0 to s1 takes out of the wall."""
        if len(self.pts) == 2:
            return strip(self.at(s0), self.at(s1), self.t + 2*TOL)
        return LineString(self.run(s0, s1)).buffer(self.t/2.0 + TOL, cap_style=2, join_style=2)


class Plan(object):
    def __init__(self, spec, house):
        self.spec, self.house = spec, house       # spec: the sheet as the house file gives it
        self.issues = []            # (level, message)
        self._envelope()
        self._walls()
        self._openings()
        self._faces()
        self._fittings()
        self._rooflights()
        for r in spec['require']:
            try:
                ok = house['scope'].truth(r['that'])
            except Exception as e:
                raise ValueError('sheet %s: require: %s' % (spec['id'], e))
            if not ok:
                self.warn(house['scope'].text(r.get('message', r['that'])), 'error')

    def warn(self, msg, level='warn'):
        self.issues.append((level, msg))

    # ---- external walls
    def _envelope(self):
        e = self.spec['envelope']
        pts, ts = e['pts'], e['t']
        self.E = Polygon(pts)
        if not self.E.is_valid:
            raise ValueError('sheet %s: the envelope crosses itself' % self.spec['id'])
        ring, norms = inner_ring(pts, ts)
        inner = Polygon(ring)
        if not inner.is_valid:
            inner = inner.buffer(0)
        self.I = inner.intersection(self.E)
        # inside faces that have passed each other still make a shape: one way round it is inside out, both
        # ways it is nearer the outside than the thinnest wall is thick
        if signed_area(ring)*signed_area(pts) <= 0 or not self.E.buffer(TOL - min(ts)).buffer(2*TOL).contains(self.I):
            raise ValueError('sheet %s: the outside walls are thicker than the building is across' % self.spec['id'])
        self.ext = self.E.difference(self.I)
        self.hosts = {}
        n = len(pts)
        self.env_hosts = []
        # a wall as written is one host, however many pieces a curve is drawn in
        for j, (i, count, name, curve) in enumerate(e['runs']):
            a, b, t = pts[i], pts[(i+count) % n], ts[i]
            mid = [_add(a, norms[i], t/2.0)]
            for k in range(i+1, i+count):
                both = _add(norms[k-1], norms[k])
                mid.append(_add(pts[k], both, (t/2.0) / (1.0 + _dot(norms[k-1], norms[k]))))
            mid.append(_add(b, norms[i+count-1], t/2.0))
            h = Host('env.%d' % j, mid, t, inward=norms[i], face=(a, b), arc=curve)
            h.open = e['open'][j]                   # the floor's edge, and no wall
            self.hosts[h.id] = h
            if name:
                h.name = str(name)                  # what the house file calls it
                self.hosts[h.name] = h
            self.env_hosts.append(h)
        if all(h.open for h in self.env_hosts):
            self.warn('no edge of the envelope is a wall: every one is `open: true`')

    # ---- partitions
    def _bodies_at(self, p, skip):
        """(direction, thickness) of every other partition leaving this point."""
        out = []
        for k, w in enumerate(self.spec['walls']):
            if k == skip:
                continue
            legs = [_unit(a, b) for a, b in zip(w['pts'], w['pts'][1:])]
            for i, (a, (u, L)) in enumerate(zip(w['pts'], legs)):
                s = _dot(_sub(p, a), u)
                if s < -TOL or s > L + TOL:
                    continue
                q = _add(a, u, s)
                if math.hypot(p[0]-q[0], p[1]-q[1]) > TOL:
                    continue
                if s < TOL and i > 0:
                    continue                        # where two pieces of a curve join: the piece before says so
                if s > L - TOL and i < len(legs) - 1:
                    v = legs[i+1][0]                # a curve passing through, as one line
                    u = _unit((0.0, 0.0), _add(u, v))[0]
                    out += [((-u[0], -u[1]), w['t']), (u, w['t'])]
                    break
                if s > TOL:
                    out.append(((-u[0], -u[1]), w['t']))
                if s < L - TOL:
                    out.append((u, w['t']))
        return out

    def _run_on(self, body, t, p, k):
        """How far a wall end must run past its meeting point.

        Nothing where it carries straight on or dies into a wall passing
        through. At a corner, far enough for the
        two outer faces to meet: half the other wall's thickness when they
        are square, much less off a chamfer."""
        if not self._clear_inside.contains(Point(p)):
            # on the inside face of an outside wall it runs on into it, so an
            # end cut square leaves no gap against a face that is not square
            # to it; what runs on is taken off with the rest outside
            return t if self.I.exterior.distance(Point(p)) <= TOL else 0.0
        ds = self._bodies_at(p, k)
        for d, _ in ds:
            if _dot(body, d) < -1 + 1e-6:
                return 0.0
        for i, (d, _) in enumerate(ds):
            for e, _ in ds[i+1:]:
                if _dot(d, e) < -1 + 1e-6:
                    return 0.0
        ext = 0.0
        for d, to in ds:
            th = math.acos(max(-1.0, min(1.0, _dot(body, d))))
            ext = max(ext, (to/2.0)*math.tan((math.pi - th)/2.0))
        return min(ext, 1.5*t)

    def _walls(self):
        self._clear_inside = prep(self.I.buffer(-TOL))
        self.bodies = []
        for k, w in enumerate(self.spec['walls']):
            pts = w['pts']
            try:
                u, v = _unit(pts[0], pts[1])[0], _unit(pts[-2], pts[-1])[0]
                _unit(w['a'], w['b'])
            except ValueError as e:
                raise ValueError('wall %s: %s' % (w['id'], e))
            ea = eb = 0.0
            if not w['butt']:
                ea = self._run_on(u, w['t'], w['a'], k)
                eb = self._run_on((-v[0], -v[1]), w['t'], w['b'], k)
            if len(pts) == 2:
                self.bodies.append(strip(w['a'], w['b'], w['t'], ea, eb))
            else:
                line = [_add(pts[0], u, -ea)] + pts[1:-1] + [_add(pts[-1], v, eb)]
                self.bodies.append(LineString(line).buffer(w['t']/2.0, cap_style=2, join_style=2))
            if w['id'] in self.hosts:
                raise ValueError('sheet %s: two walls called %r' % (self.spec['id'], w['id']))
            self.hosts[w['id']] = Host(w['id'], pts, w['t'], arc=w.get('arc'))
            if not self.E.buffer(TOL).contains(LineString(pts)):
                self.warn('wall %s runs outside the envelope' % w['id'])
        self.solids = [Polygon(p) for p in self.spec['solids']]
        for i, g in enumerate(self.solids):
            if not g.is_valid:
                raise ValueError('solids[%d]: its outline crosses itself' % i)

    # ---- openings
    def _find_host(self, o):
        if o['wall'] is not None:
            h = self.hosts.get(str(o['wall']))
            if h is not None:
                return h
            legs = self._legs(str(o['wall']))       # a wall written as a path: its legs are name.0, name.1 ...
            if not legs:
                raise ValueError('%s: no wall called %r' % (o['where'], o['wall']))
            if o['at'][0] != 'point':
                raise ValueError('%s: wall %s is a path of %d legs — name one (%s.0 to %s.%d), or give at: a point'
                                 % (o['where'], o['wall'], len(legs), o['wall'], o['wall'], len(legs) - 1))
            return min(legs, key=lambda h: self._off(h, o['at'][1]))
        best = None
        seen = set()
        for h in self.hosts.values():
            if id(h) in seen:
                continue
            seen.add(id(h))
            s, d = h.project(o['at'][1])
            if -TOL <= s <= h.L + TOL and d <= h.t/2.0 + 0.05:
                key = (d, 0 if h.inward is None else 1)
                if best is None or key < best[0]:
                    best = (key, h)
        if best is None:
            raise ValueError('%s: no wall at (%.2f, %.2f)' % ((o['where'],) + o['at'][1]))
        return best[1]

    def _legs(self, name):
        out = []
        while '%s.%d' % (name, len(out)) in self.hosts:
            out.append(self.hosts['%s.%d' % (name, len(out))])
        return out

    @staticmethod
    def _off(h, p):
        """How far a point is from a wall's own run."""
        s, d = h.project(p)
        return math.hypot(d, max(0.0, -s, s - h.L))

    def _side(self, frame, word, default):
        """Which way across the wall: a compass point, left/right of the
        wall's own direction, or in/out of the building. `frame` is the
        wall's direction and its way in, where the opening is."""
        u, inward = frame
        left = (u[1], -u[0])
        word = (word or default).lower()
        if word in ('left', 'right'):
            return left if word == 'left' else (-left[0], -left[1])
        if word in ('in', 'out'):
            if inward is None:
                return left
            return inward if word == 'in' else (-inward[0], -inward[1])
        if word in COMPASS:
            return left if _dot(left, COMPASS[word]) >= 0 else (-left[0], -left[1])
        raise ValueError('swing: use n/s/e/w, left/right or in/out, not %r' % word)

    def _openings(self):
        self.openings = []
        for o in self.spec['openings']:
            h = self._find_host(o)
            w = o['width']
            kind, val = o['at']
            if kind == 'centre':
                c = h.L/2.0
            elif kind == 'point':
                c = h.project(val)[0]
            elif kind == 'from_start':
                c = val + w/2.0
            else:
                c = h.L - val - w/2.0
            s0, s1 = c - w/2.0, c + w/2.0
            if getattr(h, 'open', False):
                self.warn('%s: %s is the floor\'s open edge — no wall is there to put an opening in'
                          % (o['where'], h.name), 'error')
            if s0 < -TOL or s1 > h.L + TOL:
                self.warn('%s: opening runs off the end of wall %s' % (o['where'], h.id), 'error')
            for a, b, other in h.cuts:
                if s0 < b - TOL and a < s1 - TOL:
                    self.warn('%s: shares a stretch of wall %s with %s' % (o['where'], h.id, other), 'error')
            h.cuts.append((s0, s1, o['where']))
            r = dict(o, host=h, s0=s0, s1=s1, centre=h.at(c),
                     hole=h.hole(s0, s1), frame=h.frame(s0, s1))
            if o['style'] == 'swing':
                r['leaves'] = self._leaves(h, r, s0, s1)
            self.openings.append(r)

    def _leaves(self, h, o, s0, s1):
        u = o['frame'][0]                           # a leaf is straight: in a curved wall it shuts across its opening
        n = self._side(o['frame'], o['swing'], 'in' if h.inward is not None else 'left')
        f = self._side(o['frame'], o['face'], None) if o.get('face') else n
        o['hung'] = f
        hinge = o['hinge'].lower()
        if hinge in COMPASS:
            far = _dot(u, COMPASS[hinge]) > 0
        elif hinge in ('start', 'end'):
            far = hinge == 'end'
        else:
            raise ValueError('%s.hinge: use start/end or n/s/e/w' % o['where'])
        j0, j1 = h.at(s0), h.at(s1)                 # the jambs, on the centreline
        off = (f[0]*h.t/2.0, f[1]*h.t/2.0)          # hung on the face it opens to, unless told
        j0, j1 = _add(j0, off), _add(j1, off)
        w = s1 - s0 if len(h.pts) == 2 else math.hypot(j1[0]-j0[0], j1[1]-j0[1])
        back = (-u[0], -u[1])
        if o['pair']:
            return [(j0, u, n, w/2.0), (j1, back, n, w/2.0)]
        return [(j1, back, n, w)] if far else [(j0, u, n, w)]

    # ---- what is built in
    def _fittings(self):
        """Stand each fitting where the house file says: its back against
        a wall, on the face it names, or at a point facing a compass
        point. What comes out is its back's middle `o`, the way along its
        back `u`, the way out from it `n`, and the floor it covers."""
        self.fittings = []
        for f in self.spec['fittings']:
            w, d = [given or usual for given, usual in zip((f['width'], f['depth']), KINDS[f['kind']])]
            kind, val = f['at']
            end = COMPASS[f['corner'][0]] if f['corner'] else None
            h = None
            if f['wall'] is not None:
                h = self._find_host(f)
                if kind != 'point':
                    # from the corner of the room, not the end of the wall's own line inside another wall
                    side = self._side(h.frame(0.0, h.L), f['side'], 'in') if (h.inward is not None or f['side']) else None
                    lo, hi = self._clear(h, side) if side else (0.0, h.L)
                    c = {'centre': (lo + hi)/2.0, 'from_start': lo + (val or 0.0) + w/2.0}.get(kind, hi - (val or 0.0) - w/2.0)
                else:
                    c = h.project(val)[0]
                    if end:                         # the point is the end of its back that way along the wall
                        along = _dot(h.frame(c, c + 0.01)[0], end)
                        if abs(along) < 1e-6:
                            raise ValueError('%s.corner: wall %s does not run that way' % (f['where'], h.name))
                        c += -w/2.0 if along > 0 else w/2.0
                frame = h.frame(c - w/2.0, c + w/2.0)
                if frame[1] is None and not f['side']:
                    raise ValueError('%s: say which `side:` of wall %s it stands on' % (f['where'], h.name))
                u, n = frame[0], self._side(frame, f['side'], 'in')
                o = _add(h.at(c), n, h.t/2.0)
            else:
                n = COMPASS[f['facing'][0]]
                u, o = (-n[1], n[0]), val
                if end:
                    along = _dot(u, end)
                    if abs(along) < 1e-6:
                        raise ValueError('%s.corner: its back does not run that way' % f['where'])
                    o = _add(o, u, -w/2.0 if along > 0 else w/2.0)
            a, b = _add(o, u, -w/2.0), _add(o, u, w/2.0)
            floor = Polygon([a, b, _add(b, n, d), _add(a, n, d)])
            if not self.I.buffer(0.02).contains(floor):
                self.warn('%s: the %s is not all inside the building' % (f['where'], f['kind']))
            elif floor.intersection(self.solid).area > 0.02:
                self.warn('%s: the %s runs into a wall' % (f['where'], f['kind']))
            self.fittings.append(dict(f, o=o, u=(-u[0], -u[1]) if f['flip'] else u, n=n, w=w, d=d,
                                      floor=floor, host=h))

    def _rooflights(self):
        """Each light in the ceiling, with the room it is over: the one
        its middle is in. One that is not over the building is reported."""
        self.rooflights = []
        for r in self.spec['rooflights']:
            shape = Polygon(r['pts'])
            over = next((m['name'] for m in self.rooms if m['face'].contains(Point(r['at']))), None)
            if not self.E.buffer(TOL).contains(shape):
                self.warn('%s: the rooflight%s is not all over the building' % (r['where'], ' %s' % r['id'] if r['id'] else ''))
            self.rooflights.append(dict(r, shape=shape, over=over))

    def _clear(self, h, side):
        """How much of a wall has floor against it on one side: from how
        far along it to how far."""
        off = _dot(side, (-h.u[1], h.u[0]))
        line = LineString(h.run(0.0, h.L, (h.t/2.0 + 0.02) * (1.0 if off > 0 else -1.0)))
        found = [h.project(p)[0] for f in self.faces for g in getattr(line.intersection(f), 'geoms', [line.intersection(f)])
                 if not g.is_empty for p in g.coords]
        return (min(found), max(found)) if found else (0.0, h.L)

    # ---- the solid plan, and the rooms left in it
    def _faces(self):
        holes = {}
        for o in self.openings:
            holes.setdefault(id(o['host']), []).append(o['hole'])
        parts = []
        ext = self.ext
        for h in self.env_hosts:
            if id(h) in holes:
                ext = ext.difference(unary_union(holes[id(h)]))
        parts.append(ext)
        for w, body in zip(self.spec['walls'], self.bodies):
            h = self.hosts[w['id']]
            b = body.intersection(self.I)
            if id(h) in holes:
                b = b.difference(unary_union(holes[id(h)]))
            parts.append(b)
        parts.extend(s.intersection(self.I) for s in self.solids)
        self.walls = unary_union([p for p in parts if not p.is_empty])
        # the same with every opening filled in: what is built, for telling
        # one sheet's walls from another's
        self.solid = unary_union([self.ext] + [b.intersection(self.I) for b in self.bodies + self.solids])

        # Rooms are found with every door shut, and with the walls swollen
        # by a few millimetres so a hairline gap cannot join two rooms.
        shut = unary_union(self.bodies + self.solids +
                           [LineString(d).buffer(TOL) for d in self.spec['dividers']])
        free = self.I.difference(shut.buffer(0.004, join_style=2))
        self.faces = [g for f in _polys(free) if f.area > 0.02
                      for g in _polys(f.buffer(0.004, join_style=2).intersection(self.I))]
        self.rooms = []
        used = {}
        for r in self.spec['rooms']:
            p = Point(r['at'])
            face = next((f for f in self.faces if f.contains(p)), None)
            if face is None:
                self.warn('%s: room %s is seeded in a wall or outside the building'
                          % (r['where'], r['name']), 'error')
                continue
            k = id(face)
            if k in used:
                self.warn('%s: %s and %s are the same space — a wall is missing or open'
                          % (r['where'], r['name'], used[k]), 'error')
            used[k] = r['name']
            if key(r) and key(r) in [key(o) for o in self.rooms]:
                self.warn('%s: two rooms are called %s — give one an `id`, or notes and zones cannot tell them apart'
                          % (r['where'], r['name']))
            self.rooms.append(dict(r, face=face, **measure(face)))
            self._expected(self.rooms[-1])
        for f in self.faces:
            if id(f) not in used and f.area > 1.0 and not self.spec['unlabelled']:
                c = f.representative_point()
                self.warn('a space of %.1f m² near (%.2f, %.2f) has no room in it'
                          % (f.area, c.x, c.y))
        self._zones()
        free = self._free_ends()
        self._inside(free)

    def _expected(self, r):
        """A room against the size it was given (`expect:`). A room turned
        or slanted on the page meets a length with either the size it
        reads, square to its own walls, or its extent on the page, since a
        quoted figure may be either."""
        x0, y0, x1, y1 = r['face'].bounds
        over = {'w': x1 - x0, 'h': y1 - y0}
        for k, (want, src) in sorted(r['expect'].items()):
            tol = AREA_NEAR if k == 'area' else NEAR
            got = [r[k]] + ([over[k]] if k in over and r['shape'] != 'rect' else [])
            if min(abs(g - want) for g in got) <= tol:
                continue
            what = {'w': 'wide', 'h': 'deep', 'area': 'm²'}[k]
            said = src if src == '%g' % want else '%s = %.2f' % (src, want)
            self.warn('%s: %s reads %.2f %s, given as %s — %.2f %s%s'
                      % (r['where'], r['name'], r[k], what, said, abs(r[k] - want),
                         'over' if r[k] > want else 'under',
                         '' if len(got) == 1 or abs(got[1] - r[k]) < 0.005 else ' (%.2f on the page)' % got[1]))

    def _zones(self):
        """Zones: rooms marked out together as one region, not laid out or
        to be dealt with later. A room that is `zone: true` is a zone of
        itself; `zones:` name several, and the walls between them are
        taken in so the region has one outline."""
        self.zones = [dict(r, rooms=[r], own=True) for r in self.rooms if r['zone']]
        for z in self.spec['zones']:
            took = []
            for want in z['rooms']:
                hit = [r for r in self.rooms if want in (r['id'], r['name'])]
                if len(hit) != 1:
                    raise ValueError('%s: %s called %r' % (z['where'], 'two rooms are' if hit else 'no room is', want))
                took.append(hit[0])
            reach = max([w['t'] for w in self.spec['walls']] + self.spec['envelope']['t'])/2.0 + 0.01
            face = unary_union([r['face'] for r in took]).buffer(reach, join_style=2).buffer(-reach, join_style=2)
            face = max(_polys(face.intersection(self.I)), key=lambda p: p.area)
            size = measure(face)
            size['area'] = sum(r['area'] for r in took)         # floor, not the walls between
            self.zones.append(dict(z, face=face, rooms=took, own=False, zone=True, dims=True,
                                   size=None, rot=None, dx=0.0, dy=0.0, **size))

    def _free_ends(self):
        """Report each wall end that meets nothing; returns the walls that have one."""
        free = set()
        for k, w in enumerate(self.spec['walls']):
            others = unary_union([b for j, b in enumerate(self.bodies) if j != k] +
                                 self.solids + [self.ext]).buffer(2*TOL)
            for end in (w['a'], w['b']):
                if not others.contains(Point(end)):
                    self.warn('wall %s ends in the open at (%.2f, %.2f)' % ((w['id'],) + end), 'info')
                    free.add(w['id'])
        return free

    def _inside(self, free):
        """What stands inside one room: a stretch of wall with the same
        room on both its faces, and a door or opening that leads from a
        room into itself. It is what is left when two rooms are made one
        and not everything that parted them was taken out. `self.inside`
        lists every such thing; what is reported is a door, and a whole
        wall that is not a nib or a screen — one with a door in it, or
        held at both ends by walls that are not themselves nibs."""
        self.inside = []
        if not self.faces:
            return
        named = dict((id(r['face']), r['name']) for r in reversed(self.rooms))    # of two in one face, the first
        STEP, OFF = 0.1, 0.03
        runs, xs, ys = [], [], []
        for w in self.spec['walls']:
            h = self.hosts[w['id']]
            n = max(1, int(round(h.L / STEP)))
            at = [h.L*(i + 0.5)/n for i in range(n)]
            runs.append((w, h, at, len(xs)))
            for side in (1.0, -1.0):
                for s in at:
                    x, y = h.at(s, side*(h.t/2.0 + OFF))
                    xs.append(x)
                    ys.append(y)
        doors = []
        for o in self.openings:
            h = o['host']
            if h.inward is not None:
                continue                            # in an outside wall: the other side is outside
            c = (o['s0'] + o['s1'])/2.0
            doors.append((o, len(xs)))
            for side in (1.0, -1.0):
                x, y = h.at(c, side*(h.t/2.0 + OFF))
                xs.append(x)
                ys.append(y)
        if not xs:
            return
        which = np.full(len(xs), -1)
        X, Y = np.asarray(xs), np.asarray(ys)
        for k, f in enumerate(self.faces):
            which[shapely.contains_xy(f, X, Y)] = k
        say = lambda k: named.get(id(self.faces[k])) or 'a space with no room in it'
        for w, h, at, i in runs:
            n = len(at)
            a, b = which[i:i+n], which[i+n:i+2*n]
            # a station with a wall beside it — where another wall ties in — says nothing either way,
            # and nor does one inside an outside wall, which a wall's line may start in
            same, differ = (a == b) & (a >= 0), (a != b) & (a >= 0) & (b >= 0)
            whole = not differ.any() and same.any() and same.sum() >= 0.8*((a >= 0) | (b >= 0)).sum() \
                and len(set(a[same])) == 1
            k = 0
            while k < n:
                if not same[k]:
                    k += 1
                    continue
                j = last = k
                while j + 1 < n and not differ[j+1] and (not same[j+1] or a[j+1] == a[k]):
                    j += 1
                    last = j if same[j] else last
                s0, s1 = (0.0, h.L) if whole else (at[k] - h.L/(2.0*n), at[last] + h.L/(2.0*n))
                if whole or s1 - s0 >= 0.3:
                    self.inside.append({'wall': w['id'], 'room': say(a[k]), 'face': self.faces[a[k]], 'whole': whole,
                                        'from': h.at(s0), 'to': h.at(s1)})
                k = j + 1
        whole = set(i['wall'] for i in self.inside if i['whole'])
        holed = {}
        for o, i in doors:
            if which[i] == which[i+1] and which[i] >= 0:
                self.inside.append({'opening': o['where'], 'kind': o['kind'], 'wall': o['host'].name,
                                    'room': say(which[i]), 'face': self.faces[which[i]], 'at': o['centre']})
                if o['host'].id in whole:           # said once, with its wall
                    holed.setdefault(o['host'].id, []).append(o['kind'])
                else:
                    self.warn('%s: the %s in wall %s leads from %s into itself — that stretch of the wall stands inside one room'
                              % (o['where'], o['kind'], o['host'].name, say(which[i])))
        # a wall with no door in it that reaches a free end — itself, or by way of others that stand in the
        # same room with it — is a nib or a screen, and meant
        plain = [i for i in self.inside if 'opening' not in i and i['whole'] and i['wall'] not in holed]
        lines = dict((i['wall'], LineString(self.hosts[i['wall']].pts)) for i in plain)
        nibs, grew = set(i['wall'] for i in plain if i['wall'] in free), True
        while grew:
            grew = False
            for i in plain:
                if i['wall'] not in nibs and any(
                        j['face'] is i['face'] and j['wall'] in nibs and lines[i['wall']].distance(lines[j['wall']])
                        <= (self.hosts[i['wall']].t + self.hosts[j['wall']].t)/2.0 + TOL for j in plain):
                    nibs.add(i['wall'])
                    grew = True
        for i in self.inside:
            if 'opening' not in i and i['whole'] and i['wall'] not in nibs:
                self.warn('wall %s has %s on both its faces — it stands inside one room%s'
                          % (i['wall'], i['room'], ', and the %s in it leads from that room into itself'
                             % ' and '.join(holed[i['wall']]) if i['wall'] in holed else ''))

    @property
    def gross(self):
        return self.E.area

    @property
    def internal(self):
        return self.I.area


def measure(face):
    """Clear size of a room, and what kind of shape it is.

    A rectangle reads its two sides and a round room its diameter. Any
    other reads its overall size: the longest a tape reads across it each
    way, which is the figure a survey or an agent gives — over a chimney
    breast, into a bay, down the long leg of an L. It is taken square to
    the page, or to the room's own walls where it lies between slanted
    ones, so that room reads its clear width. The area tells the rest."""
    x0, y0, x1, y1 = face.bounds
    area = face.area
    bb = (x1-x0)*(y1-y0)
    if area >= 0.995*bb:
        return {'w': x1-x0, 'h': y1-y0, 'area': area, 'shape': 'rect', 'rect': (x0, y0, x1, y1)}
    with warnings.catch_warnings():                 # shapely divides by zero on a shape square to the axes
        warnings.simplefilter('ignore', RuntimeWarning)
        mrr = face.minimum_rotated_rectangle
    if mrr.area > 0 and area >= 0.995*mrr.area:
        c = list(mrr.exterior.coords)
        e1, e2 = _sub(c[1], c[0]), _sub(c[2], c[1])
        l1, l2 = math.hypot(*e1), math.hypot(*e2)
        w, h = (l1, l2) if abs(e1[0]) >= abs(e1[1]) else (l2, l1)
        m = min(l1, l2)/2.0
        cx, cy = mrr.centroid.x, mrr.centroid.y
        return {'w': w, 'h': h, 'area': area, 'shape': 'skew', 'rect': (cx-m, cy-m, cx+m, cy+m)}
    if abs((x1-x0) - (y1-y0)) < 0.02*(x1-x0) and abs(area - math.pi*bb/4.0) < 0.02*bb:
        return {'w': x1-x0, 'h': y1-y0, 'area': area, 'shape': 'round', 'rect': inscribed(face)}
    r = inscribed(face)
    # A room whose walls are not square to the page is measured square to
    # them: where the rectangle that fits is larger that way round, that
    # is the way the room lies.
    lie, most = face, (r[2]-r[0])*(r[3]-r[1])
    for deg in _slants(face):
        turned = rotate(face, -deg, origin='centroid')
        t = inscribed(turned)
        if (t[2]-t[0])*(t[3]-t[1]) > 1.02*most:
            lie, most = turned, (t[2]-t[0])*(t[3]-t[1])
    w, h = across(lie)
    return {'w': w, 'h': h, 'area': area, 'shape': 'near' if area >= 0.90*bb else 'irregular', 'rect': r}


def across(face, most=120):
    """The longest straight line inside a face each way: east to west,
    then north to south. It is longest just to one side of a corner, so
    that is where it is looked for."""
    x0, y0, x1, y1 = face.bounds
    out = []
    for k, lo, hi in ((1, y0, y1), (0, x0, x1)):
        at = sorted(set(round(p[k], 7) for ring in [face.exterior] + list(face.interiors) for p in ring.coords))
        at = at[::max(1, len(at)//most)]
        best = 0.0
        for v in set(c + d for c in at for d in (-1e-6, 1e-6) if lo < c + d < hi):
            line = LineString([(x0-1, v), (x1+1, v)] if k else [(v, y0-1), (v, y1+1)])
            cut = face.intersection(line)
            best = max([best] + [g.length for g in getattr(cut, 'geoms', [cut]) if g.geom_type == 'LineString'])
        out.append(round(best, 4))
    return tuple(out)


def _slants(face, most=3):
    """The angles, in degrees off the page's own axes, of a face's longest
    walls that are not square to it."""
    pts = list(face.exterior.coords)
    runs = {}
    for a, b in zip(pts, pts[1:]):
        deg = (math.degrees(math.atan2(b[1]-a[1], b[0]-a[0])) + 45.0) % 90.0 - 45.0
        if abs(deg) > 0.5:
            runs[round(deg, 1)] = runs.get(round(deg, 1), 0.0) + math.hypot(b[0]-a[0], b[1]-a[1])
    return [d for d in sorted(runs, key=runs.get, reverse=True) if runs[d] > 0.5][:most]


def inscribed(face, limit=26):
    """Largest axis-aligned rectangle inside a face, corners on its own lines."""
    pts = list(face.exterior.coords)
    xs = sorted(set(round(p[0], 3) for p in pts))
    ys = sorted(set(round(p[1], 3) for p in pts))
    xs, ys = xs[::max(1, len(xs)//limit)], ys[::max(1, len(ys)//limit)]
    inside = face.buffer(0.001)
    shapely.prepare(inside)
    return _largest(xs, ys, inside) or _fitted(face, inside)


def _largest(xs, ys, inside):
    """The largest rectangle with its sides on these lines that is inside.
    The lines cut the plane into cells, and a rectangle is inside when
    every cell of it is: so each cell is asked once, all together, and a
    rectangle is then a sum to look up rather than a shape to test."""
    nx, ny = len(xs) - 1, len(ys) - 1
    if nx < 1 or ny < 1:
        return None
    X, Y = np.asarray(xs, dtype=float), np.asarray(ys, dtype=float)
    cells = shapely.box(X[:-1, None], Y[None, :-1], X[1:, None], Y[None, 1:])
    full = np.zeros((nx + 1, ny + 1), dtype=np.int64)
    full[1:, 1:] = shapely.contains(inside, cells).cumsum(0).cumsum(1)
    j, m = np.triu_indices(ny + 1, 1)               # every pair of lines across, c below d
    deep, tall = Y[m] - Y[j], m - j
    best = None
    for i in range(nx):
        for k in range(i + 1, nx + 1):
            col = full[k] - full[i]
            ok = col[m] - col[j] == (k - i)*tall
            if not ok.any():
                continue
            area = np.where(ok, (xs[k] - xs[i])*deep, -1.0)
            at = np.flatnonzero(area == area.max())[-1]     # of equals, the one furthest on: as they sort
            key = (float(area[at]), xs[i], ys[j[at]], xs[k], ys[m[at]])
            if best is None or key > best:
                best = key
    return best and best[1:]


def _fitted(face, inside, n=12):
    """A rectangle inside a face none of whose own lines make one — a
    triangle, whose every corner lies outside any rectangle in it. A grid
    across the face finds roughly where the largest is, and each side of
    that is then pushed out as far as it will go."""
    x0, y0, x1, y1 = face.bounds
    xs = [x0 + (x1-x0)*i/float(n) for i in range(n+1)]
    ys = [y0 + (y1-y0)*i/float(n) for i in range(n+1)]
    r = _largest(xs, ys, inside)
    r = r and list(r)
    if r is None or min(r[2]-r[0], r[3]-r[1]) < 0.05:   # too thin for anything: a mark where it is
        p = face.representative_point()
        return (p.x-0.1, p.y-0.1, p.x+0.1, p.y+0.1)
    for _ in range(2):
        for k, far in enumerate((x0, y0, x1, y1)):
            lo, hi = r[k], far                      # lo is known to fit
            for _ in range(14):
                mid = (lo + hi)/2.0
                if inside.contains(box(*(r[:k] + [mid] + r[k+1:]))):
                    lo = mid
                else:
                    hi = mid
            r[k] = lo
    return tuple(round(v, 3) for v in r)


def leaf_shape(hinge, shut, side, w, steps=6):
    """The open leaf's tip, the arc's sweep flag, and the swept sector."""
    a = math.radians(OPEN)
    tip = (hinge[0] + w*(math.cos(a)*shut[0] + math.sin(a)*side[0]),
           hinge[1] + w*(math.cos(a)*shut[1] + math.sin(a)*side[1]))
    sweep = 1 if _cross(shut, side) > 0 else 0
    arc = [(hinge[0] + w*(math.cos(a*i/steps)*shut[0] + math.sin(a*i/steps)*side[0]),
            hinge[1] + w*(math.cos(a*i/steps)*shut[1] + math.sin(a*i/steps)*side[1]))
           for i in range(steps+1)]
    return tip, sweep, Polygon([hinge] + arc)
