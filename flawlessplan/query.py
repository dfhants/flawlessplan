# -*- coding: utf-8 -*-
"""Asking a solved sheet what it has at a place, in the house file's own
names — for after a reader knows what a mark, or a remark, is about.
"""
from shapely.geometry import LineString, Point, Polygon, box as rect


def at(sheet, target, reach=0.6):
    """What a sheet has at a point (x, y) or in a box (x0, y0, x1, y1):
    (distance, description), nearest first; 0 for what a box takes in."""
    plan = sheet.plan
    if len(target) == 2:
        t = Point(target)
    else:
        t, reach = rect(*target), 0.0
    out = []

    def add(g, text):
        d = t.distance(g)
        if d <= reach:
            out.append((d, text))

    for r in plan.rooms:
        if r['face'].intersects(t):
            out.append((0.0, 'room %s%s (%.2f × %.2f m, %.1f m²) — %s'
                        % (r['name'], ' [%s]' % r['id'] if r['id'] else '', r['w'], r['h'], r['area'], r.get('where', ''))))
    for z in plan.zones:
        if z['face'].intersects(t):
            out.append((0.0, 'zone %s (%s; %.1f m²)' % (z['name'], ', '.join(r['name'] for r in z['rooms']), z['area'])))
    for o in plan.openings:
        h = o['host']
        what = {'window': 'window', 'door': 'door'}.get(o['kind'], 'opening')
        if o['style'] not in ('swing', 'window'):
            what += ' (%s)' % o['style']
        add(LineString(h.run(o['s0'], o['s1'])).buffer(h.t/2.0),
            '%s %.2f m wide in wall %s, centre (%.2f, %.2f) — %s'
            % (what, o['width'], h.name, o['centre'][0], o['centre'][1], o.get('where', '')))
    for w in plan.spec['walls']:
        add(LineString(w['pts']).buffer(w['t']/2.0),
            'partition %s, %.0f mm, (%.2f, %.2f) to (%.2f, %.2f)%s'
            % ((w['id'], w['t']*1000) + tuple(w['a']) + tuple(w['b']) + (_curved(w['arc']),)))
    for h in plan.env_hosts:
        if h.open:
            add(LineString(h.pts), 'open edge %s, where the floor ends and no wall stands, (%.2f, %.2f) to (%.2f, %.2f)%s'
                % ((h.name,) + tuple(h.face[0]) + tuple(h.face[1]) + (_curved(h.arc),)))
            continue
        add(LineString(h.pts).buffer(h.t/2.0),
            'outside wall %s, %.0f mm, face (%.2f, %.2f) to (%.2f, %.2f)%s'
            % ((h.name, h.t*1000) + tuple(h.face[0]) + tuple(h.face[1]) + (_curved(h.arc),)))
    for f in plan.fittings:
        add(f['floor'], '%s, %.2f × %.2f m%s — %s' % (f['kind'], f['w'], f['d'],
                                                      ' against wall %s' % f['host'].name if f['host'] else '', f['where']))
    for r in plan.rooflights:
        add(r['shape'], 'rooflight%s, %.2f × %.2f m%s — %s' % (' %s' % r['id'] if r['id'] else '', r['w'], r['h'],
                                                              ', over %s' % r['over'] if r['over'] else '', r['where']))
    for i, s in enumerate(plan.solids):
        c = s.centroid
        add(s, 'solid masonry (solids[%d]) round (%.2f, %.2f), %.2f m²' % (i, c.x, c.y, s.area))
    for st, b in zip(plan.spec['stairs'], sheet.stairs):
        if b['block'] is not None:
            add(b['block'], 'stair %s (%d risers; treads per leg %s)' % (st['id'], b['risers'], st['treads']))
    for a in plan.spec['areas']:
        if a.get('label'):
            add(Polygon(a['pts']), 'area "%s" (%s)' % (a['label'], a['style']))
    if not plan.E.intersects(t):
        out.append((0.0, 'outside the building'))
    return sorted(out, key=lambda x: x[0])


def _curved(arc):
    return ', curved to a radius of %.2f m' % arc['r'] if arc else ''


def lines(found):
    """The same as lines of text, the distance first where there is one."""
    return ['%s%s' % ('%.2f m — ' % d if d > 0.005 else '', text) for d, text in found] or ['nothing drawn there']
