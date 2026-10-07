# -*- coding: utf-8 -*-
"""A house file changed, by whoever is changing it: an agent's tools or the
owner's page. There is one way in. The file as it was read is named by its
version, and a change given a version is refused if the file is no longer
that one; what is written is kept only if the house still solves; and the
house's pages are drawn again, so what the owner has open is never behind.

Here too is what the page does to the sheets of a house — their order,
which are hidden, and one binned — as changes to the text of the file, with
every remark in it left where it was.
"""
import hashlib
import os
import re
import yaml
from . import model, report
from .solve import solve, house_file

LONGEST = 400000                # characters of house file that will be taken


class Refused(ValueError):
    """A change that was not made, and why, in so many words."""


def version(text):
    """A few characters that stand for a house file as it reads now: what
    whoever writes it is given, to be sure of what they are writing over."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:10]


def same(text, given, new=None):
    """Refuse to write over a file that is not the one that was read. A
    call that timed out may have been made all the same: say when what is
    being written is in the file already, and leave what to do to whoever
    reads it again."""
    if given and given != version(text):
        new = [n for n in (new if isinstance(new, list) else [new]) if n and n.strip()]
        there = bool(new) and all(text.count(n) == 1 for n in new)
        raise Refused('not changed — the file is not as it was at version %s (it is now %s)%s. Read it again'
                      % (given, version(text), ', and what this writes is already in it once: '
                         'an earlier call that seemed to fail was probably made' if there else ''))


def rewrite(path, text, ws):
    """Replace a house file, or make it, and leave things as they were if
    it does not solve. Returns its state before (None for a house that
    is new, or did not solve), the house solved after, and the house as
    it was solved before."""
    old = before = was = None
    if os.path.exists(path):
        with open(path) as fh:
            old = fh.read()
        try:
            was = solve(path)
            before = report.state(was)
        except (model.ConfigError, ValueError):
            pass
    made = not os.path.isdir(os.path.dirname(path))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as fh:
        fh.write(text)
    try:
        after = solve(path)
    except Exception as e:                  # whatever a file from anywhere gets wrong
        if old is None:
            os.remove(path)
            if made:
                os.rmdir(os.path.dirname(path))
        else:
            with open(path, 'w') as fh:
                fh.write(old)
        raise Refused('not changed — the house would not solve: %s' % (e if str(e) else type(e).__name__))
    redraw(os.path.dirname(path), ws, new=old is None)
    return before, after, was


def redraw(house, ws, new=False):
    """Draw a house's pages again once its file has changed, so what the
    owner has open is never behind it: the page asks the server whether it
    has been redrawn, and loads itself again. Only where pages have been
    drawn at all; a house that is new goes into the index of them too."""
    from . import cli                       # cli draws, and reads this module's refusals
    if not os.path.isdir(ws.build):
        return
    if new:
        cli.build_all(ws)
    else:
        cli.build_house(house, os.path.join(ws.build, os.path.basename(house)), quiet=True, root='../')


def moved(before, after, was=None):
    """What a change to a house file did. Where it made one room of two,
    what parted them and was not taken out is listed, for whoever made the
    change to decide on each."""
    with open(after.path) as fh:
        now = version(fh.read())
    out = {'version': now,
           'changed': [re.sub(r': (.+) expected, (.+) found$', r': \1 → \2', d)
                       for d in report.differences(before, report.state(after))] if before else [],
           'issues': ['%s: %s %s' % i for i in after.issues() if i[1] != 'info']}
    left = report.standing(was, after) if was else []
    if left:
        out['still_standing'] = left
    subs = report.stale(out['changed'], after)
    if subs:
        out['check_subs'] = subs
    return out


# ---- the sheets of a house: their order, which are hidden, one binned

BY_HAND = 'not changed — %s; make this change in the house file itself'


def _sheets(text):
    """The `sheets:` of a house file as its text has them: the lines
    before the first sheet, each sheet's lines — the remarks above it with
    it — and the lines after the last, with the sheets as YAML reads them.
    Only where they are written as a list of blocks."""
    try:
        raw = yaml.safe_load(text)
    except (yaml.YAMLError, RecursionError) as e:
        raise Refused('not changed — the house file cannot be read: %s' % ' '.join(str(e).split())[:200])
    listed = raw.get('sheets') if isinstance(raw, dict) else None
    lines = text.split('\n')
    top = [i for i, ln in enumerate(lines) if re.match(r'sheets:\s*(#.*)?$', ln)]
    if not isinstance(listed, list) or len(top) != 1 or not all(isinstance(f, dict) and 'id' in f for f in listed):
        raise Refused(BY_HAND % 'its sheets are not written as a list under `sheets:`, each with an `id`')
    lo = top[0] + 1
    hi = next((i for i in range(lo, len(lines)) if lines[i] and not lines[i][0].isspace() and not lines[i].startswith('#')),
              len(lines))
    while hi > lo and (not lines[hi - 1].strip() or (lines[hi - 1].startswith('#'))):
        hi -= 1                                         # remarks at the margin above the next key are that key's
    body = [i for i in range(lo, hi) if lines[i].strip() and not lines[i].lstrip().startswith('#')]
    dent = len(lines[body[0]]) - len(lines[body[0]].lstrip()) if body else 0
    starts = [i for i in body if lines[i].startswith(' '*dent + '- ')]
    if len(starts) != len(listed) or not body or body[0] != starts[0]:
        raise Refused(BY_HAND % 'its sheets are not written one block to a sheet')
    chunks = []
    for k, i in enumerate(starts):
        last = max(j for j in body if j < (starts[k + 1] if k + 1 < len(starts) else hi)) + 1
        first = i
        if k == 0:                                      # the first takes the remarks straight above it and no more
            while first > lo and lines[first - 1].lstrip().startswith('#'):
                first -= 1
        else:
            first = chunks[-1][1]                       # the gap and the remarks after the one before are this one's
        chunks.append((first, last))
    return lines, chunks, listed, raw, dent


def _put(path, text, lines, chunks, order, raw, want, given, ws, swap=None):
    """Write the file with its sheets' blocks in `order` (indices into
    `chunks`; one left out is taken out), having read it back: the sheets
    YAML then gives are `want` and nothing else in the file has moved."""
    same(text, given)
    blocks = dict((k, lines[a:b]) for k, (a, b) in enumerate(chunks))
    gaps = {}                                           # the blank lines above each place stay with the place
    for k in list(blocks):
        n = next((i for i, ln in enumerate(blocks[k]) if ln.strip()), 0)
        gaps[k], blocks[k] = n, blocks[k][n:]
    for k, block in (swap or {}).items():
        blocks[k] = block[next((i for i, ln in enumerate(block) if ln.strip()), 0):]
    new = lines[:chunks[0][0]] + [ln for p, k in enumerate(order) for ln in ['']*gaps[p] + blocks[k]] + lines[chunks[-1][1]:]
    made = '\n'.join(new)
    try:
        now = yaml.safe_load(made)
        ok = isinstance(now, dict) and now.get('sheets') == want and \
            dict((k, v) for k, v in now.items() if k != 'sheets') == dict((k, v) for k, v in raw.items() if k != 'sheets')
    except (yaml.YAMLError, RecursionError):
        ok = False
    if not ok:
        raise Refused(BY_HAND % 'the sheets are not laid out so that this can be done to their text')
    if made == text:
        return None
    return rewrite(path, made, ws)


def _read(path):
    path = house_file(path)
    with open(path) as fh:
        return path, fh.read()


def _answer(path, text, did, done):
    if done is None:                                    # nothing to do: as it is, and its version
        return dict({'did': 'nothing: it is so already', 'version': version(text), 'changed': [], 'issues': []})
    return dict({'did': did}, **moved(*done))


def depends(solved):
    """What each sheet of a house needs to be there, and before it:
    {sheet: [(the sheet it needs, why)]} — the one it `changes`, the one
    it `extends`, one whose stair it shows by `ref`."""
    out = {}
    for fl in solved.house['sheets']:
        need = [(fl[k], k) for k in ('changes', 'extends') if fl[k]]
        need += [(st['ref'], 'a stair `ref`') for st in fl['stairs'] if st.get('ref')]
        out[fl['id']] = [(a, b) for i, (a, b) in enumerate(need) if (a, b) not in need[:i]]
    return out


def order_sheets(path, order, given=None, ws=None):
    """Put the sheets named in `order` in that order, among the places
    they hold now: a sheet not named stays where it is. The order of
    `sheets:` in the file is the order of the tabs, of the file that is
    sent and of everything the tools list."""
    path, text = _read(path)
    lines, chunks, listed, raw, _ = _sheets(text)
    ids = [str(f['id']) for f in listed]
    order = [str(o) for o in order] if isinstance(order, list) else []
    lost = [o for o in order if o not in ids]
    if not order or lost or len(set(order)) != len(order):
        raise Refused('not changed — give the sheets to put in order, each once, by id (have %s)%s'
                      % (', '.join(ids), ': no sheet called ' + ', '.join(map(repr, lost)) if lost else ''))
    slots = [i for i, sid in enumerate(ids) if sid in order]
    now = list(range(len(ids)))
    for slot, sid in zip(slots, order):
        now[slot] = ids.index(sid)
    try:
        need = depends(solve(path))
    except (model.ConfigError, ValueError):
        need = {}
    at = dict((ids[k], n) for n, k in enumerate(now))
    for sid in ids:
        for other, why in need.get(sid, []):
            if other in at and at[other] > at[sid]:
                raise Refused('not changed — %s must come after %s, which is %s' % (
                    sid, other, {'changes': 'the sheet it changes', 'extends': 'the sheet it extends'}.get(why, 'where its stair is drawn')))
    done = _put(path, text, lines, chunks, now, raw, [listed[k] for k in now], given, ws)
    return dict(_answer(path, text, 'put in order', done), sheets=[ids[k] for k in now])


def hide_sheet(path, sheet, hidden=True, given=None, ws=None):
    """Hide a sheet, or show it again: `hidden: true` on it in the file. A
    hidden sheet has no tab and is not in the file that is sent; it is
    still drawn and still checked, and other sheets may still change it."""
    path, text = _read(path)
    lines, chunks, listed, raw, dent = _sheets(text)
    ids = [str(f['id']) for f in listed]
    if str(sheet) not in ids:
        raise Refused('not changed — no sheet called %r (have %s)' % (sheet, ', '.join(ids)))
    k = ids.index(str(sheet))
    if hidden and not [f for i, f in enumerate(listed) if i != k and not f.get('hidden')]:
        raise Refused('not changed — %s is the only sheet showing: a house shows at least one' % sheet)
    a, b = chunks[k]
    block = [ln for ln in lines[a:b] if not re.match(r'^\s{%d}hidden:\s*\S+\s*(#.*)?$' % (dent + 2), ln)]
    want = [dict(f) for f in listed]
    want[k].pop('hidden', None)
    if hidden:
        want[k]['hidden'] = True
        first = next(i for i, ln in enumerate(block) if ln.startswith(' '*dent + '- '))
        block[first + 1:first + 1] = ['%shidden: true' % (' '*(dent + 2))]
    done = _put(path, text, lines, chunks, list(range(len(ids))), raw, want, given, ws, swap={k: block})
    return dict(_answer(path, text, 'hidden' if hidden else 'shown again', done), sheet=str(sheet), hidden=bool(hidden))


def bin_sheet(path, sheet, given=None, ws=None):
    """Take a sheet out of the house file for good. Only one that is
    hidden, and that no other sheet needs: the owner's to do, on the page,
    where it is asked twice."""
    path, text = _read(path)
    lines, chunks, listed, raw, _ = _sheets(text)
    ids = [str(f['id']) for f in listed]
    if str(sheet) not in ids:
        raise Refused('not changed — no sheet called %r (have %s)' % (sheet, ', '.join(ids)))
    k = ids.index(str(sheet))
    if not listed[k].get('hidden'):
        raise Refused('not changed — %s is not hidden: hide a sheet before binning it' % sheet)
    try:
        s = solve(path)
        need = depends(s)
        outlined = [str(i) for i in (s.house['outline'].get('sheets') or [])]
    except (model.ConfigError, ValueError):
        need, outlined = {}, []
    held = ['%s (%s)' % (sid, why if why.startswith('a ') else '`%s:`' % why)
            for sid in ids for other, why in need.get(sid, []) if other == str(sheet)]
    held += ['the outline sheet (`outline.sheets`)'] if str(sheet) in outlined else []
    if held:
        raise Refused('not changed — %s cannot be binned while %s depend%s on it'
                      % (sheet, ', '.join(held), 's' if len(held) == 1 else ''))
    keep = [i for i in range(len(ids)) if i != k]
    done = _put(path, text, lines, chunks, keep, raw, [listed[i] for i in keep], given, ws)
    return dict(_answer(path, text, 'binned', done), sheet=str(sheet), sheets=[ids[i] for i in keep])
