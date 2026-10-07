# -*- coding: utf-8 -*-
"""What a solved house says of itself, and what is asked of it: the report,
the snapshot a house is held to and how two of them differ, what a sheet
has at a place, and what was drawn on a page laid out for reading."""
import copy
import json
import os
import pytest

from conftest import BOX, ROOM
from flawlessplan import cli, marks, query, report, solve
from flawlessplan.model import NOTE_GROUPS

NOTED = BOX + """    notes:
      summary: "Two rooms, {gross:.0f} m² in all."
      decided: ["LEFT is {LEFT_w:.2f} wide."]
      unconfirmed: ["The door may move."]
      needs: ["A survey of the east wall."]
      about: ["Inside the walls it is {internal:.1f} m²."]
"""


# ---- the report

def test_the_report_gives_every_sheet_as_measured():
    s = solve.solves(NOTED)
    rep = report.report(s, source='here.yaml')
    assert (rep['house'], rep['source'], rep['levels']) == ('<house>', 'here.yaml', ['ground'])
    assert rep['total'] == {'sheets': ['ground'], 'gross': 48.0, 'internal': 39.96}
    f, = rep['sheets']
    assert (f['id'], f['title'], f['level'], f['scheme'], f['changes']) == ('ground', 'GROUND FLOOR', 'ground', None, None)
    assert (f['gross'], f['internal']) == (48.0, 39.96) and 'gained' not in f
    assert f['rooms'] == [{'name': 'LEFT', 'w': 3.65, 'h': 5.4, 'area': 19.71, 'shape': 'rect'},
                          {'name': 'RIGHT', 'w': 3.65, 'h': 5.4, 'area': 19.71, 'shape': 'rect'}]
    assert f['openings'] == [{'kind': 'door', 'style': 'swing', 'wall': 'split', 'width': 0.842, 'centre': [4.0, 3.0]},
                             {'kind': 'window', 'style': 'window', 'wall': 'env.0', 'width': 1.2, 'centre': [2.0, 0.15]}]
    assert f['fittings'] == [] and f['zones'] == [] and f['issues'] == []
    json.dumps(rep)                                         # and all of it can be written as JSON


def test_notes_are_filled_from_the_geometry_and_keep_their_groups():
    s = solve.solves(NOTED)
    notes = report.report(s)['sheets'][0]['notes']
    assert notes == {'summary': 'Two rooms, 48 m² in all.', 'decided': ['LEFT is 3.65 wide.'],
                     'unconfirmed': ['The door may move.'], 'needs': ['A survey of the east wall.'],
                     'about': ['Inside the walls it is 40.0 m².']}
    info = s.sheet('ground').info
    assert [(k, head) for k, head, _ in info['groups']] == list(NOTE_GROUPS)        # in the order they are read
    assert info['figures'] == [('Gross external', '48.0 m²'), ('Inside the walls', '40.0 m²')]
    assert set(report.report(solve.solves(BOX))['sheets'][0]['notes']) == {'summary'}  # a group with nothing in it is left out


def test_the_notes_file_beside_an_image_says_the_same():
    md = report.info_md(solve.solves(NOTED).sheet('ground').info)
    assert md.startswith('# GROUND FLOOR\n\nTwo rooms, 48 m² in all.\n\nGross external: 48.0 m²  \nInside the walls: 40.0 m²  \n')
    assert '| LEFT | 3.65 × 5.40 m | 19.7 m² |  |' in md
    for head, line in (('## Decided', '- LEFT is 3.65 wide.'), ('## Not confirmed', '- The door may move.'),
                       ('## Needs', '- A survey of the east wall.'), ('## About this drawing', '- Inside the walls it is 40.0 m².')):
        assert '%s\n\n%s\n' % (head, line) in md
    bare = report.info_md(solve.solves(ROOM.replace("    rooms:\n      - {name: ROOM, at: [1, 1]}\n", '    unlabelled: ok\n')).sheet('ground').info)
    assert '| Room |' not in bare and '##' not in bare


def test_a_room_that_is_not_a_rectangle_says_what_its_size_means():
    ell = "sheets:\n  - id: g\n    envelope: [[0, 0], [8, 0], [8, 3], [4, 3], [4, 7], [0, 7]]\n    rooms: [{name: ELL, at: [2, 2]}]\n"
    s = solve.solves(ell)
    assert report.report(s)['sheets'][0]['rooms'] == [{'name': 'ELL', 'w': 7.4, 'h': 6.4, 'area': 31.36, 'shape': 'irregular'}]
    assert '| ELL | 7.40 × 6.40 m | 31.4 m² | overall |' in report.info_md(s.sheet('g').info)


def test_issues_come_worst_first_and_a_room_with_an_id_carries_it():
    text = BOX.replace("to: [MID, D]", "to: [MID, D/2]").replace('name: RIGHT', 'name: RIGHT, id: east, expect: {w: 1}')
    f = report.facts(solve.solves(text).sheet('ground').plan)
    assert [i['level'] for i in f['issues']] == sorted([i['level'] for i in f['issues']], key=report.LEVELS.get)
    assert {i['level'] for i in f['issues']} == {'error', 'warn', 'info'}
    assert f['rooms'][1]['id'] == 'east' and 'id' not in f['rooms'][0]


def test_the_total_is_the_house_as_it_stands_and_not_what_is_proposed():
    two = BOX + "  - {id: first, envelope: [[0, 0], [W, 0], [W, D], [0, D]], unlabelled: ok}\n"
    option = two + "  - {id: bigger, level: first, changes: first, envelope: [[0, 0], [W + 2, 0], [W + 2, D], [0, D]], unlabelled: ok}\n"
    assert report.totals(solve.solves(two)) == {'sheets': ['ground', 'first'], 'gross': 96.0, 'internal': 79.92}
    s = solve.solves(option)
    assert report.totals(s)['sheets'] == ['ground', 'first'] and report.totals(s)['gross'] == 96.0
    f = report.report(s)['sheets'][2]
    assert (f['changes'], f['gained'], f['level']) == ('first', 12.0, 'first')
    rival = two + "  - {id: other, level: first, envelope: [[0, 0], [W, 0], [W, D], [0, D]], unlabelled: ok}\n"
    assert report.totals(solve.solves(rival)) is None and 'total' not in report.report(solve.solves(rival))   # two as-builts of one level
    missing = "levels: [ground, first]\n" + BOX
    assert report.totals(solve.solves(missing)) is None


# ---- the snapshot, and how two differ

def test_a_snapshot_is_the_geometry_and_leaves_out_what_may_be_reworded():
    snap = report.snapshot(solve.solves(NOTED.replace("to: [MID, D]", "to: [MID, 5.5]")))
    g = snap['sheets']['ground']
    assert sorted(g) == ['gross', 'internal', 'issues', 'openings', 'rooms', 'zones']
    assert g['issues'] == [{'level': 'error', 'message': 'sheets.ground.rooms[1]: RIGHT and LEFT are the same space — a wall is missing or open'},
                           {'level': 'warn', 'message': 'wall split has LEFT on both its faces — it stands inside one room, '
                                                        'and the door in it leads from that room into itself'}]
    assert 'ends in the open' not in json.dumps(snap) and 'notes' not in json.dumps(snap)    # info, and words, may change freely
    assert json.loads(json.dumps(snap)) == snap                                              # as the tests compare it


def test_the_outline_sheet_is_not_part_of_a_snapshot_or_a_report():
    s = solve.solves(BOX + "  - {id: first, envelope: [[0, 0], [W, 0], [W, D], [0, D]], unlabelled: ok}\n")
    assert [x.id for x in s.sheets] == ['outline', 'ground', 'first']
    assert list(report.snapshot(s)['sheets']) == ['ground', 'first'] and [f['id'] for f in report.report(s)['sheets']] == ['ground', 'first']


SNAP = report.snapshot(solve.solves(BOX))


def changed(path, value):
    """SNAP with one thing in it set to something else."""
    out = copy.deepcopy(SNAP)
    at = out
    for k in path[:-1]:
        at = at[k]
    at[path[-1]] = value
    return json.loads(json.dumps(out))


def test_a_snapshot_agrees_with_itself():
    assert report.differences(SNAP, json.loads(json.dumps(SNAP))) == []
    assert report.differences({}, {}) == [] and report.differences([], []) == []


@pytest.mark.parametrize('path, value, said', [
    (('sheets', 'ground', 'gross'), 48.04, None),                       # areas are held to 0.05 m²
    (('sheets', 'ground', 'gross'), 48.06, 'sheets.ground.gross: 48.0 expected, 48.06 found'),
    (('sheets', 'ground', 'internal'), 39.9, 'sheets.ground.internal: 39.96 expected, 39.9 found'),
    (('sheets', 'ground', 'rooms', 0, 'area'), 19.75, None),
    (('sheets', 'ground', 'rooms', 0, 'area'), 19.8, 'sheets.ground.rooms[0].area: 19.71 expected, 19.8 found'),
    (('sheets', 'ground', 'rooms', 0, 'w'), 3.652, None),               # and every length to 2 mm
    (('sheets', 'ground', 'rooms', 0, 'w'), 3.653, 'sheets.ground.rooms[0].w: 3.65 expected, 3.653 found'),
    (('sheets', 'ground', 'rooms', 0, 'h'), 5.39, 'sheets.ground.rooms[0].h: 5.4 expected, 5.39 found'),
    (('sheets', 'ground', 'rooms', 0, 'name'), 'SITTING', "sheets.ground.rooms[0].name: 'LEFT' expected, 'SITTING' found"),
    (('sheets', 'ground', 'rooms', 0, 'shape'), 'near', "sheets.ground.rooms[0].shape: 'rect' expected, 'near' found"),
    (('sheets', 'ground', 'openings', 0, 'centre'), [4.0, 3.002], None),
    (('sheets', 'ground', 'openings', 0, 'centre'), [4.0, 3.1], 'sheets.ground.openings[0].centre[1]: 3.0 expected, 3.1 found'),
    (('sheets', 'ground', 'openings', 0, 'width'), 0.9, 'sheets.ground.openings[0].width: 0.842 expected, 0.9 found'),
    (('sheets', 'ground', 'openings', 0, 'wall'), 'env.1', "sheets.ground.openings[0].wall: 'split' expected, 'env.1' found"),
    (('sheets', 'ground', 'openings', 0, 'kind'), 'window', "sheets.ground.openings[0].kind: 'door' expected, 'window' found"),
    (('sheets', 'ground', 'rooms'), SNAP['sheets']['ground']['rooms'][:1], 'sheets.ground.rooms: 2 expected, 1 found'),
    (('sheets', 'ground', 'openings'), [], 'sheets.ground.openings: 2 expected, 0 found'),
    (('sheets', 'ground', 'issues'), [{'level': 'error', 'message': 'x'}], 'sheets.ground.issues: 0 expected, 1 found'),
    (('sheets', 'ground', 'zones'), [{'name': 'Z', 'rooms': ['LEFT'], 'area': 1.0}], 'sheets.ground.zones: 0 expected, 1 found'),
    (('house',), 'Another', "house: '<house>' expected, 'Another' found"),
    (('sheets', 'ground', 'gross'), '48.0', "sheets.ground.gross: 48.0 expected, '48.0' found"),
    (('sheets', 'ground', 'gross'), None, 'sheets.ground.gross: 48.0 expected, None found'),
    (('sheets', 'ground', 'rooms'), {}, "sheets.ground.rooms: "),
])
def test_what_moved_is_said_by_where_it_is(path, value, said):
    got = report.differences(json.loads(json.dumps(SNAP)), changed(path, value))
    if said is None:
        assert got == []
    else:
        assert len(got) == 1 and got[0].startswith(said), got


def test_a_sheet_or_a_figure_that_came_or_went_is_said():
    more = copy.deepcopy(SNAP)
    more['sheets']['first'] = more['sheets']['ground']
    assert report.differences(SNAP, more) == ['sheets.first: not expected']
    assert report.differences(more, SNAP) == ['sheets.first: missing']
    less = changed(('sheets', 'ground', 'rooms', 0), {'name': 'LEFT', 'w': 3.65, 'h': 5.4, 'area': 19.71})
    assert report.differences(json.loads(json.dumps(SNAP)), less) == ['sheets.ground.rooms[0].shape: missing']


def test_true_and_one_are_not_the_same_figure():
    assert report.differences({'a': True}, {'a': 0}) == ['a: True expected, 0 found']
    assert report.differences({'a': 1}, {'a': 1.0}) == [] and report.differences({'a': 1}, {'a': 1.01}) == ['a: 1 expected, 1.01 found']


def test_state_is_a_snapshot_with_what_no_figure_comes_of():
    text = BOX + "    stairs: [{id: main, path: [[6, 1], [6, 4]], treads: [12]}]\n    labels: [{at: [2, 5], text: hi}]\n    notes: [One note.]\n"
    st = report.state(solve.solves(text))['sheets']['ground']
    assert set(report.UNMEASURED) <= set(st) and st['title'] == 'GROUND FLOOR'
    assert st['stairs'][0]['path'] == [[6.0, 1.0], [6.0, 4.0]] and st['notes']['about'] == ['One note.']
    assert st['labels'] == [{'at': [2.0, 5.0], 'text': 'hi', 'rot': None, 'style': 'note'}]
    moved = report.state(solve.solves(text.replace('[6, 4]', '[6, 3.7]')))
    assert report.differences(report.state(solve.solves(text)), moved) == ['sheets.ground.stairs[0].path[1][1]: 4.0 expected, 3.7 found']


def test_each_example_matches_the_snapshot_it_ships_with(ws):
    for name in ws.names():
        assert cli.drift(ws.house(name)) == []
        want = json.load(open(os.path.join(ws.house(name), 'expected.json')))
        assert want == json.loads(json.dumps(report.snapshot(solve.solve(ws.house(name))))), name    # to the last digit, as written


# ---- what a sheet has at a place

SHEET = solve.solves(BOX + "    stairs: [{id: main, path: [[6, 5.2], [6, 2.2]], treads: [12]}]\n"
                           "    solids: [{rect: [[0.3, 4.7], [1.3, 5.7]]}]\n"
                           "    areas: [{rect: [[8, 0], [10, 6]], style: outdoor, label: PATIO}, {rect: [[8, 6], [9, 7]], style: outdoor}]\n").sheet('ground')


def at(*where, **kw):
    return query.lines(query.at(SHEET, where, **kw))


def test_a_point_is_answered_nearest_first_in_the_house_files_names():
    got = at(1.0, 1.0)
    assert got == ['room LEFT (3.65 × 5.40 m, 18.7 m²) — sheets.ground.rooms[0]']       # less the solid in its corner
    got = at(3.9, 3.0)
    assert got[0].startswith('room LEFT') and got[1] == '0.05 m — door 0.84 m wide in wall split, centre (4.00, 3.00) — sheets.ground.openings[0]'
    assert got[2] == '0.05 m — partition split, 100 mm, (4.00, 0.00) to (4.00, 6.00)'
    dist = [d for d, _ in query.at(SHEET, (2.0, 0.5))]
    assert dist == sorted(dist) and dist[0] == 0.0
    assert at(2.0, 0.5)[1:] == ['0.20 m — window 1.20 m wide in wall env.0, centre (2.00, 0.15) — sheets.ground.openings[1]',
                                '0.20 m — outside wall env.0, 300 mm, face (0.00, 0.00) to (8.00, 0.00)']


def test_a_radius_takes_in_more_and_a_box_what_it_covers():
    assert len(at(1.0, 1.0, reach=0.1)) == 1 and len(at(1.0, 1.0, reach=10)) > 8
    assert at(1.0, 1.0, reach=0.71)[1].startswith('0.70 m — outside wall')
    box = at(3.0, 2.0, 5.0, 4.0)
    assert [t.split(' ')[0] for t in box] == ['room', 'room', 'door', 'partition'] and not any(' m — ' in t for t in box)
    assert [t.split(' ')[0] for t in at(0.0, 0.0, 8.0, 6.0)] == ['room', 'room', 'door', 'window', 'partition'] + ['outside']*4 + ['solid', 'stair', 'area']


def test_everything_drawn_can_be_found():
    assert 'stair main (13 risers; treads per leg [12])' in at(6.0, 4.0)
    assert any(t.startswith('solid masonry (solids[0]) round (0.80, 5.20), 1.00 m²') for t in at(0.8, 5.2))
    assert at(9.0, 3.0) == ['area "PATIO" (outdoor)', 'outside the building']
    assert at(8.9, 6.9) == ['outside the building']                     # an area with no name is not something to point at
    assert at(50.0, 50.0) == ['outside the building'] and at(-9.0, -9.0, -8.0, -8.0) == ['outside the building']


def test_nothing_there_is_said_so():
    assert query.lines([]) == ['nothing drawn there']
    assert query.lines([(0.0, 'a'), (0.004, 'b'), (0.25, 'c')]) == ['a', 'b', '0.25 m — c']


def test_a_room_with_an_id_and_an_opening_that_is_not_a_door_say_so():
    text = BOX.replace('name: LEFT', 'name: LEFT, id: sitting').replace("- {door: std, wall: split, at: centre, swing: e}", "- {opening: 1.5, wall: split}\n      - {door: std, wall: env.2, style: slide}")
    sh = solve.solves(text).sheet('ground')
    assert query.lines(query.at(sh, (1, 1)))[0].startswith('room LEFT [sitting] (')
    assert any(t.startswith('opening (none) 1.50 m wide in wall split') for t in query.lines(query.at(sh, (4, 3))))
    assert any(t.startswith('door (slide) 0.84 m wide in wall env.2') for t in query.lines(query.at(sh, (4, 5.9))))


# ---- what was drawn on a page

def test_strokes_are_numbered_in_the_order_drawn_sheet_by_sheet():
    drawn = [{'type': 'pen', 'sheet': 'first', 'ts': 5000, 'pts': [[1, 1], [2, 2]]},
             {'type': 'note', 'sheet': 'ground', 'ts': 4000, 'x': 3, 'y': 3, 'text': 'second'},
             {'type': 'pen', 'ts': 1000, 'pts': [[0, 0], [1, 0], [1, 1]]},            # no sheet: the first
             {'type': 'pen', 'sheet': 'first', 'ts': 9000, 'pts': [[5, 5], [6, 6]]}]
    S = marks.strokes(drawn, 'ground')
    assert [(s['sheet'], s['n'], s['ts']) for s in S] == [('ground', 1, 1000), ('ground', 2, 4000), ('first', 1, 5000), ('first', 2, 9000)]
    assert S[0]['pts'] == [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)] and S[0]['text'] is None and S[0]['geom'].length == 2.0
    assert S[1]['pts'] == [(3.0, 3.0)] and S[1]['text'] == 'second'
    assert marks.strokes([], 'ground') == []


@pytest.mark.parametrize('junk', [
    7, None, 'words', [], [1, 2], True, {}, {'type': 'pen'}, {'type': 'pen', 'pts': []}, {'type': 'pen', 'pts': [[1, 1]]},
    {'type': 'pen', 'pts': 'abc'}, {'type': 'pen', 'pts': [[1, 1], [2]]}, {'type': 'pen', 'pts': [[1, 1], ['a', 'b']]},
    {'type': 'pen', 'pts': [[1, 1], None]}, {'type': 'pen', 'pts': [[1, 1], [float('nan'), 2]]}, {'type': 'pen', 'pts': {'a': 1}},
    {'type': 'pen', 'pts': [[1, 1], [2, 2]], 'sheet': ['ground']}, {'type': 'pen', 'pts': [[1, 1], [2, 2]], 'sheet': 5},
    {'type': 'note'}, {'type': 'note', 'x': 1}, {'type': 'note', 'x': 'a', 'y': 'b', 'text': 'hi'}, {'type': 'note', 'x': None, 'y': 2},
    {'type': 'note', 'x': float('inf'), 'y': 2}, {'type': 'circle', 'x': 1, 'y': 1}, {'type': ['pen']}, {'pts': [[1, 1], [2, 2]]},
])
def test_what_is_not_a_mark_is_passed_over(junk):
    """marks.json is written by a page in a browser, and saved as it came."""
    good = {'type': 'note', 'sheet': 'ground', 'ts': 2, 'x': 1, 'y': 1, 'text': 'kept'}
    S = marks.strokes([junk, good, junk], 'ground')
    assert [(s['n'], s['text']) for s in S] == [(1, 'kept')]


@pytest.mark.parametrize('ts', ['soon', None, [1], {'a': 1}, float('nan'), True])
def test_a_mark_with_no_time_is_kept_and_put_first(ts):
    S = marks.strokes([{'type': 'note', 'ts': 5, 'x': 1, 'y': 1, 'text': 'timed'},
                       {'type': 'note', 'ts': ts, 'x': 2, 'y': 2, 'text': 'untimed'}], 'g')
    assert [(s['text'], s['ts']) for s in S] == [('untimed', 0), ('timed', 5)]


def test_marks_that_are_not_a_list_are_no_marks():
    for junk in ({}, 'words', 7, None, {'type': 'note', 'x': 1, 'y': 1}):
        assert marks.strokes(junk, 'g') == []


def test_a_note_keeps_what_was_written_as_text():
    S = marks.strokes([{'type': 'note', 'x': 1, 'y': 1, 'text': 12}, {'type': 'note', 'x': 1, 'y': 1},
                       {'type': 'note', 'x': 1, 'y': 1, 'text': '<b>bold</b>'}], 'g')
    assert [s['text'] for s in S] == ['12', None, '<b>bold</b>']


def test_ink_that_lies_together_shares_a_picture():
    S = marks.strokes([{'type': 'pen', 'sheet': 'g', 'ts': 1, 'pts': [[0, 0], [1, 0]]},
                       {'type': 'pen', 'sheet': 'g', 'ts': 2, 'pts': [[1.5, 0], [1.5, 1]]},          # half a metre off: the same view
                       {'type': 'pen', 'sheet': 'g', 'ts': 3, 'pts': [[6, 6], [7, 7]]},
                       {'type': 'pen', 'sheet': 'h', 'ts': 4, 'pts': [[0, 0], [1, 0]]},              # another sheet: never
                       {'type': 'note', 'sheet': 'g', 'ts': 5, 'x': 3.2, 'y': 0.5, 'text': 'joins the first two to nothing else'}], 'g')
    got = sorted(sorted((s['sheet'], s['n']) for s in f) for f in marks.frames(S))
    assert got == [[('g', 1), ('g', 2)], [('g', 3)], [('g', 4)], [('h', 1)]]
    bridge = marks.strokes([{'type': 'pen', 'ts': 1, 'pts': [[0, 0], [1, 0]]}, {'type': 'pen', 'ts': 2, 'pts': [[3, 0], [4, 0]]},
                            {'type': 'pen', 'ts': 3, 'pts': [[1.5, 0], [2.5, 0]]}], 'g')
    assert [len(f) for f in marks.frames(bridge)] == [3]                # a third stroke between two joins all three


def test_the_ink_is_drawn_in_its_own_colour_and_text_is_escaped():
    S = marks.strokes([{'type': 'pen', 'ts': 1, 'pts': [[1, 1], [2, 2]]},
                       {'type': 'note', 'ts': 2, 'x': 3, 'y': 3, 'text': '</text><script>alert(1)</script>'}], 'g')
    svg = '\n'.join(marks.ink(S, 4.0))
    assert svg.count('<polyline') == 1 and svg.count(marks.INK) == 2 and svg.count(marks.NOTE) == 5
    assert '<script>' not in svg and '&lt;/text&gt;&lt;script&gt;alert(1)&lt;/script&gt;' in svg
    assert marks.INK not in ''.join(SHEET.lines) and marks.NOTE not in ''.join(SHEET.lines)      # no drawing uses either


@pytest.mark.parametrize('side, tick', [(0.5, 0.1), (1.2, 0.1), (2.0, 0.2), (3.0, 0.25), (6.0, 0.5), (12.0, 1.0), (20.0, 2.0), (60.0, 5.0)])
def test_ticks_are_spaced_to_be_read(side, tick):
    assert marks._step(side) == tick and 4 <= side/tick <= 12


def test_the_brief_says_when_the_house_has_changed_since_the_ink(tmp_path):
    s = solve.solves(BOX)
    drawn = [{'type': 'pen', 'sheet': 'ground', 'ts': 1000000, 'pts': [[2, 2], [2.5, 2.5], [3, 2]]},
             {'type': 'pen', 'sheet': 'ground', 'ts': 1003000, 'pts': [[3, 2], [2.8, 2.3]]},
             {'type': 'note', 'sheet': 'attic', 'ts': 1005000, 'x': 1, 'y': 1, 'text': 'on a sheet that is gone'}]
    out = str(tmp_path / 'marks')
    os.makedirs(out)
    open(os.path.join(out, 'stale.png'), 'w').write('old')
    text = marks.brief(s.house, s.sheets, drawn, out, cli.rasterise, changed=2000.0)
    assert '# Marks on <house>' in text and '**The house file has been edited since the last of these marks was drawn.**' in text
    assert '- **1** `mlfls` stroke, 1.41 m of ink' in text and ', 3 s after stroke 1' in text and 'nearest other ink: stroke 1, 0.00 m away' in text
    assert 'attic' not in text and 'gone' not in text                   # ink on a sheet the house no longer has is left out
    assert sorted(os.listdir(out)) == ['brief.md', 'ground-1.png', 'ground-1.svg', 'ground-sheet.png', 'ground-sheet.svg']
    assert 'edited since' not in marks.brief(s.house, s.sheets, drawn, out, cli.rasterise, changed=10.0)
    assert 'edited since' not in marks.brief(s.house, s.sheets, drawn, out, cli.rasterise)


def test_a_marks_file_that_is_not_json_is_said_and_one_that_is_not_a_list_is_empty(ws, capsys):
    open(ws.marks('cottage'), 'w').write('{not json')
    assert cli.main(['-w', ws.root, 'marks', 'cottage']) == 1
    err = capsys.readouterr().err
    assert 'marks.json is not JSON that can be read' in err and 'Traceback' not in err
    open(ws.marks('cottage'), 'w').write('{"type": "note"}')
    assert cli.main(['-w', ws.root, 'marks', 'cottage']) == 0 and 'nothing drawn yet' in capsys.readouterr().out
    json.dump([7, None, 'words', {'type': 'pen', 'pts': 'x'}], open(ws.marks('cottage'), 'w'))
    assert cli.main(['-w', ws.root, 'marks', 'cottage']) == 0 and 'Traceback' not in capsys.readouterr().err


# ---- a mark's life: open, resolved, and gone only when the owner says

LIFE = [{'type': 'pen', 'sheet': 'ground', 'ts': 1759800000000, 'pts': [[2, 2], [2.5, 2.5], [3, 2]]},
        {'type': 'note', 'sheet': 'ground', 'ts': 1759800005000, 'id': 'wider', 'x': 4, 'y': 3, 'text': 'make this wider'},
        {'type': 'pen', 'sheet': 'ground', 'ts': 1759800009000, 'pts': [[5, 4], [6, 5]]}]


def test_a_mark_is_known_by_its_id_or_by_its_time_as_the_page_writes_it():
    assert [marks.ident(m) for m in LIFE] == ['mmgfvhedc', 'wider', 'mmgfvhlbc']         # (1759800000000).toString(36)
    for odd in ({}, {'ts': 'soon'}, {'ts': None}, {'id': 7}, {'id': ''}, {'id': 'a b'}, {'id': 'x'*41}, {'id': '../x'}):
        assert marks.ident(odd) == 'm0'
    assert marks.ident({'ts': -36}) == 'm10' and marks.ident({'ts': 35.9, 'id': 'ok-1_'}) == 'ok-1_'


def test_marks_are_resolved_all_or_none_and_say_how(tmp_path):
    path = str(tmp_path / 'marks.json')
    json.dump(LIFE, open(path, 'w'))
    for ids, note, sheets, why in ((['wider', 'nope'], 'done', None, "no mark called 'nope' \\(have mmgfvhedc, mmgfvhlbc, wider\\)"),
                                   (['wider'], '  ', None, 'say in a line how'), ([], 'done', None, 'name the marks by id'),
                                   (['wider'], 'done', ['attic'], "no sheet called 'attic' \\(have ground, first\\)")):
        with pytest.raises(ValueError, match=why):
            marks.resolve(path, ids, note, sheets, ['ground', 'first'])
        assert json.load(open(path)) == LIFE
    said = marks.resolve(path, ['wider', 'mmgfvhedc'], ' Living room\n widened ', ['ground', 'first'], ['ground', 'first'])
    assert said == ['wider: resolved, applied to ground, first', 'mmgfvhedc: resolved, applied to ground, first']
    got = json.load(open(path))
    assert [(m.get('id'), m.get('status'), m.get('how'), m.get('applied')) for m in got] == [
        ('mmgfvhedc', 'resolved', 'Living room widened', ['ground', 'first']),
        ('wider', 'resolved', 'Living room widened', ['ground', 'first']), (None, None, None, None)]
    assert got[0]['resolved'] > 1759800000000 and got[0]['pts'] == LIFE[0]['pts'] and got[2] == LIFE[2]
    assert marks.resolve(path, 'wider', 'again', known=['ground']) == ['wider: resolved (it was already; now as this says)']
    assert 'applied' not in json.load(open(path))[1]
    assert marks.resolve(path, ['wider', 'mmgfvhlbc'], '', reopen=True) == ['wider: opened again', 'mmgfvhlbc: was open already']
    assert [set(m) & set(marks.LIFE) for m in json.load(open(path))][1:] == [set(), set()]
    assert os.listdir(str(tmp_path)) == ['marks.json']
    with pytest.raises(ValueError, match='no mark called'):                         # no file is no marks
        marks.resolve(str(tmp_path / 'none.json'), ['wider'], 'done')


def test_only_open_marks_are_laid_out_unless_the_resolved_are_asked_for(tmp_path):
    s = solve.solves(BOX)
    drawn = [dict(LIFE[0], status='resolved', resolved=1759800100000, how='moved the <door>', applied=['ground', 7]),
             LIFE[1], dict(LIFE[2], status='done')]                                 # a status that is not one is open
    assert [(m['id'], m['n'], m['done']) for m in marks.strokes(drawn, 'ground')] == [('wider', 1, False), ('mmgfvhlbc', 2, False)]
    S = marks.strokes(drawn, 'ground', done=True)
    assert [(m['id'], m['n'], m['done'], m['how'], m['applied']) for m in S][0] == ('mmgfvhedc', 1, True, 'moved the <door>', ['ground'])
    out = str(tmp_path / 'marks')
    text = marks.brief(s.house, s.sheets, drawn, out, cli.rasterise)
    assert '1 mark already resolved is left out' in text and 'mmgfvhedc' not in text and '- **1** `wider` written' in text
    assert marks.DONE not in open(os.path.join(out, 'ground-sheet.svg')).read()
    text = marks.brief(s.house, s.sheets, drawn, out, cli.rasterise, done=True)
    assert 'left out' not in text and '- **1** `mmgfvhedc` stroke' in text and '- **2** `wider` written' in text
    assert '  resolved 2025-10-07 ' in text and ': moved the <door> — applied to `ground`' in text
    assert open(os.path.join(out, 'ground-sheet.svg')).read().count(marks.DONE) == 1
    assert marks.brief(s.house, s.sheets, [drawn[0]], out, cli.rasterise) == '' and os.listdir(out) == []
    with pytest.raises(ValueError, match="no sheet called 'attic'"):
        marks.brief(s.house, s.sheets, drawn, out, cli.rasterise, sheet='attic')
    assert 'edited since' not in marks.brief(s.house, s.sheets, [drawn[0]], out, cli.rasterise, changed=2e9, done=True)


def test_a_page_cannot_open_again_what_was_resolved_while_it_looked():
    stored = [dict(LIFE[0], id='mmgfvhedc', status='resolved', resolved=5, how='done', applied=['ground']), LIFE[1]]
    sent = [LIFE[0], dict(LIFE[1], status='resolved', how='says the page'), LIFE[2], 7, None, {'ts': 1759800000000}]
    kept = marks.keep(stored, sent)
    assert kept[0] == dict(LIFE[0], status='resolved', resolved=5, how='done', applied=['ground'])
    assert kept[1:] == sent[1:]                                 # and nothing else is touched, a mark left out is gone
    assert marks.keep(stored, []) == [] and marks.keep([7, None, 'x'], sent) == sent
    assert marks.state(stored) == marks.state(kept[:1]) != marks.state(sent[2:]) == marks.state([]) == marks.state([7, {}])
