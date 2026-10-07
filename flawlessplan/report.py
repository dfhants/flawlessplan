# -*- coding: utf-8 -*-
"""What a solved house says about itself, as plain data: every room as
measured, every opening, every problem found. The build writes it as
report.json; a cut-down copy kept beside a house file as expected.json is
what the tests hold that house to.
"""
import json
from .model import NOTE_GROUPS

LEVELS = {'error': 0, 'warn': 1, 'info': 2}


def facts(plan):
    """One sheet's figures: areas, rooms, openings and issues, worst first."""
    fl = plan.spec
    return {
        'id': fl['id'], 'title': fl['title'],
        'gross': round(plan.gross, 2), 'internal': round(plan.internal, 2),
        'rooms': [dict({'id': str(r['id'])} if r['id'] else {},         # what notes and zones call it, where it has one
                       name=r['name'], w=round(r['w'], 3), h=round(r['h'], 3),
                       area=round(r['area'], 2), shape=r['shape']) for r in plan.rooms],
        'openings': [{'kind': o['kind'], 'style': o['style'], 'wall': o['host'].name,
                      'width': round(o['width'], 3),
                      'centre': [round(o['centre'][0], 3), round(o['centre'][1], 3)]}
                     for o in plan.openings],
        'fittings': [{'kind': f['kind'], 'w': round(f['w'], 3), 'd': round(f['d'], 3),
                      'wall': f['host'].name if f['host'] else None,
                      'back': [round(f['o'][0], 3), round(f['o'][1], 3)]} for f in plan.fittings],
        'rooflights': [dict({'id': r['id']} if r['id'] else {}, w=round(r['w'], 3), h=round(r['h'], 3),
                            at=[round(r['at'][0], 3), round(r['at'][1], 3)], over=r['over'],
                            **({'label': r['label']} if r['label'] else {})) for r in plan.rooflights],
        'zones': [{'name': z['name'], 'rooms': [r['name'] for r in z['rooms']], 'area': round(z['area'], 2)}
                  for z in plan.zones],
        'issues': [{'level': lv, 'message': m} for lv, m in
                   sorted(plan.issues, key=lambda i: LEVELS[i[0]])]}


def snapshot(solved):
    """What a house is held to: the geometry of every sheet and anything
    wrong with it. Titles, notes and `info` lines are left out — they may
    change without the plan changing."""
    out = {'house': solved.house['name'], 'sheets': {}}
    for s in solved.plans():
        f = facts(s.plan)
        out['sheets'][s.id] = {'gross': f['gross'], 'internal': f['internal'],
                              'rooms': f['rooms'], 'zones': f['zones'], 'openings': f['openings'],
                              'issues': [i for i in f['issues'] if i['level'] != 'info']}
    return out


UNMEASURED = ('title', 'stairs', 'fittings', 'rooflights', 'areas', 'solids', 'labels', 'dividers', 'gone', 'dims', 'notes')


def state(solved):
    """A snapshot, and with it what a snapshot leaves out because no figure
    comes of it — stairs, notes, fittings, text — as the house file gives
    them. Two of these differ wherever a change to the file did anything."""
    out = snapshot(solved)
    for s in solved.plans():
        out['sheets'][s.id].update((k, s.plan.spec[k]) for k in UNMEASURED)
    return json.loads(json.dumps(out, default=str))             # tuples as lists, to be compared


def totals(solved):
    """The house as it stands, every level added up: the sheets that change
    no other. None where a level has no such sheet, or more than one."""
    built = [s for s in solved.plans() if s.base is None]
    if sorted(s.level for s in built) != sorted(solved.house['levels']):
        return None
    return {'sheets': [s.id for s in built], 'gross': round(sum(s.plan.gross for s in built), 2),
            'internal': round(sum(s.plan.internal for s in built), 2)}


def standing(before, after):
    """What a change to a house left standing inside a room it made out of
    two: for each sheet, each room that now takes in rooms that were apart,
    with the walls and doors that parted them and are still there. As
    lines of text — one for whoever made the change to decide on each."""
    out = []
    was = dict((s.id, s.plan) for s in before.plans())
    for s in after.plans():
        old = was.get(s.id)
        if old is None:
            continue
        there = set((i['wall'], i.get('kind'), i['whole'] if 'whole' in i else None) for i in old.inside)
        apart = {}                                  # each face that had a room in it, once
        for r in old.rooms:
            apart.setdefault(id(r['face']), (r['face'], []))[1].append(r['name'])
        for face in s.plan.faces:
            took = [names for f, names in apart.values() if f.intersection(face).area > 0.5*f.area]
            if len(took) < 2:
                continue
            left = [i for i in s.plan.inside if i['face'] is face
                    and (i['wall'], i.get('kind'), i['whole'] if 'whole' in i else None) not in there]
            if not left:
                continue
            now = [r['name'] for r in s.plan.rooms if r['face'] is face] or ['a space with no room in it']
            said = []
            for i in left:
                if 'opening' in i:
                    said.append('the %s in %s at (%.2f, %.2f)' % ((i['kind'], i['wall']) + tuple(i['at'])))
                elif i['whole']:
                    said.append('wall %s' % i['wall'])
                else:
                    said.append('wall %s from (%.2f, %.2f) to (%.2f, %.2f)' % ((i['wall'],) + tuple(i['from']) + tuple(i['to'])))
            out.append('%s: still standing inside %s (%s were apart): %s'
                       % (s.id, now[0], ', '.join(n for names in took for n in names), '; '.join(said)))
    return out


def stale(changed, after):
    """Rooms whose size a change moved and whose `sub` — the line under
    the name — holds a figure written by hand: "plus 3.00 × 2.75 return"
    is still said after the return is gone. Nothing here can tell whether
    it still holds, so each is listed for whoever made the change to read.
    `changed` is what differences() found; a figure that comes from a name
    in braces follows the plan and is not listed."""
    import re
    out = []
    for s in after.plans():
        head = 'sheets.%s.rooms' % s.id
        hit = [c for c in changed if c.startswith(head)]
        if not hit:
            continue
        every = any(c.startswith(head + ':') for c in hit)          # a room more or fewer: any of them may have moved
        moved = set(int(m.group(1)) for c in hit for m in [re.match(re.escape(head) + r'\[(\d+)\]\.(w|h|area|shape)', c)] if m)
        for i, r in enumerate(s.plan.spec['rooms']):
            if r['sub'] and (every or i in moved) and re.search(r'\d', re.sub(r'\{[^}]*\}', '', str(r['sub']))):
                out.append('%s: %s says "%s" — a figure written by hand, and the room has changed: check it still holds'
                           % (s.id, r['name'], r['sub']))
    return out


TOL = {'gross': 0.05, 'internal': 0.05, 'area': 0.05}      # m²; every length is held to 2 mm


def differences(want, got, where='', key=None):
    """Where two snapshots disagree, as lines of text; none if they agree."""
    if isinstance(want, dict) and isinstance(got, dict):
        out = []
        for k in sorted(set(want) | set(got)):
            w = '%s.%s' % (where, k) if where else str(k)
            if k not in got:
                out.append('%s: missing' % w)
            elif k not in want:
                out.append('%s: not expected' % w)
            else:
                out += differences(want[k], got[k], w, k)
        return out
    if isinstance(want, list) and isinstance(got, list):
        if len(want) != len(got):
            return ['%s: %d expected, %d found' % (where, len(want), len(got))]
        return [d for i, (a, b) in enumerate(zip(want, got))
                for d in differences(a, b, '%s[%d]' % (where, i), key)]
    if isinstance(want, (int, float)) and isinstance(got, (int, float)) and not isinstance(want, bool):
        return [] if abs(want - got) <= TOL.get(key, 0.002) + 1e-9 else ['%s: %s expected, %s found' % (where, want, got)]
    return [] if want == got else ['%s: %r expected, %r found' % (where, want, got)]


def info(plan, scope):
    """What goes beside a sheet's drawing: its figures, its rooms as
    measured, and its notes by kind with their names filled in from
    `scope`."""
    fl = plan.spec
    return {'title': fl['title'],
            'summary': scope.text(fl['notes']['summary']),
            'figures': [('Gross external', '%.1f m²' % plan.gross),
                        ('Inside the walls', '%.1f m²' % plan.internal)],
            'rooms': [{'name': r['name'], 'w': r['w'], 'h': r['h'], 'area': r['area'], 'shape': r['shape']}
                      for r in plan.rooms],
            'groups': [(k, head, [scope.text(t) for t in fl['notes'][k]])
                       for k, head in NOTE_GROUPS if fl['notes'][k]]}


def info_md(i):
    """The same as a file to sit next to the image."""
    out = ['# ' + i['title'], '']
    if i['summary']:
        out += [i['summary'], '']
    out += ['%s: %s  ' % f for f in i['figures']] + ['']
    if i['rooms']:
        out += ['| Room | Clear size | Area | |', '|---|---|---|---|']
        out += ['| %s | %.2f × %.2f m | %.1f m² | %s |'
                % (r['name'], r['w'], r['h'], r['area'], SHAPES.get(r['shape'], '')) for r in i['rooms']]
        out.append('')
    for _, head, items in i['groups']:
        out += ['## ' + head, ''] + ['- ' + t for t in items] + ['']
    return '\n'.join(out)


# what a room's size means when the room is not a plain rectangle
SHAPES = {'near': 'overall', 'round': 'across', 'irregular': 'overall'}


def report(solved, source=None):
    """A whole house: every plan sheet's figures, notes and issues."""
    out = {'house': solved.house['name'], 'source': source or solved.path,
           'levels': solved.house['levels'], 'sheets': []}
    if totals(solved):
        out['total'] = totals(solved)
    for s in solved.plans():
        f = facts(s.plan)
        issues = f.pop('issues')
        f.update(level=s.level, scheme=s.scheme, changes=s.base.id if s.base else None, extends=s.plan.spec['extends'],
                 hidden=s.hidden)
        if s.base:
            f['gained'] = round(s.names['gained'], 2)
        f['notes'] = dict([('summary', s.info['summary'])] + [(k, items) for k, _, items in s.info['groups']])
        f['issues'] = issues
        out['sheets'].append(f)
    return out
