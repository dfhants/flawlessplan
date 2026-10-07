# -*- coding: utf-8 -*-
"""Read a house file and turn every expression in it into a number.

What comes out is plain data — dicts and tuples in metres — with nothing
left to evaluate. Geometry is geom.py's business; this only checks that
the file says what it needs to and says it unambiguously.

Coordinates: x runs east, y runs SOUTH, so north is up the page and a
plan is written the way it is read.
"""
import os
import re
import math
import yaml
from .expr import Scope, ExprError, imperial
from .geom import inner_ring, signed_area, arc
from .fittings import KINDS

DEFAULTS = {
    'ext_wall': 0.30,            # external wall thickness
    'int_wall': 0.10,            # internal partition thickness
    'leaves': {'cloak': 686, 'std': 762, 'wide': 838},   # UK door leaves, mm
    'frame': 80,                 # 2 x 30 mm frame + tolerance, mm
    'cut_plane': 1.20,           # height the plan is cut at
    'going': 0.225,              # stair tread
}


# What is written about a sheet, by kind. None of it is drawn: it goes
# beside the sheet on the page and into a file next to the image.
NOTE_GROUPS = (('decided', 'Decided'), ('unconfirmed', 'Not confirmed'),
               ('needs', 'Needs'), ('about', 'About this drawing'))


def notes(v, where):
    """A sheet's notes as {summary, decided, unconfirmed, needs, about}.
    A plain list is taken as `about`."""
    out = {'summary': ''}
    out.update((k, []) for k, _ in NOTE_GROUPS)
    if v is None:
        return out
    if isinstance(v, list):
        v = {'about': v}
    if not isinstance(v, dict):
        raise ConfigError('%s.notes: expected a list or a mapping' % where)
    for k, x in v.items():
        if k == 'summary':
            out[k] = str(x or '')
        elif k in out:
            out[k] = [str(t) for t in (x if isinstance(x, list) else [x]) if t is not None]
        else:
            raise ConfigError('%s.notes: no group called %r (summary, %s)'
                              % (where, k, ', '.join(g for g, _ in NOTE_GROUPS)))
    return out


def join_notes(a, b):
    """`a` then `b`; the first summary given stands."""
    if not a or not b:
        return a or b
    out = {'summary': a['summary'] or b['summary']}
    out.update((k, a[k] + b[k]) for k, _ in NOTE_GROUPS)
    return out


AREA_STYLES = ('outdoor', 'below', 'new', 'zone', 'fitting')
TEXT_STYLES = ('name', 'small', 'mini', 'note', 'zone')
DIM_STYLES = ('', 'soft', 'calc')
COMPASS = ('north', 'east', 'south', 'west')
NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]*\Z')     # \Z: `$` would let an id end in a newline
MOST_TREADS = 60             # to a leg: more than any stair has, and few enough to draw


def stem(path):
    """What a house with no name is called: its folder, or its file when it has none."""
    base = os.path.basename(path)
    if base == 'house.yaml':
        return os.path.basename(os.path.dirname(os.path.abspath(path))) or 'house'
    return os.path.splitext(base)[0]


class ConfigError(ValueError):
    pass


def _need(d, key, where):
    if not isinstance(d, dict) or key not in d:
        raise ConfigError('%s: missing %r' % (where, key))
    return d[key]


class Loader(object):
    def __init__(self, raw, path='<house>'):
        if not isinstance(raw, dict):
            raise ConfigError('%s: a house file is a mapping at the top level' % path)
        self.raw, self.path = raw, path
        self.defaults = dict(DEFAULTS)
        for k, v in (raw.get('defaults') or {}).items():
            if k not in DEFAULTS:
                raise ConfigError('defaults: unknown key %r' % k)
            self.defaults[k] = v
        self.status, self.written = {}, {}
        self.known = {}                 # the walls of the sheet being read that a point may be put on
        self.scope = self._scope()

    def op(self, kind, pair=False):
        """Structural opening in metres for a standard leaf, single or pair."""
        leaves = self.defaults['leaves']
        if kind not in leaves:
            raise ExprError('unknown door leaf %r (have %s)' % (kind, ', '.join(sorted(leaves))))
        n = 2 if pair else 1
        return (leaves[kind]*n + self.defaults['frame'] + (10 if pair else 0)) / 1000.0

    def _scope(self):
        sc = Scope(funcs={'op': self.op})
        sc.names['EW'] = float(self.defaults['ext_wall'])
        sc.names['IW'] = float(self.defaults['int_wall'])
        for k, v in (self.raw.get('survey') or {}).items():
            st = 'given'
            if isinstance(v, dict):
                st = v.get('status', 'given')
                v = _need(v, 'value', 'survey.%s' % k)
            self._define(sc, k, v, 'survey')
            self.status[k] = str(st)
            if isinstance(v, str) and imperial(v) is not None:
                self.written[k] = v.strip()             # the figure as it was given
        for k, v in (self.raw.get('lines') or {}).items():
            self._define(sc, k, v, 'lines')
            self.status[k] = 'derived'
        return sc

    def _define(self, sc, k, v, table):
        if k in sc.names:
            raise ConfigError('%s.%s: the name is already defined' % (table, k))
        try:
            sc.names[k] = sc.ev(v)
        except ExprError as e:
            raise ConfigError('%s.%s: %s' % (table, k, e))

    # -- helpers that report where in the file a bad value sits
    def num(self, v, where):
        try:
            return self.scope.ev(v)
        except ExprError as e:
            raise ConfigError('%s: %s' % (where, e))

    def some(self, v, where, what='a size'):
        """A number above nothing: a thickness, a width."""
        n = self.num(v, where)
        if n <= 0:
            raise ConfigError('%s: %s is more than nothing, not %g' % (where, what, n))
        return n

    def turn(self, v, where):
        """`rot:` — how far text is turned, in degrees, or None."""
        return None if v is None else self.num(v, where + '.rot')

    def pt(self, v, where):
        if isinstance(v, dict):
            return self.on(v, where)
        try:
            return self.scope.pt(v)
        except ExprError as e:
            raise ConfigError('%s: %s' % (where, e))

    def text(self, v, where, scope=None):
        try:
            return (scope or self.scope).text(v)
        except (ExprError, ValueError) as e:
            raise ConfigError('%s: %s' % (where, e))

    def on(self, v, where):
        """A point given by one coordinate and the wall it lies on:
        `{y: YM, wall: east}` is where the east wall is at that y, whatever
        angle it runs at. On an outside wall that is its inside face, or
        with `side: out` its outside one; on a partition its centreline,
        or with `side:` a compass point the face on that side. `clear:` is
        a distance further that way, measured square to the wall, so two
        points with the same `clear` make a line parallel to it."""
        axes = [k for k in ('x', 'y') if k in v]
        if 'wall' not in v or len(axes) != 1 or set(v) - set(('x', 'y', 'wall', 'side', 'clear')):
            raise ConfigError('%s: a point on a wall is {x: or y:, wall: its name}, with side: and clear: if wanted' % where)
        name, k = str(v['wall']), 'xy'.index(axes[0])
        if name not in self.known and name + '.0' in self.known:        # a path: whichever leg is there
            n, last = 0, None
            while '%s.%d' % (name, n) in self.known:
                try:
                    return self.on(dict(v, wall='%s.%d' % (name, n)), where)
                except ConfigError as e:
                    last = e
                n += 1
            raise ConfigError('%s: no leg of %s is there (%s)' % (where, name, str(last).split(': ', 1)[-1]))
        if name not in self.known:
            raise ConfigError('%s: no wall called %r yet (an outside wall by its `id`, or a wall above this one)'
                              % (where, name))
        segs = self.known[name]
        t, inward = segs[0][2], segs[0][3]
        c = self.num(v[axes[0]], '%s.%s' % (where, axes[0]))
        off = self.num(v.get('clear', 0), where + '.clear')
        side = str(v.get('side', 'in' if inward else '')).lower()
        turn = None                                 # for a partition: which side of its own direction, +1 the right
        if inward:
            if side not in ('in', 'out'):
                raise ConfigError('%s.side: %s is an outside wall — use in or out' % (where, name))
            shift = t + off if side == 'in' else -off
        elif not side:
            if off:
                raise ConfigError('%s.clear: say which `side:` of %s it is measured to' % (where, name))
            shift = 0.0
        else:
            want = {'n': (0, -1), 's': (0, 1), 'e': (1, 0), 'w': (-1, 0)}.get(side[:1] if side in COMPASS else side)
            (ax, ay), (bx, by) = segs[0][0], segs[-1][1]
            dot = (by-ay)*want[0] - (bx-ax)*want[1] if want else 0.0        # against the wall end to end
            if abs(dot) < 1e-6:
                raise ConfigError('%s.side: %s has no %r side — use a compass point it faces' % (where, name, side))
            turn, shift = (1.0 if dot > 0 else -1.0), t/2.0 + off
        flat, slack = True, abs(shift) + t + 0.01
        for i, (a, b, _, inward) in enumerate(segs):
            L = math.hypot(b[0]-a[0], b[1]-a[1])
            d = ((b[0]-a[0])/L, (b[1]-a[1])/L)
            n = inward or (d[1]*(turn or 0.0), -d[0]*(turn or 0.0))
            p = (a[0] + n[0]*shift, a[1] + n[1]*shift)
            if abs(d[k]) < 1e-9:
                continue
            flat = False
            s = (c - p[k]) / d[k]
            if (-slack if i == 0 else -0.02) <= s <= L + (slack if i == len(segs) - 1 else 0.02):
                q = (p[0] + d[0]*s, p[1] + d[1]*s)
                return (c, q[1]) if k == 0 else (q[0], c)
        if flat:
            raise ConfigError('%s: %s runs along %s, so no one point of it is at %s = %g' % (where, name, axes[0], axes[0], c))
        raise ConfigError('%s: %s does not reach %s = %.3f' % (where, name, axes[0], c))

    def curve(self, x, a, b, out, where):
        """The points of a wall from a to b: the two of them, or the arc
        between that `rise:`, `radius:` or `via:` asks for. `out` is the
        unit vector a rise stands off the straight line along (None: say
        with `toward:`). Returns (points, None or what the arc is)."""
        asked = [k for k in ('rise', 'radius', 'via') if k in x]
        if not asked:
            return [a, b], None
        if len(asked) > 1:
            raise ConfigError('%s: give one of rise, radius and via' % where)
        chord = math.hypot(b[0]-a[0], b[1]-a[1])
        if chord < 1e-9:
            raise ConfigError('%s: a curve needs two ends — draw a circle as two halves' % where)
        if asked[0] == 'via':
            via = self.pt(x['via'], where + '.via')
        else:
            if 'toward' in x or out is None:
                word = str(x.get('toward', '')).lower()
                want = {'n': (0, -1), 's': (0, 1), 'e': (1, 0), 'w': (-1, 0)}.get(word[:1] if word in COMPASS else word)
                left = ((b[1]-a[1])/chord, -(b[0]-a[0])/chord)
                dot = left[0]*want[0] + left[1]*want[1] if want else 0.0
                if abs(dot) < 1e-6:
                    raise ConfigError('%s.toward: say which way it curves — a compass point across the wall' % where)
                out = left if dot > 0 else (-left[0], -left[1])
            h = self.num(x[asked[0]], '%s.%s' % (where, asked[0]))
            if asked[0] == 'radius':
                if h < chord/2.0 - 1e-9:
                    raise ConfigError('%s.radius: %.3f is too tight for ends %.3f apart' % (where, h, chord))
                h = h - math.sqrt(max(0.0, h*h - chord*chord/4.0))
            if abs(h) < 1e-6:
                return [a, b], None
            via = ((a[0]+b[0])/2.0 + out[0]*h, (a[1]+b[1])/2.0 + out[1]*h)
        try:
            pts, r = arc(a, b, via)
        except ValueError as e:
            raise ConfigError('%s: %s' % (where, e))
        mid = pts[len(pts)//2]                       # which way it stands off its chord, and roughly how far
        side = ((mid[0]-a[0])*(b[1]-a[1]) - (mid[1]-a[1])*(b[0]-a[0])) / chord
        sag = math.sqrt(max(0.0, r*r - chord*chord/4.0))    # exactly how far: the middle piece need not end at the arc's middle
        return pts, {'r': r, 'rise': math.copysign(r + sag if abs(side) > r else r - sag, side)}

    def shape(self, d, where):
        """A polygon given as `points`, or as `rect: [[x0, y0], [x1, y1]]`."""
        if 'rect' in d:
            (x0, y0), (x1, y1) = [self.pt(p, where + '.rect') for p in d['rect']]
            return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        pts = [self.pt(p, where + '.points') for p in _need(d, 'points', where)]
        if len(pts) < 3:
            raise ConfigError('%s.points: a shape needs at least three points' % where)
        return pts

    # -- parts: named groups of walls, openings, rooms ... that sheets share
    LISTS = ('walls', 'dividers', 'openings', 'rooms', 'stairs', 'areas', 'solids', 'fittings',
             'rooflights', 'labels', 'gone', 'dims', 'require', 'zones')

    def merged(self, f, where, seen=()):
        out = {}
        parts = self.raw.get('parts') or {}
        for name in f.get('use') or []:
            if name not in parts:
                raise ConfigError('%s.use: no part called %r' % (where, name))
            if name in seen:
                raise ConfigError('%s.use: part %r uses itself' % (where, name))
            for k in ('omit', 'extends'):
                if k in (parts[name] or {}):
                    raise ConfigError('parts.%s.%s: a sheet says that, of itself; a part cannot' % (name, k))
            for k, v in self.merged(parts[name] or {}, 'parts.%s' % name, seen + (name,)).items():
                if k == 'notes':
                    out[k] = join_notes(out.get(k), v)
                else:
                    out[k] = out.get(k, []) + v if k in self.LISTS else v
        for k, v in f.items():
            if k == 'use':
                continue
            if k == 'notes':                        # a sheet's own notes lead
                out[k] = join_notes(notes(v, where), out.get(k))
            elif k in self.LISTS:
                out[k] = out.get(k, []) + list(v or [])
            else:
                out[k] = v
        return out

    # -- a sheet that is another sheet, and more: and what a sheet leaves out
    OWN = ('id', 'title', 'tab', 'scheme', 'notes', 'hidden', 'use', 'extends', 'omit')    # never taken from the sheet extended
    OMITS = (('wall', 'walls'), ('opening', 'openings'), ('room', 'rooms'), ('stair', 'stairs'), ('rooflight', 'rooflights'))

    def extended(self, f, own, where):
        """`extends: <sheet>`: that sheet as it was read — its parts in,
        what it omits out — with this one's lists after its, and whatever
        else this one says in place of what that one said. What a sheet
        says of itself — its title, its tab, its scheme, its notes — is
        not taken on."""
        if 'extends' not in f:
            return own
        base = str(f['extends'])
        if base not in self.flat:
            raise ConfigError('%s.extends: no earlier sheet called %r' % (where, base))
        out = dict((k, list(v) if k in self.LISTS else v) for k, v in self.flat[base].items() if k not in self.OWN)
        for k, v in own.items():
            out[k] = out.get(k, []) + v if k in self.LISTS else v
        return out

    def omitted(self, f, where):
        """`omit: [hall_leg, {room: HALL}]`: the sheet without them, once
        its parts are in. A name is a wall, an opening, a room or a stair
        by its `id`, or a room by its name; `{wall: x}` says which kind.
        A wall takes the openings and fittings that name it with it. One
        that names nothing is an error: it would be left behind unnoticed
        when what it named is renamed."""
        omit = f.get('omit')
        if not omit:
            return f
        if not isinstance(omit, list):
            raise ConfigError('%s.omit: a list of ids — walls, openings, rooms, stairs' % where)
        f = dict(f)
        # a wall with no id is called by its place in the list, which taking one out would change
        f['walls'] = [x if not isinstance(x, dict) or 'id' in x else dict(x, id='w%d' % i)
                      for i, x in enumerate(f.get('walls') or [])]
        kinds = dict(self.OMITS)
        for n, o in enumerate(omit):
            ww = '%s.omit[%d]' % (where, n)
            if isinstance(o, dict):
                if len(o) != 1 or list(o)[0] not in kinds:
                    raise ConfigError('%s: a name, or one of %s with a name' % (ww, ', '.join('{%s: ...}' % k for k, _ in self.OMITS)))
                (kind, name), = o.items()
                look = [(kind, kinds[kind])]
            else:
                name, look = o, self.OMITS
            name, found = str(name), False
            for kind, key in look:
                keep = [x for x in f.get(key) or []
                        if not (isinstance(x, dict) and (str(x.get('id')) == name and x.get('id') is not None
                                                         or kind == 'room' and str(x.get('name')) == name))]
                if len(keep) != len(f.get(key) or []):
                    f[key], found = keep, True
                    if kind == 'wall':              # and what was in it or against it; `name.1` is a leg of a path
                        for held in ('openings', 'fittings'):
                            f[held] = [x for x in f.get(held) or [] if not (
                                isinstance(x, dict) and x.get('wall') is not None
                                and (str(x['wall']) == name or str(x['wall']).startswith(name + '.')))]
            if not found:
                raise ConfigError('%s: nothing called %r on this sheet — a wall, an opening, a room, a stair or a rooflight '
                                  'by its `id`, or a room by its name' % (ww, name))
        return f

    # -- the sheets
    def house(self):
        h = self.raw.get('house') or {}
        if 'floors' in self.raw:
            raise ConfigError('%s: `floors:` is now `sheets:` — a sheet is one drawing of one '
                              'level, and says which with `level:`' % self.path)
        if 'shell' in self.raw:
            raise ConfigError('%s: `shell:` is now `outline:`, and lists `sheets:`' % self.path)
        if h.get('front') is not None and h['front'] not in COMPASS:
            raise ConfigError('house.front: use one of %s, not %r' % (', '.join(COMPASS), h['front']))
        sheets = self.raw.get('sheets')
        if not sheets:
            raise ConfigError('%s: no sheets' % self.path)
        if isinstance(sheets, dict):
            sheets = [dict(v or {}, id=k) for k, v in sheets.items()]
        if not isinstance(sheets, list) or [f for f in sheets if not isinstance(f, dict)]:
            raise ConfigError('%s: `sheets:` is a list of sheets, each a mapping with an `id`' % self.path)
        # the storeys, bottom up; left out, every sheet that names no level is one
        levels = self.raw.get('levels') or [str(_need(f, 'id', 'sheet')) for f in sheets if 'level' not in f]
        self.levels = [str(v) for v in levels]
        out = {'name': str(h.get('name') or stem(self.path)),
               'front': h.get('front'), 'front_note': None if h.get('front_note') is None else str(h['front_note']),
               'private': bool(h.get('private', False)),
               'defaults': self.defaults, 'names': dict(self.scope.names),
               'status': dict(self.status), 'written': dict(self.written), 'scope': self.scope, 'sheets': [],
               'levels': self.levels, 'outline': self.raw.get('outline') or {}}
        if not isinstance(out['outline'], dict):
            raise ConfigError('outline: a mapping — `sheets:` to say which, and `notes:`')
        seen, self.flat = {}, {}                    # the sheets read; each as written out whole, for one that extends it
        for f in sheets:
            try:
                fl = self.sheet(f, seen)
            except ConfigError:
                raise
            except (AttributeError, TypeError, KeyError, IndexError, ValueError) as e:
                raise ConfigError('sheets.%s: not laid out as a sheet is — %s'
                                  % (f.get('id', '?') if isinstance(f, dict) else '?', e))
            if fl['id'] in seen:
                raise ConfigError('sheets: two sheets called %r' % fl['id'])
            seen[fl['id']] = fl
            out['sheets'].append(fl)
        if all(fl['hidden'] for fl in out['sheets']):
            raise ConfigError('sheets: every sheet is `hidden: true` — a house shows at least one')
        named = out['outline'].get('sheets') or []
        if not isinstance(named, list) or [i for i in named if str(i) not in seen]:
            raise ConfigError('outline.sheets: list sheets by their id (have %s)' % ', '.join(seen))
        return out

    def sheet(self, f, earlier):
        fid = str(_need(f, 'id', 'sheet'))
        if not NAME.match(fid):                     # it becomes a file name and an element id
            raise ConfigError('sheets: id %r — use letters, digits, - and _ only' % fid)
        w = 'sheets.%s' % fid
        extends = None if f.get('extends') is None else str(f['extends'])
        f = self.omitted(dict(self.extended(f, self.merged(f, w), w), omit=f.get('omit')), w)
        level = str(f.get('level', fid))
        if level not in self.levels:
            raise ConfigError('%s.level: no level called %r (have %s)' % (w, level, ', '.join(self.levels)))
        changes = f.get('changes')
        if changes is not None:
            changes = str(changes)
            if changes not in earlier:
                raise ConfigError('%s.changes: no earlier sheet called %r' % (w, changes))
            if earlier[changes]['level'] != level:
                raise ConfigError('%s.changes: %r is the %s level, this sheet the %s'
                                  % (w, changes, earlier[changes]['level'], level))
        name = fid.replace('-', ' ')
        env = self.envelope(_need(f, 'envelope', w), w + '.envelope')
        n = len(env['pts'])
        norms = inner_ring(env['pts'], env['t'])[1]
        self.known = {}
        for j, (i, count, wall, _) in enumerate(env['runs']):
            self.known['env.%d' % j] = [(env['pts'][k], env['pts'][(k+1) % n], env['t'][k], norms[k])
                                        for k in range(i, i + count)]
            if wall:
                self.known[str(wall)] = self.known['env.%d' % j]
        fl = {'id': fid, 'title': f.get('title', name.upper() + (' FLOOR' if fid == level else '')),
              'tab': f.get('tab', name.title()),
              'level': level, 'scheme': f.get('scheme'), 'changes': changes, 'extends': extends,
              'hidden': self.flag(f.get('hidden', False), w + '.hidden'),
              'demolition': bool(f.get('demolition', True)),
              'unlabelled': f.get('unlabelled') == 'ok', 'gone': [], 'dims': [],
              'require': list(f.get('require') or []),
              'envelope': env,
              'walls': [], 'openings': [], 'rooms': [], 'stairs': [], 'areas': [],
              'solids': [], 'labels': [], 'dividers': [], 'zones': [], 'notes': [], 'fittings': [], 'rooflights': []}
        for i, x in enumerate(f.get('walls') or []):
            made = self.wall(x, '%s.walls[%d]' % (w, i), i)
            fl['walls'].extend(made)
            self.known.update((v['id'], [(a, b, v['t'], None) for a, b in zip(v['pts'], v['pts'][1:])]) for v in made)
        for i, x in enumerate(f.get('dividers') or []):
            ww = '%s.dividers[%d]' % (w, i)
            fl['dividers'].append((self.pt(_need(x, 'from', ww), ww), self.pt(_need(x, 'to', ww), ww)))
        for i, x in enumerate(f.get('openings') or []):
            fl['openings'].append(self.opening(x, '%s.openings[%d]' % (w, i)))
        for i, x in enumerate(f.get('rooms') or []):
            fl['rooms'].append(self.room(x, '%s.rooms[%d]' % (w, i)))
        for i, x in enumerate(f.get('zones') or []):
            ww = '%s.zones[%d]' % (w, i)
            rooms = _need(x, 'rooms', ww)
            if not isinstance(rooms, list) or not rooms:
                raise ConfigError('%s.rooms: list the rooms the zone takes in' % ww)
            fl['zones'].append({'name': str(_need(x, 'name', ww)), 'id': x.get('id'),
                                'rooms': [str(r) for r in rooms], 'sub': x.get('sub'),
                                'label': self.label(x.get('label', True), ww), 'where': ww})
        for i, x in enumerate(f.get('stairs') or []):
            fl['stairs'].append(self.stair(x, '%s.stairs[%d]' % (w, i), earlier))
        for i, x in enumerate(f.get('areas') or []):
            ww = '%s.areas[%d]' % (w, i)
            if x.get('style', 'below') not in AREA_STYLES:
                raise ConfigError('%s.style: no area style %r (have %s)'
                                  % (ww, x['style'], ', '.join(AREA_STYLES)))
            fl['areas'].append({'pts': self.shape(x, ww), 'style': x.get('style', 'below'),
                                'label': x.get('label'), 'sub': x.get('sub'),
                                'rot': self.turn(x.get('rot'), ww)})
        for i, x in enumerate(f.get('solids') or []):
            fl['solids'].append(self.shape(x, '%s.solids[%d]' % (w, i)))
        for i, x in enumerate(f.get('fittings') or []):
            fl['fittings'].append(self.fitting(x, '%s.fittings[%d]' % (w, i)))
        for i, x in enumerate(f.get('rooflights') or []):
            fl['rooflights'].append(self.rooflight(x, '%s.rooflights[%d]' % (w, i)))
        for i, x in enumerate(f.get('labels') or []):
            ww = '%s.labels[%d]' % (w, i)
            fl['labels'].append({'at': self.pt(_need(x, 'at', ww), ww),
                                 'text': self.text(_need(x, 'text', ww), ww),
                                 'rot': self.turn(x.get('rot'), ww), 'style': x.get('style', 'note')})
            if fl['labels'][-1]['style'] not in TEXT_STYLES:
                raise ConfigError('%s.style: no text style %r (have %s)'
                                  % (ww, x['style'], ', '.join(TEXT_STYLES)))
        for i, x in enumerate(f.get('gone') or []):
            fl['gone'].append([self.pt(p, '%s.gone[%d]' % (w, i)) for p in x])
        for i, x in enumerate(f.get('dims') or []):
            ww = '%s.dims[%d]' % (w, i)
            fl['dims'].append({'a': self.pt(_need(x, 'from', ww), ww),
                               'b': self.pt(_need(x, 'to', ww), ww),
                               'text': self.text(x.get('text', ''), ww),
                               'style': x.get('style') or ''})
            if fl['dims'][-1]['style'] not in DIM_STYLES:
                raise ConfigError('%s.style: no dimension style %r (have soft, calc)' % (ww, x['style']))
        fl['notes'] = f.get('notes') or notes(None, w)          # filled in once rooms are measured
        self.flat[fid] = dict(f, level=level)
        return fl

    def envelope(self, e, where):
        """Outer faces, in order. A point may carry the thickness and the
        name of the wall that LEAVES it, and how that wall curves:
        `{at: [x, y], t: 0.25, id: south, rise: 0.6}`. A curve is drawn as
        short straight pieces; `runs` says which pieces are one wall."""
        self.known = {}                             # its own points cannot be put on its own walls
        t0 = self.defaults['ext_wall']
        if isinstance(e, dict):
            t0 = self.some(e.get('t', t0), where + '.t', 'a wall')
            e = _need(e, 'points', where)
        corners, said = [], []
        for i, p in enumerate(e):
            ww = '%s[%d]' % (where, i)
            x = {}
            if isinstance(p, dict):
                x, p = p, _need(p, 'at', ww)
            elif isinstance(p, (list, tuple)) and len(p) == 3:
                x, p = {'t': p[2]}, p[:2]
            corners.append(self.pt(p, ww))
            # `open: true`: no wall leaves this point — the floor ends there, at a drop or a rise to the level beside it
            said.append((x, 0.0 if x.get('open') else self.some(x.get('t', t0), ww + '.t', 'a wall'), ww))
        if len(corners) < 2 or (len(corners) < 3 and not any(set(x) & set(('rise', 'radius', 'via')) for x, _, _ in said)):
            raise ConfigError('%s: an envelope needs at least three points' % where)
        s = 1.0 if signed_area(corners) > 0 else -1.0       # which way round it was written
        if len(corners) == 2:
            s = 1.0                                         # two curves: a rise stands to the left of each
        pts, ts, ids, runs, edges = [], [], [], [], []
        for i, (a, (x, t, ww)) in enumerate(zip(corners, said)):
            b = corners[(i+1) % len(corners)]
            L = math.hypot(b[0]-a[0], b[1]-a[1]) or 1.0
            line, curve = self.curve(x, a, b, ((b[1]-a[1])/L*s, -(b[0]-a[0])/L*s), ww)
            runs.append((len(pts), len(line) - 1, x.get('id'), curve))
            edges.append(bool(x.get('open')))
            pts += line[:-1]
            ts += [t]*(len(line) - 1)
            ids += [x.get('id')]*(len(line) - 1)
        return {'pts': pts, 't': ts, 'ids': ids, 'runs': runs, 'open': edges}

    def wall(self, x, where, i):
        """A partition, or the legs of one written as a `path`. A leg is
        straight unless it says how it curves: `rise:` or `radius:` with
        `toward:` a compass point, or `via:` a point it passes through —
        on the wall itself, or in a path on the point the leg leaves."""
        t = self.some(x.get('t', self.defaults['int_wall']), where + '.t', 'a wall')
        wid = x.get('id', 'w%d' % i)
        butt = bool(x.get('butt', False))

        def leg(lid, a, b, how, ww):
            pts, curve = self.curve(how, a, b, None, ww)
            return {'id': lid, 'a': a, 'b': b, 'pts': pts, 'arc': curve, 't': t, 'butt': butt}

        if 'path' in x:
            how = [p if isinstance(p, dict) and 'at' in p else {} for p in x['path']]
            pts = [self.pt(p['at'] if h else p, where + '.path') for p, h in zip(x['path'], how)]
            return [leg('%s.%d' % (wid, k), a, b, how[k], '%s.path[%d]' % (where, k))
                    for k, (a, b) in enumerate(zip(pts, pts[1:]))]
        return [leg(wid, self.pt(_need(x, 'from', where), where + '.from'),
                    self.pt(_need(x, 'to', where), where + '.to'), x, where)]

    def opening(self, x, where):
        kinds = [k for k in ('door', 'window', 'opening') if k in x]
        if len(kinds) != 1:
            raise ConfigError('%s: give exactly one of door, window, opening' % where)
        kind = kinds[0]
        v, pair = x[kind], bool(x.get('pair', False))
        if isinstance(v, str) and v in self.defaults['leaves']:
            width, leaf = self.op(v, pair), v
        else:
            width, leaf = self.some(v, '%s.%s' % (where, kind), 'an opening'), None
        at = self.along(x, where)
        style = x.get('style', {'door': 'swing', 'window': 'window', 'opening': 'none'}[kind])
        if style not in ('swing', 'window', 'none', 'fold', 'slide', 'frame'):
            raise ConfigError('%s.style: unknown style %r' % (where, style))
        return {'kind': kind, 'width': width, 'leaf': leaf, 'pair': pair, 'at': at,
                'wall': x.get('wall'), 'hinge': str(x.get('hinge', 'start')),
                'swing': str(x['swing']) if 'swing' in x else None,
                'face': str(x['face']) if 'face' in x else None,
                'style': style, 'id': x.get('id'), 'where': where}

    def along(self, x, where):
        """Where something sits in a wall: ('centre', None), ('point', p),
        or ('from_start' or 'from_end', a distance)."""
        at = x.get('at', 'centre')
        if isinstance(at, (list, tuple)):
            at = ('point', self.pt(at, where + '.at'))
        elif isinstance(at, dict) and ('x' in at or 'y' in at):
            at = ('point', self.pt(at, where + '.at'))
        elif isinstance(at, dict):
            (k, val), = at.items()
            if k not in ('from_start', 'from_end'):
                raise ConfigError('%s.at: use centre, [x, y], from_start or from_end' % where)
            at = (k, self.num(val, where + '.at'))
        elif at in ('centre', 'center'):
            at = ('centre', None)
        else:
            raise ConfigError('%s.at: use centre, [x, y], from_start or from_end' % where)
        if at[0] != 'point' and 'wall' not in x:
            raise ConfigError('%s: name the wall, or give at: [x, y]' % where)
        return at

    def fitting(self, x, where):
        """Something built in: `{bath: 1.7, wall: north, at: [X, 0], corner: w}`.
        The value is its width along its back, or `true` for the usual."""
        kinds = [k for k in KINDS if k in x]
        if len(kinds) != 1:
            raise ConfigError('%s: give exactly one of %s' % (where, ', '.join(sorted(KINDS))))
        kind = kinds[0]
        v = x[kind]
        size = [None if a in (None, True) else self.some(a, '%s.%s' % (where, k), 'a fitting')
                for a, k in ((v, kind), (x.get('depth'), 'depth'))]
        words = dict((k, str(x[k]).lower()) for k in ('side', 'facing', 'corner') if k in x)
        for k, word in words.items():
            if word[:1] not in 'nsew' or word not in ('n', 's', 'e', 'w') + COMPASS:
                if not (k == 'side' and word in ('in', 'out', 'left', 'right')):
                    raise ConfigError('%s.%s: use a compass point, not %r' % (where, k, x[k]))
        if 'wall' not in x and 'facing' not in words:
            raise ConfigError('%s: name the `wall:` its back is against, or say which way it is `facing:`' % where)
        return {'kind': kind, 'width': size[0], 'depth': size[1], 'at': self.along(x, where),
                'wall': x.get('wall'), 'side': words.get('side'), 'facing': words.get('facing'),
                'corner': words.get('corner'), 'flip': bool(x.get('flip', False)),
                'label': None if x.get('label') is None else str(x['label']), 'where': where}

    def rooflight(self, x, where):
        """A light in the ceiling over this sheet's floor, seen from below:
        `{at: [x, y], w: 0.8, h: 1.0}` — its middle, how far it runs east
        to west and north to south, and `rot:` if it is turned. `id:` is
        what notes and `omit` call it; `label:` is written beside it."""
        if not isinstance(x, dict) or set(x) - set(('at', 'w', 'h', 'rot', 'label', 'id')):
            raise ConfigError('%s: a rooflight is {at: [x, y], w:, h:}, with id:, label: and rot: if wanted' % where)
        (cx, cy), rot = self.pt(_need(x, 'at', where), where + '.at'), self.turn(x.get('rot'), where) or 0.0
        w, h = [self.some(_need(x, k, where), '%s.%s' % (where, k), 'a rooflight') for k in ('w', 'h')]
        c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
        pts = [(cx + dx*c - dy*s, cy + dx*s + dy*c) for dx, dy in ((-w/2, -h/2), (w/2, -h/2), (w/2, h/2), (-w/2, h/2))]
        if x.get('id') is not None and not NAME.match(str(x['id'])):
            raise ConfigError('%s.id: %r — use letters, digits, - and _ only' % (where, x['id']))
        return {'id': None if x.get('id') is None else str(x['id']), 'at': (cx, cy), 'w': w, 'h': h, 'rot': rot, 'pts': pts,
                'label': None if x.get('label') is None else str(x['label']), 'where': where}

    def room(self, x, where):
        expect = x.get('expect') or {}
        if not isinstance(expect, dict) or set(expect) - set(('w', 'h', 'area')):
            raise ConfigError('%s.expect: give any of w, h and area' % where)
        return {'name': str(_need(x, 'name', where)), 'id': x.get('id'),
                'expect': dict((k, (self.num(v, '%s.expect.%s' % (where, k)), str(v))) for k, v in expect.items()),
                'at': self.pt(_need(x, 'at', where), where + '.at'),
                'sub': x.get('sub'), 'rot': self.turn(x.get('rot'), where), 'size': x.get('size'),
                'dims': x.get('dims', True), 'zone': bool(x.get('zone', False)),
                'label': self.label(x.get('label', True), where),
                'dx': self.num(x.get('dx', 0), where + '.dx'),
                'dy': self.num(x.get('dy', 0), where + '.dy'), 'where': where}

    def flag(self, v, where):
        if not isinstance(v, bool):
            raise ConfigError('%s: true or false, not %r' % (where, v))
        return v

    def label(self, v, where):
        """Where a room's label goes: True, wherever it fits inside; a
        compass side, in the margin on that side with a line to the room;
        False, nowhere."""
        if isinstance(v, bool) or v in COMPASS:
            return v
        raise ConfigError('%s.label: use true, false or one of %s' % (where, ', '.join(COMPASS)))

    def stair(self, x, where, earlier):
        if 'ref' in x:
            fid, _, sid = str(x['ref']).partition('.')
            src = [s for s in earlier.get(fid, {}).get('stairs', []) if s['id'] == sid]
            if not src:
                raise ConfigError('%s.ref: no stair %r on an earlier sheet' % (where, x['ref']))
            st = dict(src[0], ref=fid)                  # the sheet it is drawn on, which this one cannot do without
            st['show'] = x.get('show', 'above')
            st['label'] = x.get('label', 'DN' if st['show'] == 'above' else 'UP')
            return st
        path = [self.pt(p, where + '.path') for p in _need(x, 'path', where)]
        legs = len(path) - 1
        if legs < 1:
            raise ConfigError('%s.path: a stair needs a foot and a head' % where)

        def per_leg(key, default=None):
            v = x.get(key, default)
            if v is None:
                return [None]*legs
            if not isinstance(v, (list, tuple)):
                v = [v]*legs
            if len(v) != legs:
                raise ConfigError('%s.%s: one value per leg (%d)' % (where, key, legs))
            return [None if a is None else self.num(a, '%s.%s' % (where, key)) for a in v]

        turns = x.get('turns', ['landing']*(legs-1))
        if len(turns) != legs - 1:
            raise ConfigError('%s.turns: one per corner (%d)' % (where, legs-1))
        tn, reach = [], []
        for t in turns:
            if t == 'landing':
                tn.append(0)
                reach.append(False)
            elif isinstance(t, dict) and 'winders' in t:
                tn.append(int(self.num(t['winders'], where + '.turns')))
                reach.append(bool(t.get('reach')))
            else:
                raise ConfigError('%s.turns: use landing or {winders: n}' % where)
        going = self.num(x.get('going', self.defaults['going']), where + '.going')
        if going <= 0:
            raise ConfigError('%s.going: a tread is some way deep, not %g' % (where, going))
        width = per_leg('width', 0.9)
        treads = [None if a is None else int(round(a)) for a in per_leg('treads')]
        if [a for a in width if a is None or a <= 0]:
            raise ConfigError('%s.width: a flight is some way wide' % where)
        if [a for a in treads if a is not None and not 0 <= a <= MOST_TREADS]:
            raise ConfigError('%s.treads: none, or up to %d to a leg' % (where, MOST_TREADS))
        if [n for n in tn if not 0 <= n <= 6]:
            raise ConfigError('%s.turns: up to six winders in a corner' % where)
        cut = x.get('cut_risers')
        show = x.get('show', 'all' if cut is None else 'below')
        return {'id': str(x.get('id', 'stair')), 'path': path,
                'width': width, 'treads': treads,
                'going': going,
                'turns': tn, 'reach': reach, 'cut': None if cut is None else self.num(cut, where + '.cut_risers'),
                'show': show, 'label': x.get('label', 'UP'), 'where': where}


MOST = 400000                # values in a house file, counting one that is repeated each time it is


def _weigh(raw, path):
    """Refuse a file that is small as written and vast as read: an anchor
    repeated inside an anchor, ten deep, is a few lines of YAML and more
    values than there is memory for. Counted, never built."""
    n, stack = 0, [raw]
    while stack:
        v = stack.pop()
        n += 1
        if n > MOST:
            raise ConfigError('%s: too much to be a house file — is an anchor repeated inside itself?' % path)
        if isinstance(v, dict):
            stack.extend(v.values())
        elif isinstance(v, list):
            stack.extend(v)


def load(path):
    with open(path) as fh:
        return loads(fh.read(), path)


def loads(text, path='<house>'):
    """A house from the text of its file. Whatever is wrong with the file
    is a ConfigError: a house file comes from anywhere, and a command given
    one that is not laid out as a house says so in a line."""
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ConfigError('%s: not YAML that can be read — %s' % (path, ' '.join(str(e).split())[:300]))
    except RecursionError:
        raise ConfigError('%s: nested too deep to be a house file' % path)
    _weigh(raw, path)
    try:
        return Loader(raw, path).house()
    except ConfigError:
        raise
    except RecursionError:
        raise ConfigError('%s: nested too deep to be a house file' % path)
    except (AttributeError, TypeError, KeyError, IndexError, ValueError) as e:
        # a list where a mapping goes, a number where a list goes: said, if not as well as a ConfigError of its own
        raise ConfigError('%s: not laid out as a house file is — %s' % (path, e))
