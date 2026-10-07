# -*- coding: utf-8 -*-
"""Command line.

    flawlessplan init [DIR]                       # make a workspace, with the example houses
    flawlessplan build [HOUSE ...] [--png]        # no house: all of them, and the index
    flawlessplan build --public                   # only what may be hosted, into public/
    flawlessplan share HOUSE                      # one file to send: every sheet, to be read
    flawlessplan check HOUSE                      # problems, and any drift from its snapshot
    flawlessplan crop  HOUSE ground 2.8 10.5 5.4 14.3    # no box: the whole sheet
    flawlessplan at    HOUSE ground 2.0 8.1       # what the plan has there
    flawlessplan serve                            # the pages, saving marks
    flawlessplan marks HOUSE [--all] [--sheet S]  # lay out what was drawn on the pages and is still open
    flawlessplan resolve HOUSE ID ... --note HOW  # close marks that have been built in
    flawlessplan snapshot HOUSE                   # rewrite its expected.json
    flawlessplan mcp                              # the same as tools for an agent, over stdio

A HOUSE is its name in the workspace (`cottage`), or a path to its folder
or its `house.yaml`. The workspace is where houses are kept and drawings
go: `--workspace DIR`, else $FLAWLESSPLAN_WORKSPACE, else this folder.
`python -m flawlessplan` is the same command.
"""
import argparse
import json
import os
import shutil
import sys
from . import __version__, edit, model, render, page, marks, report, query, server
from .solve import solve, beside
from .workspace import Workspace


def build_house(path, out=None, png=False, quiet=False, root=None, ws=None):
    """Draw every sheet of one house, its page and the file to send.
    Returns its report, issues included, and the solved house it was drawn
    from. `root` is the way from its page back to the index of houses, when
    it is being built beside one."""
    s = solve(path)
    out = out or os.path.join((ws or Workspace()).build, s.name)
    os.makedirs(out, exist_ok=True)
    for sheet in s.sheets:
        dest = os.path.join(out, sheet.id + '.svg')
        with open(dest, 'w') as fh:
            fh.write(sheet.svg())
        with open(dest[:-4] + '.md', 'w') as fh:     # the notes, next to the image
            fh.write(report.info_md(sheet.info))
        if png:
            rasterise(dest)
    rep = report.report(s)
    with open(os.path.join(out, 'report.json'), 'w') as fh:
        json.dump(rep, fh, indent=1, ensure_ascii=False)
    with open(os.path.join(out, sent(s.name)), 'w') as fh:
        fh.write(page.share(s.house['name'], s.shown()))
    with open(s.path) as fh:
        version = edit.version(fh.read())
    with open(os.path.join(out, 'index.html'), 'w') as fh:
        fh.write(page.markup(s.house['name'], s.shown(), root, send=sent(s.name),
                             hidden=[p for p in s.sheets if p.hidden], version=version))
    if not quiet:
        summarise(rep, out)
    return rep, s


def build_all(ws, public=False, png=False, quiet=True):
    """Every house of a workspace and the index of them, into build/ — or,
    with `public`, only the houses not marked private, into public/, which
    is emptied first. Returns ([(name, report)], [paths that failed])."""
    out = ws.public if public else ws.build
    if public:
        for old in os.listdir(out) if os.path.isdir(out) else []:
            if old != '.vercel':                    # which project this folder deploys to; never uploaded
                old = os.path.join(out, old)        # nothing else from an earlier build may be left to be hosted
                shutil.rmtree(old) if os.path.isdir(old) else os.remove(old)
    built, reps, failed = [], [], []
    for path in ws.every():
        try:
            if public and solve(path).house['private']:
                print('%s: private, left out' % path)
                continue
            rep, s = build_house(path, os.path.join(out, os.path.basename(path)), png, quiet, root='../')
        except (model.ConfigError, ValueError) as e:
            print('%s: %s' % (path, e), file=sys.stderr)
            failed.append(path)
            continue
        built.append((s.name, s))
        reps.append((s.name, rep))
    os.makedirs(out, exist_ok=True)
    page.install(out)
    with open(os.path.join(out, 'index.html'), 'w') as fh:
        fh.write(page.index(built))
    if public:
        shutil.copyfile(os.path.join(page.ASSETS, 'vercel.json'), os.path.join(out, 'vercel.json'))
    return reps, failed


def sent(name):
    """What a house's file to send is called, beside its page."""
    return name + '-plans.html'


def share(path, out=None, ws=None):
    """A house as one file to send: every sheet and what is said of it, to
    be read and not drawn on. Returns where it was written."""
    s = solve(path)
    out = out or os.path.join((ws or Workspace()).build, s.name, sent(s.name))
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    with open(out, 'w') as fh:
        fh.write(page.share(s.house['name'], s.shown()))
    return out


def rasterise(svg):
    """A PNG beside an SVG file."""
    import resvg_py
    with open(svg[:-4] + '.png', 'wb') as fh:
        fh.write(bytes(resvg_py.svg_to_bytes(svg_path=svg)))


WHOLE = 1600.0                  # pixels along the longer side of a whole sheet


def crop(path, sheet, box=None, out=None, scale=3.0, ink=False, ws=None, ids=None):
    """A close view of part of one sheet — the way to read fine detail.
    `box` is x0, y0, x1, y1 in metres; the PNG is `scale` pixels per cm.
    With no box it is the whole sheet, small enough to take in at once:
    its shape and arrangement, not its detail.
    With `ink` it is two panels: the drawing, and the drawing with what the
    owner drew on it and is still open, both with metre ticks.
    With `ids` it is those marks, open or resolved and whichever sheet
    they were drawn on, set on this sheet as it is now: what was built
    beside what was drawn, to show the owner. With no box it is framed
    round them."""
    s = solve(path)
    sh = s.sheet(sheet)
    mine = None
    if ids:
        every = dict((m['id'], m) for m in marks.strokes(drawn_on(path), s.plans()[0].id, done=True))
        lost = [i for i in ids if i not in every]
        if lost:
            raise ValueError('no mark called %s (have %s)' % (', '.join(map(repr, lost)), ', '.join(sorted(every)) or 'none'))
        mine = [dict(every[i], done=False) for i in ids]        # in their own colour: this is what was asked for
        if box is None:
            x, y, w, h = marks._square(mine)
            box = (x, y, x + w, y + h)
    if box is None:
        box = (sh.vb[0]/render.U, sh.vb[1]/render.U, (sh.vb[0] + sh.vb[2])/render.U, (sh.vb[1] + sh.vb[3])/render.U)
        scale = min(scale, WHOLE / max(sh.vb[2], sh.vb[3]))
    x0, y0, x1, y1 = box
    out = out or os.path.join((ws or Workspace()).build, s.name, 'crop-%s.svg' % sheet)
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    if ink or mine:
        if mine is None:
            mine = [m for m in marks.strokes(drawn_on(path), s.plans()[0].id) if m['sheet'] == sheet]
        marks.panels(out, sh.lines, (x0, y0, x1-x0, y1-y0), mine,
                     '%s · %s · x %.2f–%.2f, y %.2f–%.2f m' % (s.house['name'], sheet, x0, x1, y0, y1),
                     names=marks.BUILT if ids else marks.NAMES)
    else:
        vb = (x0*render.U, y0*render.U, (x1-x0)*render.U, (y1-y0)*render.U)
        with open(out, 'w') as fh:
            fh.write(render.standalone(sh.lines, vb, scale=1.0/scale))
    rasterise(out)
    return out[:-4] + '.png'


def marked(path, ws=None, done=False, sheet=None):
    """Lay out what was drawn on a house's page for reading: the strokes
    in order and pictures of them on the drawing — the marks still open,
    and with `done` the resolved ones too; of one sheet, or of all. Returns
    the brief, which is also build/<house>/marks/brief.md, or '' where
    there is nothing to lay out. It does not interpret."""
    drawn = drawn_on(path)
    if not drawn:
        return ''
    s = solve(path)
    return marks.brief(s.house, s.sheets, drawn, os.path.join((ws or Workspace()).build, s.name, 'marks'),
                       rasterise, changed=os.path.getmtime(s.path), done=done, sheet=sheet)


def drawn_on(path):
    return marks.load(beside(path, 'marks.json'))


def nothing(path, name, done=False, sheet=None):
    """What to say when there is nothing to lay out: nothing drawn, or
    nothing still open."""
    S = marks.strokes(drawn_on(path), '', done=True)
    S = [m for m in S if sheet in (None, m['sheet'])]
    where = '%s, sheet %s' % (name, sheet) if sheet else name
    if not S:
        return '%s: nothing drawn yet' % where
    return '%s: nothing still open — %d resolved%s' % (where, len(S), '' if done else ' (ask for resolved marks to see them)')


def resolve(path, ids, note, sheets=None, reopen=False):
    """Close the marks of a house that have been built in, or open them
    again. Returns what was done, as lines."""
    return marks.resolve(beside(path, 'marks.json'), ids, note, sheets, [p.id for p in solve(path).sheets], reopen)


def at(path, sheet, where):
    """What a sheet has at a point (x, y), within a radius (x, y, r), or
    in a box (x0, y0, x1, y1) — as lines of text, nearest first."""
    sh = solve(path).sheet(sheet)
    if len(where) == 3:
        return query.lines(query.at(sh, where[:2], reach=where[2]))
    if len(where) in (2, 4):
        return query.lines(query.at(sh, where))
    raise ValueError('give X Y, X Y RADIUS or X0 Y0 X1 Y1')


def snapshot(path):
    """Write a house's expected.json from the plan as it now solves."""
    dest = beside(path, 'expected.json')
    now = report.snapshot(solve(path))              # solved before the file is opened: one that will not solve keeps its snapshot
    with open(dest, 'w') as fh:
        json.dump(now, fh, indent=1, ensure_ascii=False)
        fh.write('\n')
    return dest


def drift(path):
    """Where a house no longer matches the expected.json beside it, as
    lines of text; none if it matches or has no snapshot."""
    want = beside(path, 'expected.json')
    if not os.path.exists(want):
        return []
    got = json.loads(json.dumps(report.snapshot(solve(path))))
    return report.differences(json.load(open(want)), got)


def summarise(rep, out):
    print('%s -> %s/' % (rep['house'], os.path.relpath(out)))
    for f in rep['sheets']:
        print('  %-15s %6.1f m² gross  %d rooms  %d openings'
              % (f['id'], f['gross'], len(f['rooms']), len(f['openings'])))
        for r in f['rooms']:
            print('      %-16s %5.2f × %5.2f  %5.1f m²  %s'
                  % (r['name'], r['w'], r['h'], r['area'], '' if r['shape'] == 'rect' else r['shape']))
        for i in f['issues']:
            print('    %-5s %s' % (i['level'], i['message']))


def main(argv=None):
    ap = argparse.ArgumentParser(prog='flawlessplan')
    ap.add_argument('--version', action='version', version='flawlessplan ' + __version__)
    ap.add_argument('--workspace', '-w', metavar='DIR',
                    help='where the houses are kept (default: $FLAWLESSPLAN_WORKSPACE, else this folder)')
    ap.add_argument('--houses', metavar='DIR', help='the houses folder, when it is not <workspace>/houses')
    sub = ap.add_subparsers(dest='cmd', required=True)
    i = sub.add_parser('init', help='make a folder a workspace, with the example houses to start from')
    i.add_argument('dir', nargs='?', help='default: the workspace')
    i.add_argument('--bare', action='store_true', help='no example houses')
    b = sub.add_parser('build', help='draw every sheet of a house')
    b.add_argument('house', nargs='*', help='none: every house in the workspace, and the index of them')
    b.add_argument('--png', action='store_true', help='also rasterise every sheet')
    b.add_argument('--out', help='output directory (one house only)')
    b.add_argument('--quiet', action='store_true', help='print errors and warnings only')
    b.add_argument('--public', action='store_true',
                   help='into public/, emptied first, leaving out any house marked `private: true`: what may be hosted')
    b.add_argument('--serve', action='store_true', help='then serve build/, saving what is drawn on the pages')
    h = sub.add_parser('share', help='a house as one file to send: every sheet and its notes, to be read and not drawn on')
    h.add_argument('house')
    h.add_argument('--out', metavar='FILE', help='default: build/<house>/<house>-plans.html')
    c = sub.add_parser('check', help='report problems, and where a house has moved from its expected.json')
    c.add_argument('house', nargs='+')
    k = sub.add_parser('crop', help='render a close view of part of one sheet')
    k.add_argument('house')
    k.add_argument('sheet')
    k.add_argument('box', nargs='*', type=float, metavar='N', help='X0 Y0 X1 Y1, in metres; none for the whole sheet')
    k.add_argument('--out')
    k.add_argument('--marks', action='store_true', help='two panels: the drawing, and the same with what was drawn on it')
    k.add_argument('--ids', nargs='+', metavar='ID', help='those marks, open or resolved, on this sheet as it is now: '
                   'what was built beside what was drawn; with no box, framed round them')
    w = sub.add_parser('at', help='what a sheet has at a point, within a radius, or in a box')
    w.add_argument('house')
    w.add_argument('sheet')
    w.add_argument('where', nargs='+', type=float, metavar='N', help='X Y, X Y RADIUS or X0 Y0 X1 Y1')
    s = sub.add_parser('serve', help='serve build/ and save what is drawn on the pages')
    s.add_argument('--port', type=int, default=8765)
    m = sub.add_parser('marks', help='lay out what was drawn on the pages: strokes in order, pictures')
    m.add_argument('house', nargs='+')
    m.add_argument('--all', action='store_true', help='the resolved marks too, in grey')
    m.add_argument('--sheet', help='the marks drawn on one sheet only')
    r = sub.add_parser('resolve', help='close marks that have been built in: they stay, out of the way')
    r.add_argument('house')
    r.add_argument('ids', nargs='+', metavar='ID', help='as `marks` lists them')
    r.add_argument('--note', default='', help='how they were dealt with, in a line')
    r.add_argument('--sheets', nargs='+', metavar='SHEET', help='the sheets they were applied to, if not only the one drawn on')
    r.add_argument('--reopen', action='store_true', help='open them again instead')
    n = sub.add_parser('snapshot', help="rewrite a house's expected.json from the plan as it now solves")
    n.add_argument('house', nargs='+')
    sub.add_parser('mcp', help='the houses as tools for an agent (Model Context Protocol, stdio)')
    a = ap.parse_args(argv)
    ws = Workspace(a.workspace, a.houses)
    if a.cmd == 'init':
        made = Workspace(a.dir or a.workspace).init(examples=not a.bare)
        print('\n'.join(made) or 'nothing to do: already a workspace')
        return 0
    if a.cmd == 'mcp':
        from . import mcp_server
        mcp_server.serve(ws)
        return 0
    if a.cmd == 'serve':
        server.serve(ws, a.port)
        return 0
    try:
        if a.cmd == 'at':
            print('\n'.join(at(ws.find(a.house), a.sheet, a.where)))
        elif a.cmd == 'crop':
            if len(a.box) not in (0, 4):
                raise ValueError('give X0 Y0 X1 Y1, or nothing for the whole sheet')
            print(crop(ws.find(a.house), a.sheet, a.box or None, a.out, ink=a.marks, ws=ws, ids=a.ids))
        elif a.cmd == 'share':
            print(share(ws.find(a.house), a.out, ws))
        elif a.cmd == 'marks':
            for h in a.house:
                print(marked(ws.find(h), ws, a.all, a.sheet) or nothing(ws.find(h), h, a.all, a.sheet))
        elif a.cmd == 'resolve':
            print('\n'.join(resolve(ws.find(a.house), a.ids, a.note, a.sheets, a.reopen)))
        elif a.cmd == 'snapshot':
            for h in a.house:
                print(snapshot(ws.find(h)))
        if a.cmd in ('at', 'crop', 'share', 'marks', 'resolve', 'snapshot'):
            return 0
    except (model.ConfigError, ValueError) as e:
        print('%s' % e, file=sys.stderr)
        return 1
    bad = 0
    if a.cmd == 'build' and (a.public or not a.house):
        if a.public and (a.house or a.out):
            ap.error('--public builds every house that is not private, into public/')
        reps, failed = build_all(ws, a.public, a.png, a.quiet)
        issues = [(name, f['id'], i['level'], i['message']) for name, rep in reps
                  for f in rep['sheets'] for i in f['issues']]
        bad = len(failed)
    else:
        issues = []
        for h in a.house:
            try:
                path = ws.find(h)
                if a.cmd == 'build':
                    rep, _ = build_house(path, a.out if len(a.house) == 1 else None, a.png, a.quiet, ws=ws)
                    issues += [(h, f['id'], i['level'], i['message']) for f in rep['sheets'] for i in f['issues']]
                else:
                    issues += [(h,) + i for i in solve(path).issues()]
                    issues += [(h, 'snapshot', 'error', d) for d in drift(path)]
            except (model.ConfigError, ValueError) as e:
                print('%s: %s' % (h, e), file=sys.stderr)
                bad += 1
    if a.cmd == 'check' or a.quiet:
        for name, sid, lv, msg in issues:
            if a.cmd == 'check' or lv != 'info':    # quiet means what needs doing something about
                print('%s: %s: %-5s %s' % (name, sid, lv, msg))
    bad += sum(1 for i in issues if i[2] == 'error')
    if a.cmd == 'build' and a.serve:
        server.serve(ws)
    return 1 if bad else 0
