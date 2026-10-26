# -*- coding: utf-8 -*-
"""A house, solved: the one thing every output reads.

`solve(path)` loads a house file and works out each of its sheets once —
the plan's geometry, its stairs, where every label goes, the names its
notes may use, what is said beside it. The drawing, the report, the page,
the marks brief and `at` all take a Sheet and work nothing out again.
"""
import math
import os
from shapely.errors import ShapelyError
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union
from . import model, geom, stairs, labels, report, render, outline

def house_file(path):
    """The house file a path names: itself, or `house.yaml` in a folder."""
    return os.path.join(path, 'house.yaml') if os.path.isdir(path) else path


def stem(path):
    """A house's short name: its folder, or its file when it has none."""
    return model.stem(house_file(path))


def beside(path, name):
    """A file kept with a house: in its folder, or next to a bare file."""
    path = house_file(path)
    if os.path.basename(path) == 'house.yaml':
        return os.path.join(os.path.dirname(path), name)
    return '%s.%s' % (os.path.splitext(path)[0], name)


def metrics(plan):
    """Room sizes as names — KITCHEN_w, KITCHEN_h, KITCHEN_area — for notes."""
    out = {'gross': plan.gross, 'internal': plan.internal}
    for r in plan.rooms:
        key = geom.key(r)
        if key:
            out.update({key + '_w': r['w'], key + '_h': r['h'], key + '_area': r['area']})
    for z in plan.zones:
        key = geom.key(z)
        if key and not z['own']:
            out[key + '_area'] = z['area']
    for r in plan.rooflights:                       # by its id, where it has one: a note may say how big it is
        key = geom.key({'id': r['id'], 'name': ''})
        if key and key + '_w' in out:
            plan.warn('%s: a rooflight and a room are both called %s — notes cannot tell them apart' % (r['where'], r['id']))
        elif key:
            out.update({key + '_w': r['w'], key + '_h': r['h'], key + '_area': r['w']*r['h']})
    return out


SLIVER = 0.01                   # what is thinner than twice this is not a wall or a floor


def _lumps(g):
    """A difference of two shapes with the slivers taken off, or None."""
    g = g.buffer(-SLIVER, join_style=2).buffer(SLIVER, join_style=2)
    return None if g.is_empty else g


class Sheet(object):
    """One drawing. A plan sheet has a `plan` (geom.Plan) and everything
    worked out from it; the outline sheet has none. Either way `lines` and
    `vb` are the drawing and `info` is what is said beside it."""
    kind = 'plan'
    scale = 1.5                 # SVG units per pixel when written as a file

    def __init__(self, house, plan, extra, base=None):
        fl = plan.spec
        self.house, self.plan, self.base = house, plan, base
        plan.flights = []           # each stair's rise and going, as the report gives them
        self.id, self.tab, self.title = fl['id'], fl['tab'], fl['title']
        self.level, self.scheme, self.hidden = fl['level'], fl['scheme'], fl['hidden']
        self.names = dict(extra, **metrics(plan))
        self.gained = self.demolition = None
        if base is not None:
            # what this sheet does to the one it changes: the floor it adds
            # and the walls it takes away, neither written down anywhere
            self.gained = _lumps(plan.E.difference(base.plan.E))
            if fl['demolition']:
                self.demolition = _lumps(base.plan.solid.difference(plan.solid))
            self.names.update(base_gross=base.plan.gross, gained=plan.gross - base.plan.gross)
        self.scope = house['scope'].child(**self.names)
        self.stairs = [self._flight(st) for st in fl['stairs']]
        for g in self.stairs:
            g['void'], g['rail'] = stairs.well(g, plan.solid)
        self.labels = self._place()
        self.info = report.info(plan, self.scope)
        self._drawn = None

    def _flight(self, st):
        """A stair drawn, and what it climbs. Its riser is given, or is the
        height of the storey it climbs over its risers; with its going that
        is its pitch, held to Approved Document K. On the level above, with
        the floor's depth known, the well is as far back from the head as
        there would be less than HEADROOM over the pitch line: below that the
        floor runs over the flight."""
        g = stairs.build(st)
        heights, levels = self.house['heights'], self.house['levels']
        H = heights.get(st['level'], {}).get('height')
        R = st['riser'] or (H / g['risers'] if H else None)
        if st.get('ref') is not None:
            up = levels.index(st['level']) + 1 if st['level'] in levels else len(levels)
            fd = heights[levels[up]]['floor_depth'] if up < len(levels) else None
            if st['show'] == 'above' and H and fd is not None and R:
                g = stairs.build(dict(st, open_from=(H - fd - stairs.HEADROOM) / R - 1))
            return g
        plan = self.plan
        if R is None or not g['going']:
            return g
        G, where = g['going'], st['where']
        pitch = math.degrees(math.atan2(R, G))
        plan.flights.append({'id': st['id'], 'risers': g['risers'], 'riser': round(R, 4), 'going': round(G, 4),
                             'pitch': round(pitch, 1), '2R+G': round(2*R + G, 4)})
        if st['riser'] and H and abs(R*g['risers'] - H) > 0.015:
            plan.warn('%s: %d risers of %.0f mm climb %.3f m, and the %s level is %.3f m high'
                      % (where, g['risers'], R*1000, R*g['risers'], st['level'], H))
        why = 'a stair built before the regulations, or a drawing error'
        if pitch > stairs.STEEPEST:
            plan.warn('%s: the stair pitches at %.1f° — steeper than %g°: %s'
                      % (where, pitch, stairs.STEEPEST, why))
        lo, hi = stairs.STRIDE
        if not lo <= 2*R + G <= hi:
            plan.warn('%s: twice the riser and the going is %.0f mm (riser %.0f, going %.0f), outside %.0f–%.0f: %s'
                      % (where, (2*R + G)*1000, R*1000, G*1000, lo*1000, hi*1000, why))
        return g

    def _place(self):
        """Each room's label as (items, x, y), in the plan's room order."""
        plan, fl = self.plan, self.plan.spec
        blocks = [Polygon(a['pts']) for a in fl['areas'] if a['style'] == 'fitting']
        blocks += [g[k] for g in self.stairs for k in ('block', 'void') if g[k] is not None]
        blocks += [f['floor'] for f in plan.fittings]
        for r in plan.rooflights:
            blocks.append(r['shape'])
            if r['label']:
                blocks.append(labels.text_box(render.rooflight_label(r), r['label'], render.TEXT['note'], None))
        swings = [geom.leaf_shape(*leaf)[2] for o in plan.openings for leaf in o.get('leaves', [])]
        swings = [(b.bounds, b) for b in swings]
        blocks += [labels.text_box(lb['at'], lb['text'], render.TEXT[lb['style']], lb['rot']) for lb in fl['labels']]
        if self.demolition is not None:
            blocks.append(self.demolition)
        blocks = [(b.bounds, b) for b in blocks if not b.is_empty]
        # how far the building and what is drawn round it run: a label in the margin stands past both
        extent = unary_union([plan.E] + [Polygon(a['pts']) for a in fl['areas']])
        out, margin, self.leaders = [], [], []
        for r in plan.rooms + [z for z in plan.zones if not z['own']]:      # zones last, off the rooms' own labels
            if r['label'] is False:                 # measured, and named nowhere on the sheet
                continue
            if r['sub'] is not None:
                r['sub'] = self.scope.child(w=r['w'], h=r['h'], area=r['area']).text(r['sub'])
            if r['label'] is not True:              # in the margin on that side, with a line to the room
                items, x, y, leader = labels.outside(r, r['label'], extent, self.house.get('front') == r['label'])
                margin.append((len(out), r['label'], leader))
            else:
                # a label goes inside its room, so only what reaches the room can be in its way
                x0, y0, x1, y1 = r['face'].bounds
                near = lambda bs: [b for (bx0, by0, bx1, by1), b in bs if bx0 <= x1 and bx1 >= x0 and by0 <= y1 and by1 >= y0]
                found = False
                for these in (near(blocks + swings), near(blocks)):     # off the door swings; else over one
                    items, x, y, found = labels.place(r, unary_union(these) if these else box(0, 0, 0, 0))
                    if found:
                        break
                if not found:                       # too small or too busy: in the margin nearest it, with a line
                    side = labels.nearest_side(r, extent)
                    items, x, y, leader = labels.outside(r, side, extent, self.house.get('front') == side)
                    margin.append((len(out), side, leader))
                    _, ix, iy, inside = labels.place(dict(r, dx=0.0, dy=0.0, size='small'), box(0, 0, 0, 0))
                    x0, y0, x1, y1 = r['rect']
                    hint = (' or `size: small, dx: %.2f, dy: %.2f` sets it inside, over what is in the way'
                            % (ix - (x0 + x1)/2.0, iy - (y0 + y1)/2.0)) if inside else ''
                    plan.warn('%s: no room inside for the label %s: it is set in the %s margin — `label: %s` keeps it there%s'
                              % (r['where'], r['name'], side, side, hint), 'info')
                    out.append((items, x, y))
                    continue
                for dx, dy, t, cls, rot in items:
                    b = labels.text_box((x+dx, y+dy), t, cls, rot)
                    blocks.append((b.bounds, b))
            out.append((items, x, y))
        # labels in one margin are moved along it clear of each other, and each one's line follows it
        named = [Polygon(a['pts']) for a in fl['areas'] if a['label']]
        moved = labels.spread([(side, out[i][1], out[i][2], out[i][0]) for i, side, _ in margin])
        for (i, side, (a, tip)), (x, y) in zip(margin, moved):
            leader = ((a[0] + x - out[i][1], a[1] + y - out[i][2]), tip)
            out[i] = (out[i][0], x, y)
            if not any(LineString(leader).crosses(p) for p in named):       # no line through other writing
                self.leaders.append(leader)
        return out

    def _draw(self):
        return render.draw(self)

    @property
    def lines(self):
        if self._drawn is None:
            self._drawn = self._draw()
        return self._drawn[0]

    @property
    def vb(self):
        if self._drawn is None:
            self._drawn = self._draw()
        return self._drawn[1]

    @property
    def issues(self):
        return self.plan.issues if self.plan is not None else []

    def svg(self):
        return render.standalone(self.lines, self.vb, scale=self.scale)


class Outline(Sheet):
    """The dimensioned outline sheet: each envelope, every face measured."""
    kind = 'outline'
    scale = 3.0

    def __init__(self, house, plans):
        self.house, self.plan, self._plans = house, None, plans
        self.id, self.tab, self.title = 'outline', 'Outline', 'OUTLINE'
        self.level = self.scheme = self.base = None
        self.hidden = False
        self.info = outline.info(house, plans)
        self._drawn = None

    def _draw(self):
        return outline.draw(self.house, self._plans)


class Solved(object):
    def __init__(self, house, sheets, path):
        self.house, self.sheets, self.path = house, sheets, path
        self.name = stem(path)

    def plans(self):
        """The sheets that are plans, in the house file's order."""
        return [s for s in self.sheets if s.plan is not None]

    def shown(self):
        """The sheets that have a tab and are sent: every one not `hidden`."""
        return [s for s in self.sheets if not s.hidden]

    def sheet(self, sid):
        for s in self.sheets:
            if s.id == sid and s.plan is not None:
                return s
        raise ValueError('no sheet called %r (have %s)' % (sid, ', '.join(s.id for s in self.plans())))

    def issues(self):
        """(sheet id, level, message) for everything found, in sheet order."""
        return [(s.id, lv, m) for s in self.plans() for lv, m in s.plan.issues]


def solved(house, path='<house>'):
    """Solve a house that model has already read."""
    plans = {}
    for fl in house['sheets']:
        plans[fl['id']] = _worked(fl['id'], geom.Plan, fl, house)
    extra = dict(('gross_' + k.replace('-', '_'), p.gross) for k, p in plans.items())
    sheets, done = [], {}
    if len(plans) > 1 or house['outline']:
        sheets.append(_worked('outline', Outline, house, plans))
    for fl in house['sheets']:
        done[fl['id']] = _worked(fl['id'], Sheet, house, plans[fl['id']], extra, done.get(fl['changes']))
        sheets.append(done[fl['id']])
    first = next((sh.plan for sh in sheets if sh.plan is not None), None)
    for where, k in house.get('unknown') or []:     # said where every sheet's checks are read, once
        first.warn('%s: `%s` is not a key the engine reads, so it does nothing' % (where, k))
    if house.get('connections'):
        connected(house['connections'], [sh.plan for sh in sheets if sh.plan is not None and sh.plan.spec['changes'] is None])
    return Solved(house, sheets, path)


def _called(r):
    """What a room may be called in `connections`: its name or its id, in any case."""
    if r is None or r.get('name') is None:
        return set()
    return set(str(v).lower() for v in (r['name'], r['id']) if v is not None)


def _fits(c, k):
    """Whether a link is of the kind a connection asks for."""
    if c['kind'] == 'window':
        return k['side'] is not None
    if k['kind'] == 'window' or k['style'] == 'frame':
        return False
    return c['kind'] == 'way' or c['kind'] == k['kind']


def _between(k):
    names = [r['name'] if r else 'a space with no room in it' for r in k['rooms']]
    return names[0] if k['side'] else '%s and %s' % tuple(names)


def connected(wanted, plans):
    """The connections the house file expects, read off its source,
    against what the as-built sheets — the ones that change nothing —
    have drawn. Each one missing, extra, or between the wrong rooms is
    reported, and a door that swings or is hung the wrong way."""
    if not plans:
        return
    mine = dict((id(p), []) for p in plans)
    for c in wanted:
        names = [n.lower() for n in c['rooms'] if n.lower() != 'outside']
        home = next((p for p in plans if all(any(n in _called(r) for r in p.rooms) for n in names)), None)
        if home is None:
            lost = [n for n in c['rooms'] if n.lower() != 'outside' and not any(n.lower() in _called(r) for p in plans for r in p.rooms)]
            plans[0].warn('%s: no as-built sheet has %s' % (c['where'], (
                'a room called %s' % ' or '.join(lost)) if lost else 'both %s and %s' % c['rooms']), 'error')
            continue
        mine[id(home)].append(c)
    for p in plans:
        want = mine[id(p)]
        if not want:
            continue
        have = [k for k in p.links if k['side'] is not None or (k['kind'] != 'window' and k['style'] != 'frame')]

        def same(c, k):
            got = [_called(r) if r is not OUTSIDE else set(['outside']) for r in k['rooms']]
            if c['kind'] == 'window':
                return c['rooms'][0].lower() in got[0] and c['side'] == k['side']
            a, b = [n.lower() for n in c['rooms']]
            return (a in got[0] and b in got[1]) or (b in got[0] and a in got[1])
        left = list(have)
        unmet = []
        for c in want:
            k = next((k for k in left if _fits(c, k) and same(c, k)), None)
            if k is None:
                unmet.append(c)
                continue
            left.remove(k)
            o = k['opening']
            if c['into'] and k['into'] is not None and c['into'].lower() not in _called(k['into']):
                p.warn('%s: the door between %s swings into %s, not %s (%s)'
                       % (c['where'], _between(k), k['into']['name'] or 'a space with no room in it', c['into'], o['where']))
            if c['hinge'] and k['hinge'] and c['hinge'] != k['hinge']:
                p.warn('%s: the door between %s is hung on its %s side, not its %s (%s)'
                       % (c['where'], _between(k), WORDS[k['hinge']], WORDS[c['hinge']], o['where']))
        for c in unmet:
            names = set(n.lower() for n in c['rooms'])
            k = next((k for k in left if _fits(c, k) and names & set().union(*[
                _called(r) if r is not OUTSIDE else set(['outside']) for r in k['rooms']])), None)
            what = 'window' if c['kind'] == 'window' else 'way' if c['kind'] == 'way' else c['kind']
            if k is not None:
                left.remove(k)
                if c['kind'] == 'window':
                    p.warn('%s: the window in %s looks %s, not %s (%s)'
                           % (c['where'], c['rooms'][0], WORDS[k['side']], WORDS[c['side']], k['opening']['where']))
                else:
                    p.warn('%s: the %s is drawn between %s, not %s and %s (%s)'
                           % (c['where'], k['kind'], _between(k), c['rooms'][0], c['rooms'][1], k['opening']['where']))
            elif c['kind'] == 'window':
                p.warn('%s: no window in %s looks %s' % (c['where'], c['rooms'][0], WORDS[c['side']]))
            else:
                p.warn('%s: no %s between %s and %s' % (c['where'], 'way through' if what == 'way' else what,
                                                        c['rooms'][0], c['rooms'][1]))
        for k in left:
            p.warn('%s: the %s %s is not in `connections`'
                   % (k['opening']['where'], k['kind'], ('in %s, looking %s' % (_between(k), WORDS[k['side']]))
                      if k['side'] else 'between ' + _between(k)))


WORDS = {'n': 'north', 'e': 'east', 's': 'south', 'w': 'west', 'pair': 'pair'}
OUTSIDE = geom.OUTSIDE


def _worked(sid, make, *args):
    """One sheet worked out. A house file comes from anywhere, so whatever
    it gets wrong that model let through is still a ValueError that names
    the sheet — said in a line, not a page of where the engine was."""
    try:
        return make(*args)
    except ValueError as e:
        raise ValueError(str(e) if str(e).startswith('sheet %s: ' % sid) else 'sheet %s: %s' % (sid, e))
    except (ArithmeticError, TypeError, KeyError, IndexError, AttributeError, ShapelyError, RecursionError) as e:
        raise ValueError('sheet %s: could not be worked out — %s' % (sid, e or type(e).__name__))


KEPT = {}                       # house file -> (its text, that solved): the last few asked for


def solve(path):
    """Everything about the house at `path` (a folder or a file). A house
    whose file reads as it did the last time is not worked out again: a
    command solves one more than once, and an agent's tools ask about the
    same house many times between changes to it."""
    path = house_file(path)
    with open(path) as fh:
        text = fh.read()
    key = os.path.abspath(path)
    if key in KEPT and KEPT[key][0] == text:
        return KEPT[key][1]
    s = solved(model.loads(text, path), path)
    if len(KEPT) >= 8:
        KEPT.clear()
    KEPT[key] = (text, s)
    return s


def solves(text):
    """The same from the text of a house file."""
    return solved(model.loads(text))
