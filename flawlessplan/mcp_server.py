# -*- coding: utf-8 -*-
"""The houses as tools for an agent, over the Model Context Protocol.

    flawlessplan mcp [--workspace DIR]     # stdio

A thin adapter: every tool is one call into solve, report, query or marks,
the same ones the command line makes. Two tools write to a house file, and
only in ways that cannot break "a dimension is written down once": a
measured value in `survey`, and which group a note sits in. Walls, openings
and sheets are edited in the house file itself — which an agent with no
folder to write in does through `write_house` and `edit_house`, the file
whole or one passage of it, kept only if the house still solves.

The transport is the `mcp` SDK's; the functions below are plain and can be
called, and tested, without it.
"""
import contextlib
import functools
import os
import re
import sys
from typing import Literal, Optional
import yaml
from mcp.server.mcpserver import MCPServer, Image
from mcp.server.mcpserver.exceptions import ToolError as Refusal
from . import cli, edit, model, query, report, server
from .page import ASSETS
from .solve import solve, house_file
from .workspace import Workspace, EXAMPLES

WS = Workspace()                # the workspace the tools work in; serve() sets it
PAGES = {}                      # workspace root -> the URL its pages are being served at

INSTRUCTIONS = """Flawlessplan draws floor plans from house files: named measurements, walls, openings and rooms, \
with every room size measured from the geometry. Coordinates are metres, x east and y south.

To draw a house that is not there yet, call `guide` first and follow it: it is the procedure, every \
key of a house file and two whole houses to copy from. Then `write_house` makes it. You need no other \
access to the owner's machine.

A dimension is written down once. To change a measured size use set_measurement; never work a \
figure out and write it somewhere else. Anything structural — a wall, a door, a new sheet — is an \
edit to houses/<house>/house.yaml: `read_house`, then `edit_house` for one passage or `write_house` \
for the whole file, or `add_to_house` for one more wall, room or note at the end of its list (or edit \
the file itself, where you have it). Each answers with what check finds and the file's new `version`: \
pass the version you last had and a change is refused if the file is not that one, so after a call \
that timed out, try it again with the same version rather than guessing whether it was made. A \
change that is several passages at once — the file would not solve between them — is one `edit_house` \
with `edits`, solved once at the end and kept or refused whole.

After any change, read what `report` or `check` says rather than judging a picture: rooms come back \
as measured, and a missing wall is reported as two rooms being one space. Use `crop` on a metre or \
two when a detail matters; whole sheets are too small to read faults in. `crop` with no box is the \
whole sheet: use it for shape and arrangement — set it beside the drawing the house came from — and \
for nothing finer.

When the owner has drawn on a page, call `marks`. Look at the pictures before the coordinates and \
read the ink as signs: strokes drawn seconds apart and touching are usually one sign (a shaft and a \
V are an arrow). Decide what a sign is about — an arrow its tip, a ring its inside — and only then \
ask `at` what the plan has there. A mark says where and what, never why: say back to the owner what \
you take each mark to mean before changing anything, and ask where the plan does not settle it. \
Once a mark is built in, close it with `resolve_marks` in the same turn: `marks` then stops sending it."""


class ToolError(Refusal, ValueError):
    """What a tool will not do, said to the agent in so many words."""


def _house(name):
    """The folder of a house named as list_houses gives it."""
    try:
        return WS.house(name)
    except ValueError as e:
        raise ToolError(str(e))


def houses():
    return WS.names()


def _png(path):
    if not os.path.exists(path):
        raise ToolError('no picture was made of %s' % os.path.basename(path))
    return Image(path=path)


# ---- reading

def list_houses() -> list:
    out = []
    for name in houses():
        try:
            s = solve(_house(name))
        except (model.ConfigError, ValueError) as e:
            out.append({'house': name, 'error': str(e)})
            continue
        out.append({'house': name, 'name': s.house['name'], 'levels': s.house['levels'],
                    'sheets': [{'id': p.id, 'title': p.title, 'level': p.level, 'scheme': p.scheme,
                                'changes': p.base.id if p.base else None,
                                'extends': p.plan.spec['extends'], 'hidden': p.hidden} for p in s.plans()]})
    return out


def check(house: str) -> str:
    issues = solve(_house(house)).issues()
    order = sorted(issues, key=lambda i: report.LEVELS[i[1]])
    return '\n'.join('%s: %-5s %s' % i for i in order) or 'nothing found'


def sheet_report(house: str, sheet: Optional[str] = None, brief: bool = False) -> dict:
    rep = report.report(solve(_house(house)))
    if sheet is not None:
        rep['sheets'] = [f for f in rep['sheets'] if f['id'] == sheet]
        if not rep['sheets']:
            raise ToolError('no sheet called %r' % sheet)
    if brief:
        del rep['source']
        rep['sheets'] = [dict((k, v) for k, v in f.items() if k not in ('openings', 'fittings', 'rooflights', 'notes', 'title'))
                         for f in rep['sheets']]
    return rep


def at(house: str, sheet: str, x: float, y: float, radius: Optional[float] = None,
       x1: Optional[float] = None, y1: Optional[float] = None) -> str:
    sh = solve(_house(house)).sheet(sheet)
    if x1 is not None and y1 is not None:
        return '\n'.join(query.lines(query.at(sh, (min(x, x1), min(y, y1), max(x, x1), max(y, y1)))))
    if radius is not None:
        return '\n'.join(query.lines(query.at(sh, (x, y), reach=radius)))
    return '\n'.join(query.lines(query.at(sh, (x, y))))


def crop(house: str, sheet: str, x0: Optional[float] = None, y0: Optional[float] = None,
         x1: Optional[float] = None, y1: Optional[float] = None, marks: bool = False,
         mark_ids: Optional[list] = None) -> list:
    box = (x0, y0, x1, y1)
    if all(v is None for v in box):
        png = _png(cli.crop(_house(house), sheet, ink=bool(marks), ws=WS, ids=mark_ids))
        return ['%s · %s · %s' % (house, sheet, 'what was built, beside what was drawn: marks %s' % ', '.join(mark_ids)
                                  if mark_ids else 'the whole sheet'), png]
    if None in box or x1 <= x0 or y1 <= y0:
        raise ToolError('give the box as x0 < x1 and y0 < y1, or leave all four out for the whole sheet')
    png = cli.crop(_house(house), sheet, box, ink=bool(marks), ws=WS, ids=mark_ids)
    return ['%s · %s · x %.2f–%.2f, y %.2f–%.2f m' % (house, sheet, x0, x1, y0, y1), _png(png)]


def marks(house: str, include_resolved: bool = False, sheet: Optional[str] = None) -> list:
    brief = cli.marked(_house(house), WS, bool(include_resolved), sheet)
    if not brief:
        said = cli.nothing(_house(house), house, bool(include_resolved), sheet)
        return ['nothing drawn on %s yet' % house if said.endswith('nothing drawn yet') and not sheet else said]
    out = [brief]
    for png in re.findall(r'`([^`]+\.png)`', brief):          # in the order the brief speaks of them
        out += [png, _png(png)]
    return out


def resolve_marks(house: str, ids: list, note: str, sheets: Optional[list] = None, reopen: bool = False) -> str:
    return '\n'.join(cli.resolve(_house(house), ids, note, sheets, bool(reopen)))


def show(house: Optional[str] = None, sheet: Optional[str] = None) -> str:
    """Build the workspace and serve its pages from this process."""
    reps, failed = cli.build_all(WS)
    at = ''
    if sheet is not None:
        if house is None:
            raise ToolError('name the house whose sheet it is')
        s = solve(_house(house))
        if s.sheet(sheet).hidden:
            raise ToolError('%s is hidden: it has no tab to open on (hide_sheet with hidden false shows it again)' % sheet)
        at = '#' + sheet
    elif house is not None:
        _house(house)
    if WS.root not in PAGES:
        PAGES[WS.root] = server.background(WS)
    return '%s%s  —  what is drawn there is saved, and `marks` reads it%s' % (
        PAGES[WS.root], house + '/' + at if house else '',
        '\nnot built: ' + ', '.join(failed) if failed else '')


def share(house: str) -> str:
    return cli.share(_house(house), ws=WS)


def init_workspace(examples: bool = True) -> str:
    """Make the folder the tools work in a workspace."""
    made = WS.init(examples=examples)
    return '\n'.join(['workspace: %s' % WS.root] + made) if made else 'already a workspace: %s' % WS.root


def guide() -> str:
    """How a house is written: the procedure, the keys, and the examples whole."""
    out = [open(os.path.join(ASSETS, name)).read() for name in ('new-house.md', 'house-file.md')]
    for name in sorted(os.listdir(EXAMPLES)):
        path = os.path.join(EXAMPLES, name, 'house.yaml')
        if os.path.exists(path):
            out.append('## Example: %s\n\n```yaml\n%s```\n' % (name, open(path).read()))
    return '\n'.join(out)


def _said(fn):
    """One of edit's, with what it refuses said as a tool says it and the
    workspace the tools work in."""
    @functools.wraps(fn)
    def run(*a, **k):
        try:
            return fn(*a, **k)
        except edit.Refused as e:
            raise ToolError(str(e))
    return run


_version = edit.version
_same = _said(edit.same)


def read_house(house: str) -> dict:
    with open(house_file(_house(house))) as fh:
        text = fh.read()
    return {'house': house, 'version': _version(text), 'text': text}


def measurements(house: str) -> dict:
    h = solve(_house(house)).house
    return {'survey': dict((k, dict({'value': round(h['names'][k], 4), 'status': st},
                                    **({'written': h['written'][k]} if k in h['written'] else {})))
                           for k, st in h['status'].items() if st != 'derived'),
            'lines': dict((k, round(h['names'][k], 4)) for k, st in h['status'].items() if st == 'derived')}


# ---- writing

def _rewrite(path, text):
    """Replace a house file, or make it, by the one way in: kept only if
    it solves, and its pages drawn again."""
    return _said(edit.rewrite)(path, text, WS)


_moved = edit.moved


LONGEST = edit.LONGEST


def write_house(house: str, text: str, version: Optional[str] = None) -> dict:
    try:
        path = os.path.join(WS.place(house), 'house.yaml')
    except ValueError as e:
        raise ToolError(str(e))
    if len(text) > LONGEST:
        raise ToolError('that is too long to be a house file')
    new = not os.path.exists(path)
    if version and new:
        raise ToolError('not changed — there is no house %s for that to be a version of' % house)
    if not new:
        with open(path) as fh:
            _same(fh.read(), version)
    before, after, was = _rewrite(path, text if text.endswith('\n') else text + '\n')
    return dict({'house': house, 'did': 'made' if new else 'replaced',
                 'sheets': [p.id for p in after.plans()]}, **_moved(before, after, was))


def edit_house(house: str, old: Optional[str] = None, new: Optional[str] = None, version: Optional[str] = None,
               edits: Optional[list] = None) -> dict:
    path = house_file(_house(house))
    with open(path) as fh:
        text = fh.read()
    if edits is None:
        if old is None or new is None:
            raise ToolError('give `old` and `new`, or `edits`: a list of {old, new}')
        steps = [(old, new, '')]
    else:
        if old is not None or new is not None:
            raise ToolError('give `old` and `new`, or `edits` — not both')
        if not isinstance(edits, list) or not edits or not all(
                isinstance(e, dict) and set(e) == {'old', 'new'} and all(isinstance(v, str) for v in e.values()) for e in edits):
            raise ToolError('`edits` is a list of {old, new}, each a passage and what goes there instead')
        steps = [(e['old'], e['new'], 'edits[%d]: ' % i) for i, e in enumerate(edits)]
    _same(text, version, [s[1] for s in steps])
    made = text
    for was_, now, which in steps:                      # each on the file as the ones before it left it
        if not was_ or made.count(was_) != 1:
            raise ToolError('not changed — %s%s: give a passage that is there exactly once, with enough round it to be '
                            'the only one%s' % (which, 'that is in the file %d times' % made.count(was_) if was_ and was_ in made
                                                else 'nothing in the file reads exactly that',
                                                ' (as the edits before it leave the file)' if which and which != 'edits[0]: ' else ''))
        made = made.replace(was_, now)
        if len(made) > LONGEST:
            raise ToolError('that is too long to be a house file')
    before, after, was = _rewrite(path, made)
    return dict({'house': house, 'did': 'edited'}, **_moved(before, after, was))


BLOCK = r'^(\s*)(?:- )?(%s):\s*(#.*)?$'              # a key with its value on the lines under it
ITEM = r'^(\s*)- \{?\s*id:\s*(%s)\s*([,}#].*)?$'      # the entry of a list that has that id


def _within(lines, lo, hi, name):
    """Where in lines[lo:hi] the block called `name` is: a key with its
    value on the lines under it, or the entry of a list that has that id.
    Returns (line, the indent its own lines have at least, where it ends),
    or None. The nearest the margin is the one meant."""
    found = None
    for i in range(lo, hi):
        m = re.match(BLOCK % re.escape(name), lines[i])
        item = re.match(ITEM % re.escape(name), lines[i])
        if m and lines[i].lstrip().startswith('- '):
            m = None                                    # `- walls:` is an entry that begins with a key, not this
        if not (m or item):
            continue
        dent = len((m or item).group(1))
        if found is None or dent < found[1]:
            found = (i, dent, bool(item))
    if found is None:
        return None
    i, dent, item = found
    end = i + 1
    while end < hi:
        ln = lines[end]
        if ln.strip() and not ln.lstrip().startswith('#'):
            d = len(ln) - len(ln.lstrip())
            # an entry's lines are further in than its dash; a key's list may sit level with the key
            if d < dent or (d == dent and (item or not ln.lstrip().startswith('- '))):
                break
        end += 1
    return i, dent, end


def _last(lines, lo, hi):
    """The line after the last thing written in lines[lo:hi]: remarks and
    gaps before whatever comes next stay with what comes next."""
    while hi > lo and (not lines[hi - 1].strip() or lines[hi - 1].lstrip().startswith('#')):
        hi -= 1
    return hi


def _reach(data, parts):
    for p in parts:
        if isinstance(data, dict) and p in data:
            data = data[p]
        elif isinstance(data, list):
            data = next((v for v in data if isinstance(v, dict) and str(v.get('id')) == p), None)
        else:
            return None
    return data


def add_to_house(house: str, to: str, entry: str, version: Optional[str] = None) -> dict:
    path = house_file(_house(house))
    with open(path) as fh:
        text = fh.read()
    body = [ln for ln in entry.strip('\n').split('\n')]
    gap = min([len(ln) - len(ln.lstrip()) for ln in body if ln.strip()] or [0])
    body = [ln[gap:].rstrip() for ln in body]
    if body and body[0].startswith('- '):
        body = [body[0][2:]] + [ln[2:] if ln.startswith('  ') else ln for ln in body[1:]]
    written = '\n'.join(body)
    _same(text, version, written)
    parts = [p for p in to.split('.') if p]
    if not parts or not written.strip():
        raise ToolError('say where it goes — `sheets.ground.walls`, `survey`, `sheets.first.notes.decided` — and what the entry is')
    if len(text) + len(entry) + 80 > LONGEST:
        raise ToolError('that is too long to be a house file')
    by_hand = 'not changed — %s; make this one with edit_house'
    lines = text.split('\n')
    lo, hi, dent, missing = 0, len(lines), -2, []
    for n, p in enumerate(parts):
        got = _within(lines, lo, hi, p)
        if got is None:
            # a key that is not there is begun, where what holds it is; a sheet or a part is not made up
            held = yaml.safe_load(text) if n else None
            if not isinstance(_reach(held, parts[:n]), dict) or _reach(held, parts[:n + 1]) is not None:
                raise ToolError(by_hand % ('nothing in the file is laid out as `%s`, a key or an id with its entries '
                                           'on the lines under it' % '.'.join(parts[:n + 1])))
            missing = parts[n:]
            break
        dent, (lo, hi) = got[1], (got[0] + 1, got[2])
    inner = [ln for ln in lines[lo:hi] if ln.strip() and not ln.lstrip().startswith('#')]
    step = len(inner[0]) - len(inner[0].lstrip()) if inner else dent + 2
    put = _last(lines, lo, hi)
    new = []
    for key in missing:                                 # the list is not there yet: begin it, at the end of what holds it
        new.append('%s%s:' % (' '*step, key))
        step, inner = step + 2, []
    listed = inner[0].lstrip().startswith('- ') if inner else parts[-1] not in ('survey', 'lines', 'leaves')
    for k, ln in enumerate(body):
        lead = ('- ' if k == 0 else '  ') if listed else ''
        new.append((' '*step + lead + ln) if ln else '')
    after_text = '\n'.join(lines[:put] + new + lines[put:])
    try:                                                # the file read back: that entry, there, and nothing else touched
        was, now = yaml.safe_load(text), yaml.safe_load(after_text)
        at_was, at_now = _reach(was, parts), _reach(now, parts)
        one = yaml.safe_load(written)
        if listed:
            ok = isinstance(at_now, list) and at_now[:-1] == (at_was or []) and at_now[-1] == one
        else:
            ok = isinstance(at_now, dict) and isinstance(one, dict) and len(one) == 1 and not set(one) & set(at_was or {}) \
                and at_now == dict(at_was or {}, **one)
    except (yaml.YAMLError, RecursionError):
        ok = False
    if not ok:
        raise ToolError(by_hand % ('that did not go in as one new entry of `%s`%s'
                                   % (to, '' if listed else ' (a name that is there already is changed, not added)')))
    before, after, was = _rewrite(path, after_text)
    return dict({'house': house, 'did': 'added', 'to': to}, **_moved(before, after, was))


def set_measurement(house: str, name: str, value: float) -> dict:
    path = house_file(_house(house))
    h = solve(path).house
    if h['status'].get(name) == 'derived':
        raise ToolError('%s is worked out in `lines`, not measured: change what it is stepped off' % name)
    if name not in h['status']:
        raise ToolError('no measurement called %r in survey (see measurements)' % name)
    lines = open(path).read().split('\n')
    start = next((i for i, ln in enumerate(lines) if re.match(r'survey:\s*(#.*)?$', ln)), None)
    if start is None:
        raise ToolError('survey is not written as a block in this file; edit it by hand')
    spot = re.compile(r'^(\s+%s:\s*(?:\{\s*value:\s*)?)(-?\d+(?:\.\d+)?)(?=\s*(?:[,}#]|$))' % re.escape(name))
    old = None
    for i in range(start + 1, len(lines)):
        if lines[i] and not lines[i][0].isspace() and not lines[i].startswith('#'):
            break                                               # the next top-level key
        m = spot.match(lines[i])
        if m:
            old = float(m.group(2))
            lines[i] = m.group(1) + ('%g' % value) + lines[i][m.end():]
            break
    if old is None:
        raise ToolError('%s is not written as a plain number in survey; edit it by hand' % name)
    moved = _moved(*_rewrite(path, '\n'.join(lines)))
    return {'measurement': name, 'was': old, 'now': float(value), 'version': moved['version'],
            'changed': moved['changed'] or ['nothing in any sheet depends on it'],
            'issues': moved['issues'],
            'note': 'expected.json is not updated: run `flawlessplan snapshot` once the change is agreed'}


def order_sheets(house: str, order: list, version: Optional[str] = None) -> dict:
    return dict({'house': house}, **_said(edit.order_sheets)(_house(house), order, version, WS))


def hide_sheet(house: str, sheet: str, hidden: bool = True, version: Optional[str] = None) -> dict:
    return dict({'house': house}, **_said(edit.hide_sheet)(_house(house), sheet, bool(hidden), version, WS))


GROUPS = [k for k, _ in model.NOTE_GROUPS]


def settle_note(house: str, sheet: str, text: str,
                to: Literal['decided', 'unconfirmed', 'needs', 'about'] = 'decided') -> str:
    if to not in GROUPS:
        raise ToolError('no group called %r (have %s)' % (to, ', '.join(GROUPS)))
    path = house_file(_house(house))
    sh = solve(path).sheet(sheet)
    lines = open(path).read().split('\n')
    item = re.compile(r'^(\s*)- (.+)$')
    found = []
    for i, ln in enumerate(lines):
        m = item.match(ln)
        if not m:
            continue
        try:
            raw = yaml.safe_load(m.group(2))
        except yaml.YAMLError:
            continue
        if not isinstance(raw, str):
            continue
        try:
            shown = sh.scope.text(raw)
        except Exception:
            shown = raw
        if text.strip() in (raw.strip(), shown.strip()):
            found.append(i)
    if len(found) != 1:
        raise ToolError('%s notes read exactly that' % ('no' if not found else 'more than one of the'))
    i = found[0]
    indent = len(item.match(lines[i]).group(1))
    head = max(k for k in range(i) if lines[k].strip() and not lines[k].lstrip().startswith(('-', '#'))
               and len(lines[k]) - len(lines[k].lstrip()) < indent)
    group = lines[head].strip().rstrip(':')
    if group not in GROUPS:
        raise ToolError('that line is not a note in a group (it is under %r)' % group)
    if group == to:
        return 'already under %s' % to
    key = len(lines[head]) - len(lines[head].lstrip())
    note = lines.pop(i)
    if not (head + 1 < len(lines) and item.match(lines[head + 1])):      # the group it left is empty
        lines.pop(head)
    # the groups of this one `notes:` — the lines under it indented as deep as its keys
    top = max(k for k in range(head) if lines[k].strip() and len(lines[k]) - len(lines[k].lstrip()) < key)
    end = top + 1
    while end < len(lines) and (not lines[end].strip() or len(lines[end]) - len(lines[end].lstrip()) >= key):
        end += 1
    while not lines[end - 1].strip():
        end -= 1
    dest = next((k for k in range(top + 1, end) if lines[k].strip() == to + ':'
                 and len(lines[k]) - len(lines[k].lstrip()) == key), None)
    if dest is None:
        lines[end:end] = [' '*key + to + ':', note]
    else:
        last = dest + 1
        while last < end and (not lines[last].strip() or len(lines[last]) - len(lines[last].lstrip()) > key):
            last += 1
        while not lines[last - 1].strip():
            last -= 1
        lines[last:last] = [note]
    _rewrite(path, '\n'.join(lines))
    return 'moved from %s to %s' % (group, to)


# ---- the tools as the protocol lists them

TOOLS = [
    (list_houses, 'list_houses', 'Every house, with its levels and its sheets: which level each draws, '
     'its scheme, the sheet it changes, the sheet it extends, and whether it is hidden. They are in the order of '
     'the tabs, which is the order of `sheets:` in the file.'),
    (guide, 'guide', 'How to draw a house that is not there yet, or add to one: what to ask the owner, the '
     'order to work in, every key of a house file, and two whole houses to copy from. Read it before '
     'write_house or edit_house; it is long, and needs reading once.'),
    (init_workspace, 'init_workspace', 'Set up the folder the tools work in as a workspace: a `houses/` folder, '
     'and unless examples is false two example houses to copy from. Nothing already there is touched. Use '
     'it when list_houses comes back empty.'),
    (check, 'check', 'Everything the checks find wrong with a house, errors first: openings off their '
     'wall, rooms that are one space (a wall is missing), labels with nowhere to go. `house` is a folder '
     'name in houses/, as list_houses gives it.'),
    (sheet_report, 'report', "A house as figures: each sheet's areas, every room as measured, every "
     'opening with its wall, centre and width, every fitting and rooflight, its notes by kind, and issues. Name a sheet for one. With '
     '`brief`, areas, rooms and issues only: what to read after a change. `total` adds up the levels as '
     'they stand. `internal` is everything inside the outside walls — partitions, stairs and stairwells '
     'with it, whatever the headroom — so it is not always the figure an agent quotes.'),
    (show, 'show', 'Draw every house and open its pages on this machine: returns the address to give the '
     'owner, where each sheet is a tab they can draw and write on. Name a house to get its page, and a `sheet` '
     'for the address that opens on that tab — the one just changed. Once '
     'shown, a page follows every change these tools make to its house: it is redrawn and loads itself '
     'again, so there is no need to call this a second time.'),
    (share, 'share', 'A house as one file for the owner to send to someone else: every sheet with what is '
     'said beside it, each drawn once. Nothing can '
     'be drawn on it and it needs nothing else to open. Returns where the file is. It holds the whole plan, '
     'private houses included: who gets it is the owner\'s to decide.'),
    (measurements, 'measurements', 'The names a house is drawn from: `survey` (with whether each was '
     'given, traced off a drawing or assumed, and the feet and inches it was written in, if it was) and '
     '`lines` (worked out from them).'),
    (at, 'at', "What a sheet has at a point, by the house file's own names: rooms, walls, openings, "
     'stairs. Give x, y in metres; add radius to reach further, or x1, y1 for a box. Decide what a mark '
     'or a remark is about before asking.'),
    (crop, 'crop', 'A close picture of part of one sheet, in metres. Use a metre or two: faults a whole '
     "sheet hides show up. With marks, two panels: the drawing, and the same with the owner's ink. Leave "
     'the box out for the whole sheet: its shape and arrangement, to set beside the drawing it was taken '
     'from. With `mark_ids`, those marks — open or resolved, whichever sheet they were drawn on — are set on '
     'this sheet as it is now, framed round them if no box is given: one picture of what was built beside what '
     'was drawn, to show the owner after a change made from their marks.'),
    (marks, 'marks', "What the owner drew on a house's page, laid out for reading: for each cluster of "
     'ink a picture of two panels (the drawing; the same with the ink in magenta, numbered in blue), and '
     'the strokes in the order drawn, each with its id. It does not interpret: read the ink as signs '
     'first, then ask `at`. Only the marks still open, unless `include_resolved`, which adds the ones '
     'dealt with, in grey, with how; `sheet` is the marks drawn on one sheet. Says if the house file has '
     'changed since the marks were made.'),
    (resolve_marks, 'resolve_marks', 'Close the marks you have built in, in the same turn as the change: `ids` as '
     '`marks` lists them, `note` one line saying how they were dealt with. They stay in the file and can be '
     'shown on the page in grey, but are no longer sent by `marks`. `sheets` records the sheets a mark was '
     'applied to where that is not only the one it was drawn on — the owner drew on one option and meant '
     'two. All of the ids or none. `reopen` opens them again. Only the owner deletes a mark, on the page.'),
    (set_measurement, 'set_measurement', "Change one measured value in a house's `survey`, in metres. "
     'Everything stepped off it follows. Returns what moved in every sheet and any new problem. Refuses '
     'a name from `lines`, which is derived.'),
    (read_house, 'read_house', "A house's file as it is written: the YAML that every sheet is drawn from, "
     'as `text`, and its `version`. Read it before edit_house. Give the version to a tool that writes the '
     'file and it is refused if the file has changed since — which is how to find out, after a call that '
     'timed out, whether it was made: the refusal says if what you were writing is already there.'),
    (write_house, 'write_house', 'Make a new house, or replace the whole file of one that is there: `house` is '
     'its folder name (letters, digits, - and _), `text` the whole of its house.yaml. Kept only if it '
     'solves; otherwise nothing changes and the fault is said. Returns what check finds, and for a house '
     'that was there what moved. Build a house up in steps — envelope, walls, rooms, openings, stairs — '
     'not in one go. Read `guide` first.'),
    (edit_house, 'edit_house', "Change one passage of a house's file: `old` is text that is in it exactly "
     'once, `new` what goes there instead. For anything structural — a wall, a door, a room, a sheet, a '
     'note. Kept only if the house still solves. Returns what moved in every sheet — stairs and notes '
     'as written, everything else as measured — and what check finds. Where the change made one room of '
     'two, `still_standing` lists the walls and doors that parted them and are still there, inside the '
     'room: decide on each. '
     '`check_subs` lists rooms the change resized whose `sub` holds a figure written by hand, which may '
     'no longer hold. A measured size is set_measurement, not this. `version`, from read_house or the last change, '
     'makes it safe to try again. For a change that takes several passages — a new name in `survey`, the '
     'line stepped off it and the wall on that line; a part taken out and every sheet that used it — give '
     '`edits`, a list of {old, new}, in place of `old` and `new`: they are made in order, the house is '
     'solved once at the end, and all of them are kept or none.'),
    (add_to_house, 'add_to_house', 'Add one entry to the end of a list in a house\'s file, without quoting what is '
     'there: `to` is where — `sheets.ground.walls`, `sheets.first.rooms`, `parts.core.openings`, '
     '`sheets.ground.notes.decided`, or `survey` or `lines` for a new name — and `entry` is the entry as '
     'it would be written, without its dash: `{id: larder_e, from: [LX, 0], to: [LX, LY]}`. A list the '
     'sheet does not have yet is begun. Kept only if the house still solves; returns what moved and what '
     'check finds, as edit_house does. Where the file is not laid out in blocks it says so, and '
     'edit_house makes the change. `version` as for edit_house.'),
    (order_sheets, 'order_sheets', "Put a house's sheets in another order: `order` is sheet ids, each once, and those "
     'sheets are rearranged among the places they hold now — name them all, or only the ones to move. It is '
     'the order of `sheets:` in the file, so the tabs, the file that is sent and every tool follow it. A sheet '
     'stays after the one it changes or extends. Returns what edit_house does; `version` as for it.'),
    (hide_sheet, 'hide_sheet', 'Hide a sheet, or with `hidden` false show it again: `hidden: true` on it in the house '
     'file. A hidden sheet has no tab on the page and is left out of the file that is sent; it is still drawn, '
     'still checked and can still be changed or extended by another. The last sheet showing cannot be hidden. '
     'A sheet is taken out for good only by the owner, on the page, from its list of hidden sheets.'),
    (settle_note, 'settle_note', 'Move one note of a sheet to another group — by default from '
     '`unconfirmed` to `decided`, once the owner has agreed it. Give the note as the report shows it.'),
]


def _quiet(fn):
    """Run a tool with stdout turned aside — it is the protocol's, and the
    engine prints — and with what a house file gets wrong passed on as said."""
    @functools.wraps(fn)
    def run(*a, **k):
        try:
            with contextlib.redirect_stdout(sys.stderr):
                return fn(*a, **k)
        except Refusal:
            raise
        except (model.ConfigError, ValueError) as e:
            raise ToolError(str(e))
    return run


def make():
    app = MCPServer('flawlessplan', instructions=INSTRUCTIONS)
    for fn, name, about in TOOLS:
        app.add_tool(_quiet(fn), name=name, description=about)
    return app


def serve(ws=None):
    global WS
    WS = ws or Workspace()
    make().run()
