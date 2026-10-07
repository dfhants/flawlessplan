# -*- coding: utf-8 -*-
"""The engine on small made-up plans: rooms as measured, walls, openings,
stairs, labels, the outline sheet and the drawing itself."""
import math
import os
import re
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from flawlessplan import model, geom, stairs, solve
from flawlessplan.expr import Scope, ExprError

from shapely.geometry import Polygon
from conftest import BOX, ROOM, plan, said
from flawlessplan import labels, query, render, report

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


def test_expressions():
    s = Scope({'a': 2.0, 'b': 0.5})
    assert s.ev('a*3 - b') == 5.5
    assert s.ev('centred(0, 4, 1)') == 1.5
    assert s.text('{a:.2f} by {a+b}') == '2.00 by 2.5'
    for bad in ('__import__("os")', 'a.real', 'c + 1', '[1, 2]'):
        with pytest.raises(ExprError):
            s.ev(bad)


def test_rooms_are_measured_clear():
    p, _ = plan(BOX)
    rooms = {r['name']: r for r in p.rooms}
    # 8.0 wide: 0.30 external each side, a 0.10 partition in the middle
    assert rooms['LEFT']['w'] == pytest.approx(3.65, abs=1e-3)
    assert rooms['LEFT']['h'] == pytest.approx(5.40, abs=1e-3)
    assert rooms['RIGHT']['area'] == pytest.approx(3.65*5.40, abs=1e-2)
    assert p.gross == pytest.approx(48.0)
    assert not [i for i in p.issues if i[0] != 'info']


def test_opening_finds_its_wall_and_cuts_only_it():
    p, _ = plan(BOX)
    door, win = p.openings
    assert door['host'].id == 'split' and win['host'].id == 'env.0'
    assert door['width'] == pytest.approx(0.842)
    solid = geom.strip((4, 0), (4, 6), 0.1).area + p.ext.area - 0.1*0.3*2   # partition overlaps both walls
    assert p.walls.area == pytest.approx(solid - 0.842*0.1 - 1.2*0.3, abs=0.01)


def test_missing_wall_is_reported():
    p, _ = plan(BOX.replace("to: [MID, D]", "to: [MID, D/2]"))
    assert any('same space' in m for lv, m in p.issues if lv == 'error')


def test_two_rooms_of_one_name_are_reported():
    p, _ = plan(BOX.replace('name: RIGHT', 'name: LEFT'))
    assert any('two rooms are called LEFT' in m for lv, m in p.issues if lv == 'warn')
    p, _ = plan(BOX.replace('name: RIGHT', 'name: LEFT, id: east'))
    assert not [i for i in p.issues if i[0] != 'info']


def test_overlapping_openings_are_reported():
    p, _ = plan(BOX.replace("- {window: 1.2, at: [2.0, 0]}",
                            "- {window: 1.2, at: [2.0, 0]}\n      - {window: 1.2, at: [2.5, 0]}"))
    assert any('shares a stretch' in m for lv, m in p.issues)


def test_opening_off_the_end_is_reported():
    p, _ = plan(BOX.replace("at: [2.0, 0]", "at: [0.2, 0]"))
    assert any('runs off the end' in m for lv, m in p.issues)


def test_per_edge_thickness_and_any_angle():
    text = """
sheets:
  - id: g
    envelope:
      - [0, 0]
      - {at: [6, 0], t: 0.5}
      - [6, 4]
      - [2, 6]
      - [0, 4]
    rooms: [{name: ROOM, at: [3, 2]}]
    openings: [{door: 0.9, at: [4, 5], swing: in}]
"""
    p, house = plan(text)
    assert p.rooms[0]['shape'] == 'irregular' or p.rooms[0]['shape'] == 'near'
    x0, _, x1, _ = p.I.bounds
    assert (x0, x1) == (pytest.approx(0.3), pytest.approx(5.5))
    assert p.openings[0]['host'].id == 'env.2'
    assert '<svg' in solve.solved(house).plans()[0].svg()


def test_corner_fills_square():
    text = """
sheets:
  - id: g
    envelope: [[0, 0], [8, 0], [8, 8], [0, 8]]
    walls:
      - {from: [0, 4], to: [4, 4], t: 0.3}
      - {from: [4, 4], to: [4, 8]}
    rooms: [{name: A, at: [2, 6]}, {name: B, at: [6, 2]}]
"""
    p, _ = plan(text)
    # the thick wall runs on half the thin one, the thin wall half the thick
    assert p.walls.contains(geom.Point(4.04, 3.86).buffer(0.005))
    assert {r['name'] for r in p.rooms} == {'A', 'B'}
    assert not [i for i in p.issues if i[0] == 'error']


def test_stair_counts_and_cuts():
    st = {'id': 's', 'path': [(1, 5), (1, 1), (3, 1), (3, 4)], 'width': [0.9]*3,
          'treads': [5, 0, 6], 'going': 0.25, 'turns': [0, 3], 'cut': 5.0,
          'show': 'below', 'label': 'UP', 'where': 't'}
    below = stairs.build(st)
    above = stairs.build(dict(st, show='above'))
    assert below['risers'] == 5 + 1 + 3 + 6 + 1
    whole = stairs.build(dict(st, cut=None, show='all'))['block'].area
    assert below['block'].area + above['block'].area == pytest.approx(whole, rel=0.02)


def test_winders_reach_back_over_a_level_run():
    """The gap a banister leaves between two flights is part of the lowest
    winder when asked, not a strip of landing with an edge of its own."""
    st = {'id': 's', 'path': [(1, 1), (1, 3), (2.2, 3), (2.2, 0)], 'width': [0.9, 0.9, 0.8],
          'treads': [1, 0, 6], 'going': 0.25, 'turns': [0, 3], 'cut': None,
          'show': 'all', 'label': 'UP', 'where': 't'}
    plain = stairs.build(st)
    joined = stairs.build(dict(st, reach=[False, True]))
    assert len(joined['polys']) == len(plain['polys']) - 1
    assert joined['block'].area == pytest.approx(plain['block'].area)
    assert joined['risers'] == plain['risers']


# the two strokes the owner drew at the porch: a shaft, then its head
SHAFT = [[2.14, 6.81], [2.14, 6.88], [2.14, 6.96], [2.14, 7.06], [2.13, 7.17], [2.12, 7.26], [2.11, 7.36],
         [2.1, 7.44], [2.1, 7.53], [2.09, 7.62], [2.08, 7.7], [2.07, 7.77], [2.06, 7.83], [2.05, 7.87],
         [2.05, 7.93], [2.04, 7.99], [2.04, 8.03]]
HEAD = [[1.77, 7.63], [1.77, 7.67], [1.77, 7.71], [1.78, 7.75], [1.79, 7.8], [1.82, 7.86], [1.83, 7.91],
        [1.86, 7.95], [1.9, 8], [1.93, 8.04], [1.95, 8.09], [1.97, 8.14], [2.03, 8.15], [2.1, 8.11],
        [2.18, 8.07], [2.23, 8.04], [2.27, 8.02], [2.32, 8], [2.36, 7.99], [2.43, 7.95], [2.48, 7.93]]


def test_marks_are_laid_out_not_interpreted():
    """Strokes come back in the order drawn and numbered; ones that lie
    together share a picture. What they mean is left to the reader."""
    from flawlessplan import marks
    drawn = [{'type': 'pen', 'sheet': 'g', 'ts': 3000, 'pts': HEAD},
             {'type': 'pen', 'sheet': 'g', 'ts': 1000, 'pts': SHAFT},
             {'type': 'note', 'sheet': 'g', 'ts': 9000, 'x': 8.0, 'y': 14.0, 'text': 'here'}]
    S = marks.strokes(drawn, 'g')
    assert [(s['n'], s['text']) for s in S] == [(1, None), (2, None), (3, 'here')]
    assert S[0]['pts'][0] == tuple(SHAFT[0])
    assert sorted(len(f) for f in marks.frames(S)) == [1, 2]
    assert not hasattr(marks, 'read')


def test_the_plan_can_be_asked_what_is_at_a_point():
    from flawlessplan import query
    p = solve.solves(BOX).sheet('ground')
    found = [t for _, t in query.at(p, (4.0, 3.0))]
    assert any(t.startswith('door') and 'wall split' in t for t in found)
    assert any(t.startswith('partition split') for t in found)
    assert [t for _, t in query.at(p, (0.5, 0.5, 1.5, 1.5))][0].startswith('room LEFT')


def test_the_page_has_each_control_once_and_a_pane_per_sheet():
    from flawlessplan import page
    info = {'title': 'T', 'summary': '', 'figures': [], 'rooms': [], 'groups': []}
    class Blank(object):
        vb, lines = (0, 0, 100, 100), []

        def __init__(self, key):
            self.id, self.tab, self.info = key, key.upper(), info
    html = page.markup('A house', [Blank('a'), Blank('b')])
    for key in 'ab':
        for part in ('tab-', 'cv-', 'sv-', 'mk-', 'gh-', 'in-'):
            assert html.count('id="%s%s"' % (part, key)) == 1
    for control in ('undo', 'redo', 'clear', 'clear-sheet', 'clear-all', 'zin', 'zout', 'zfit', 'notes', 'sheets', 'sheetmenu', 'sheetwrap'):
        assert html.count('id="%s"' % control) == 1
    assert [html.count('data-tool="%s"' % t) for t in ('pen', 'note', 'pan')] == [1, 1, 1]
    assert 'window.confirm' not in html and 'notetext' not in html      # text is typed on the plan; clearing is undone, not confirmed
    assert 'var HIDDEN=[], MOVABLE=["a", "b"], VERSION=null;' in html and 'id="sheetwrap" hidden' in html   # offered only once it is known to be served
    hid = page.markup('A house', [Blank('a')], hidden=[Blank('b</script>')], version='abc123')
    assert 'HIDDEN=[{"id": "b\\u003c/script\\u003e", "label": "B\\u003c/SCRIPT\\u003e"}], MOVABLE=["a"], VERSION="abc123";' in hid
    for must in ('Bin for good?', '{hide:k}', '{show:h.id}', '{bin:h.id}', '{order:order}', 'what.version=VERSION', 'if(busy||!local) return;'):
        assert must in html, must
    assert '__' not in html.replace('__proto__', '')
    assert html.startswith('<!doctype html>') and 'class="home"' not in html and 'id="send"' not in html
    assert page.markup('A house', [Blank('a')], send='a b-plans.html').count('id="send" class="toggle" href="a%20b-plans.html" download') == 1
    assert 'fonts.googleapis' not in html and '@font-face' not in html         # on its own: the system's faces, nobody asked
    beside = page.markup('A house', [Blank('a')], root='../')        # built beside an index: a way back, fonts, installable
    assert beside.count('class="home" href="../index.html"') == 1 and 'href="../manifest.webmanifest"' in beside
    assert 'url(../fonts/archivo.woff2)' in beside
    assert html.count('<h1') == 1 and '<h1 class="vh">A house floor plans</h1>' in html     # one heading, said and not shown


def test_the_page_that_is_sent_stands_alone_and_draws_each_sheet_once():
    from flawlessplan import page
    s = solve.solves(CHANGED)
    html = page.share('A "house"', s.sheets)
    assert '__' not in html and '<title>A &quot;house&quot;</title>' in html
    about = re.findall(r'<meta name="description" content="([^"]*)">', html)       # what a search shows: the house and its sheets
    assert len(about) == 1 and about[0].startswith('A &quot;house&quot; floor plans drawn to scale: ' + ', '.join(p.tab for p in s.sheets))
    assert len(page.about('A house', s.sheets*40)) <= 160 and html.count('<h1') == 1
    assert 'src=' not in html and '<link rel="manifest"' not in html and 'fetch(' not in html     # nothing asked of anywhere
    assert html.count('url(data:font/woff2;base64,') == 3 and not re.search(r'url\((?!data:|#)', html)
    assert 'data-tool' not in html and 'marks.json' not in html                # read, not drawn on
    for key in ('outline', 'ground', 'proposed'):
        for part in ('tab-', 'cv-', 'sv-'):
            assert html.count('id="%s%s"' % (part, key)) == 1
    # a sheet that changes another is its own drawing and nothing more: that already shows what goes and what is gained
    assert html.count('<svg id="sv-') == 3 and html.count('class="new"') == html.count('class="gone"') == 1


CHANGED = BOX + """
  - id: proposed
    level: ground
    changes: ground
    envelope: [[0, 0], [W + 2, 0], [W + 2, D], [0, D]]
    rooms:
      - {name: OPEN, at: [1, 1], zone: true}
    notes: ["{gained:.1f} m² on {base_gross:.1f}"]
"""


def test_a_change_derives_what_goes_and_what_is_gained():
    s = solve.solves(CHANGED).sheet('proposed')
    assert s.base.id == 'ground' and s.level == 'ground'
    assert abs(s.gained.area - 2*6.0) < 0.01                  # the envelope grew 2 m east
    # the partition goes, and the old east wall where the new one is not
    assert abs(s.demolition.area - (0.1*5.4 + 0.3*5.4)) < 0.05
    assert s.info['groups'][0][2] == ['12.0 m² on 48.0']
    assert 'class="zone"' in s.svg() and 'class="gone"' in s.svg() and 'class="new"' in s.svg()
    quiet = solve.solves(CHANGED.replace('changes: ground', 'changes: ground\n    demolition: false')).sheet('proposed')
    assert quiet.demolition is None and quiet.gained is not None


def test_a_sheet_says_which_level_it_draws():
    with pytest.raises(model.ConfigError, match='is now `sheets:`'):
        model.loads(BOX.replace('sheets:', 'floors:'))
    with pytest.raises(model.ConfigError, match='no level called'):
        model.loads(CHANGED.replace('level: ground', 'level: attic'))
    with pytest.raises(model.ConfigError, match='this sheet the proposed'):      # a level of its own cannot change another
        model.loads(CHANGED.replace('    level: ground\n', ''))
    with pytest.raises(model.ConfigError, match='no earlier sheet'):
        model.loads(CHANGED.replace('changes: ground', 'changes: attic'))


def test_check_reports_a_label_with_nowhere_to_go():
    tight = BOX.replace('{name: LEFT, at: [1, 1]}', '{name: LEFT, at: [1, 1]}').replace('W: 8.0, D: 6.0', 'W: 1.0, D: 0.9')
    tight = tight.replace('- {window: 1.2, at: [2.0, 0]}', '').replace("- {door: std, wall: split, at: centre, swing: e}", '')
    issues = solve.solves(tight.replace('at: [7, 1]', 'at: [0.9, 0.5]').replace('at: [1, 1]', 'at: [0.4, 0.5]')).issues()
    assert any('no clear place for the label' in m for _, _, m in issues)


def test_a_label_can_stand_in_the_margin():
    s = solve.solves(BOX.replace('{name: LEFT, at: [1, 1]}', '{name: LEFT, at: [1, 1], label: west}')).sheet('ground')
    items, x, y = s.labels[0]
    assert x == 0.0 and abs(y - 3.0) < 0.01 and items[0][0] < 0          # off the west face, level with the room
    (a, b), = s.leaders
    assert a[0] < 0 < b[0] and 'class="leader"' in s.svg()
    with pytest.raises(model.ConfigError, match='label'):
        model.loads(BOX.replace('{name: LEFT, at: [1, 1]}', '{name: LEFT, at: [1, 1], label: up}'))


def test_a_zone_takes_in_rooms_and_the_walls_between():
    text = BOX + """    zones:
      - {name: LATER, rooms: [LEFT, RIGHT], sub: "{area:.1f} m² to do", label: north}
    notes: ["{LATER_area:.1f} m² is for later"]
"""
    s = solve.solves(text).sheet('ground')
    z, = s.plan.zones
    assert [r['name'] for r in z['rooms']] == ['LEFT', 'RIGHT']
    assert abs(z['face'].area - 7.4*5.4) < 0.01                  # one outline, across the partition
    assert abs(z['area'] - (7.4*5.4 - 0.1*5.4)) < 0.01           # but its area is floor
    assert s.info['groups'][0][2] == ['39.4 m² is for later']
    assert len(s.labels) == 3 and s.svg().count('class="zone"') == 1
    from flawlessplan import query
    assert any(t.startswith('zone LATER (LEFT, RIGHT') for _, t in query.at(s, (2.0, 3.0)))
    with pytest.raises(ValueError, match='no room is called'):
        solve.solves(text.replace('[LEFT, RIGHT]', '[LEFT, ATTIC]'))


def test_what_a_house_file_writes_cannot_break_out_of_the_page():
    from flawlessplan import page, render
    assert render.esc('a"b\'c<d') == 'a&quot;b&#39;c&lt;d'
    with pytest.raises(model.ConfigError, match='letters, digits'):
        model.loads(BOX.replace('id: ground', 'id: "../x"'))
    nasty = solve.solves(BOX.replace('id: ground', 'id: ground\n    tab: "</script><script>alert(1)</script>"'))
    local = page.markup('A "house"', nasty.sheets)
    assert '<script>alert(1)' not in local and '<title>A &quot;house&quot;</title>' in local
    s = Scope({'a': 2.0})
    with pytest.raises(ExprError):
        s.ev('9**9**9')
    with pytest.raises(ExprError):
        s.text('{a:>999999}')
    assert s.text('{a:.2f} {a*2:.0f}') == '2.00 4'


def test_a_private_house_is_marked():
    assert model.loads(BOX)['private'] is False
    assert model.loads('house: {private: true}\n' + BOX)['private'] is True


SPLAY = """
lines: {YM: 4.5, HALF: 0.45}
sheets:
  - id: ground
    envelope: [[0, 0], {at: [10, 0], id: east}, [8.7, 9], [0, 9]]
    walls:
      - {id: mid, from: [0, YM], to: {y: YM, wall: east}}
      - {id: slant, from: [4, 0], to: [5, YM]}
      - {id: stub, from: [0, 2], to: {y: 2, wall: slant}}
    openings:
      - {window: 1.2, at: {y: 2, wall: east}}
    stairs:
      - {id: main, path: [{y: 0.5, wall: east, clear: HALF}, {y: 3.5, wall: east, clear: HALF}]}
    rooms:
      - {name: NW, at: [1, 1]}
      - {name: W, at: [1, 3]}
      - {name: NE, at: [7, 2]}
      - {name: S, at: [3, 7]}
"""


def test_a_point_is_given_by_the_wall_it_is_on():
    """Against a wall that is not square to the page, nothing is worked
    out by hand: a partition runs to it and closes, an opening sits in it,
    a stair runs along it."""
    from flawlessplan import solve, model
    s = solve.solves(SPLAY)
    assert not [i for i in s.issues() if i[1] != 'info']        # four rooms, four spaces: no gap at the splay
    sh = s.sheet('ground')
    walls = dict((w['id'], w) for w in sh.plan.spec['walls'])
    x, y = walls['mid']['b']
    assert y == 4.5 and abs(x - (10 - 1.3*4.5/9 - 0.3*math.hypot(9, 1.3)/9)) < 1e-9      # the inside face at YM
    assert abs(walls['stub']['b'][0] - 4.5) < 0.1 and sh.plan.openings[0]['host'].name == 'east'
    (x0, y0), (x1, y1) = sh.plan.spec['stairs'][0]['path']
    assert abs((x1 - x0)/(y1 - y0) - -1.3/9) < 1e-9             # parallel to the wall
    for bad, why in (("{y: YM, wall: west}", 'no wall called'), ("{y: 0, wall: mid}", 'runs along y'),
                     ("{y: 20, wall: east}", 'does not reach'), ("{y: 2, wall: slant, clear: 1}", 'which `side:`')):
        with pytest.raises(model.ConfigError, match=why):
            solve.solves(SPLAY.replace("{y: 2, wall: slant}", bad))


def test_a_wall_written_as_a_path_answers_to_its_name():
    from flawlessplan import solve
    text = """
sheets:
  - id: ground
    envelope: [[0, 0], [8, 0], [8, 6], [0, 6]]
    walls: [{id: core, path: [[0, 3], [4, 3], [4, 6]]}, {id: tie, from: {x: 2, wall: core}, to: [2, 0]}]
    openings:
      - {door: std, wall: core.1, at: centre}
      - {door: std, wall: core, at: [1, 3]}
      - {door: std, wall: core, at: {y: 5.5, wall: core}}
    unlabelled: ok
"""
    plan = solve.solves(text).sheet('ground').plan
    assert [o['host'].name for o in plan.openings] == ['core.1', 'core.0', 'core.1']
    assert plan.spec['walls'][2]['a'] == (2.0, 3.0) and plan.openings[2]['centre'] == (4.0, 5.5)
    with pytest.raises(ValueError, match=r'path of 2 legs — name one \(core.0 to core.1\)'):
        solve.solves(text.replace('wall: core.1, at: centre', 'wall: core, at: centre'))


CURVES = """
survey: {W: 10.0, D: 8.0, R: 3.0}
levels: [ground, tower]
sheets:
  - id: ground
    envelope:
      - [0, 0]
      - [W, 0]
      - [W, D]
      - {at: [4.5, D], id: bow, rise: 0.7}
      - [1.5, D]
      - [0, D]
    walls:
      - {id: mid, from: [0, 4], to: [W, 4]}
      - {id: sweep, from: [6, 4], to: [6, D], rise: 0.8, toward: e}
      - {id: tie, from: {y: 6, wall: sweep}, to: [W, 6]}
    openings:
      - {window: 2.0, wall: bow, at: centre}
      - {door: std, wall: sweep, at: {from_start: 0.4}, hinge: n, swing: e}
    rooms:
      - {name: NORTH, at: [3, 2]}
      - {name: SITTING, at: [3, 6]}
      - {name: NOOK, at: [8.5, 5]}
      - {name: STORE, at: [8.5, 7]}
  - id: tower
    envelope: [{at: [0, R], id: north, rise: R}, {at: [2*R, R], id: south, rise: R}]
    rooms:
      - {name: ROUND, at: [R, R], expect: {w: 2*R - 2*EW}}
"""


def test_a_wall_may_curve_and_is_still_one_wall():
    """A bow, a curved partition and a round building: each curve is one
    wall with one name, openings follow it, walls meet it and close."""
    from flawlessplan import solve, query
    s = solve.solves(CURVES)
    assert not [i for i in s.issues() if i[1] != 'info']
    plan = s.sheet('ground').plan
    assert len(plan.env_hosts) == 6 and len(plan.spec['envelope']['pts']) > 12      # six walls, however many pieces
    bow = plan.hosts['bow']
    assert abs(bow.arc['r'] - (1.5**2 + 0.7**2)/(2*0.7)) < 1e-9 and bow.L > 3.0
    win, door = plan.openings
    assert win['host'] is bow and abs(win['centre'][0] - 3.0) < 1e-6
    assert abs(win['centre'][1] - (8.0 + 0.7 - 0.15)) < 0.005                       # mid-wall, at the bow's furthest
    assert abs(plan.gross - (80.0 + bow.arc['r']**2*math.asin(1.5/bow.arc['r']) - 1.5*(bow.arc['r'] - 0.7))) < 0.02
    assert door['host'].name == 'sweep' and abs(door['leaves'][0][3] - door['width']) < 0.01   # a straight leaf across it
    x, y = [w for w in plan.spec['walls'] if w['id'] == 'tie'][0]['a']
    assert y == 6.0 and abs(x - 6.8) < 0.005                                        # on the curve where it stands furthest east
    assert 'curved to a radius' in '\n'.join(query.lines(query.at(s.sheet('ground'), (3, 8.6))))
    round_ = s.sheet('tower').plan.rooms[0]
    assert round_['shape'] == 'round' and abs(round_['w'] - 5.4) < 0.01 and abs(round_['area'] - math.pi*2.7**2) < 0.1
    assert '6.00 · r 3.00' in '\n'.join(s.sheets[0].lines)                           # the outline: across it, and its radius
    for bad, why in (('rise: 0.8, toward: e', 'rise: 0.8'), 'which way it curves'), \
                    (('rise: 0.7}', 'radius: 1.0}'), 'too tight'), (('rise: 0.7}', 'rise: 0.7, via: [3, 9]}'), 'one of rise'):
        with pytest.raises(ValueError, match=why):
            solve.solves(CURVES.replace(*bad))


FITTED = """
survey: {W: 7.0, D: 5.0}
lines: {BX: 4.5}
sheets:
  - id: ground
    envelope: [{at: [0, 0], id: north}, {at: [W, 0], id: east}, {at: [W - 0.6, D], id: south}, {at: [0, D], id: west}]
    walls: [{id: split, from: [BX, 0], to: [BX, D]}]
    fittings:
      - {worktop: 3.6, wall: north, at: {from_start: 0}}
      - {sink: true, wall: north, at: [1.6, 0]}
      - {bath: 1.7, wall: north, at: [BX + 0.05, 0], corner: w}
      - {wc: true, wall: east, at: {y: 2.0, wall: east}}
      - {basin: true, wall: split, side: e, at: [BX, 2.6]}
      - {cylinder: true, at: [5.2, 4.0], facing: s}
    rooms:
      - {name: KITCHEN, at: [2, 3]}
      - {name: BATHROOM, at: [5.5, 3]}
"""


def test_what_is_built_in_stands_against_its_wall():
    from flawlessplan import solve, report, query
    s = solve.solves(FITTED)
    assert not [i for i in s.issues() if i[1] != 'info']
    sh = s.sheet('ground')
    top, sink, bath, wc, basin, cyl = sh.plan.fittings
    assert top['floor'].bounds == pytest.approx((0.3, 0.3, 3.9, 0.9))           # from the room's corner, not the wall's
    assert (sink['w'], sink['d']) == (1.0, 0.5) and sink['o'] == pytest.approx((1.6, 0.3))
    assert bath['floor'].bounds == pytest.approx((4.55, 0.3, 6.25, 1.0))        # its west end where it was put
    assert wc['n'][0] < -0.98 and abs(wc['n'][1]) > 0.1                         # square to a wall that is not
    assert basin['n'] == pytest.approx((1.0, 0.0)) and basin['o'][0] == pytest.approx(4.55)
    assert cyl['host'] is None and cyl['floor'].bounds[1] == pytest.approx(4.0)
    assert [f['kind'] for f in report.report(s)['sheets'][0]['fittings']][:2] == ['worktop', 'sink']
    assert 'fittings' not in report.snapshot(s)['sheets']['ground']
    assert query.lines(query.at(sh, (5.5, 0.6)))[1].startswith('bath, 1.70 × 0.70 m against wall north')
    assert sh.svg().count('class="fitting"') == 7 and 'class="fitline"' in sh.svg()   # a WC is two shapes
    for bad, why in (('{sink: true, wall: north, at: [1.6, 0]}', '{sink: 3.0, wall: north, at: [3.2, 0]}'), 'runs into a wall'), \
                    (('side: e, ', ''), 'which `side:`'), ((', facing: s', ''), 'which way it is `facing:`'), \
                    (('{cylinder: true', '{sofa: true'), 'exactly one of'):
        try:
            said = ' '.join(i[2] for i in solve.solves(FITTED.replace(*bad)).issues())
        except ValueError as e:
            said = str(e)
        assert why in said


SPLIT = """
levels: [lower, upper]
sheets:
  - id: lower
    envelope: [{at: [0, 5], open: true, id: step}, [8, 5], [8, 10], [0, 10]]
    stairs: [{id: half, path: [[6.5, 6.6], [6.5, 5]], treads: [6], cut_risers: 3}]
    areas: [{rect: [[0, 0], [8, 5]], style: below, label: UPPER}]
    rooms: [{name: LIVING, at: [3, 7.5]}]
  - id: upper
    envelope: [[0, 0], [8, 0], {at: [8, 5], open: true}, [0, 5]]
    stairs: [{ref: lower.half, show: above}]
    rooms: [{name: KITCHEN, at: [4, 2]}]
"""


def test_a_half_level_ends_at_an_open_edge():
    """Split levels are levels: each half its own sheet, the edge between
    them the floor's and not a wall, the flight between drawn once."""
    from flawlessplan import solve, report
    s = solve.solves(SPLIT)
    assert not [i for i in s.issues() if i[1] != 'info']
    lower = s.sheet('lower')
    assert lower.plan.hosts['step'].open and lower.plan.hosts['step'].t == 0
    assert lower.plan.rooms[0]['h'] == pytest.approx(4.7)                       # floor right up to the edge: no wall there
    assert lower.plan.gross == 40.0 and report.totals(s)['gross'] == 80.0
    assert lower.svg().count('class="edge"') == 1 and s.sheet('upper').svg().count('class="edge"') == 1


# ---- measuring a room


def shaped(env, at='[2, 2]'):
    p, _ = plan("sheets:\n  - id: g\n    envelope: %s\n    rooms: [{name: R, at: %s}]\n" % (env, at))
    return p.rooms[0]


def test_a_rectangle_reads_its_two_sides():
    r = shaped('[[0, 0], [5, 0], [5, 4], [0, 4]]')
    assert (r['shape'], r['w'], r['h'], r['area']) == ('rect', pytest.approx(4.4), pytest.approx(3.4), pytest.approx(14.96))
    assert r['rect'] == pytest.approx((0.3, 0.3, 4.7, 3.7))
    assert geom.measure(Polygon([(0, 0), (3, 0), (3, 2), (0, 2)])) == {'w': 3.0, 'h': 2.0, 'area': 6.0, 'shape': 'rect', 'rect': (0.0, 0.0, 3.0, 2.0)}


def test_a_nib_too_small_to_matter_leaves_a_rectangle_a_rectangle():
    nib = geom.measure(Polygon([(0, 0), (3, 0), (3, 2), (1.6, 2), (1.6, 1.9), (1.4, 1.9), (1.4, 2), (0, 2)]))
    assert (nib['shape'], nib['w'], nib['h']) == ('rect', 3.0, 2.0) and nib['area'] == pytest.approx(5.98)   # the area is still the true one


def test_a_chamfered_room_reads_its_overall_size():
    r = shaped('[[0, 0], [5, 0], [5, 3.4], [4.4, 4], [0, 4]]')
    assert (r['shape'], r['w'], r['h']) == ('near', pytest.approx(4.4), pytest.approx(3.4))
    assert 14.7 < r['area'] < 14.96                                 # less the corner


def test_an_l_shaped_room_reads_its_overall_size_and_its_true_area():
    """The longest a tape reads each way, down each leg: the figure a
    survey gives. It once read the largest rectangle inside, 3.40 × 6.40."""
    r = shaped('[[0, 0], [8, 0], [8, 3], [4, 3], [4, 7], [0, 7]]')
    assert (r['shape'], r['w'], r['h']) == ('irregular', pytest.approx(7.4), pytest.approx(6.4))
    assert r['rect'] == pytest.approx((0.3, 0.3, 3.7, 6.7))          # where its label goes is still inside it
    assert r['area'] == pytest.approx(7.4*2.4 + 3.4*4.0)             # what to trust: the two legs of it
    assert geom.inscribed(Polygon([(0, 0), (4, 0), (4, 2), (2, 2), (2, 4), (0, 4)])) == (0.0, 0.0, 4.0, 2.0)


def test_a_room_turned_on_the_page_reads_its_own_sides():
    r = shaped('[[0, 0], [5, 1], [4.2, 5], [-0.8, 4]]')
    side, end = math.hypot(5, 1), math.hypot(0.8, 4)
    assert r['shape'] == 'skew' and r['w'] == pytest.approx(side - 0.6, abs=0.01) and r['h'] == pytest.approx(end - 0.6, abs=0.01)
    assert r['area'] == pytest.approx(r['w']*r['h'], rel=0.005)


def test_a_room_between_slanted_walls_reads_its_clear_width():
    r = shaped('[[0, 0], [6, 0], [8, 4], [2, 4]]', '[4, 2]')
    # 6 wide along the page; square to its slanted walls it is 6·sin(63.4°) between them
    # 8 overall on the page, and nowhere is it more than 5.33 from wall to wall
    assert r['shape'] == 'irregular' and r['h'] == pytest.approx(3.4)
    assert r['w'] == pytest.approx(5.33, abs=0.01) and r['area'] == pytest.approx(r['w']*r['h'], abs=0.01)
    assert geom._slants(Polygon([(0, 0), (6, 0), (8, 4), (2, 4)])) == [-26.6]


def test_a_triangular_room_reads_its_two_legs_and_is_labelled_inside_it():
    """No rectangle in a triangle has a corner on one of the triangle's
    own; it once read the 0.20 × 0.20 that stands for nothing found."""
    r = shaped('[[0, 0], [8, 0], [0, 8]]')
    leg = 8 - 0.3 - 0.3*(1 + math.sqrt(2))                           # each clear leg, inside the three walls
    assert r['shape'] == 'irregular' and r['area'] == pytest.approx(leg*leg/2, abs=0.01)
    assert r['w'] == pytest.approx(leg, abs=0.01) and r['h'] == pytest.approx(leg, abs=0.01)
    x0, y0, x1, y1 = r['rect']
    assert (x1 - x0)*(y1 - y0) >= 0.95*(leg/2)**2                    # the largest inside is half of each leg: 3.49 × 3.49
    assert 2.6 < x1 - x0 < 4.4 and 2.6 < y1 - y0 < 4.4
    assert r['face'].buffer(0.002).contains(geom.box(x0, y0, x1, y1))    # and it does fit


@pytest.mark.parametrize('pts', [
    [(0, 0), (8, 0), (0, 8)], [(0, 0), (8, 0), (8, 8)], [(0, 0), (6, 0), (3, 5)], [(0, 3), (4, 0), (8, 3), (4, 6)],
    [(0, 0), (9, 1), (2, 7)], [(0, 0), (10, 0), (5, 0.5)],
])
def test_a_shape_with_no_square_corner_still_reads_a_rectangle_inside_it(pts):
    face = Polygon(pts)
    x0, y0, x1, y1 = geom.inscribed(face)
    assert face.buffer(0.002).contains(geom.box(x0, y0, x1, y1))
    assert (x1 - x0)*(y1 - y0) >= 0.42*face.area                     # half the area is the most a triangle allows
    for k, far in enumerate(face.bounds):                            # and no side of it can be pushed further out
        grown = [x0, y0, x1, y1]
        grown[k] += 0.02 if k > 1 else -0.02
        assert not face.contains(geom.box(*grown)) or abs(grown[k] - far) < 0.03


def test_a_face_too_thin_for_any_rectangle_is_marked_where_it_is():
    x0, y0, x1, y1 = geom.inscribed(Polygon([(0, 0), (5, 0), (5, 0.0004)]))
    assert (x1 - x0, y1 - y0) == (pytest.approx(0.2), pytest.approx(0.2))


def test_what_a_room_is_called_in_a_note():
    assert geom.key({'id': None, 'name': 'BED 2 (en-suite)'}) == 'BED_2__en_suite'
    assert geom.key({'id': 'b2', 'name': 'BED 2'}) == 'b2' and geom.key({'id': None, 'name': '--'}) == ''
    s = solve.solves(ROOM.replace('name: ROOM', 'name: BED 2 (en-suite)') + "    notes: ['{BED_2__en_suite_w:.2f} by {BED_2__en_suite_h:.2f}, {BED_2__en_suite_area:.1f}']\n")
    assert s.sheet('ground').info['groups'][0][2] == ['7.40 by 5.40, 40.0']


def test_every_sheets_gross_area_is_a_name_any_note_may_use():
    text = BOX + "    notes: ['{gross:.0f} here, {gross_ground:.0f} and {gross_first_floor:.0f} in all {gross_ground + gross_first_floor:.0f}']\n" \
        "  - {id: first-floor, level: first-floor, envelope: [[0, 0], [W, 0], [W, 3], [0, 3]], unlabelled: ok}\n"
    assert solve.solves('levels: [ground, first-floor]\n' + text).sheet('ground').info['groups'][0][2] == ['48 here, 48 and 24 in all 72']


# ---- walls

def test_the_inside_face_is_each_wall_in_by_its_own_thickness():
    assert geom.inner_ring([(0, 0), (4, 0), (4, 4), (0, 4)], [0.3]*4)[0] == pytest.approx([(0.3, 0.3), (3.7, 0.3), (3.7, 3.7), (0.3, 3.7)])
    ring, norms = geom.inner_ring([(0, 0), (0, 4), (4, 4), (4, 0)], [0.3, 0.2, 0.3, 0.2])       # written the other way round
    assert ring == pytest.approx([(0.3, 0.2), (0.3, 3.8), (3.7, 3.8), (3.7, 0.2)]) and norms[0] == pytest.approx((1.0, 0.0))
    step, _ = geom.inner_ring([(0, 0), (4, 0), (8, 0), (8, 4), (0, 4)], [0.3, 0.5, 0.3, 0.3, 0.3])   # a wall that thickens along its run
    assert (4.0, 0.3) in [pytest.approx(p) for p in step] and (4.0, 0.5) in [pytest.approx(p) for p in step]


def test_a_wall_body_is_its_centreline_its_thickness_and_what_it_runs_on():
    assert geom.strip((0, 0), (4, 0), 0.1).bounds == pytest.approx((0.0, -0.05, 4.0, 0.05))
    assert geom.strip((0, 0), (4, 0), 0.1, 0.5, 0.25).bounds == pytest.approx((-0.5, -0.05, 4.25, 0.05))
    assert geom.strip((0, 0), (3, 4), 0.2).area == pytest.approx(1.0)
    with pytest.raises(ValueError, match='zero-length run'):
        geom.strip((1, 1), (1, 1), 0.1)


def bodies(walls):
    p, _ = plan(ROOM + "    unlabelled: ok\n    walls:\n" + walls)
    return [tuple(round(v, 3) for v in b.bounds) for b in p.bodies], p


def test_a_partition_runs_on_only_at_a_corner():
    corner, _ = bodies("      - {id: a, from: [0, 3], to: [4, 3], t: 0.3}\n      - {id: b, from: [4, 3], to: [4, 6]}\n")
    assert corner == [(0.0, 2.85, 4.05, 3.15), (3.95, 2.85, 4.05, 6.0)]         # each by half the other's thickness
    tee, _ = bodies("      - {id: a, from: [0, 3], to: [8, 3]}\n      - {id: b, from: [4, 3], to: [4, 6]}\n")
    assert tee == [(0.0, 2.95, 8.0, 3.05), (3.95, 3.0, 4.05, 6.0)]              # dying into a wall passing through: not at all
    on, _ = bodies("      - {id: a, from: [0, 3], to: [4, 3]}\n      - {id: b, from: [4, 3], to: [8, 3]}\n")
    assert on == [(0.0, 2.95, 4.0, 3.05), (4.0, 2.95, 8.0, 3.05)]               # nor where it carries straight on


def test_butt_stops_a_wall_running_on_at_all():
    butt, p = bodies("      - {id: a, from: [0, 3], to: [4, 3], t: 0.3, butt: true}\n      - {id: b, from: [4, 3], to: [4, 6], butt: true}\n")
    assert butt == [(0.0, 2.85, 4.0, 3.15), (3.95, 3.0, 4.05, 6.0)] and p.spec['walls'][0]['butt'] is True


def test_a_wall_that_ends_in_the_open_is_information_and_not_a_fault():
    p, _ = plan(ROOM + "    walls: [{id: nib, from: [4, 0], to: [4, 2]}]\n")
    assert p.issues == [('info', 'wall nib ends in the open at (4.00, 2.00)')]
    assert p.rooms[0]['shape'] == 'rect' and p.rooms[0]['area'] == pytest.approx(39.96 - 1.7*0.1)


def test_a_wall_that_leaves_the_building_is_warned_of():
    p, _ = plan(ROOM + "    walls: [{id: out, from: [4, 3], to: [12, 3]}]\n")
    assert 'wall out runs outside the envelope' in said(p, 'warn')
    assert p.walls.bounds == pytest.approx((0, 0, 8, 6))                        # and what is outside is cut off


def test_a_partition_meets_a_slanted_outside_wall_with_no_gap():
    text = ("sheets:\n  - id: g\n    envelope: [[0, 0], {at: [10, 0], id: east}, [8, 8], [0, 8]]\n"
            "    walls: [{id: mid, from: [0, 4], to: {y: 4, wall: east}}]\n    rooms: [{name: N, at: [2, 2]}, {name: S, at: [2, 6]}]\n")
    p, _ = plan(text)
    assert not said(p, 'error') and len(p.rooms) == 2
    assert p.rooms[0]['area'] + p.rooms[1]['area'] == pytest.approx(p.internal - 0.1*(p.spec['walls'][0]['b'][0] - 0.3), abs=0.02)


def test_two_walls_of_one_name_are_refused():
    for other in ('split', 'env.0'):
        with pytest.raises(ValueError, match="sheet ground: two walls called '%s'" % other.replace('.', r'\.')):
            solve.solves(BOX.replace("- {id: split, from: [MID, 0], to: [MID, D]}",
                                     "- {id: split, from: [MID, 0], to: [MID, D]}\n      - {id: %s, from: [2, 0], to: [2, D]}" % other))


def test_solid_masonry_is_wall_and_takes_floor_from_its_room():
    p, _ = plan(ROOM + "    solids: [{rect: [[3, 2], [4, 3]]}]\n")
    assert p.walls.area - p.ext.area == pytest.approx(1.0) and p.rooms[0]['area'] == pytest.approx(38.96)
    with pytest.raises(ValueError, match=r'sheet ground: solids\[0\]: its outline crosses itself'):
        solve.solves(ROOM + "    solids: [{points: [[1, 1], [2, 2], [2, 1], [1, 2]]}]\n")


# ---- openings

def door(spec):
    p, _ = plan(BOX.replace("- {door: std, wall: split, at: centre, swing: e}", "- " + spec))
    return p.openings[0], p


@pytest.mark.parametrize('spec, hinge, shut, side', [
    ('{door: std, wall: split, swing: e}', (4.05, 2.579), (0, 1), (1, 0)),               # hung on the face it opens to
    ('{door: std, wall: split, swing: w}', (3.95, 2.579), (0, 1), (-1, 0)),
    ('{door: std, wall: split, swing: left}', (4.05, 2.579), (0, 1), (1, 0)),            # left of the wall's own direction
    ('{door: std, wall: split, swing: right}', (3.95, 2.579), (0, 1), (-1, 0)),
    ('{door: std, wall: split}', (4.05, 2.579), (0, 1), (1, 0)),                         # a partition, nothing said: left
    ('{door: std, wall: split, swing: e, hinge: s}', (4.05, 3.421), (0, -1), (1, 0)),
    ('{door: std, wall: split, swing: e, hinge: end}', (4.05, 3.421), (0, -1), (1, 0)),
    ('{door: std, wall: split, swing: e, hinge: n}', (4.05, 2.579), (0, 1), (1, 0)),
    ('{door: std, wall: split, swing: e, hinge: start}', (4.05, 2.579), (0, 1), (1, 0)),
    ('{door: std, wall: split, swing: e, face: w}', (3.95, 2.579), (0, 1), (1, 0)),      # opens east, sits flush with the west face
    ('{door: std, wall: env.0, swing: in}', (3.579, 0.3), (1, 0), (0, 1)),
    ('{door: std, wall: env.0}', (3.579, 0.3), (1, 0), (0, 1)),                          # an outside wall, nothing said: in
    ('{door: std, wall: env.0, swing: out}', (3.579, 0.0), (1, 0), (0, -1)),
    ('{door: std, wall: env.0, swing: out, face: in}', (3.579, 0.3), (1, 0), (0, -1)),
    ('{door: std, wall: env.0, swing: s}', (3.579, 0.3), (1, 0), (0, 1)),
])
def test_a_leaf_is_hung_where_it_is_told_and_swings_where_it_is_told(spec, hinge, shut, side):
    o, p = door(spec)
    (h, u, n, w), = o['leaves']
    assert h == pytest.approx(hinge) and u == pytest.approx(shut) and n == pytest.approx(side) and w == pytest.approx(0.842)
    tip, _, sector = geom.leaf_shape(h, u, n, w)
    assert math.hypot(tip[0] - h[0], tip[1] - h[1]) == pytest.approx(w) and not said(p)
    assert geom._dot(geom._sub(tip, h), u) == pytest.approx(w*math.cos(math.radians(60)))   # drawn 60° open


def test_a_pair_is_two_leaves_that_meet_in_the_middle():
    o, _ = door('{door: std, wall: split, pair: true}')
    (h0, u0, n0, w0), (h1, u1, n1, w1) = o['leaves']
    assert o['width'] == pytest.approx(1.614) and w0 == w1 == pytest.approx(0.807)
    assert h0 == pytest.approx((4.05, 3 - 0.807)) and h1 == pytest.approx((4.05, 3 + 0.807)) and u0 == pytest.approx((0, 1)) and u1 == pytest.approx((0, -1))


def test_a_leaf_sweeps_a_sixth_of_a_circle_one_way_or_the_other():
    tip, sweep, sector = geom.leaf_shape((0, 0), (1, 0), (0, 1), 1.0)
    assert tip == pytest.approx((0.5, math.sqrt(3)/2)) and sweep == 1 and sector.area == pytest.approx(math.pi/6, rel=0.01)
    assert geom.leaf_shape((0, 0), (1, 0), (0, -1), 1.0)[1] == 0


@pytest.mark.parametrize('spec, s0, s1', [
    ('{door: std, wall: split}', 3 - 0.421, 3 + 0.421),
    ('{door: std, wall: split, at: centre}', 3 - 0.421, 3 + 0.421),
    ('{door: std, wall: split, at: center}', 3 - 0.421, 3 + 0.421),
    ('{door: std, wall: split, at: {from_start: 0.5}}', 0.5, 1.342),
    ('{door: std, wall: split, at: {from_end: 0.5}}', 6 - 1.342, 5.5),
    ('{door: std, at: [4, 2]}', 2 - 0.421, 2 + 0.421),                       # no wall named: the one the point is in
    ('{door: std, wall: split, at: [9, 2]}', 2 - 0.421, 2 + 0.421),          # a wall named: where the point is along it
    ('{opening: 1.5, wall: split}', 2.25, 3.75),
    ('{window: 0.6, wall: split, at: {from_start: MID - 3.5}}', 0.5, 1.1),
])
def test_an_opening_sits_at_a_place_along_its_wall(spec, s0, s1):
    o, p = door(spec)
    assert o['host'].name == 'split' and (o['s0'], o['s1']) == (pytest.approx(s0), pytest.approx(s1))
    assert o['centre'] == pytest.approx((4.0, (s0 + s1)/2)) and o['hole'].area == pytest.approx((s1 - s0)*0.104)


@pytest.mark.parametrize('spec, kind, style, leaves', [
    ('{door: std, wall: split}', 'door', 'swing', 1), ('{door: std, wall: split, style: slide}', 'door', 'slide', 0),
    ('{door: std, wall: split, style: fold}', 'door', 'fold', 0), ('{door: std, wall: split, style: none}', 'door', 'none', 0),
    ('{window: 1.2, wall: split}', 'window', 'window', 0), ('{opening: 1.2, wall: split}', 'opening', 'none', 0),
    ('{window: 0.3, wall: split, style: frame}', 'window', 'frame', 0),
])
def test_each_kind_of_opening_is_drawn_its_own_way(spec, kind, style, leaves):
    o, p = door(spec)
    assert (o['kind'], o['style'], len(o.get('leaves', []))) == (kind, style, leaves)
    svg = '\n'.join(solve.solves(BOX.replace("- {door: std, wall: split, at: centre, swing: e}", "- " + spec)).sheet('ground').lines)
    assert svg.count('class="swing"') == leaves and svg.count('class="fold"') == (style == 'fold')
    assert svg.count('class="win"') == 3*((style == 'window') + 1)             # the window in the north wall is always there
    assert svg.count('class="dr"') == {'swing': 1, 'slide': 2, 'frame': 1}.get(style, 0)


def test_a_frame_beside_a_door_is_drawn_on_the_face_the_leaf_is_hung_on():
    spec = "- {door: std, wall: split, at: {from_start: 2.0}, swing: %s}\n      - {window: 0.3, style: frame, wall: split, at: {from_start: 1.7}}"
    for swing, x in (('e', '405'), ('w', '395')):
        lines = solve.solves(BOX.replace("- {door: std, wall: split, at: centre, swing: e}", spec % swing)).sheet('ground').lines
        assert '<line x1="%s" y1="170" x2="%s" y2="200" class="dr"/>' % (x, x) in lines       # in the door's plane, so the two meet
    lone = solve.solves(BOX.replace("- {door: std, wall: split, at: centre, swing: e}", "- {window: 0.3, style: frame, wall: split}")).sheet('ground').lines
    assert '<line x1="400" y1="285" x2="400" y2="315" class="dr"/>' in lone                   # by itself: on the centreline


@pytest.mark.parametrize('spec, why', [
    ('{door: std, at: [2, 3]}', r'sheet ground: sheets.ground.openings\[0\]: no wall at \(2.00, 3.00\)'),
    ('{door: std, wall: nope}', r"sheet ground: sheets.ground.openings\[0\]: no wall called 'nope'"),
    ('{door: std, wall: split, swing: up}', 'sheet ground: swing: use n/s/e/w, left/right or in/out, not \'up\''),
    ('{door: std, wall: split, face: up}', 'swing: use n/s/e/w, left/right or in/out'),
    ('{door: std, wall: split, hinge: up}', r'sheets.ground.openings\[0\].hinge: use start/end or n/s/e/w'),
])
def test_an_opening_that_cannot_be_placed_says_why(spec, why):
    with pytest.raises(ValueError, match=why):
        solve.solves(BOX.replace("- {door: std, wall: split, at: centre, swing: e}", "- " + spec))


def test_an_opening_wider_than_its_wall_is_reported_at_both_ends():
    o, p = door('{opening: 7, wall: split}')
    assert said(p, 'error').count('opening runs off the end of wall split') == 1
    assert 'no clear place' not in said(p)


def test_openings_that_only_touch_do_not_share_a_stretch():
    spec = "{door: std, wall: split, at: {from_start: 1.0}}\n      - {window: 1.0, wall: split, at: {from_start: 1.842}}"
    o, p = door(spec)
    assert 'shares a stretch' not in said(p)
    o, p = door(spec.replace('1.842', '1.80'))
    assert 'sheets.ground.openings[1]: shares a stretch of wall split with sheets.ground.openings[0]' in said(p, 'error')


# ---- rooms: what they are held to, how a space is split, what goes unnamed

@pytest.mark.parametrize('expect, why', [
    ('{w: 7.4, h: 5.4, area: 39.96}', None),
    ('{w: 7.44}', None),                                             # within 50 mm: that is its size
    ('{w: 7.36}', None),
    ('{area: 40.4}', None),                                          # within half a square metre
    ('{w: "24\'3\\""}', None),                                       # as the agent's plan gave it: 7.39 m
    ('{w: W - 2*EW}', None),
    ('{w: 7.46}', 'sheets.ground.rooms[0]: ROOM reads 7.40 wide, given as 7.46 — 0.06 under'),
    ('{w: 7.0}', 'ROOM reads 7.40 wide, given as 7.0 = 7.00 — 0.40 over'),
    ('{h: W - 2}', 'ROOM reads 5.40 deep, given as W - 2 = 6.00 — 0.60 under'),
    ('{area: 40.5}', 'ROOM reads 39.96 m², given as 40.5 — 0.54 under'),
    ('{h: "12\'8\\""}', 'ROOM reads 5.40 deep, given as 12\'8" = 3.86 — 1.54 over'),
])
def test_a_room_is_held_to_the_size_it_was_given(expect, why):
    p, _ = plan(ROOM.replace('at: [1, 1]', 'at: [1, 1], expect: %s' % expect))
    assert said(p) == (why or '') or why in said(p, 'warn')
    assert said(p).count('reads') == (1 if why else 0)


def test_a_room_that_is_not_a_rectangle_is_held_to_its_overall_size():
    ell = "sheets:\n  - id: g\n    envelope: [[0, 0], [8, 0], [8, 3], [4, 3], [4, 7], [0, 7]]\n    rooms: [{name: R, at: [2, 2], expect: %s}]\n"
    assert not said(plan(ell % '{w: 7.4, h: 6.4}')[0])               # the size it reads
    assert said(plan(ell % '{w: 5.0}')[0]) == 'sheets.g.rooms[0]: R reads 7.40 wide, given as 5.0 = 5.00 — 2.40 over'


def test_a_divider_splits_one_space_into_two_rooms_and_is_not_a_wall():
    two = ROOM.replace('at: [1, 1]', 'at: [1, 1]}\n      - {name: EAST, at: [7, 1]')
    p, _ = plan(two)
    assert 'ROOM are the same space' in said(p, 'error') and 'EAST' in said(p, 'error')
    p, _ = plan(two + "    dividers: [{from: [4, 0], to: [4, D]}]\n")
    assert not said(p) and [r['name'] for r in p.rooms] == ['ROOM', 'EAST']
    assert p.rooms[0]['w'] == pytest.approx(3.7, abs=0.005) and p.walls.area == pytest.approx(p.ext.area)   # no wall was built
    assert p.rooms[0]['area'] + p.rooms[1]['area'] == pytest.approx(39.96, abs=0.05)


def test_a_wall_may_stop_at_a_divider():
    text = ROOM.replace('at: [1, 1]', 'at: [1, 1]}\n      - {name: EAST, at: [7, 1]') + \
        "    walls: [{id: stub, from: [4, 0], to: [4, 3]}]\n    dividers: [{from: [4, 3], to: [4, D]}]\n"
    p, _ = plan(text)
    assert not said(p, 'error') and not said(p, 'warn') and 'wall stub ends in the open at (4.00, 3.00)' in said(p, 'info')


def test_a_space_with_no_room_in_it_is_warned_of_unless_the_sheet_says_it_is_meant():
    text = ROOM + "    walls: [{id: s, from: [4, 0], to: [4, D]}]\n"
    assert said(plan(text)[0]) == 'a space of 19.7 m² near (5.88, 3.00) has no room in it'
    assert not said(plan(text + "    unlabelled: ok\n")[0])
    tiny = ROOM + "    walls: [{id: s, path: [[0.3, 1.2], [1.2, 1.2], [1.2, 0.3]]}]\n"
    assert 'has no room in it' not in said(plan(tiny.replace('at: [1, 1]', 'at: [4, 3]'))[0])   # under a square metre: a duct, a cupboard


def test_a_room_seeded_in_a_wall_or_outside_is_an_error():
    for at in ('[0.1, 0.1]', '[50, 50]', '[-1, 3]'):
        p, _ = plan(ROOM.replace('at: [1, 1]', 'at: %s' % at))
        assert 'sheets.ground.rooms[0]: room ROOM is seeded in a wall or outside the building' in said(p, 'error') and not p.rooms


def test_a_sheets_own_require_speaks_in_its_own_words():
    p, _ = plan(ROOM + "    require: [{that: 'W > 9', message: 'only {W:.1f} wide'}, {that: 'D > 9'}, {that: 'W > 1'}]\n")
    assert p.issues == [('error', 'only 8.0 wide'), ('error', 'D > 9')]
    for bad, why in (("[{that: 'W'}]", 'not a comparison'), ("[{that: 'nope > 1'}]", "unknown name 'nope'"), ('[5]', 'subscriptable')):
        with pytest.raises(ValueError, match='sheet ground: require: .*' + why):
            solve.solves(ROOM + "    require: %s\n" % bad)


# ---- stairs

def flight(path, treads, turns=None, cut=None, show='all', width=0.9, reach=None):
    legs = len(path) - 1
    return {'id': 's', 'path': path, 'width': [width]*legs, 'treads': treads, 'going': 0.25,
            'turns': turns or [0]*(legs - 1), 'cut': cut, 'show': show, 'label': 'UP', 'where': 'stairs[0]', 'reach': reach}


@pytest.mark.parametrize('name, st, risers, area', [
    ('a straight flight', flight([(2, 1), (2, 4)], [12]), 13, 2.7),
    ('treads worked out from the going', flight([(2, 1), (2, 4)], [None]), 13, 2.7),
    ('a quarter landing', flight([(1, 5), (1, 1), (4, 1)], [4, 4]), 4 + 1 + 4 + 1, 0.9*(4.45 + 3.45) - 0.81),
    ('a half landing', flight([(1, 5), (1, 1), (2, 1), (2, 5)], [5, 0, 5]), 5 + 1 + 1 + 5 + 1, None),
    ('three winders', flight([(1, 5), (1, 1), (4, 1)], [4, 4], [3]), 4 + 3 + 4 + 1, 0.9*(4.45 + 3.45) - 0.81),
    ('a level run', flight([(2, 1), (2, 4)], [0]), 1, 2.7),
])
def test_every_tread_is_a_riser_a_landing_one_winders_each_one_and_one_more_onto_the_floor(name, st, risers, area):
    b = stairs.build(st)
    assert b['risers'] == risers, name
    if area:
        assert b['block'].area == pytest.approx(area)
    assert b['label'][1] == 'UP' and b['head'][0] == st['path'][-1]             # the arrow ends at the head


def test_treads_are_drawn_as_nosings_between_them():
    b = stairs.build(flight([(2, 1), (2, 4)], [12]))
    assert len(b['lines']) == 11 and len(b['polys']) == 1
    ys = sorted(a[1] for a, _ in b['lines'])
    assert ys == pytest.approx([1 + 0.25*k for k in range(1, 12)]) and all(abs(a[0] - c[0]) == pytest.approx(0.9) for a, c in b['lines'])
    fan = stairs.build(flight([(1, 5), (1, 1), (4, 1)], [4, 4], [3]))
    assert len(fan['lines']) == 3 + 3 + 2                                       # the nosings of each flight, and two winder lines


@pytest.mark.parametrize('cut', [0, 1, 2.5, 5, 6, 11])
def test_cut_at_any_riser_the_two_sheets_show_the_flight_once_between_them(cut):
    st = flight([(2, 1), (2, 4)], [12], cut=float(cut), show='below')
    below, above = stairs.build(st), stairs.build(dict(st, show='above'))
    assert below['block'].area + above['block'].area == pytest.approx(2.7, rel=0.02)
    assert below['block'].intersection(above['block']).area < 1e-6              # and no tread twice
    assert len(below['lines']) + len(above['lines']) == 11
    assert below['block'].bounds[1] == pytest.approx(1.0) and above['block'].bounds[3] == pytest.approx(4.0)
    assert above['head'][1] == pytest.approx((0.0, -1.0)) and below['head'][1] == pytest.approx((0.0, 1.0))   # each arrow toward the cut


def test_the_cut_end_is_the_zigzag_itself():
    below = stairs.build(flight([(2, 1), (2, 4)], [12], cut=5.0, show='below'))
    poly, = below['polys']
    assert len(poly) == 2 + 5                                                   # the two foot corners, and the five points of the break
    cut_y = 1 + 5.5*0.25                                                        # half a tread past a nosing, so they never coincide
    assert {round(abs(p[1] - cut_y), 3) for p in poly[1:-1]} == {0.0, stairs.BREAK_AMP}


@pytest.mark.parametrize('cut', [12, 13, 50, 1e9])
def test_a_cut_above_the_head_of_the_stair_is_refused(cut):
    """Once it drew the whole flight on both sheets."""
    for show in ('below', 'above'):
        with pytest.raises(ValueError, match='cut_risers: .* is past the top of the stair, which has 13 risers'):
            stairs.build(flight([(2, 1), (2, 4)], [12], cut=float(cut), show=show))
    with pytest.raises(ValueError, match=r'sheet ground: sheets.ground.stairs\[0\].cut_risers: 40 is past the top'):
        solve.solves(ROOM + "    stairs: [{path: [[2, 2], [2, 5]], treads: [12], cut_risers: 40}]\n")


def test_a_stair_shown_whole_ignores_where_it_would_be_cut():
    whole = stairs.build(flight([(2, 1), (2, 4)], [12], cut=5.0, show='all'))
    assert whole['block'].area == pytest.approx(2.7) and len(whole['lines']) == 11


def test_a_sheet_shows_a_stair_to_its_cut_and_the_level_above_the_rest():
    text = """
levels: [ground, first]
sheets:
  - id: ground
    envelope: [[0, 0], [8, 0], [8, 6], [0, 6]]
    stairs: [{id: main, path: [[2, 5], [2, 2]], treads: [12], cut_risers: 6, label: UP}]
    rooms: [{name: HALL, at: [5, 3]}]
  - id: first
    envelope: [[0, 0], [8, 0], [8, 6], [0, 6]]
    stairs: [{ref: ground.main, show: above}]
    rooms: [{name: LANDING, at: [5, 3]}]
"""
    s = solve.solves(text)
    below, above = s.sheet('ground').stairs[0], s.sheet('first').stairs[0]
    assert s.sheet('ground').plan.spec['stairs'][0]['show'] == 'below' and s.sheet('first').plan.spec['stairs'][0]['show'] == 'above'
    assert below['block'].area + above['block'].area == pytest.approx(3.0*0.9, rel=0.02)
    assert (below['label'][1], above['label'][1]) == ('UP', 'DN') and not [i for i in s.issues() if i[1] != 'info']
    whole = solve.solves(text.replace(', cut_risers: 6', '')).sheet('ground')
    assert whole.plan.spec['stairs'][0]['show'] == 'all' and whole.stairs[0]['block'].area == pytest.approx(2.7)
    assert solve.solves(text.replace('show: above', 'show: above, label: DOWN')).sheet('first').stairs[0]['label'][1] == 'DOWN'


@pytest.mark.parametrize('st, why', [
    (flight([(2, 1), (2, 1)], [3]), 'stairs\\[0\\]: two path points coincide'),
    (flight([(2, 2), (2, 2.2), (4, 2.2)], [1, 3]), 'stairs\\[0\\]: leg 0 is shorter than the corners at its ends'),
])
def test_a_stair_that_cannot_be_built_says_why(st, why):
    with pytest.raises(ValueError, match=why):
        stairs.build(st)


# ---- labels

KITCHEN = {'name': 'KITCHEN', 'w': 4.0, 'h': 3.0, 'area': 12.0, 'sub': None, 'dims': True, 'rot': None, 'size': None, 'zone': False}


def texts(layout):
    return [(t, cls, rot) for _, _, t, cls, rot in layout[0]]


def test_a_label_is_set_as_large_as_the_room_allows():
    big = labels.layouts(KITCHEN, 4, 3)
    assert texts(big[0]) == [('KITCHEN', 'rmname', None), ('4.00 × 3.00 m', 'rmdim', None), ('12.0 m²', 'rmarea', None)]
    assert texts(big[-1]) == [('KITCHEN', 'rmname small', None)]                # the last resort: its name
    assert [len(o[0]) for o in big] == [3, 2, 3, 1] and all(o[1] <= 2.4 for o in big)
    narrow = labels.layouts(KITCHEN, 1.2, 3)
    assert texts(narrow[0]) == [('KITCHEN', 'rmname small', -90), ('4.00 × 3.00 m', 'rmarea sm', -90)]   # turned to run up it
    assert narrow[0][1] < 1.2 < narrow[0][2]
    assert texts(labels.layouts(KITCHEN, 0.5, 0.5)[0]) == [('KITCHEN', 'rmname tiny', None)]             # a cupboard


def test_each_way_of_asking_for_a_label_changes_what_is_set():
    assert texts(labels.layouts(dict(KITCHEN, dims=False), 4, 3)[0]) == [('KITCHEN', 'rmname', None)]
    assert texts(labels.layouts(dict(KITCHEN, sub='tiled'), 4, 3)[0])[-1] == ('tiled', 'rmarea', None)   # in place of its area
    assert texts(labels.layouts(dict(KITCHEN, size='small'), 4, 3)[0])[0] == ('KITCHEN', 'rmname small', None)
    assert all(rot == -90 for o in labels.layouts(dict(KITCHEN, rot=-90), 4, 3) for _, _, rot in texts(o))
    zone, = labels.layouts(dict(KITCHEN, zone=True, sub='to do'), 4, 3)
    assert texts(zone) == [('KITCHEN', 'zonelabel', None), ('to do', 'rmarea sm', None), ('12.0 m²', 'rmarea sm', None)]


def test_every_label_class_has_a_measured_width_and_a_style():
    from flawlessplan import render
    for cls in labels.CH:
        assert '.' + cls.split()[0] in render.CSS, cls
    assert set(labels.NAMES) <= set(labels.CH) and labels.tw('ABC', 'rmname') == pytest.approx(0.999)
    assert [labels.CH[c] for c in labels.NAMES] == sorted([labels.CH[c] for c in labels.NAMES], reverse=True)
    assert labels.text_box((2, 2), 'hello', 'note').bounds == pytest.approx((1.58, 1.85, 2.42, 2.15))
    assert labels.text_box((2, 2), 'hello', 'note', -90).bounds == pytest.approx((1.85, 1.58, 2.15, 2.42))   # turned: its box turns too
    assert labels.text_box((2, 2), 'hello', 'unknown').bounds == labels.text_box((2, 2), 'hello', 'rmarea sm').bounds


def label_of(room):
    sh = solve.solves(BOX.replace('{name: LEFT, at: [1, 1]}', room)).sheet('ground')
    return sh, [(items, x, y) for items, x, y in sh.labels if items[0][2] == 'LEFT']


def test_a_label_sits_in_its_room_off_the_door_and_can_be_moved_by_hand():
    sh, ((items, x, y),) = label_of('{name: LEFT, at: [1, 1]}')
    assert (x, y) == (pytest.approx(2.125), pytest.approx(3.0)) and len(items) == 3
    moved, ((_, mx, my),) = label_of('{name: LEFT, at: [1, 1], dx: 0.5, dy: -1}')
    assert (mx, my) == (pytest.approx(2.625), pytest.approx(2.0))
    right = [(i, a, b) for i, a, b in sh.labels if i[0][2] == 'RIGHT'][0]
    swing = geom.leaf_shape(*sh.plan.openings[0]['leaves'][0])[2]
    for dx, dy, t, cls, rot in right[0]:
        assert not labels.text_box((right[1] + dx, right[2] + dy), t, cls, rot).intersects(swing)
    assert right[1] > 5.875                                         # pushed off the door that opens into it


def test_a_label_can_be_left_off_and_the_room_is_still_measured():
    sh, found = label_of('{name: LEFT, at: [1, 1], label: false}')
    assert found == [] and len(sh.labels) == 1 and [r['name'] for r in sh.plan.rooms] == ['LEFT', 'RIGHT']
    assert '>LEFT<' not in sh.svg() and sh.info['rooms'][0]['name'] == 'LEFT'


def test_a_rooms_sub_line_is_filled_from_its_own_size():
    _, ((items, _, _),) = label_of('{name: LEFT, at: [1, 1], sub: "{w:.1f} by {h:.1f}, {area:.0f}"}')
    assert items[-1][2] == '3.7 by 5.4, 20'
    with pytest.raises(ValueError, match="sheet ground: unknown name 'nope'"):
        label_of('{name: LEFT, at: [1, 1], sub: "{nope}"}')


@pytest.mark.parametrize('side, at, rot, leader', [
    ('north', (2.125, 0.0), None, ((2.125, -0.14), (2.125, 0.55))),
    ('east', (8.0, 3.0), 90, ((8.14, 3.0), (3.7, 3.0))),            # across RIGHT, to just inside LEFT
    ('south', (2.125, 6.0), None, ((2.125, 6.14), (2.125, 5.45))),
    ('west', (0.0, 3.0), -90, ((-0.14, 3.0), (0.55, 3.0))),
])
def test_a_label_in_the_margin_stands_off_that_face_with_a_line_to_its_room(side, at, rot, leader):
    sh, ((items, x, y),) = label_of('{name: LEFT, at: [1, 1], label: %s}' % side)
    assert (x, y) == pytest.approx(at) and [i[4] for i in items] == [rot, rot]
    assert [i[2] for i in items] == ['LEFT', '3.65 × 5.40 m'] and len(sh.leaders) == 1
    assert sh.leaders[0][0] == pytest.approx(leader[0]) and sh.leaders[0][1] == pytest.approx(leader[1])
    for dx, dy, *_ in items:                                        # every line of it outside the building
        assert not sh.plan.E.contains(geom.Point(x + dx, y + dy))
    assert sh.plan.rooms[0]['face'].contains(geom.Point(sh.leaders[0][1]))


def test_a_margin_label_on_the_front_steps_out_past_the_caption():
    plain, ((a, _, _),) = label_of('{name: LEFT, at: [1, 1], label: west}')
    front = solve.solves('house: {front: west}\n' + BOX.replace('{name: LEFT, at: [1, 1]}', '{name: LEFT, at: [1, 1], label: west}')).sheet('ground')
    b = [i for i, _, _ in front.labels if i[0][2] == 'LEFT'][0]
    assert b[0][0] == pytest.approx(a[0][0] - 0.75) and 'FRONT (WEST)' in front.svg()


def test_labels_in_one_margin_are_moved_clear_of_each_other():
    """Two small rooms side by side, both named in the margin below them:
    the names once printed one over the other."""
    text = ("sheets:\n  - id: g\n    envelope: [[0, 0], [8, 0], [8, 6], [0, 6]]\n"
            "    walls:\n      - {id: a, from: [1.2, 0], to: [1.2, 6]}\n      - {id: b, from: [2.4, 0], to: [2.4, 6]}\n"
            "    rooms:\n      - {name: LARDER, at: [0.7, 3], label: %s}\n      - {name: BOILER ROOM, at: [1.8, 3], label: %s}\n"
            "      - {name: KITCHEN, at: [5, 3]%s}\n")
    def boxes(sh):
        return [labels.text_box((x + dx, y + dy), t, cls, rot) for items, x, y in sh.labels[:2] for dx, dy, t, cls, rot in items]
    sh = solve.solves(text % ('south', 'south', '')).sheet('g')
    (_, x1, y1), (_, x2, y2) = sh.labels[:2]
    assert y1 == y2 == 6.0 and x1 < x2 and (x1 + x2)/2 == pytest.approx((0.725 + 1.8)/2)       # moved apart evenly, in their rooms' order
    b = boxes(sh)
    assert not b[0].intersects(b[2]) and not b[1].intersects(b[3]) and not said(sh.plan, 'warn')
    assert [a[0] for a, _ in sh.leaders] == pytest.approx([x1, x2])                            # each line starts under its own name
    assert all(r['face'].contains(geom.Point(tip)) for r, (_, tip) in zip(sh.plan.rooms, sh.leaders))
    # one each side of the building were never in each other's way, nor is a third at the far end
    sh = solve.solves(text % ('south', 'north', '')).sheet('g')
    assert [(x, y) for _, x, y in sh.labels[:2]] == [(pytest.approx(0.725), 6.0), (pytest.approx(1.8), 0.0)]
    sh = solve.solves(text % ('south', 'south', ', label: south')).sheet('g')
    assert sh.labels[2][1] == pytest.approx(5.075) and sh.labels[0][1] < 0.725


def test_labels_standing_off_different_faces_are_not_neighbours():
    marks = [('west', 0.0, 3.0, [(0, 0, 'LARDER', 'rmname small', -90)]), ('west', -4.0, 3.2, [(0, 0, 'STORE', 'rmname small', -90)])]
    assert labels.spread(marks) == [(0.0, 3.0), (-4.0, 3.2)]
    assert labels.spread([]) == []


# ---- the outline sheet

THREE = BOX + "  - {id: first, envelope: [[0, 0], [W, 0], [W, D], [0, D]], unlabelled: ok}\n" \
              "  - {id: loft, envelope: [[0, 0], [W, 0], [W, 3], [0, 3]], unlabelled: ok}\n"


def test_the_outline_is_drawn_first_when_there_is_more_than_one_sheet():
    assert [s.id for s in solve.solves(BOX).sheets] == ['ground']
    assert [s.id for s in solve.solves(THREE).sheets] == ['outline', 'ground', 'first', 'loft']
    assert [s.id for s in solve.solves('outline: {notes: [Asked for.]}\n' + BOX).sheets] == ['outline', 'ground']
    o = solve.solves(THREE).sheets[0]
    assert (o.kind, o.title, o.tab, o.plan, o.issues, o.base) == ('outline', 'OUTLINE', 'Outline', None, [], None)
    assert [s.id for s in solve.solves(THREE).plans()] == ['ground', 'first', 'loft']
    with pytest.raises(ValueError, match="no sheet called 'outline' \\(have ground, first, loft\\)"):
        solve.solves(THREE).sheet('outline')


def test_the_outline_shows_each_shape_once_with_every_face_measured():
    from flawlessplan import outline
    s = solve.solves(THREE)
    assert outline._distinct(s.house) == ['ground', 'loft']                     # first is the same shape as ground
    o = s.sheets[0]
    assert o.info['figures'] == [('Ground', '48.0 m² gross'), ('Loft', '24.0 m² gross')] and o.info['rooms'] == []
    drawn = '\n'.join(o.lines)
    assert drawn.count('class="env"') == 2 and drawn.count('>8.00<') == 4 and drawn.count('>6.00<') == 2 and drawn.count('>3.00<') == 2
    assert '>8.00 overall<' in drawn and '>6.00 overall<' in drawn and '>GROSS AREA<' in drawn
    assert '48.0 m² gross external' in drawn and '24.0 m² gross external' in drawn
    assert o.svg().startswith('<svg') and o.vb[2] > 2*800


def test_the_outline_can_be_told_which_sheets_and_carries_notes():
    s = solve.solves('outline: {sheets: [loft, first], notes: {summary: "{W:.0f} m wide.", needs: [The loft measured.]}}\n' + THREE)
    o = s.sheets[0]
    assert o.info['figures'] == [('Loft', '24.0 m² gross'), ('First', '48.0 m² gross')]
    assert o.info['summary'] == '8 m wide.' and o.info['groups'] == [('needs', 'Needs', ['The loft measured.'])]
    assert '\n'.join(o.lines).index('LOFT FLOOR') < '\n'.join(o.lines).index('FIRST FLOOR')
    with pytest.raises(model.ConfigError, match='outline.sheets: list sheets by their id'):
        solve.solves('outline: {sheets: [attic]}\n' + THREE)
    with pytest.raises(ValueError, match='sheet outline: outline.notes: expected a list or a mapping'):
        solve.solves('outline: {notes: 5}\n' + THREE)


# ---- where a house is, and what it is called

def test_a_house_is_its_folder_or_a_bare_file(tmp_path):
    folder = tmp_path / 'elms'
    folder.mkdir()
    (folder / 'house.yaml').write_text(ROOM)
    bare = tmp_path / 'plan.yaml'
    bare.write_text(ROOM)
    for given in (str(folder), str(folder) + '/', str(folder / 'house.yaml')):
        assert os.path.samefile(solve.house_file(given), str(folder / 'house.yaml'))
        assert solve.stem(given) == 'elms' and solve.beside(given, 'marks.json').endswith('elms/marks.json')
        assert solve.solve(given).name == 'elms'
    assert solve.stem(str(bare)) == 'plan' and solve.beside(str(bare), 'expected.json') == str(tmp_path / 'plan.expected.json')
    assert solve.solve(str(bare)).house['name'] == 'plan' and solve.solve(str(bare)).name == 'plan'


def test_solving_twice_gives_the_same_drawing():
    a, b = solve.solves(THREE), solve.solves(THREE)
    assert [s.svg() for s in a.sheets] == [s.svg() for s in b.sheets]
    sh = a.sheet('ground')
    assert sh.lines is sh.lines and sh.vb == sh.vb                  # drawn once, however often it is asked for


def test_issues_are_given_by_sheet_in_the_house_files_order():
    s = solve.solves(THREE.replace('unlabelled: ok}\n  - {id: loft', '}\n  - {id: loft'))
    assert s.issues() == [('first', 'warn', 'a space of 40.0 m² near (4.00, 3.00) has no room in it')]


# ---- the drawing itself

def test_numbers_are_written_short_and_paths_in_drawing_units():
    from flawlessplan import render
    assert [render.n2(v) for v in (0, 1.0, 1.256, 100.10, -0.001, -2.5, 1e-9)] == ['0', '1', '1.26', '100.1', '-0', '-2.5', '0']
    assert render.path([(0, 0), (1, 0.5)]) == 'M 0 0 L 100 50 Z' and render.path([(0, 0), (1, 0.5)], close=False) == 'M 0 0 L 100 50'
    assert render.U == 100.0 and render.esc(None) == 'None' and render.esc(5) == '5'
    assert render.esc('a & b < c > d "e" \'f\'') == 'a &amp; b &lt; c &gt; d &quot;e&quot; &#39;f&#39;'
    assert render.esc('&lt;') == '&amp;lt;'                         # escaped once, whatever it already looks like


def test_every_style_a_house_file_may_name_is_one_the_drawing_has():
    from flawlessplan import render
    assert set(render.AREAS) == set(model.AREA_STYLES) and set(render.TEXT) == set(model.TEXT_STYLES)
    for style in model.DIM_STYLES:
        assert not style or '.dimtext.%s{' % style in render.css()
    for cls in ('floor', 'wall', 'gone', 'new', 'zone', 'edge', 'fitting', 'fitline', 'stair', 'stairline', 'win', 'dr', 'swing',
                'fold', 'leader', 'dimline', 'compass', 'northarrow', 'arrow', 'arrowhead', 'front', 'note'):
        assert '.%s{' % cls in render.css() or '.%s,' % cls in render.css() or ',.%s{' % cls in render.css(), cls


def test_a_sheet_as_a_file_stands_alone():
    svg = solve.solves(BOX).sheet('ground').svg()
    assert svg.startswith('<svg xmlns="http://www.w3.org/2000/svg"') and svg.rstrip().endswith('</svg>')
    assert '<style>' in svg and 'href=' not in svg and 'url(' not in svg and '<script' not in svg
    assert 'GROUND FLOOR · 48.0 m² gross' in svg and '>N<' in svg    # the one line that is drawn, and north
    import xml.etree.ElementTree as ET
    ET.fromstring(svg)


def test_the_front_of_the_house_is_written_on_that_side():
    for side, rot in (('north', None), ('south', None), ('east', 90), ('west', -90)):
        svg = solve.solves('house: {front: %s, front_note: "the <lane>"}\n' % side + BOX).sheet('ground').svg()
        line = [ln for ln in svg.split('\n') if 'class="front"' in ln]
        assert len(line) == 1 and 'FRONT (%s) — the &lt;lane&gt;' % side.upper() in line[0]
        assert ('rotate(%s ' % rot in line[0]) if rot else 'rotate' not in line[0]
    assert 'class="front"' not in solve.solves(BOX).sheet('ground').svg()


def test_dimensions_and_free_text_are_drawn_where_they_are_put():
    extra = ("    dims: [{from: [0, 7], to: [W, 7], text: '{W:.2f} overall', style: calc}, {from: [9, 0], to: [9, D], text: deep}]\n"
             "    labels: [{at: [2, 5], text: '{MID} to the wall', style: small, rot: -90}]\n"
             "    areas: [{rect: [[8, 2], [10, 4]], style: outdoor, label: PATIO, sub: paved}, {points: [[1, 1], [2, 1], [2, 2]], style: fitting}]\n"
             "    gone: [[[1, 5], [3, 5]]]\n")
    sh = solve.solves(BOX + extra).sheet('ground')
    svg = sh.svg()
    assert '<text x="400" y="682" class="dimtext calc" text-anchor="middle">8.00 overall</text>' in svg      # above its line
    assert 'class="dimtext" text-anchor="middle" transform="rotate(-90 900 300)">deep</text>' in svg
    assert 'class="rmname small" text-anchor="middle" transform="rotate(-90 200 500)">4 to the wall</text>' in svg
    assert '>PATIO<' in svg and '>paved<' in svg and svg.count('class="outdoor"') == 1 and svg.count('class="fitting"') == 1
    assert '<path d="M 100 500 L 300 500" class="gone"/>' in svg and svg.count('class="dimline"') == 6
    assert sh.vb[0] + sh.vb[2] >= 1000 and sh.vb[1] + sh.vb[3] >= 700           # the sheet grows to take them in


# ---- the corners the tests above did not reach

@pytest.mark.parametrize('env, at, across, along', [
    ('[[0, 0], [3, 0], [9, 6], [6, 6]]', '[4.5, 3]', 3*math.sin(math.radians(45)) - 0.6, math.hypot(6, 6) - 0.6*math.sqrt(2)),
    ('[[0, 0], [4, 0], [12, 6], [8, 6]]', '[6, 3]', 4*math.sin(math.atan2(6, 8)) - 0.6, 10 - 0.6/0.6),
])
def test_a_room_between_steeply_slanted_walls_reads_square_to_them(env, at, across, along):
    """Square to the page it would read a sliver; square to its own walls, its clear width."""
    r = shaped(env, at)
    assert r['shape'] == 'irregular' and min(r['w'], r['h']) == pytest.approx(across, abs=0.01)
    assert max(r['w'], r['h']) == pytest.approx(along, abs=0.07)                # the length of its long walls
    assert r['w']*r['h'] == pytest.approx(r['area'], rel=0.01)
    assert min(geom.across(r['face'])) > across + 0.3                           # along the page it would read wider than it is


def test_a_point_can_be_put_on_either_face_of_a_partition_or_clear_of_it():
    text = ROOM + ("    unlabelled: ok\n    walls:\n      - {id: a, from: [4, 0], to: [4, D]}\n"
                   "      - {id: b, from: {y: 2, wall: a, side: e}, to: [8, 2]}\n"
                   "      - {id: c, from: {y: 4, wall: a, side: west, clear: 1}, to: [0, 4]}\n"
                   "      - {id: d, from: {y: 5, wall: a}, to: [8, 5]}\n")
    p, _ = plan(text)
    assert [w['a'] for w in p.spec['walls']] == [(4.0, 0.0), pytest.approx((4.05, 2.0)), pytest.approx((2.95, 4.0)), (4.0, 5.0)]


def test_a_point_on_a_path_that_no_leg_of_it_reaches_says_which_leg_came_nearest():
    with pytest.raises(model.ConfigError, match=r'walls\[1\].from: no leg of core is there \(core.1 runs along x'):
        plan(ROOM + "    walls:\n      - {id: core, path: [[0, 3], [4, 3], [4, 6]]}\n      - {from: {x: 6, wall: core}, to: [6, 0]}\n")


def test_in_and_out_mean_nothing_on_a_partition_and_are_taken_as_left():
    o, _ = door('{door: std, wall: split, swing: in}')
    assert o['leaves'][0][2] == pytest.approx((1.0, 0.0)) == door('{door: std, wall: split, swing: left}')[0]['leaves'][0][2]


def test_outside_walls_thicker_than_the_building_are_refused():
    for env in ('{t: 3, points: [[0, 0], [4, 0], [4, 4], [0, 4]]}', '[[0, 0, 2.5], [4, 0], [4, 4, 2.5], [0, 4]]'):
        with pytest.raises(ValueError, match='sheet g: the outside walls are thicker than the building is across'):
            solve.solves("sheets:\n  - id: g\n    envelope: %s\n    unlabelled: ok\n" % env)
    thin = solve.solves("sheets:\n  - id: g\n    envelope: {t: 1.9, points: [[0, 0], [4, 0], [4, 4], [0, 4]]}\n    unlabelled: ok\n")
    assert thin.sheet('g').plan.internal == pytest.approx(0.04)


def test_a_wall_of_no_length_is_refused_by_name():
    with pytest.raises(ValueError, match=r'sheet ground: wall dot: zero-length run at \(1.000, 1.000\)'):
        solve.solves(ROOM + "    walls: [{id: dot, from: [1, 1], to: [1, 1]}]\n")


def test_a_corner_of_a_stair_may_be_said_to_be_a_landing():
    fl = model.loads(ROOM + "    stairs: [{path: [[2, 5], [2, 2], [5, 2], [5, 5]], treads: [5, 0, 5], turns: [landing, {winders: 3, reach: true}]}]\n")['sheets'][0]
    assert fl['stairs'][0]['turns'] == [0, 3] and fl['stairs'][0]['reach'] == [False, True]


def test_a_face_too_short_to_carry_a_figure_is_not_dimensioned_on_the_outline():
    s = solve.solves("sheets:\n  - {id: a, unlabelled: ok, envelope: [[0, 0], [8, 0], [8, 6], [0.4, 6], [0, 5.7]]}\n"
                     "  - {id: b, unlabelled: ok, envelope: [[0, 0], [8, 0], [8, 6], [0, 6]]}\n")
    drawn = '\n'.join(s.sheets[0].lines)
    assert '>0.50<' not in drawn and '>7.60<' in drawn and '>5.70<' in drawn    # the 0.5 chamfer goes unmarked; its neighbours do not


def test_a_house_is_not_worked_out_again_until_its_file_changes(tmp_path):
    f = tmp_path / 'house.yaml'
    f.write_text(ROOM)
    first = solve.solve(str(tmp_path))
    assert solve.solve(str(f)) is first                                    # the folder and the file are the one house
    f.write_text(ROOM.replace('at: [1, 1]', 'at: [2, 2]'))
    second = solve.solve(str(f))
    assert second is not first and second.plans()[0].plan.spec['rooms'][0]['at'] == (2.0, 2.0)
    f.write_text('sheets: [')
    with pytest.raises(model.ConfigError):                                 # and one that stops reading is not answered from before
        solve.solve(str(f))


def test_the_rectangle_in_a_room_is_the_largest_on_its_own_lines():
    """Held to the plain way of finding it: every rectangle tried, largest first."""
    from shapely.geometry import box
    from shapely.affinity import rotate
    ell = Polygon([(0, 0), (5, 0), (5, 2), (3, 2), (3, 4), (0, 4)])
    breast = Polygon([(0, 0), (6, 0), (6, 4), (3.5, 4), (3.5, 3.6), (2.5, 3.6), (2.5, 4), (0, 4)])
    cut = Polygon([(0, 0), (4, 0), (5, 1), (5, 3), (0, 3)])
    for face in (ell, breast, cut, rotate(ell, 30), rotate(breast, -12), ell.buffer(1.0)):
        pts = list(face.exterior.coords)
        xs = sorted(set(round(p[0], 3) for p in pts))
        ys = sorted(set(round(p[1], 3) for p in pts))
        xs, ys = xs[::max(1, len(xs)//26)], ys[::max(1, len(ys)//26)]
        inside = face.buffer(0.001)
        tried = sorted((((b-a)*(d-c), a, c, b, d) for i, a in enumerate(xs) for b in xs[i+1:]
                        for j, c in enumerate(ys) for d in ys[j+1:]), reverse=True)
        plain = next((t[1:] for t in tried if inside.contains(box(*t[1:]))), None)
        assert geom._largest(xs, ys, inside) == plain


# ---- what is left standing inside a room made out of two

MERGED = """
survey: {W: 8.0, D: 6.0}
lines: {MID: W/2, HY: D/2}
sheets:
  - id: ground
    envelope: [[0, 0], [W, 0], [W, D], [0, D]]
    walls:
      - {id: split, from: [MID, 0], to: [MID, HY]}
      - {id: cross, from: [MID, HY], to: [W, HY]}
      - {id: nib, from: [2, 0], to: [2, 1.2]}
    openings:
      - {door: std, wall: split, at: centre, swing: e}
    rooms:
      - {name: LEFT, at: [1, 1]}
      - {name: RIGHT, at: [7, 1]}
"""


def test_nothing_is_said_of_walls_that_part_rooms_or_of_a_nib():
    p, _ = plan(MERGED)
    assert 'inside' not in said(p, 'warn') and 'inside' not in said(p, 'error')
    assert [(i['wall'], i['room'], i['whole']) for i in p.inside] == [('nib', 'LEFT', True)]     # known of, and not a fault


def test_a_wall_and_its_door_left_inside_one_room_are_reported():
    """`cross` is taken out: `split` and its door now stand in the middle of one room."""
    p, _ = plan(MERGED.replace("      - {id: cross, from: [MID, HY], to: [W, HY]}\n", ''))
    assert said(p, 'warn') == ('wall split has LEFT on both its faces — it stands inside one room, '
                               'and the door in it leads from that room into itself')
    assert 'RIGHT and LEFT are the same space' in said(p, 'error')
    got = dict((i.get('opening', i['wall']), i) for i in p.inside)
    assert got['split']['whole'] and got['split']['from'] == (4.0, 0.0) and got['split']['to'] == (4.0, 3.0)
    assert got['sheets.ground.openings[0]']['kind'] == 'door' and got['sheets.ground.openings[0]']['wall'] == 'split'


def test_walls_that_part_rooms_and_screens_that_reach_a_free_end_are_not_reported():
    p, _ = plan(MERGED.replace("      - {id: cross, from: [MID, HY], to: [W, HY]}\n",
                               "      - {id: screen, from: [5, 0], to: [5, D]}\n")
                .replace("to: [MID, HY]}", "to: [MID, D]}").replace("      - {door: std, wall: split, at: centre, swing: e}\n",
                                                                      "      - {opening: 5.0, wall: split, at: centre}\n")
                .replace("- {name: RIGHT, at: [7, 1]}", "- {name: RIGHT, at: [7, 1]}\n    dividers:\n      - {from: [MID, 0], to: [MID, D]}"))
    assert 'inside' not in said(p)                  # an opening in a wall between two rooms that a divider tells apart
    p, _ = plan(ROOM.replace('    rooms:', '    walls:\n      - {id: screen, from: [5, 0], to: [5, D]}\n'
                             '      - {id: other, from: [0, 3], to: [5, 3]}\n    rooms:')
                .replace('- {name: ROOM, at: [1, 1]}', '- {name: ROOM, at: [1, 1]}\n      - {name: SOUTH, at: [1, 5]}\n      - {name: EAST, at: [7, 1]}'))
    assert 'inside' not in said(p)
    p, _ = plan(ROOM.replace('    rooms:', '    walls:\n      - {id: pier, from: [3, 2], to: [5, 2]}\n'
                             '      - {id: tie, from: [5, 0], to: [5, 2]}\n      - {id: tie2, from: [3, 0], to: [3, 2]}\n    rooms:')
                .replace('- {name: ROOM, at: [1, 1]}', '- {name: ROOM, at: [1, 1]}\n      - {name: BOX, at: [4, 1]}'))
    assert 'inside' not in said(p)                  # each of the three has BOX on one face
    p, _ = plan(ROOM.replace('    rooms:', '    walls:\n      - {id: a, from: [3, 0], to: [3, 2]}\n'
                             '      - {id: b, from: [3, 2], to: [5, 2]}\n    rooms:'))
    assert 'inside' not in said(p, 'warn')          # an L of screens, one end free: each is a nib
    p, _ = plan(ROOM.replace('    rooms:', '    walls:\n      - {id: a, from: [2, 2], to: [2, 4]}\n      - {id: b, from: [2, 4], to: [4, 4]}\n'
                             '      - {id: c, from: [4, 4], to: [4, 2]}\n      - {id: d, from: [4, 2], to: [2, 2]}\n    rooms:')
                .replace('- {name: ROOM, at: [1, 1]}', '- {name: ROOM, at: [1, 1]}\n      - {name: CORE, at: [3, 3]}'))
    assert 'inside' not in said(p)                  # a room within a room: each wall has it on one face
    p, _ = plan(ROOM.replace('    rooms:', '    walls:\n      - {id: ring, from: [3, 0], to: [3, 3]}\n      - {id: tie, from: [0, 3], to: [3, 3]}\n'
                             '      - {id: lost, from: [0, 1.5], to: [3, 1.5]}\n    rooms:')
                .replace('- {name: ROOM, at: [1, 1]}', '- {name: ROOM, at: [6, 4]}\n      - {name: NORTH, at: [1, 0.8]}\n      - {name: SOUTH, at: [1, 2.4]}'))
    assert 'inside' not in said(p)
    q, _ = plan(ROOM.replace('    rooms:', '    walls:\n      - {id: ring, from: [3, 0], to: [3, 3]}\n      - {id: tie, from: [0, 3], to: [3, 3]}\n'
                             '      - {id: lost, from: [1, 1.5], to: [2, 1.5]}\n    rooms:')
                .replace('- {name: ROOM, at: [1, 1]}', '- {name: ROOM, at: [6, 4]}\n      - {name: NORTH, at: [1, 0.8]}'))
    assert said(q, 'warn') == ''                    # held by nothing: a screen, known of and not reported
    assert [(i['wall'], i['room']) for i in q.inside] == [('lost', 'NORTH')]


def test_a_wall_with_no_door_held_at_both_ends_inside_one_room_is_reported():
    """A room that runs all the way round a core, and a wall from the core
    to the outside wall: it parts nothing, and is no nib."""
    p, _ = plan(ROOM.replace('    rooms:', '    walls:\n      - {id: a, from: [2, 2], to: [2, 4]}\n      - {id: b, from: [2, 4], to: [4, 4]}\n'
                             '      - {id: c, from: [4, 4], to: [4, 2]}\n      - {id: d, from: [4, 2], to: [2, 2]}\n'
                             '      - {id: spur, from: [4, 3], to: [W, 3]}\n    rooms:')
                .replace('- {name: ROOM, at: [1, 1]}', '- {name: ROOM, at: [1, 1]}\n      - {name: CORE, at: [3, 3]}'))
    assert said(p, 'warn') == 'wall spur has ROOM on both its faces — it stands inside one room'


def test_a_stretch_of_wall_inside_a_room_is_known_and_its_door_reported():
    """`long` parts LEFT from RIGHT for half its length and then runs on into RIGHT alone."""
    text = ROOM.replace('    rooms:', '    walls:\n      - {id: long, from: [4, 0], to: [4, 5]}\n'
                        '      - {id: cross, from: [0, 3], to: [4, 3]}\n    openings:\n'
                        '      - {door: std, wall: long, at: [4, 4], swing: e}\n    rooms:') \
               .replace('- {name: ROOM, at: [1, 1]}', '- {name: LEFT, at: [1, 1]}\n      - {name: RIGHT, at: [7, 1]}')
    p, _ = plan(text)
    assert said(p, 'warn') == ('sheets.ground.openings[0]: the door in wall long leads from RIGHT into itself — '
                               'that stretch of the wall stands inside one room')
    stretch = [i for i in p.inside if i.get('wall') == 'long' and 'opening' not in i][0]
    assert not stretch['whole'] and stretch['room'] == 'RIGHT'
    assert abs(stretch['from'][1] - 3.0) < 0.11 and stretch['to'] == (4.0, 5.0)


# ---- rooflights: what is in the ceiling over a sheet's floor

LIT = ROOM + """    rooflights:
      - {id: north_light, at: [2, 1.5], w: 0.8, h: 1.0, label: RL1}
      - {at: [6, 4], w: 1.2, h: 0.6, rot: 90}
    notes:
      about: ["The rooflight is {north_light_w:.2f} by {north_light_h:.2f}, {north_light_area:.2f} m2."]
"""


def test_a_rooflight_is_read_set_over_its_room_drawn_and_reported():
    s = solve.solves(LIT)
    sh = s.sheet('ground')
    a, b = sh.plan.rooflights
    assert (a['id'], a['at'], a['w'], a['h'], a['label'], a['over']) == ('north_light', (2.0, 1.5), 0.8, 1.0, 'RL1', 'ROOM')
    assert a['pts'] == [(1.6, 1.0), (2.4, 1.0), (2.4, 2.0), (1.6, 2.0)] and a['where'] == 'sheets.ground.rooflights[0]'
    xs, ys = [round(p[0], 3) for p in b['pts']], [round(p[1], 3) for p in b['pts']]
    assert (min(xs), max(xs), min(ys), max(ys)) == (5.7, 6.3, 3.4, 4.6) and b['id'] is None      # turned: it runs north to south
    drawn = '\n'.join(sh.lines)
    assert drawn.count('class="rooflight"') == 4 and 'M 160 100 L 240 100 L 240 200 L 160 200 Z' in drawn
    assert 'M 160 100 L 240 200 M 240 100 L 160 200' in drawn and '>RL1</text>' in drawn
    assert drawn.index('class="rooflight"') > drawn.index('class="wall"')
    assert '.rooflight{' in render.CSS and 'stroke-dasharray' in render.CSS.split('.rooflight{')[1].split('}')[0]
    assert sh.info['groups'] == [('about', 'About this drawing', ['The rooflight is 0.80 by 1.00, 0.80 m2.'])]
    rep = report.report(s)['sheets'][0]['rooflights']
    assert rep == [{'id': 'north_light', 'w': 0.8, 'h': 1.0, 'at': [2.0, 1.5], 'over': 'ROOM', 'label': 'RL1'},
                   {'w': 1.2, 'h': 0.6, 'at': [6.0, 4.0], 'over': 'ROOM'}]
    assert 'rooflights' not in report.snapshot(s)['sheets']['ground'] and len(report.state(s)['sheets']['ground']['rooflights']) == 2
    found = query.lines(query.at(sh, (2.0, 1.5)))
    assert 'rooflight north_light, 0.80 × 1.00 m, over ROOM — sheets.ground.rooflights[0]' in found
    assert [i for i in s.issues() if i[1] != 'info'] == []


def test_a_rooms_label_keeps_off_a_rooflight_and_its_label():
    plain = solve.solves(ROOM).sheet('ground')
    (_, x, y), = plain.labels
    lit = solve.solves(ROOM + "    rooflights:\n      - {at: [%s, %s], w: 1.0, h: 1.0, label: RL}\n" % (x, y)).sheet('ground')
    (items, lx, ly), = lit.labels
    light = lit.plan.rooflights[0]['shape']
    boxes = [labels.text_box((lx + dx, ly + dy), t, cls, rot) for dx, dy, t, cls, rot in items]
    assert (lx, ly) != (x, y) and not any(b.intersects(light) for b in boxes)
    assert not any(b.intersects(labels.text_box(render.rooflight_label(lit.plan.rooflights[0]), 'RL', render.TEXT['note'], None)) for b in boxes)
    assert 'no clear place' not in ' '.join(m for _, m in lit.plan.issues)


@pytest.mark.parametrize('entry, why', [
    ('{at: [2, 2], w: 0.8}', "sheets.ground.rooflights\\[0\\]: missing 'h'"),
    ('{w: 0.8, h: 1}', "sheets.ground.rooflights\\[0\\]: missing 'at'"),
    ('{at: [2, 2], w: 0, h: 1}', 'sheets.ground.rooflights\\[0\\].w: a rooflight is more than nothing'),
    ('{at: [2, 2], w: 1, h: -1}', 'sheets.ground.rooflights\\[0\\].h: a rooflight is more than nothing'),
    ('{at: [2, 2], w: 1, h: 1, style: zone}', 'a rooflight is {at: \\[x, y\\], w:, h:}'),
    ('[2, 2, 1, 1]', 'a rooflight is {at:'), ('{at: [2, 2], w: 1, h: 1, id: "a b"}', "rooflights\\[0\\].id: 'a b'"),
    ('{at: [2, 2], w: wide, h: 1}', 'sheets.ground.rooflights\\[0\\].w'), ('{at: [2, 2], w: 1, h: 1, rot: east}', 'rooflights\\[0\\].rot'),
])
def test_a_rooflight_written_wrong_is_said(entry, why):
    with pytest.raises(model.ConfigError, match=why):
        solve.solves(ROOM + '    rooflights:\n      - %s\n' % entry)


def test_a_rooflight_off_the_building_or_named_as_a_room_is_reported():
    s = solve.solves(ROOM + "    rooflights:\n      - {id: ROOM, at: [7.9, 1], w: 1.0, h: 1.0}\n")
    said_ = ' | '.join(m for _, lv, m in s.issues() if lv == 'warn')
    assert 'sheets.ground.rooflights[0]: the rooflight ROOM is not all over the building' in said_
    assert 'a rooflight and a room are both called ROOM' in said_ and s.sheet('ground').names['ROOM_w'] > 7      # the room keeps its name
    over_wall = solve.solves(BOX + "    rooflights:\n      - {at: [4, 3], w: 1.0, h: 1.0}\n").sheet('ground').plan
    assert over_wall.rooflights[0]['over'] is None and 'rooflight' not in said(over_wall)       # across a wall: over no one room, and no fault


def test_a_rooflight_comes_from_a_part_and_is_left_out_by_id():
    text = LIT.replace('sheets:', 'levels: [ground]\nsheets:') + "  - id: dark\n    extends: ground\n    omit: [north_light]\n    notes: {}\n"
    dark = solve.solves(text).sheet('dark')
    assert [r['id'] for r in dark.plan.rooflights] == [None] and 'north_light_w' not in dark.names
    with pytest.raises(model.ConfigError, match='a room, a stair or a rooflight by its `id`'):
        solve.solves(text.replace('omit: [north_light]', 'omit: [south_light]'))
    assert [r['id'] for r in solve.solves(text.replace('omit: [north_light]', 'omit: [{rooflight: north_light}]')).sheet('dark').plan.rooflights] == [None]


def test_both_example_houses_have_a_rooflight_drawn_and_spoken_of():
    for name, sheet, word in (('cottage', 'first', 'rooflight lights the landing'), ('bungalow', 'infill', 'm² of glass')):
        s = solve.solve(os.path.join(ROOT, 'flawlessplan', 'examples', name))
        sh = s.sheet(sheet)
        assert len(sh.plan.rooflights) == 1 and sh.plan.rooflights[0]['over'] and 'class="rooflight"' in '\n'.join(sh.lines)
        assert any(word in t for _, _, items in sh.info['groups'] for t in items)
        assert not [a for p in s.plans() for a in p.plan.spec['areas'] if a['style'] == 'zone']         # and none is faked as an area


def test_the_floor_above_shows_the_well_shaded_and_railed_where_no_wall_is():
    """Past the zigzag is no floor. The cottage's flight runs down the west
    wall of the landing: the well is shaded, and the balustrade is on its
    open side and its foot, not along the wall and not across the head."""
    import os
    from flawlessplan.solve import solve
    from flawlessplan.workspace import EXAMPLES
    house = solve(os.path.join(EXAMPLES, 'cottage'))
    up, down = house.sheet('first').stairs[0], house.sheet('ground').stairs[0]
    assert down['void'] is None and down['rail'] == []
    assert up['void'].area > 0.5 and up['void'].intersection(house.sheet('first').plan.solid).area < 1e-6
    assert up['block'].intersection(up['void']).area < 0.05
    (run,) = up['rail']
    xs, ys = [p[0] for p in run], [p[1] for p in run]
    whole = up['block'].union(up['void']).bounds
    assert abs(max(xs) - whole[2]) < 0.05 and abs(max(ys) - whole[3]) < 0.05      # the east side and the foot
    assert min(ys) > whole[1] - 0.05 and not any(abs(a[1] - whole[1]) < 0.01 and abs(b[1] - whole[1]) < 0.01
                                                 for a, b in zip(run, run[1:]))    # nothing across the head
    drawn = house.sheet('first').svg()
    assert 'class="well"' in drawn and 'class="rail"' in drawn
