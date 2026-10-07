# -*- coding: utf-8 -*-
"""Walls that curve, what is built in, and floors that end at an open
edge: each on a made-up plan small enough to work out by hand."""
import math
import pytest

from conftest import ROOM, plan, said
from flawlessplan import fittings, geom, model, query, report, solve
from flawlessplan.model import ConfigError


def bowed(how, extra=''):
    """An 8 by 6 building whose south wall, 8 long, curves as `how` says."""
    return ("survey: {W: 8.0, D: 6.0}\nsheets:\n  - id: ground\n"
            "    envelope: [{at: [0, 0], id: north}, {at: [W, 0], id: east}, {at: [W, D], id: bow, %s}, {at: [0, D], id: west}]\n"
            "    rooms:\n      - {name: ROOM, at: [4, 3]}\n%s" % (how, extra))


# a chord of 8 standing 1 off it: r = (4² + 1²)/2 = 8.5, and the segment it adds
R85 = 8.5
SEGMENT = R85**2*math.asin(4/R85) - 4*(R85 - 1)
DRAWN = 0.05         # m²: a curve is drawn in 5° pieces, inside the true arc, so its area is a hair under


# ---- the arc itself

def test_an_arc_runs_through_its_three_points_in_short_straight_pieces():
    pts, r = geom.arc((0, 0), (4, 0), (2, -1))
    assert r == pytest.approx(2.5) and pts[0] == (0, 0) and pts[-1] == (4, 0)       # the ends exactly as given
    assert pts[len(pts)//2] == pytest.approx((2.0, -1.0))
    centre = (2.0, 1.5)
    assert all(math.hypot(x - centre[0], y - centre[1]) == pytest.approx(2.5) for x, y in pts)
    turns = [math.degrees(math.atan2(b[1]-centre[1], b[0]-centre[0]) - math.atan2(a[1]-centre[1], a[0]-centre[0])) % 360
             for a, b in zip(pts, pts[1:])]
    assert max(turns) <= geom.FACET + 1e-9 and max(turns) == pytest.approx(min(turns))  # even pieces, none over 5°


def test_an_arc_goes_the_way_round_that_passes_through_its_middle_point():
    over, _ = geom.arc((0, 0), (4, 0), (2, -1))
    under, _ = geom.arc((0, 0), (4, 0), (2, 1))
    long_way, r = geom.arc((0, 0), (4, 0), (2, -4))
    assert all(y <= 1e-9 for _, y in over) and all(y >= -1e-9 for _, y in under)
    assert r == pytest.approx(2.5) and min(y for _, y in long_way) == pytest.approx(-4.0, abs=0.01)   # more than half a circle
    assert len(long_way) > len(over)


def test_a_gentle_arc_is_still_at_least_two_pieces():
    pts, r = geom.arc((0, 0), (4, 0), (2, -0.001))
    assert len(pts) == 3 and r > 1000


@pytest.mark.parametrize('via', [(2, 0), (1, 0), (9, 0), (0, 0), (4, 0)])
def test_an_arc_cannot_run_straight(via):
    with pytest.raises(ValueError, match='cannot run straight through'):
        geom.arc((0, 0), (4, 0), via)


# ---- an outside wall that curves

@pytest.mark.parametrize('how', ['rise: 1.0', 'radius: 8.5', 'via: [4, 7]'])
def test_rise_radius_and_via_are_three_ways_to_say_one_curve(how):
    p, _ = plan(bowed(how))
    bow = p.hosts['bow']
    assert bow.arc['r'] == pytest.approx(R85) and bow.arc['rise'] == pytest.approx(1.0)
    assert 48.0 + SEGMENT - DRAWN < p.gross < 48.0 + SEGMENT            # the room it bows out of, and the segment
    assert not said(p)


def test_a_curved_wall_is_one_wall_however_many_pieces_it_is_drawn_in():
    p, _ = plan(bowed('rise: 1.0'))
    assert [h.name for h in p.env_hosts] == ['north', 'east', 'bow', 'west'] and len(p.spec['envelope']['pts']) > 12
    assert p.hosts['bow'] is p.hosts['env.2'] and p.hosts['bow'].face == ((8.0, 6.0), (0.0, 6.0))
    assert p.hosts['bow'].L == pytest.approx(2*(R85 - 0.15)*math.asin(4/R85), abs=0.03)     # its length is along its middle
    assert p.hosts['north'].arc is None and len(p.hosts['north'].pts) == 2                  # and a straight one is as it was


def test_a_rise_below_nothing_bows_in():
    p, _ = plan(bowed('rise: -1.0'))
    assert p.hosts['bow'].arc == {'r': pytest.approx(R85), 'rise': pytest.approx(-1.0)}
    assert 48.0 - SEGMENT < p.gross < 48.0 - SEGMENT + DRAWN
    assert p.rooms[0]['area'] < 7.4*5.4 and not said(p)


def test_a_bow_reads_the_same_whichever_way_round_the_envelope_is_written():
    text = ("sheets:\n  - id: g\n    envelope: [{at: [0, 0], id: west}, {at: [0, 6], id: bow, rise: 1.0}, [8, 6], [8, 0]]\n"
            "    rooms: [{name: ROOM, at: [4, 3]}]\n")
    p, _ = plan(text)
    assert 48.0 + SEGMENT - DRAWN < p.gross < 48.0 + SEGMENT and abs(p.hosts['bow'].arc['rise']) == pytest.approx(1.0)
    assert max(y for _, y in p.spec['envelope']['pts']) == pytest.approx(7.0)               # out, not in


def test_a_bowed_room_reads_its_overall_size_and_its_true_area():
    p, _ = plan(bowed('rise: 1.0'))
    r = p.rooms[0]
    assert (r['shape'], r['w']) == ('near', pytest.approx(7.4)) and r['h'] == pytest.approx(6.4, abs=0.01)
    straight = 7.4*5.4
    assert straight + 0.6*SEGMENT < r['area'] < straight + SEGMENT      # more than the square room, by most of the segment


def test_a_round_building_is_two_curves_and_reads_its_diameter():
    text = "survey: {R: 3.0}\nsheets:\n  - id: g\n    envelope: [{at: [0, R], id: n, rise: R}, {at: [2*R, R], id: s, rise: R}]\n    rooms: [{name: ROUND, at: [R, R]}]\n"
    p, _ = plan(text)
    r = p.rooms[0]
    assert len(p.env_hosts) == 2 and p.gross == pytest.approx(math.pi*9, rel=0.002)         # 5° pieces: a hair under πr²
    assert r['shape'] == 'round' and r['w'] == pytest.approx(5.4, abs=0.01) and r['h'] == pytest.approx(5.4, abs=0.01)
    assert r['area'] == pytest.approx(math.pi*2.7**2, rel=0.003) and not said(p)
    assert report.SHAPES['round'] == 'across'


def test_the_outline_gives_a_curve_across_its_ends_and_its_radius():
    s = solve.solves(bowed('rise: 1.0') + "  - id: first\n    envelope: [[0, 0], [8, 0], [8, 6], [0, 6]]\n    unlabelled: ok\n")
    drawn = '\n'.join(s.sheets[0].lines)
    assert s.sheets[0].kind == 'outline' and '8.00 · r 8.50' in drawn and drawn.count(' · r ') == 1


def test_openings_follow_a_curve_and_are_measured_along_it():
    extra = ("    openings:\n      - {window: 2.0, wall: bow, at: centre}\n      - {window: 1.0, wall: bow, at: {from_start: 0.5}}\n"
             "      - {window: 1.0, wall: bow, at: {from_end: 0.5}}\n")
    p, _ = plan(bowed('rise: 1.0', extra))
    mid, first, last = p.openings
    L = p.hosts['bow'].L
    assert (mid['s0'], mid['s1']) == (pytest.approx(L/2 - 1), pytest.approx(L/2 + 1))
    assert mid['centre'] == pytest.approx((4.0, 6.85), abs=0.005)                 # in the middle of the wall, where it stands furthest out
    assert (first['s0'], first['s1']) == (pytest.approx(0.5), pytest.approx(1.5))
    assert (last['s0'], last['s1']) == (pytest.approx(L - 1.5), pytest.approx(L - 0.5))
    assert first['centre'][0] == pytest.approx(8 - last['centre'][0]) and first['centre'][1] == pytest.approx(last['centre'][1])
    for o in p.openings:
        assert o['hole'].area == pytest.approx(o['width']*0.3, rel=0.03)         # what it takes out: its width by the wall
    whole = plan(bowed('rise: 1.0'))[0].walls.area
    assert p.walls.area == pytest.approx(whole - 4.0*0.3, abs=0.03) and not said(p)


def test_an_opening_given_by_a_point_finds_its_place_on_the_curve():
    p, _ = plan(bowed('rise: 1.0', "    openings: [{window: 1.2, at: [4, 7]}, {door: std, wall: bow, at: {x: 2, wall: bow}}]\n"))
    win, door = p.openings
    assert win['host'].name == 'bow' and win['centre'] == pytest.approx((4.0, 6.85), abs=0.005)
    assert door['host'].name == 'bow' and door['centre'][0] == pytest.approx(2.0, abs=0.06)    # square off the curve from that point
    (hinge, shut, side, w), = door['leaves']
    assert w == pytest.approx(door['width'], abs=0.01)                            # a leaf is straight: it shuts across its opening
    assert math.hypot(*shut) == pytest.approx(1.0) and abs(geom._dot(shut, side)) < 1e-9


@pytest.mark.parametrize('at, why', [
    ('{from_start: -0.5}', 'opening runs off the end of wall env.2'),
    ('{from_end: -0.5}', 'opening runs off the end of wall env.2'),
    ('{from_start: 7.5}', 'opening runs off the end of wall env.2'),
])
def test_an_opening_off_the_end_of_a_curve_is_reported(at, why):
    p, _ = plan(bowed('rise: 1.0', "    openings: [{window: 2.0, wall: bow, at: %s}]\n" % at))
    assert why in said(p, 'error')


def test_two_openings_sharing_a_stretch_of_a_curve_are_reported():
    p, _ = plan(bowed('rise: 1.0', "    openings: [{window: 2.0, wall: bow}, {door: std, wall: bow, at: [4, 7]}]\n"))
    assert 'sheets.ground.openings[1]: shares a stretch of wall env.2 with sheets.ground.openings[0]' in said(p, 'error')


def test_a_point_can_be_put_on_a_curve_at_either_face():
    text = bowed('rise: 1.0', "    walls:\n      - {id: a, from: [2, 0], to: {x: 2, wall: bow}}\n"
                              "      - {id: b, from: [6, 0], to: {x: 6, wall: bow, side: out}}\n")
    p, _ = plan(text.replace('at: [4, 3]', 'at: [4, 3]}\n      - {name: LEFT, at: [1, 3]}\n      - {name: RIGHT, at: [7, 3]'))
    a, b = [w['b'] for w in p.spec['walls']]
    centre = (4.0, 6.0 + 1.0 - R85)
    assert a[0] == 2.0 and math.hypot(a[0]-centre[0], a[1]-centre[1]) == pytest.approx(R85 - 0.3, abs=0.01)    # the inside face
    assert b[0] == 6.0 and math.hypot(b[0]-centre[0], b[1]-centre[1]) == pytest.approx(R85, abs=0.01)          # the outside
    assert not said(p, 'error') and len(p.rooms) == 3                             # each wall meets the curve and closes
    with pytest.raises(ConfigError, match='bow does not reach x = 20.000'):
        plan(text.replace('{x: 2, wall: bow}', '{x: 20, wall: bow}'))


@pytest.mark.parametrize('how, why', [
    ('rise: 1, radius: 9', 'envelope[2]: give one of rise, radius and via'),
    ('rise: 1, via: [4, 7]', 'envelope[2]: give one of rise, radius and via'),
    ('radius: 3.9', 'envelope[2].radius: 3.900 is too tight for ends 8.000 apart'),
    ('via: [4, 6]', 'cannot run straight through (4.00, 6.00)'),
    ('via: [4]', 'envelope[2].via: expected a point'),
    ('rise: tall', "envelope[2].rise: unknown name 'tall'"),
    ('radius: 1/0', 'envelope[2].radius'),
])
def test_a_curve_that_cannot_be_drawn_says_why(how, why):
    with pytest.raises(ConfigError) as e:
        plan(bowed(how))
    assert 'sheets.ground.' in str(e.value) and why in str(e.value)


def test_a_radius_of_half_the_chord_is_a_half_circle_and_a_rise_of_nothing_is_straight():
    half, _ = plan(bowed('radius: 4'))
    assert half.hosts['bow'].arc == {'r': pytest.approx(4.0), 'rise': pytest.approx(4.0)}
    assert half.gross == pytest.approx(48 + math.pi*16/2, rel=0.002)
    flat, _ = plan(bowed('rise: 0'))
    assert flat.hosts['bow'].arc is None and flat.gross == 48.0 and len(flat.spec['envelope']['pts']) == 4


# ---- a partition that curves

SWEPT = ROOM.replace('at: [1, 1]', 'at: [1, 1]}\n      - {name: EAST, at: [7, 1]') + "    walls:\n      - {id: sweep, from: [4, 0], to: [4, D], %s}\n"


@pytest.mark.parametrize('how, r, rise, mid', [
    ('rise: 0.6, toward: e', (9 + 0.36)/1.2, 0.6, (4.6, 3.0)),
    ('rise: 0.6, toward: east', (9 + 0.36)/1.2, 0.6, (4.6, 3.0)),
    ('rise: 0.6, toward: w', (9 + 0.36)/1.2, -0.6, (3.4, 3.0)),
    ('rise: -0.6, toward: e', (9 + 0.36)/1.2, -0.6, (3.4, 3.0)),
    ('radius: 5, toward: e', 5.0, 1.0, (5.0, 3.0)),
    ('radius: 3, toward: w', 3.0, -3.0, (1.0, 3.0)),
    ('via: [4.5, 3]', (9 + 0.25)/1.0, 0.5, (4.5, 3.0)),
    ('via: [3.5, 1]', None, None, None),
])
def test_a_partition_says_which_way_it_curves(how, r, rise, mid):
    p, _ = plan(SWEPT % how)
    w = p.spec['walls'][0]
    assert w['a'] == (4.0, 0.0) and w['b'] == (4.0, 6.0) and len(w['pts']) > 3
    if r is not None:
        assert w['arc']['r'] == pytest.approx(r) and w['arc']['rise'] == pytest.approx(rise)
        assert geom.LineString(w['pts']).distance(geom.Point(mid)) < 0.01              # it passes through its furthest point, to a 5° piece
    assert not said(p, 'error') and {x['name'] for x in p.rooms} == {'ROOM', 'EAST'}        # it still divides the two
    left, right = sorted(p.rooms, key=lambda x: x['face'].centroid.x)
    assert left['area'] + right['area'] == pytest.approx(7.4*5.4 - p.hosts['sweep'].L*0.1, abs=0.35)   # the floor, less the wall


@pytest.mark.parametrize('how, why', [
    ('rise: 0.6', 'walls[0].toward: say which way it curves — a compass point across the wall'),
    ('rise: 0.6, toward: n', 'walls[0].toward: say which way it curves'),        # along the wall, not across it
    ('rise: 0.6, toward: up', 'walls[0].toward: say which way it curves'),
    ('radius: 2, toward: e', 'walls[0].radius: 2.000 is too tight for ends 6.000 apart'),
    ('rise: 0.6, radius: 4, toward: e', 'walls[0]: give one of rise, radius and via'),
    ('via: [4, 3]', 'cannot run straight through'),
])
def test_a_curved_partition_that_cannot_be_drawn_says_why(how, why):
    with pytest.raises(ConfigError) as e:
        plan(SWEPT % how)
    assert 'sheets.ground.' + why in str(e.value) or why in str(e.value)


def test_a_door_in_a_curved_partition_cuts_only_that_wall():
    p, _ = plan(SWEPT % 'rise: 0.6, toward: e' + "    openings: [{door: std, wall: sweep, at: centre, swing: e, hinge: n}]\n")
    door, = p.openings
    whole = plan(SWEPT % 'rise: 0.6, toward: e')[0].walls.area
    assert door['host'].name == 'sweep' and door['centre'] == pytest.approx((4.6, 3.0), abs=0.01)
    assert whole - p.walls.area == pytest.approx(0.842*0.1, rel=0.05) and not said(p, 'error')


def test_a_wall_written_as_a_path_may_curve_leg_by_leg():
    text = ROOM.replace('at: [1, 1]', 'at: [1, 5]}\n      - {name: NORTH, at: [1, 1]') + \
        "    walls: [{id: core, path: [[0, 3], {at: [4, 3], rise: 0.5, toward: n}, [8, 3]]}]\n" \
        "    openings: [{door: std, wall: core, at: [6, 2.6]}, {door: std, wall: core.0}]\n"
    p, _ = plan(text)
    assert p.hosts['core.0'].arc is None and p.hosts['core.1'].arc['r'] == pytest.approx((4 + 0.25)/1.0)
    assert [o['host'].name for o in p.openings] == ['core.1', 'core.0'] and not said(p, 'error')


# ---- a wall, straight or not, asked where it is

CURVE = geom.Host('c', geom.arc((0, 0), (4, 0), (2, -1))[0], 0.1)
LINE = geom.Host('l', [(0, 0), (4, 0)], 0.1)


def test_a_place_on_a_wall_is_a_distance_along_it():
    assert LINE.L == 4.0 and CURVE.L == pytest.approx(2*2.5*math.asin(2/2.5), rel=0.002)
    for h in (LINE, CURVE):
        for s in (0.0, 0.4, h.L/2, h.L - 0.3, h.L):
            for off in (0.0, 0.2, -0.2):
                got = h.project(h.at(s, off))
                near = 1e-6 if h is LINE or not off else 0.03       # off a curve, to the nearest piece of it
                assert got[0] == pytest.approx(s, abs=near) and got[1] == pytest.approx(abs(off), abs=near)
    assert LINE.project((-1, 0))[0] == -1.0 and LINE.project((5, 0))[0] == 5.0      # past an end: so an opening off it is seen to be
    assert CURVE.project((-1, 0.5))[0] < 0 and CURVE.project((5, 0.5))[0] > CURVE.L


def test_a_run_along_a_wall_is_as_long_as_asked_and_stands_off_it():
    assert LINE.run(1, 2, 0.5) == [(1.0, 0.5), (2.0, 0.5)]
    length = lambda pts: sum(math.hypot(b[0]-a[0], b[1]-a[1]) for a, b in zip(pts, pts[1:]))
    for s0, s1 in ((0.0, CURVE.L), (0.5, 3.0), (1.0, 1.2)):
        assert length(CURVE.run(s0, s1)) == pytest.approx(s1 - s0, abs=1e-6)
    assert len(CURVE.run(0.0, CURVE.L)) == len(CURVE.pts) and len(CURVE.run(1.0, 1.05)) == 2
    inside, outside = CURVE.run(0, CURVE.L, 0.3), CURVE.run(0, CURVE.L, -0.3)
    assert length(inside) < CURVE.L < length(outside)                               # the inside of a bend is the shorter
    centre = (2.0, 1.5)
    assert all(math.hypot(x-centre[0], y-centre[1]) == pytest.approx(2.2, abs=0.005) for x, y in inside)


def test_a_wall_says_which_way_it_runs_where_an_opening_is():
    assert LINE.frame(1, 2) == ((1.0, 0.0), None) and LINE.frame(0, 4) == LINE.frame(3, 3.5)
    whole, start, end = CURVE.frame(0, CURVE.L), CURVE.frame(0, 0.2), CURVE.frame(CURVE.L - 0.2, CURVE.L)
    assert whole[0] == pytest.approx((1.0, 0.0)) and start[0][1] < -0.5 and end[0][1] > 0.5     # it turns along its length
    assert start[0][0] == pytest.approx(end[0][0])


def test_an_outside_wall_knows_its_way_in_all_along_a_curve():
    p, _ = plan(bowed('rise: 1.0'))
    bow = p.hosts['bow']
    centre = (4.0, 6.0 + 1.0 - R85)
    for s in (0.3, bow.L/2, bow.L - 0.3):
        u, inward = bow.frame(s - 0.1, s + 0.1)
        at = bow.at(s)
        to_centre = geom._unit(at, centre)[0]
        assert geom._dot(inward, to_centre) == pytest.approx(1.0, abs=1e-3) and abs(geom._dot(u, inward)) < 1e-9
    assert p.hosts['north'].frame(1, 2) == ((1.0, 0.0), pytest.approx((0.0, 1.0)))


def test_what_an_opening_takes_out_of_a_straight_wall_is_a_plain_strip():
    hole = LINE.hole(1, 2)
    assert hole.bounds == pytest.approx((1.0, -0.052, 2.0, 0.052)) and hole.area == pytest.approx(0.104)
    assert CURVE.hole(1, 2).area == pytest.approx(0.104, rel=0.03)


# ---- what is built in

def fitted(f, extra=''):
    return ("survey: {W: 8.0, D: 6.0}\nsheets:\n  - id: ground\n"
            "    envelope: [{at: [0, 0], id: north}, {at: [W, 0], id: east}, {at: [W, D], id: south}, {at: [0, D], id: west}]\n"
            "    walls: [{id: split, from: [4, 0], to: [4, D]}]\n"
            "    rooms:\n      - {name: A, at: [1, 1]}\n      - {name: B, at: [7, 1]}\n"
            "    fittings:\n      - %s\n%s" % (f, extra))


def one(f):
    p, _ = plan(fitted(f))
    return p.fittings[0], p


@pytest.mark.parametrize('kind', sorted(fittings.KINDS))
def test_every_kind_has_a_usual_size_and_a_symbol_inside_it(kind):
    w, d = fittings.KINDS[kind]
    assert 0.3 <= w <= 2.0 and 0.3 <= d <= 1.0
    for size in ((w, d), (w*2, d*1.5), (w*0.8, d)):
        parts = fittings.symbol(kind, size[0], size[1], 'FF' if kind == 'unit' else None)
        assert parts[0][0] == 'fill' and {p[0] for p in parts} <= {'fill', 'line', 'text'}
        for part in parts:
            pts = [part[1]] if part[0] == 'text' else part[1]
            assert all(-size[0]/2 - 1e-9 <= a <= size[0]/2 + 1e-9 and -1e-9 <= b <= size[1] + 1e-9 for a, b in pts), part
            assert part[0] != 'line' or part[2] in (True, False)
    f, p = one('{%s: true, wall: south%s}' % (kind, ', at: {from_start: 0.5}'))
    assert (f['kind'], f['w'], f['d']) == (kind, w, d) and not said(p)


def test_the_kinds_in_the_guide_are_the_kinds_there_are():
    from flawlessplan import page
    row = [ln for ln in page.asset('house-file.md').split('\n') if ln.startswith('| `fittings` |')][0]
    for kind in fittings.KINDS:
        assert '`%s`' % kind in row, kind
    assert set(fittings.ORDER) <= set(fittings.KINDS) and set(fittings.LETTER) <= set(fittings.KINDS)


def test_a_unit_carries_its_label_and_a_boiler_its_letter():
    assert fittings.symbol('unit', 0.6, 0.6, 'WM')[-1] == ('text', (0, 0.3), 'WM')
    assert fittings.symbol('boiler', 0.45, 0.35)[-1] == ('text', (0, 0.175), 'B')
    assert fittings.symbol('boiler', 0.45, 0.35, 'combi')[-1][2] == 'combi'
    assert not [p for p in fittings.symbol('unit', 0.6, 0.6) if p[0] == 'text']
    assert fittings.symbol('unit', 0.6, 0.6, 7)[-1][2] == '7'


@pytest.mark.parametrize('f, bounds, back', [
    ('{bath: 1.5, wall: north, at: {from_start: 0}}', (0.3, 0.3, 1.8, 1.0), (1.05, 0.3)),        # from the corner of the room
    ('{bath: 1.5, wall: north, at: {from_end: 0}}', (6.2, 0.3, 7.7, 1.0), (6.95, 0.3)),
    ('{bath: 1.5, wall: north, at: {from_start: 0.2}, depth: 0.8}', (0.5, 0.3, 2.0, 1.1), (1.25, 0.3)),
    ('{bath: true, wall: north, at: [2, 0]}', (1.15, 0.3, 2.85, 1.0), (2.0, 0.3)),               # a point is its middle
    ('{bath: true, wall: north, at: [2, 0], corner: w}', (2.0, 0.3, 3.7, 1.0), (2.85, 0.3)),     # ... or the end it names
    ('{bath: true, wall: north, at: [2, 0], corner: e}', (0.3, 0.3, 2.0, 1.0), (1.15, 0.3)),
    ('{wardrobe: 2, wall: south, at: {from_start: 0}}', (5.7, 5.1, 7.7, 5.7), (6.7, 5.7)),       # south runs west: its start is east
    ('{wc: true, wall: split, side: w}', (3.25, 2.81, 3.95, 3.19), (3.95, 3.0)),
    ('{wc: true, wall: split, side: e}', (4.05, 2.81, 4.75, 3.19), (4.05, 3.0)),
    ('{wardrobe: 2, wall: split, side: w, at: {from_end: 0}}', (3.35, 3.7, 3.95, 5.7), (3.95, 4.7)),
    ('{wardrobe: 2, wall: split, side: w, at: {from_start: 0}}', (3.35, 0.3, 3.95, 2.3), (3.95, 1.3)),
    ('{cylinder: true, at: [2, 3], facing: s}', (1.75, 3.0, 2.25, 3.5), (2.0, 3.0)),             # against no wall
    ('{cylinder: true, at: [2, 3], facing: north}', (1.75, 2.5, 2.25, 3.0), (2.0, 3.0)),
    ('{unit: true, at: [2, 3], facing: e, corner: n, label: FF}', (2.0, 3.0, 2.6, 3.6), (2.0, 3.3)),
])
def test_a_fitting_stands_where_it_is_put(f, bounds, back):
    got, p = one(f)
    assert got['floor'].bounds == pytest.approx(bounds) and got['o'] == pytest.approx(back)
    assert got['floor'].area == pytest.approx(got['w']*got['d']) and not said(p)
    assert abs(geom._dot(got['u'], got['n'])) < 1e-9
    reach = (got['o'][0] + got['n'][0]*got['d']/2, got['o'][1] + got['n'][1]*got['d']/2)
    assert got['floor'].contains(geom.Point(reach))                     # `n` is the way out from its back


def test_flip_turns_a_fitting_end_for_end_and_moves_nothing():
    a, _ = one('{bath: true, wall: north, at: [2, 0]}')
    b, _ = one('{bath: true, wall: north, at: [2, 0], flip: true}')
    assert a['floor'].equals(b['floor']) and b['u'] == pytest.approx((-a['u'][0], -a['u'][1])) and a['n'] == b['n']


def test_a_fitting_on_a_curved_wall_stands_square_to_it_there():
    p, _ = plan(bowed('rise: 1.0', "    fittings: [{basin: true, wall: bow, at: {x: 6.5, wall: bow}}, {wc: true, wall: bow}]\n"))
    basin, wc = p.fittings
    assert wc['n'] == pytest.approx((0.0, -1.0), abs=1e-6) and wc['o'] == pytest.approx((4.0, 6.7), abs=0.005)
    assert basin['n'][0] < -0.2 and basin['n'][1] < -0.9 and not said(p)          # leaning in toward the middle of the room


@pytest.mark.parametrize('f, why', [
    ('{bath: true, wall: north}', 'sheets.ground.fittings[0]: the bath runs into a wall'),        # across the partition
    ('{worktop: 30, wall: north, at: {from_start: 0}}', 'sheets.ground.fittings[0]: the worktop is not all inside the building'),
    ('{wc: true, wall: north, side: out}', 'the wc is not all inside the building'),
    ('{unit: true, wall: north, at: {from_start: -3}}', 'the unit is not all inside the building'),
    ('{cylinder: true, at: [20, 20], facing: s}', 'the cylinder is not all inside the building'),
    ('{shower: true, at: [3.6, 3], facing: e}', 'the shower runs into a wall'),
])
def test_a_fitting_that_does_not_fit_is_reported(f, why):
    got, p = one(f)
    assert why in said(p, 'warn') and not said(p, 'error')


@pytest.mark.parametrize('f, why', [
    ('{wc: true, wall: split}', 'sheets.ground.fittings[0]: say which `side:` of wall split it stands on'),
    ('{bath: true, wall: nope}', "sheets.ground.fittings[0]: no wall called 'nope'"),
    ('{bath: true, wall: north, at: [2, 0], corner: n}', 'sheets.ground.fittings[0].corner: wall north does not run that way'),
    ('{unit: true, at: [2, 3], facing: e, corner: e}', 'sheets.ground.fittings[0].corner: its back does not run that way'),
])
def test_a_fitting_that_cannot_be_stood_says_why(f, why):
    with pytest.raises(ValueError) as e:
        solve.solves(fitted(f))
    assert str(e.value) == 'sheet ground: ' + why


def test_a_worktop_is_drawn_under_what_sits_in_it():
    extra = "      - {worktop: 3, wall: north, at: {from_start: 0}}\n      - {oven: true, wall: north, at: [2.5, 0]}\n      - {hob: true, wall: north, at: [2.5, 0]}\n"
    sh = solve.solves(fitted('{sink: true, wall: north, at: [1, 0]}', extra)).sheet('ground')
    svg = sh.svg()
    fills = [m for m in svg.split('\n') if 'class="fitting"' in m]
    assert len(fills) == 4 and 'M 30 30 L 330 30' in fills[0]                    # the worktop first, whatever order they were written in
    assert 'M 220 30' in fills[1] and svg.count('class="fitline"') == 4 + 1 + 4  # then the oven; sink, oven and hob lines
    assert not [i for i in sh.issues if i[0] != 'info']                          # a sink in a worktop is not a fault


def test_labels_keep_off_what_is_built_in():
    bare = solve.solves(fitted('{unit: 0.1, depth: 0.1, at: [7.6, 5.6], facing: n}')).sheet('ground')
    full = solve.solves(fitted('{wardrobe: 3.4, depth: 2.2, wall: west, at: centre}')).sheet('ground')
    (_, x0, y0), (_, x1, y1) = bare.labels[0], full.labels[0]
    block = full.plan.fittings[0]['floor']
    assert block.contains(geom.Point(x0, y0)) and not block.buffer(0.3).contains(geom.Point(x1, y1))


def test_fittings_are_in_the_report_and_not_in_what_a_house_is_held_to():
    s = solve.solves(fitted('{bath: 1.5, wall: north, at: {from_start: 0}}', "      - {cylinder: true, at: [2, 3], facing: s}\n"))
    rep = report.report(s)['sheets'][0]['fittings']
    assert rep == [{'kind': 'bath', 'w': 1.5, 'd': 0.7, 'wall': 'north', 'back': [1.05, 0.3]},
                   {'kind': 'cylinder', 'w': 0.5, 'd': 0.5, 'wall': None, 'back': [2.0, 3.0]}]
    assert 'fittings' not in report.snapshot(s)['sheets']['ground']
    assert [f['kind'] for f in report.state(s)['sheets']['ground']['fittings']] == ['bath', 'cylinder']
    assert 'fittings' in report.UNMEASURED


def test_the_plan_says_what_is_built_in_at_a_point():
    sh = solve.solves(fitted('{bath: true, wall: north, at: [2, 0]}', "      - {cylinder: true, at: [2, 3], facing: s}\n")).sheet('ground')
    assert 'bath, 1.70 × 0.70 m against wall north — sheets.ground.fittings[0]' in query.lines(query.at(sh, (2, 0.5)))
    assert 'cylinder, 0.50 × 0.50 m — sheets.ground.fittings[1]' in query.lines(query.at(sh, (2, 3.2)))
    assert not any('bath' in t for t in query.lines(query.at(sh, (2, 2.0))))        # a metre off: out of reach
    assert any(t.startswith('0.40 m — bath') for t in query.lines(query.at(sh, (2, 1.4))))


# ---- a floor that ends at an open edge

HALF = "sheets:\n  - id: g\n    envelope: [{at: [0, 0], open: true, id: step}, [8, 0], [8, 5], [0, 5]]\n    rooms: [{name: L, at: [3, 2]}]\n"


def test_an_open_edge_is_the_floors_and_no_wall_stands_on_it():
    p, _ = plan(HALF)
    step = p.hosts['step']
    assert step.open and step.t == 0 and [h.open for h in p.env_hosts] == [True, False, False, False]
    assert p.gross == 40.0 and p.internal == pytest.approx(7.4*4.7)
    assert p.ext.area == pytest.approx(40 - 7.4*4.7)                    # three walls' worth, and nothing along the top
    r = p.rooms[0]
    assert (r['w'], r['h'], r['shape']) == (pytest.approx(7.4), pytest.approx(4.7), 'rect')     # floor right up to the edge
    assert r['face'].bounds[1] == pytest.approx(0.0, abs=0.005) and not said(p)


def test_an_open_edge_is_drawn_as_an_edge_and_not_as_a_wall():
    sh = solve.solves(HALF).sheet('g')
    svg = sh.svg()
    assert svg.count('class="edge"') == 1 and '<line x1="0" y1="0" x2="800" y2="0" class="edge"/>' in svg
    found = query.lines(query.at(sh, (4, 0.2)))
    assert '0.20 m — open edge step, where the floor ends and no wall stands, (0.00, 0.00) to (8.00, 0.00)' in found
    assert not any('outside wall step' in t for t in found)


def test_gross_area_is_the_same_whether_an_edge_is_a_wall_or_open():
    walled, _ = plan(HALF.replace('open: true, ', ''))
    opened, _ = plan(HALF)
    assert walled.gross == opened.gross == 40.0 and opened.internal - walled.internal == pytest.approx(7.4*0.3)


def test_an_opening_cannot_be_put_in_an_open_edge():
    p, _ = plan(HALF + "    openings: [{door: std, wall: step}]\n")
    assert "sheets.g.openings[0]: step is the floor's open edge — no wall is there to put an opening in" in said(p, 'error')
    p, _ = plan(HALF + "    openings: [{window: 1.0, at: [4, 0]}]\n")
    assert 'open edge' in said(p, 'error')


def test_an_envelope_with_no_wall_at_all_is_reported():
    p, _ = plan(HALF.replace('[8, 0], [8, 5], [0, 5]', '{at: [8, 0], open: true}, {at: [8, 5], open: true}, {at: [0, 5], open: true}'))
    assert 'no edge of the envelope is a wall: every one is `open: true`' in said(p, 'warn')
    assert p.internal == p.gross == 40.0
    assert 'every one is' not in said(plan(HALF)[0])


def test_a_curved_edge_may_be_open_too():
    p, _ = plan(HALF.replace('open: true, id: step', 'open: true, id: step, rise: 1.0'))
    assert p.hosts['step'].open and p.hosts['step'].arc['r'] == pytest.approx(R85)
    svg = solve.solves(HALF.replace('open: true, id: step', 'open: true, id: step, rise: 1.0')).sheet('g').svg()
    assert svg.count('class="edge"') == 1 and 'class="edge" fill="none"' in svg


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


def test_the_flight_between_two_half_levels_is_drawn_once_between_them():
    s = solve.solves(SPLIT)
    lower, upper = s.sheet('lower'), s.sheet('upper')
    below, above = lower.stairs[0], upper.stairs[0]
    whole = 1.6*0.9
    assert below['risers'] == above['risers'] == 7
    assert below['block'].area + above['block'].area == pytest.approx(whole, rel=0.03)
    assert below['block'].intersection(above['block']).area < 0.01
    assert above['label'][1] == 'DN' and below['label'][1] == 'UP'
    assert report.totals(s) == {'sheets': ['lower', 'upper'], 'gross': 80.0, 'internal': pytest.approx(2*7.4*4.7)}
    assert not [i for i in s.issues() if i[1] != 'info']
