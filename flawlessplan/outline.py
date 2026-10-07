# -*- coding: utf-8 -*-
"""The outline sheet: each envelope on a metre grid with every face
dimensioned, beside each sheet's gross area. Nothing on it is written by
hand.
"""
import math
from .render import Canvas, path, n2, dim, U

GAP = 5.20               # clear space between one plan and the next
OFF = 0.60               # how far a face's dimension stands off it


def _distinct(house):
    """Sheets with an outline no earlier sheet has, of the ones that show."""
    seen, out = [], []
    for f in [f for f in house['sheets'] if not f['hidden']]:
        key = [(round(x, 3), round(y, 3)) for x, y in f['envelope']['pts']]
        if key not in seen:
            seen.append(key)
            out.append(f['id'])
    return out


def draw(house, plans):
    cfg = house['outline']
    ids = cfg.get('sheets') or _distinct(house)
    missing = [i for i in ids if i not in plans]
    if missing:
        raise ValueError('outline.sheets: no sheet called %s' % ', '.join(missing))

    bounds = [plans[i].E.bounds for i in ids]
    x0, y0 = min(b[0] for b in bounds), min(b[1] for b in bounds)
    x1, y1 = max(b[2] for b in bounds), max(b[3] for b in bounds)
    pitch = (x1 - x0) + GAP
    sh = Canvas()

    for k, fid in enumerate(ids):
        plan = plans[fid]
        e = plan.spec['envelope']
        pts, n = e['pts'], len(e['pts'])
        sh.out('<g transform="translate(%s 0)">' % n2(k*pitch*U))
        cid = 'outline-%s' % fid
        sh.out('<defs><clipPath id="%s"><path d="%s"/></clipPath></defs>' % (cid, path(pts)))
        sh.out('<path d="%s" class="floor"/>' % path(pts))
        sh.out('<g clip-path="url(#%s)">' % cid)
        for i in range(int(math.floor(x0)), int(math.ceil(x1)) + 1):
            sh.line((i, y0), (i, y1), 'grid5' if i % 5 == 0 else 'grid')
        for j in range(int(math.floor(y0)), int(math.ceil(y1)) + 1):
            sh.line((x0, j), (x1, j), 'grid5' if j % 5 == 0 else 'grid')
        sh.out('</g>')
        sh.out('<path d="%s" class="env"/>' % path(pts))
        bx0, by0, bx1, by1 = plan.E.bounds
        sh.text(((x0+x1)/2.0, y0 - 2.70), plan.spec['title'], 'sheetname')
        sh.text(((x0+x1)/2.0, y0 - 2.22), '%.1f m² gross external' % plan.gross, 'caption')
        for h in plan.env_hosts:
            a, b = h.face
            length = math.hypot(b[0]-a[0], b[1]-a[1])
            if length < 0.5:
                continue
            off, said = OFF, '%.2f' % length
            if h.arc:                               # a curve: across its ends, clear of how far it stands out, and its radius
                off += max(0.0, -h.arc['rise']*h.turn)
                said += ' · r %.2f' % h.arc['r']
            out = (-h.inward[0]*off, -h.inward[1]*off)
            dim(sh, (a[0]+out[0], a[1]+out[1]), (b[0]+out[0], b[1]+out[1]), said, '')
        dim(sh, (bx0, y0 - 1.45), (bx1, y0 - 1.45), '%.2f overall' % (bx1 - bx0), 'calc')
        dim(sh, (x0 - 1.80, by0), (x0 - 1.80, by1), '%.2f overall' % (by1 - by0), 'calc')
        sh.out('</g>')

    # ---- each sheet's gross area
    tx, ty = len(ids)*pitch - GAP + 2.60 + x0, y0 - 2.30
    sh.text((tx, ty), 'GROSS AREA', 'sheetname', anchor='start')
    row = ty + 0.92
    for fid in ids:
        sh.text((tx, row), '%-10s %.1f m²' % (plans[fid].spec['tab'], plans[fid].gross),
                'figure', anchor='start')
        row += 0.56
    vx, vy = x0 - 3.2, y0 - 3.6
    vw = (tx + 6.6) - vx
    vh = max(y1 + 1.6, row + 0.4) - vy
    return sh.buf, (vx*U, vy*U, vw*U, vh*U)


def info(house, plans):
    """What goes beside the outline sheet: its notes, not drawn on it."""
    from .model import notes, NOTE_GROUPS
    cfg = house['outline']
    n = notes(cfg.get('notes'), 'outline')
    text = house['scope'].text
    ids = cfg.get('sheets') or _distinct(house)
    return {'title': 'OUTLINE', 'summary': text(n['summary']),
            'figures': [(plans[f].spec['tab'], '%.1f m² gross' % plans[f].gross) for f in ids],
            'rooms': [],
            'groups': [(k, head, [text(t) for t in n[k]]) for k, head in NOTE_GROUPS if n[k]]}
