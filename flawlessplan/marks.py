# -*- coding: utf-8 -*-
"""What the owner drew on a sheet, laid out for whoever has to read it.

This module does not interpret. Deciding that a shaft and a V are an arrow,
and that the arrow is about its tip, is the reader's job; code that guesses
it gets it wrong quietly. The reader's first mistake was a different one:
it looked up where the ink was before it had looked at what the ink was.
So the output is built to be looked at first:

  pictures   one image per cluster of ink, two panels of the same view —
             the drawing as it is, and the drawing with the ink on it — so
             what is ink and what is drawing can be told apart at a glance
             and what the ink covers can still be seen. The drawing keeps
             its own colours: greying it hid the very faults being marked.
             Both panels carry the same metre ticks, so a point seen in the
             picture can be read off and asked about.
  strokes    in the order drawn, numbered as in the pictures, each with its
             path, when it was drawn and what other ink it touches

What the plan has at a point, by the names the house file uses, is query.at
— for after the reader knows what is meant.

The owner's ink is INK. What this module adds on top is NOTE: a dot and a
number where each stroke starts, a ring where it ends, the ticks. No
drawing uses either colour.

A mark has a life: it is open until whoever built it in says so, and then
it is resolved — kept, with when and how it was dealt with and the sheets
it was applied to, but out of the way. Only the owner deletes one, on the
page. A mark is known by its id, which is its time where it has no other.
"""
import datetime
import hashlib
import json
import math
import os
import re
import threading
import time
from shapely.geometry import LineString, Point, Polygon
from . import query, render

INK = '#D0199B'             # the owner's marks, and nothing else
NOTE = '#0A6CFF'            # stroke numbers, added here
DONE = '#8A9590'            # ink that has been dealt with, when it is asked for
LIFE = ('status', 'resolved', 'how', 'applied')     # what resolving a mark writes on it
KINDS = ('pen', 'note', 'box')                      # a stroke; a comment on a pin; a comment on a box
LOCK = threading.Lock()     # one writer of a marks file at a time, in this process
ID = re.compile(r'^[\w-]{1,40}\Z')
JOIN_M = 1.0                # ink this close shares a picture
NEAR = 0.5                  # what is this close to a pin is what it is on
U = render.U

HOW = """## How to read this

These are the marks still open, unless resolved ones were asked for: those are grey in the pictures \
and say how they were dealt with. Each mark has an id, in backticks after its number. A stroke is ink; \
a comment is a numbered pin or a box, with its words listed beside the pictures and below. A comment \
carries what it is on — its room and the doors, walls and fittings at it, read off the plan when it was \
made (`on:`) — and the version of the house file it was made on. Read both before acting on it: where \
the version is not the file's now, the picture sets the drawing it was made on beside the drawing as it \
is, and what it pointed at may already have moved or been fixed. When you have built a mark in, reply \
to it with `resolve_marks` in the same turn: the line you give is your reply, the owner reads it under \
the mark, and it resolves it — with the sheets it was applied to, where the owner drew on one sheet and \
meant others too. A reply from the owner on a resolved mark opens it again: read it as what they \
still want.

1. **Open the pictures first, and read the ink as signs.** Each picture is one view twice: LEFT the \
drawing as it is, RIGHT the same with the owner's ink. Strokes drawn seconds apart and touching are \
usually one sign — a shaft and a V are an arrow, two strokes through a point a cross. Decide what each \
sign is and what it is about (an arrow: what its tip touches; a ring: what is inside it) before reading \
any coordinate. Where the ink lies is not what it means.
2. **What is ink and what is drawing.** Magenta is the owner's ink and nothing else. Blue is added by \
this brief: a dot and number where a stroke starts, a ring where it ends, and the metre ticks round \
each panel. Everything else is the drawing, in its own colours. Anything in the right panel that is \
not in the left is ink or annotation.
3. **Then look closer at what the sign is about.** Read the place off the ticks and render it large: \
`python -m flawlessplan crop HOUSE SHEET X0 Y0 X1 Y1 --marks` gives the same two panels for any box — \
a metre or less across shows faults a wider view hides. `python -m flawlessplan at HOUSE SHEET X Y` \
(or `X Y RADIUS`, or a box) lists what the plan has there by the names in the house file.
4. **A mark says where and what, never why.** Look at the drawing under the sign for what is wrong \
with it. Say back to the owner what you take each sign to mean before changing anything, and ask \
where the drawing does not settle it."""


def number(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def ident(m):
    """What a mark is called: the id the page gave it, or its time written
    as the page would have written it, so an older mark has one too."""
    if isinstance(m.get('id'), str) and ID.match(m['id']):
        return m['id']
    n, out = int(abs(number(m.get('ts')) or 0)), ''
    while n:
        n, r = divmod(n, 36)
        out = '0123456789abcdefghijklmnopqrstuvwxyz'[r] + out
    return 'm' + (out or '0')


STATES = ('resolved', 'blocked', 'question')        # answered: fixed; needs code or information; asked the owner something


def resolved(m):
    return m.get('status') == 'resolved'


def answered(m):
    """Whether the agent has replied and the owner has not since: resolved,
    blocked or asked a question. Anything else is open."""
    return m.get('status') in STATES


def load(path):
    """The marks in a marks.json, as a list; none where there is no file."""
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding='utf-8') as fh:
            drawn = json.load(fh)
    except ValueError as e:
        raise ValueError('%s is not JSON that can be read (%s)' % (path, e))
    return drawn if isinstance(drawn, list) else []


def save(path, marks):
    """Write a marks.json whole: all of it or none of it."""
    with open(path + '.tmp', 'w', encoding='utf-8') as fh:
        json.dump(marks, fh, indent=1, ensure_ascii=False)
    os.replace(path + '.tmp', path)


def replies(m):
    """A mark's replies, oldest first: each {by: agent or owner, text, ts}."""
    got = m.get('replies') if isinstance(m.get('replies'), list) else []
    return sorted([r for r in got if isinstance(r, dict) and r.get('by') in ('agent', 'owner')
                   and isinstance(r.get('text'), str) and number(r.get('ts')) is not None], key=lambda r: r['ts'])


def _reopened(m, since):
    """Whether the owner has replied to a mark since it was resolved: that opens it again."""
    return any(r['by'] == 'owner' and r['ts'] > (number(since) or 0) for r in replies(m))


def keep(stored, sent):
    """What a page sent, with what was resolved since the page read its
    marks kept so: a page holds the whole list and sends it back, and must
    not open again a mark that was closed while it was looking. Replies
    from both sides are kept; one from the owner after a mark was resolved
    opens it again, which is how the owner says it was not."""
    was = dict((ident(m), m) for m in stored if isinstance(m, dict))
    out = []
    for m in sent:
        if isinstance(m, dict) and m.get('type') in KINDS and ident(m) in was:
            old = was[ident(m)]
            both = dict(((r['by'], r['ts']), r) for r in replies(old) + replies(m))
            m = dict(m)
            if both:
                m['replies'] = [both[k] for k in sorted(both, key=lambda k: k[1])]
            for k in ('version', 'context', 'room'):            # what the server wrote on it, which a page may not have
                if k in old and k not in m:
                    m[k] = old[k]
            if answered(old) and not _reopened(m, old.get('resolved')):
                m.update((k, old[k]) for k in LIFE if k in old)
            elif answered(old):
                for k in LIFE:
                    m.pop(k, None)
        out.append(m)
    return out


def context(sheet, m):
    """What a comment is on, as the plan has it where it was put: for a pin
    the room it is in and the doors, walls and fittings near it; for a box
    what is inside it. The owner never picks these out: they are read off
    the plan when the comment is made, and handed back with it."""
    if m.get('type') == 'box':
        x0, y0, x1, y1 = [float(v) for v in m['box']]
        found = query.at(sheet, (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))
    else:
        found = query.at(sheet, (float(m['x']), float(m['y'])), reach=NEAR)
    rooms = [t.split(' (')[0][5:] for d, t in found if d == 0 and t.startswith('room ')]
    return rooms, query.lines(found)[:12]


def attach(sent, stored, sheets, version):
    """Each comment a page sent that the store has not seen, with the house
    version it was made on and what it is on (`context`). `sheets` are the
    house's solved sheets by id, as the file is at `version`; a comment the
    page says it made on another version keeps that one, and nothing is
    read off a plan it was not made on."""
    seen = set(ident(m) for m in stored if isinstance(m, dict))
    for m in sent:
        if not isinstance(m, dict) or m.get('type') not in ('note', 'box') or ident(m) in seen or 'context' in m:
            continue
        if not isinstance(m.get('version'), str) or not ID.match(m['version']):
            m['version'] = version
        sheet = sheets.get(m.get('sheet'))
        if m['version'] != version or sheet is None:
            continue
        try:
            m['room'], m['context'] = context(sheet, m)
        except (KeyError, TypeError, ValueError, IndexError):
            pass                                    # not a place: strokes() passes it over too
    return sent


KEPT = '.versions'          # beside a house file: each version a comment was made on


def remember(folder, version, text):
    """Keep a version of a house file that a comment was made on."""
    dest = os.path.join(folder, KEPT, version + '.yaml')
    if ID.match(version) and not os.path.exists(dest):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest + '.tmp', 'w') as fh:
            fh.write(text)
        os.replace(dest + '.tmp', dest)


def recall(folder, version):
    """The text of a house file at a version a comment was made on, or None."""
    dest = os.path.join(folder, KEPT, str(version) + '.yaml')
    if not version or not ID.match(str(version)) or not os.path.exists(dest):
        return None
    with open(dest) as fh:
        return fh.read()


def state(marks):
    """A few characters that stand for which marks are resolved, and how."""
    said = sorted((ident(m), [m.get(k) for k in LIFE]) for m in marks if isinstance(m, dict) and answered(m))
    return hashlib.sha256(json.dumps(said, sort_keys=True, default=str).encode('utf-8')).hexdigest()[:6]


def resolve(path, ids, note, sheets=None, known=(), reopen=False, state='resolved', vet=None):
    """Reply to the marks with these ids. `note` is the reply, a line the
    owner reads under each, and `state` what it says: `resolved`, built
    in; `blocked`, it needs a change to the engine or information nobody
    has; `question`, it asks the owner something. A blocked mark or a
    question stays where the owner sees it, and a reply from the owner to
    any of the three opens it again. `sheets` is the sheets each was
    applied to — by mark, {id: [sheets]}, since one mark may be meant for
    two options and the next for one; none is the sheet it was drawn on.
    A plain list is taken only for a single mark. With `reopen` they are
    opened again instead. All of them or none: an id that is not there is
    said and nothing is written. `vet`, once the marks are found, may still
    refuse. Returns what was done, as lines."""
    ids = [ids] if isinstance(ids, str) else list(ids or [])
    note = ' '.join(str(note or '').split())[:300]
    if not ids:
        raise ValueError('name the marks by id, as `marks` lists them')
    if state not in STATES:
        raise ValueError('a reply says the mark is %s, not %r' % (', '.join(STATES[:-1]) + ' or ' + STATES[-1], state))
    if not note and not reopen:
        raise ValueError('say in a line how the marks were dealt with' if state == 'resolved' else
                         'say in a line what it needs' if state == 'blocked' else 'ask the question, in a line')
    if isinstance(sheets, dict):
        lost = [i for i in sheets if i not in ids]
        if lost:
            raise ValueError('sheets names %s, which %s not among the marks replied to' % (', '.join(map(repr, lost)), 'is' if len(lost) == 1 else 'are'))
        each = dict((i, list(sheets.get(i) or [])) for i in ids)
    elif sheets and len(ids) > 1:
        raise ValueError('sheets is per mark: give {id: [sheets]} for the marks that were applied beyond the sheet they were drawn on')
    else:
        each = dict((i, list(sheets or [])) for i in ids)
    wrong = sorted(set(s for v in each.values() for s in v if s not in known))
    if wrong:
        raise ValueError('no sheet called %s (have %s)' % (', '.join(map(repr, wrong)), ', '.join(known)))
    with LOCK:
        marks = load(path)
        mine = dict((ident(m), m) for m in marks if isinstance(m, dict))
        lost = [i for i in ids if i not in mine]
        if lost:
            raise ValueError('no mark called %s (have %s)' % (', '.join(map(repr, lost)), ', '.join(sorted(mine)) or 'none'))
        if vet:
            vet()
        out = []
        for i in ids:
            m = mine[i]
            m['id'] = i
            was = m.get('status') if answered(m) else None
            for k in LIFE:
                m.pop(k, None)
            if reopen:
                out.append('%s: %s' % (i, 'opened again' if was else 'was open already'))
                continue
            now = int(time.time()*1000)
            m.update(status=state, resolved=now, how=note)
            m['replies'] = replies(m) + [{'by': 'agent', 'text': note, 'ts': now, 'state': state}]
            if each[i]:
                m['applied'] = each[i]
            out.append('%s: %s%s%s' % (i, state, ' (it was %s; now as this says)' % was if was else '',
                                       ', applied to ' + ', '.join(each[i]) if each[i] else ''))
        save(path, marks)
    return out


def strokes(marks, first_sheet, done=False):
    """Marks in the order drawn, numbered per sheet from 1: the open ones,
    and with `done` the resolved ones too. marks.json is written by a page
    in a browser and may hold anything: what is not a stroke or a note with
    a place in metres is passed over, not tripped on."""
    def place(p):
        if isinstance(p, (list, tuple)) and len(p) == 2 and None not in (number(p[0]), number(p[1])):
            return (float(p[0]), float(p[1]))

    out, n = [], {}
    marks = [m for m in (marks if isinstance(marks, list) else []) if isinstance(m, dict)]
    for m in sorted(marks, key=lambda m: number(m.get('ts')) or 0):
        sheet = m.get('sheet', first_sheet)
        if not isinstance(sheet, str):
            continue
        if m.get('type') == 'pen' and isinstance(m.get('pts'), list) and len(m['pts']) > 1:
            pts = [place(p) for p in m['pts']]
            if None in pts:
                continue
            g = LineString(pts)
        elif m.get('type') == 'note' and place([m.get('x'), m.get('y')]):
            pts = [place([m['x'], m['y']])]
            g = Point(pts[0])
        elif m.get('type') == 'box' and isinstance(m.get('box'), list) and len(m['box']) == 4 \
                and place(m['box'][:2]) and place(m['box'][2:]):
            (x0, y0), (x1, y1) = place(m['box'][:2]), place(m['box'][2:])
            x0, x1, y0, y1 = min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1)
            pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
            g = Polygon(pts)
        else:
            continue
        n[sheet] = n.get(sheet, 0) + 1              # every mark on a sheet counts: a number never moves
        if answered(m) and not done:              # replied to, and the owner has not answered back
            continue
        applied = m.get('applied') if isinstance(m.get('applied'), list) else []
        out.append({'n': n[sheet], 'sheet': sheet, 'ts': number(m.get('ts')) or 0, 'pts': pts, 'geom': g,
                    'id': ident(m), 'done': resolved(m), 'when': number(m.get('resolved')),
                    'state': m['status'] if answered(m) else 'open',
                    'how': str(m['how'])[:300] if resolved(m) and m.get('how') is not None else None,
                    'applied': [a for a in applied if isinstance(a, str)] if resolved(m) else [],
                    'text': (None if m.get('text') is None else str(m['text'])) if m.get('type') in ('note', 'box') else None,
                    'kind': m['type'], 'version': m['version'] if isinstance(m.get('version'), str) else None,
                    'context': [str(c) for c in m['context'] if isinstance(c, str)][:12] if isinstance(m.get('context'), list) else [],
                    'replies': replies(m)})
    return out


def frames(S):
    """Strokes that lie close together, so one picture can show them at a
    readable scale. This is framing only: it says nothing about which
    strokes belong to one sign."""
    out = []
    for s in S:
        hit = [f for f in out if f[0]['sheet'] == s['sheet']
               and any(o['geom'].distance(s['geom']) <= JOIN_M for o in f)]
        for f in hit[1:]:
            hit[0].extend(f)
            out.remove(f)
        if hit:
            hit[0].append(s)
        else:
            out.append([s])
    return out


def ink(S, side):
    """Marks as SVG, for a view `side` metres wide. A stroke is the ink in
    INK, fine and a little transparent so what is under it shows, and in
    NOTE a dot and its number where it starts and a ring where it ends. A
    comment is a numbered pin, or a box with its pin at a corner: its words
    are listed beside the picture, never written over the drawing, where
    they hid it and ran off the edge. Colours are written as style=, which
    the sheet's stylesheet cannot override."""
    w, f = side*U/260.0, side*U/42.0
    out = []
    for s in S:
        x, y = s['pts'][0][0]*U, s['pts'][0][1]*U
        col = DONE if s.get('done') else INK                    # ink that was dealt with is grey
        if s['text'] is not None:
            if s['kind'] == 'box':
                out.append('<polygon points="%s" style="fill:%s;fill-opacity:0.08;stroke:%s;stroke-width:%s;'
                           'stroke-dasharray:%s %s"/>'
                           % (' '.join('%s,%s' % (render.n2(a*U), render.n2(b*U)) for a, b in s['pts']),
                              col, col, render.n2(w), render.n2(w*4), render.n2(w*2.5)))
            out.append('<circle cx="%s" cy="%s" r="%s" style="fill:%s;stroke:#FFFFFF;stroke-width:%s"/>'
                       % (render.n2(x), render.n2(y), render.n2(f*0.62), col, render.n2(w*0.5)))
            out.append('<text x="%s" y="%s" text-anchor="middle" font-family="Helvetica,Arial,sans-serif" font-size="%s"'
                       ' font-weight="700" style="fill:#FFFFFF">%d</text>'
                       % (render.n2(x), render.n2(y + f*0.28), render.n2(f*0.78), s['n']))
            continue
        out.append('<polyline points="%s" style="fill:none;stroke:%s;stroke-width:%s;stroke-opacity:0.8;'
                   'stroke-linecap:round;stroke-linejoin:round"/>'
                   % (' '.join('%s,%s' % (render.n2(a*U), render.n2(b*U)) for a, b in s['pts']),
                      col, render.n2(w)))
        ex, ey = s['pts'][-1][0]*U, s['pts'][-1][1]*U
        out.append('<circle cx="%s" cy="%s" r="%s" style="fill:none;stroke:%s;stroke-width:%s"/>'
                   % (render.n2(ex), render.n2(ey), render.n2(w*1.5), NOTE, render.n2(w*0.4)))
        out.append('<circle cx="%s" cy="%s" r="%s" style="fill:%s"/>'
                   % (render.n2(x), render.n2(y), render.n2(w*0.8), NOTE))
        out.append('<text x="%s" y="%s" text-anchor="end" font-family="Helvetica,Arial,sans-serif" font-size="%s"'
                   ' font-weight="700" style="fill:%s">%d</text>'
                   % (render.n2(x - w*1.6), render.n2(y - w*1.6), render.n2(f*0.8), NOTE, s['n']))
    return out


def _wrap(text, width=40):
    """Words in lines of at most `width` characters, for the list beside a picture."""
    out, line = [], ''
    for word in text.split():
        if line and len(line) + 1 + len(word) > width:
            out.append(line)
            line = word
        else:
            line = (line + ' ' + word).strip()
    return out + ([line] if line else [])


def _step(side):
    """A tick spacing that puts five to twelve ticks along a side."""
    return next(t for t in (0.1, 0.2, 0.25, 0.5, 1.0, 2.0, 5.0) if side/t <= 12)


NAMES = ('the drawing as it is', 'the same view, with the ink')
BUILT = ('what was built: the drawing as it is now', 'what was drawn: the same view, with the ink')


def panels(dest, lines, box, S, title, px=900, names=NAMES, views=None):
    """One view of a sheet (x, y, w, h in metres) as an SVG of two panels:
    the drawing as it is, and the same with the ink of `S` on it. With no
    ink there is one panel. Both carry the same metre ticks. `names` are
    what the two are called above them. `views` is any other set of
    panels, as (name, the drawing's lines, whether the ink is on it): the
    drawing a mark was made on beside the drawing as it is now. What the
    comments say is listed down the right, by their numbers."""
    x0, y0, w, h = box
    ph = px*h/float(w)
    M, HEAD, GAP = 46, 74, 30                       # tick margin, caption, space between panels
    if views is None:
        views = [(names[0], lines, False), (names[1], lines, True)] if S else [('', lines, False)]
    n = len(views)
    said = [(s['n'], s['text'], s.get('done')) for s in S if s['text'] is not None]
    rows = [(k, ln, done) for k, text, done in said for ln in (_wrap(text) or [''])]
    LIST = 340 if said else 0                       # the comments, beside the pictures
    W, H = n*(px + M) + (n - 1)*GAP + 16 + LIST, max(ph + M + HEAD + 12, HEAD + M + 22*len(rows) + 12*len(said) + 40)
    tick = _step(w)
    T = 'font-family="Helvetica,Arial,sans-serif"'
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %s %s">'
           % (W, H, render.n2(W), render.n2(H)),
           '<style>%s</style>' % render.CSS,
           '<rect width="100%%" height="100%%" style="fill:#FFFFFF"/>',
           '<text x="12" y="26" %s font-size="17" font-weight="700" style="fill:#131A18">%s</text>'
           % (T, render.esc(title))]
    if S:
        out.append('<text x="12" y="50" %s font-size="14" style="fill:#131A18">'
                   '<tspan style="fill:%s" font-weight="700">magenta</tspan> = the owner\'s ink   ·   '
                   '<tspan style="fill:%s" font-weight="700">blue</tspan> = added here: dot + number where a stroke '
                   'starts, ring where it ends, ticks in metres   ·   everything else = the drawing</text>'
                   % (T, INK, NOTE))
    for k, (name, drawn, inked) in enumerate(views):
        ox, oy = M + k*(px + M + GAP), HEAD + M
        out.append('<text x="%s" y="%s" %s font-size="14" font-weight="700" style="fill:#131A18">%s</text>'
                   % (render.n2(ox), HEAD - 4, T, render.esc(name.upper())))
        # a clipped, scaled group and not a nested <svg>: the rasteriser does not clip those
        out.append('<clipPath id="pane%d"><rect x="%s" y="%s" width="%s" height="%s"/></clipPath>'
                   % (k, render.n2(ox), render.n2(oy), px, render.n2(ph)))
        out.append('<g clip-path="url(#pane%d)"><g transform="translate(%s %s) scale(%.6f) translate(%s %s)">'
                   % (k, render.n2(ox), render.n2(oy), px/(w*U), render.n2(-x0*U), render.n2(-y0*U)))
        out.append('<rect x="%s" y="%s" width="%s" height="%s" style="fill:#F8FAF9"/>'
                   % (render.n2(x0*U), render.n2(y0*U), render.n2(w*U), render.n2(h*U)))
        out += drawn
        if inked:
            out += ink(S, w)
        out.append('</g></g>')
        out.append('<rect x="%s" y="%s" width="%s" height="%s" style="fill:none;stroke:%s;stroke-width:1"/>'
                   % (render.n2(ox), render.n2(oy), px, render.n2(ph), NOTE))
        i = math.ceil(x0/tick - 1e-9)
        while i*tick <= x0 + w + 1e-9:
            X = ox + (i*tick - x0)/w*px
            out.append('<line x1="%s" y1="%s" x2="%s" y2="%s" style="stroke:%s;stroke-width:1"/>'
                       % (render.n2(X), render.n2(oy - 6), render.n2(X), render.n2(oy), NOTE))
            out.append('<text x="%s" y="%s" text-anchor="middle" %s font-size="12" style="fill:%s">%s</text>'
                       % (render.n2(X), render.n2(oy - 10), T, NOTE, ('%.2f' % (i*tick)).rstrip('0').rstrip('.')))
            i += 1
        i = math.ceil(y0/tick - 1e-9)
        while i*tick <= y0 + h + 1e-9:
            Y = oy + (i*tick - y0)/h*ph
            out.append('<line x1="%s" y1="%s" x2="%s" y2="%s" style="stroke:%s;stroke-width:1"/>'
                       % (render.n2(ox - 6), render.n2(Y), render.n2(ox), render.n2(Y), NOTE))
            out.append('<text x="%s" y="%s" text-anchor="end" %s font-size="12" style="fill:%s">%s</text>'
                       % (render.n2(ox - 9), render.n2(Y + 4), T, NOTE, ('%.2f' % (i*tick)).rstrip('0').rstrip('.')))
            i += 1
    if said:
        lx, ly = W - LIST + 4, HEAD + M
        out.append('<text x="%s" y="%s" %s font-size="14" font-weight="700" style="fill:#131A18">COMMENTS</text>'
                   % (render.n2(lx), HEAD - 4, T))
        last = None
        for k, ln, done in rows:
            first = k != last
            if first and last is not None:
                ly += 12
            if first:
                out.append('<circle cx="%s" cy="%s" r="11" style="fill:%s"/>' % (render.n2(lx + 11), render.n2(ly - 5), DONE if done else INK))
                out.append('<text x="%s" y="%s" text-anchor="middle" %s font-size="13" font-weight="700" style="fill:#FFFFFF">%d</text>'
                           % (render.n2(lx + 11), render.n2(ly), T, k))
            out.append('<text x="%s" y="%s" %s font-size="15" style="fill:%s">%s</text>'
                       % (render.n2(lx + 30), render.n2(ly), T, DONE if done else '#131A18', render.esc(ln)))
            ly += 22
            last = k
    out.append('</svg>')
    with open(dest, 'w') as fh:
        fh.write('\n'.join(out))
    return dest


def _square(S, least=2.5, grow=1.8):
    xs = [v for s in S for v in (s['geom'].bounds[0], s['geom'].bounds[2])]
    ys = [v for s in S for v in (s['geom'].bounds[1], s['geom'].bounds[3])]
    side = max(least, grow*max(max(xs)-min(xs), max(ys)-min(ys)))
    return ((min(xs)+max(xs))/2.0 - side/2.0, (min(ys)+max(ys))/2.0 - side/2.0, side, side)


def _path(s):
    """A stroke's path in a few points: enough to see its shape in text."""
    g = s['geom'].simplify(0.05)
    return ' → '.join('(%.2f, %.2f)' % p for p in g.coords)


def _dealt(s):
    """How a mark that was replied to was dealt with, as the line under it."""
    if s['state'] == 'open':
        return []
    when = datetime.datetime.fromtimestamp(s['when']/1000.0).strftime(' %Y-%m-%d %H:%M') if s['when'] else ''
    return ['  %s%s: %s%s' % (s['state'], when, s['how'] or 'no word of how',
                                    ' — applied to ' + ', '.join('`%s`' % a for a in s['applied']) if s['applied'] else '')]


def _about(s, now):
    """What the store holds about a comment beyond where it is: what it is
    on, the version it was made on, and what has been said back and forth."""
    out = []
    if s['context']:
        out.append('  on: ' + '; '.join(s['context']))
    if s['version'] and now and s['version'] != now:
        out.append('  made on version `%s`; the house file is now `%s` — check that what it is about is still there'
                   % (s['version'], now))
    for r in s['replies']:
        when = datetime.datetime.fromtimestamp(r['ts']/1000.0).strftime('%Y-%m-%d %H:%M')
        out.append('  %s replied %s: %s' % ('you' if r['by'] == 'agent' else 'the owner', when, ' '.join(r['text'].split())[:600]))
    return out


def brief(house, sheets, marks, out, rasterise, changed=None, done=False, sheet=None, now=None, then=None):
    """Write the brief and its pictures into `out`; return the brief, or
    '' where there is nothing to lay out. `sheets` are the house's solved
    sheets; `changed` is when the house file was last edited, in seconds.
    The marks still open, and with `done` the resolved ones as well; of
    one `sheet`, or of them all. `now` is the house file's version; `then`
    gives the house solved as it was at an older one, or None, so a
    comment made on it is shown on the drawing it was made on beside the
    drawing as it is now."""
    if os.path.isdir(out):
        for old in os.listdir(out):
            os.remove(os.path.join(out, old))
    os.makedirs(out, exist_ok=True)
    by_key = dict((s.id, s) for s in sheets)
    if sheet is not None and sheet not in by_key:
        raise ValueError('no sheet called %r (have %s)' % (sheet, ', '.join(by_key)))
    every = [s for s in strokes(marks, sheets[0].id, done=True) if s['sheet'] in by_key]
    S = [s for s in strokes(marks, sheets[0].id, done=done) if s['sheet'] in by_key and sheet in (None, s['sheet'])]
    if not S:
        return ''
    md = ['# Marks on %s' % house['name'], '', HOW, '']
    left = len([s for s in every if s['done']]) if not done else 0
    if left:
        md += ['%d mark%s already resolved %s left out; ask for resolved marks to see them.'
               % (left, '' if left == 1 else 's', 'is' if left == 1 else 'are'), '']
    waits = len([s for s in every if s['state'] in ('blocked', 'question')]) if not done else 0
    if waits:
        md += ['%d mark%s waiting on the owner — blocked, or a question asked — %s left out until they reply; '
               'ask for resolved marks to see them.' % (waits, '' if waits == 1 else 's', 'is' if waits == 1 else 'are'), '']
    still = [s for s in S if not s['done']]
    if changed and still and changed > max(s['ts'] for s in still)/1000.0:
        md += ['**The house file has been edited since the last of these marks was drawn.** The ink was '
               'drawn on an earlier drawing; what it pointed at may already have moved or been fixed.', '']
    for key in [k for k in by_key if any(s['sheet'] == k for s in S)]:
        mine = [s for s in S if s['sheet'] == key]
        vb, lines = by_key[key].vb, by_key[key].lines
        md += ['## Sheet `%s`' % key, '']
        for i, f in enumerate(frames(mine), 1):
            f = sorted(f, key=lambda s: s['n'])
            box = _square(f)
            views, old = None, [s['version'] for s in f if s['version'] and now and s['version'] != now]
            was = then(max(set(old), key=old.count)) if old and then else None
            if was is not None and key in [p.id for p in was.plans()]:
                views = [('made on: version %s, with the ink' % max(set(old), key=old.count), was.sheet(key).lines, True),
                         ('as it is now: version %s, with the ink' % now, lines, True)]
            dest = panels(os.path.join(out, '%s-%d.svg' % (key, i)), lines, box, f,
                          '%s · %s · x %.2f–%.2f, y %.2f–%.2f m'
                          % (house['name'], key, box[0], box[0]+box[2], box[1], box[1]+box[3]), views=views)
            rasterise(dest)
            md += ['### Ink %d — `%s`' % (i, dest[:-4] + '.png'), '',
                   'View x %.2f–%.2f, y %.2f–%.2f. In the order drawn:' % (box[0], box[0]+box[2], box[1], box[1]+box[3]), '']
            for s in f:
                when = datetime.datetime.fromtimestamp(s['ts']/1000.0).strftime('%H:%M:%S')
                prev = [o for o in mine if o['n'] == s['n'] - 1]
                gap = ', %.0f s after stroke %d' % ((s['ts'] - prev[0]['ts'])/1000.0, prev[0]['n']) if prev else ''
                if s['text'] is not None and s['kind'] == 'box':
                    (bx0, by0), (bx1, by1) = s['pts'][0], s['pts'][2]
                    md.append('- **%d** `%s` box x %.2f–%.2f, y %.2f–%.2f: "%s" — %s%s'
                              % (s['n'], s['id'], bx0, bx1, by0, by1, s['text'], when, gap))
                    md += _about(s, now) + _dealt(s)
                    continue
                if s['text'] is not None:
                    md.append('- **%d** `%s` written "%s" at (%.2f, %.2f) — %s%s'
                              % (s['n'], s['id'], s['text'], s['pts'][0][0], s['pts'][0][1], when, gap))
                    md += _about(s, now) + _dealt(s)
                    continue
                others = sorted((o['geom'].distance(s['geom']), o['n']) for o in f if o is not s)
                near = ('; nearest other ink: stroke %d, %.2f m away' % (others[0][1], others[0][0])) if others else ''
                md.append('- **%d** `%s` stroke, %.2f m of ink — %s%s%s'
                          % (s['n'], s['id'], s['geom'].length, when, gap, near))
                md.append('  path: %s' % _path(s))
                md += _about(s, now) + _dealt(s)
            md.append('')
        whole = panels(os.path.join(out, '%s-sheet.svg' % key), lines,
                       tuple(v/U for v in vb), mine, '%s · %s · whole sheet' % (house['name'], key), px=800)
        rasterise(whole)
        md += ['Whole sheet, to place them: `%s`' % (whole[:-4] + '.png'), '']
    text = '\n'.join(md)
    with open(os.path.join(out, 'brief.md'), 'w') as fh:
        fh.write(text)
    return text
