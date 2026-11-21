# -*- coding: utf-8 -*-
"""Split levels: levels by their floor above a datum, rooms on another
level than their sheet, a stair whose flights join levels and whose
landings may be a level's floor, each sheet drawing what of it it holds,
and what stands over what."""
import pytest
from flawlessplan import model, solve, stairs

SPLIT = '''
house: {name: Split, front: south}
survey: {W: 12.0, D: 8.0}
lines:
  WA: 4.0          # the hall's west wall
  WB: 7.7          # its east wall: the half-levels are past it
  SX: 7.2          # the first flight runs up beside WB
  LY: 3.5          # the half landing
levels:
  - {id: ground, floor: 0, floor_depth: 0.25}
  - {id: half, floor: 1.35, floor_depth: 0.25}
  - {id: first, floor: 2.7, floor_depth: 0.25}
  - {id: upper, floor: 4.05, floor_depth: 0.25}
parts:
  shell:
    envelope: [[0, 0], [W, 0], [W, D], [0, D]]
    walls:
      - {id: wa, from: [WA, 0], to: [WA, D]}
      - {id: wb, from: [WB, 0], to: [WB, D]}
sheets:
  - id: ground
    use: [shell]
    openings:
      - {door: std, wall: env.2, at: [5.5, D], hinge: w, swing: n}
      - {door: std, wall: wa, at: [WA, 6.5], hinge: s, swing: w}
      - {door: std, wall: wb, at: [WB, LY], hinge: n, swing: e}
    stairs:
      - id: main
        from: ground
        to: first
        path: [[SX, 5.8], [SX, LY], [4.95, LY]]
        width: 0.9
        going: 0.25
        turns: [{landing: half}]
    rooms:
      - {name: LIVING, at: [2, 4]}
      - {name: HALL, at: [5, 6.5]}
      - {name: KITCHEN, at: [10, 4], level: half}
  - id: first
    use: [shell]
    openings:
      - {door: std, wall: wa, at: [WA, 6.5], hinge: s, swing: w}
      - {door: std, wall: wb, at: [WB, 1.0], hinge: n, swing: e}
    stairs:
      - {ref: ground.main}
      - id: up
        from: first
        to: upper
        path: [[5.0, 1.0], [6.75, 1.0]]
        width: 0.9
        going: 0.25
    rooms:
      - {name: BEDROOM 1, at: [2, 4]}
      - {name: LANDING, at: [5, 6.5]}
      - {name: BEDROOM 2, at: [10, 4], level: upper}
'''


def build(text=SPLIT):
    return solve.solves(text)


def said(s, level=None):
    return [m for _, lv, m in s.issues() if level in (None, lv)]


def parts(sheet, i=0):
    return [f['part'] for f in sheet.stairs[i]['flights']]


def test_levels_are_given_by_their_floor():
    h = model.loads(SPLIT)
    assert h['floors'] == {'ground': 0.0, 'half': 1.35, 'first': 2.7, 'upper': 4.05}
    assert h['sheets'][0]['levels'] == ['ground', 'half'] and h['sheets'][1]['levels'] == ['first', 'upper']
    with pytest.raises(model.ConfigError, match='listed above'):
        model.loads(SPLIT.replace('{id: half, floor: 1.35', '{id: half, floor: -1'))


def test_a_floor_is_stepped_up_by_the_storey_heights_where_it_is_not_given():
    h = model.loads(SPLIT.replace('{id: half, floor: 1.35, floor_depth: 0.25}', '{id: half, height: 1.35}')
                    .replace('{id: ground, floor: 0, floor_depth: 0.25}', '{id: ground, floor: 0, height: 1.35}')
                    .replace('{id: first, floor: 2.7, floor_depth: 0.25}', '{id: first}'))
    assert h['floors']['half'] == 1.35 and h['floors']['first'] == 2.7


def test_one_sheet_draws_the_flight_between_its_own_levels_whole_and_cuts_the_next():
    s = build()
    g = s.sheet('ground')
    assert parts(g) == ['whole', 'below']
    assert [a[2][1] for a in g.stairs[0]['arrows']] == ['UP', 'UP']
    risers = [(f['id'], f['risers'], f['riser']) for f in g.plan.flights]
    assert risers == [('main ground-half', 8, 0.1688), ('main half-first', 8, 0.1688)]
    assert not said(s), said(s)


def test_the_level_above_shows_the_rest_as_its_well_and_what_runs_under_it():
    f = build().sheet('first')
    assert parts(f) == ['under', 'open'] and parts(f, 1) == ['whole']
    g = f.stairs[0]
    assert g['open'] is not None and g['rail'] and [a[2][1] for a in g['arrows']] == ['DN']


def test_a_room_on_another_level_says_how_far_up_it_is():
    g = build().sheet('ground')
    kitchen = [r for r in g.plan.rooms if r['name'] == 'KITCHEN'][0]
    assert kitchen['sub'].startswith('+1.35 m · ')
    assert any('+1.35 m · 29.2 m²' in l for l in g.lines)


def test_a_landing_that_is_a_level_is_walked_on():
    s = build()
    assert s.sheet('ground').stairs[0]['landing'] is not None and not said(s)
    s = build(SPLIT.replace('{door: std, wall: wb, at: [WB, LY]', '{door: std, wall: wb, at: [WB, 5.0]'))
    assert any('door in wall wb opens onto less than 0.5 m clear in HALL' in m for m in said(s)), said(s)


def test_without_the_depth_of_a_floor_the_flight_is_cut_and_the_rest_shown_above():
    s = build(SPLIT.replace('{id: first, floor: 2.7, floor_depth: 0.25}', '{id: first, floor: 2.7}'))
    f = s.sheet('first')
    assert parts(f) == [None, 'above'] and f.stairs[0]['void'] is not None
    assert any('the flight from ground to half has 1.35 m headroom under LANDING (sheet first)' in m for m in said(s)), said(s)


def test_a_room_with_too_little_over_it_is_said_and_its_clear_height_reported():
    s = build()
    k = [r for r in s.sheet('ground').plan.rooms if r['name'] == 'KITCHEN'][0]
    assert k['clear'] == {'height': 2.45, 'under': 'BEDROOM 2', 'sheet': 'first'}
    s = build(SPLIT.replace('{id: upper, floor: 4.05', '{id: upper, floor: 3.2'))
    assert any('KITCHEN has 1.60 m clear under BEDROOM 2 (sheet first), less than 2.0 m' in m for m in said(s)), said(s)


def test_a_stair_that_joins_a_level_with_no_floor_is_refused():
    with pytest.raises(ValueError, match='joins half, which has no floor height'):
        build(SPLIT.replace('{id: half, floor: 1.35, floor_depth: 0.25}', 'half'))


def test_where_two_rooms_on_different_levels_are_open_to_each_other_the_floor_steps():
    text = SPLIT.replace("      - {id: wb, from: [WB, 0], to: [WB, D]}\n", "      - {id: wb, from: [WB, 0], to: [WB, 5]}\n") \
        .replace("    rooms:\n      - {name: LIVING", "    dividers:\n      - {from: [WB, 5], to: [WB, D]}\n    rooms:\n      - {name: LIVING", 1)
    s = build(text)
    g = s.sheet('ground')
    assert len(g.steps) == 1 and abs(g.steps[0]['rise']) == 1.35 and abs(g.steps[0]['line'].length - 2.75) < 0.06
    assert any('class="step"' in l for l in g.lines)
    assert any('HALL and KITCHEN are open to each other and 1.35 m apart in level' in m for m in said(s, 'info'))


BOTH = SPLIT + "  - {id: both-floors, title: GROUND AND FIRST, shows: [ground, first]}\n"


def test_a_sheet_can_show_several_floors_side_by_side():
    s = build(BOTH)
    ids = [sh.id for sh in s.shown()]
    assert ids == ['outline', 'ground', 'first', 'both-floors']
    both = s.shown()[-1]
    assert both.plan is None and both.kind == 'combined' and [m.id for m in both.members] == ['ground', 'first']
    assert sum(1 for l in both.lines if l.startswith('<g transform="translate(')) == 2
    g, f = s.sheet('ground'), s.sheet('first')
    assert abs(both.vb[2] - (g.vb[2] + f.vb[2] + both.GAP*100)) < 1e-6
    assert both.info['figures'][0][0] == g.tab
    assert [sh.id for sh in s.plans()] == ['ground', 'first']       # what is checked and reported: the plans


def test_hiding_the_sheets_it_shows_leaves_it_alone_and_showing_them_splits_it_again():
    s = build(BOTH.replace('  - id: ground\n', '  - id: ground\n    hidden: true\n').replace('  - id: first\n', '  - id: first\n    hidden: true\n'))
    assert [sh.id for sh in s.shown()] == ['outline', 'both-floors']


@pytest.mark.parametrize('bad, why', [
    ('shows: [ground]', 'two or more plan sheets'),
    ('shows: [ground, attic]', 'two or more plan sheets'),
    ('shows: [ground, first], level: ground', 'takes title, tab, hidden and notes, not level'),
])
def test_what_is_wrong_with_a_sheet_that_shows_others_is_said(bad, why):
    with pytest.raises(model.ConfigError, match=why):
        build(SPLIT + "  - {id: both, %s}\n" % bad)
