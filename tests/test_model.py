# -*- coding: utf-8 -*-
"""Reading a house file: what each part of it comes out as, and what is
said of one that is wrong — where in the file, and in what words."""
import pytest

from conftest import BOX, ROOM
from flawlessplan import model, solve
from flawlessplan.model import ConfigError


def sheet(extra='', text=ROOM):
    return model.loads(text + extra)['sheets'][0]


# ---- what a file must have, and how it is laid out

@pytest.mark.parametrize('text, why', [
    ('', 'a mapping at the top level'),
    ('[1, 2]', 'a mapping at the top level'),
    ('just words', 'a mapping at the top level'),
    ('5', 'a mapping at the top level'),
    ('survey: {W: 1}', 'no sheets'),
    ('sheets: []', 'no sheets'),
    ('sheets: [{envelope: [[0, 0], [1, 0], [1, 1]]}]', "missing 'id'"),
    ('sheets: [{id: g}]', "sheets.g: missing 'envelope'"),
    ('sheets: [5]', 'each a mapping with an `id`'),
    ('sheets: [null]', 'each a mapping with an `id`'),
    ('sheets: 5', 'each a mapping with an `id`'),
    ('sheets: ground', 'each a mapping with an `id`'),
    ('sheets: [{id: g, envelope: [[0, 0], [1, 1]]}]', 'at least three points'),
    ('sheets: [{id: g, envelope: {t: 0.2}}]', "sheets.g.envelope: missing 'points'"),
    ('sheets: [{id: g, envelope: square}]', 'sheets.g'),
    ('sheets: [{id: g, envelope: 5}]', 'sheets.g'),
    ('sheets: [{id: g, envelope: [a, b, c]}]', 'sheets.g.envelope[0]'),
    ('sheets: [{id: g, envelope: [[0, 0, 1, 1], [1, 0], [1, 1]]}]', 'expected a point'),
    ('a: [', 'not YAML that can be read'),
    ('survey:\n\tW: 1', 'not YAML that can be read'),
    ('a: b: c', 'not YAML that can be read'),
    ('!!python/object/apply:os.system ["true"]', 'not YAML that can be read'),
    ('a: &x [*x]\nsheets: 5', 'too much to be a house file'),            # a list that holds itself
])
def test_a_file_that_is_not_a_house_says_so(text, why):
    with pytest.raises(ConfigError) as e:
        model.loads(text, 'the.yaml')
    assert why in str(e.value)


def test_the_error_names_the_file_it_was_read_from(tmp_path):
    path = tmp_path / 'house.yaml'
    path.write_text('a: [')
    with pytest.raises(ConfigError, match='house.yaml: not YAML'):
        model.load(str(path))
    path.write_text('- not\n- a house\n')
    with pytest.raises(ConfigError, match='house.yaml: a house file is a mapping'):
        model.load(str(path))


@pytest.mark.parametrize('old, why', [
    ('floors', 'is now `sheets:`'), ('shell', 'is now `outline:`'),
])
def test_a_key_that_was_renamed_says_what_it_is_now(old, why):
    with pytest.raises(ConfigError, match=why):
        model.loads(BOX + '%s: {}\n' % old)


# ---- the names: survey, lines, defaults

def test_survey_and_lines_become_names_with_where_each_came_from():
    h = model.loads("""
survey:
  W: 8.0
  D: {value: 6.0, status: assumed}
  bay: 4'6"
  deep: {value: 10', status: traced}
lines: {MID: W/2, HW: IW/2}
sheets: [{id: g, envelope: [[0, 0], [W, 0], [W, D], [0, D]]}]
""")
    n = h['names']
    assert (n['W'], n['D'], n['MID'], n['HW']) == (8.0, 6.0, 4.0, 0.05)
    assert n['bay'] == pytest.approx(1.3716) and n['deep'] == pytest.approx(3.048)
    assert (n['EW'], n['IW']) == (0.30, 0.10)                       # the thicknesses, by the names lines step off
    assert h['status'] == {'W': 'given', 'D': 'assumed', 'bay': 'given', 'deep': 'traced', 'MID': 'derived', 'HW': 'derived'}
    assert h['written'] == {'bay': '4\'6"', 'deep': "10'"}          # a figure in feet is kept as it was given


@pytest.mark.parametrize('head, why', [
    ('survey: {W: 8, W2: nope}', "survey.W2: unknown name 'nope'"),
    ('survey: {W: {status: given}}', "survey.W: missing 'value'"),
    ('survey: {W: 1/0}', 'survey.W'),
    ('survey: {W: .nan}', 'survey.W'),
    ('survey: {W: .inf}', 'survey.W'),
    ('survey: {W: -.inf}', 'survey.W'),
    ('survey: {W: [1, 2]}', 'survey.W: expected a number'),
    ('survey: {W: true}', 'survey.W: expected a number'),
    ('survey: {W: null}', 'survey.W: expected a number'),
    ('survey: {W: 8}\nlines: {W: 9}', 'lines.W: the name is already defined'),
    ('survey: {EW: 8}', 'survey.EW: the name is already defined'),
    ('lines: {IW: 8}', 'lines.IW: the name is already defined'),
    ('lines: {A: B + 1, B: 2}', "lines.A: unknown name 'B'"),            # a line steps off what is above it
    ('lines: {A: B + 1, B: A + 1}', "lines.A: unknown name 'B'"),
    ('lines: {A: A + 1}', "lines.A: unknown name 'A'"),
    ('lines: {A: min()}', 'lines.A'),
    ('lines: {A: "9**9**9"}', 'lines.A: power out of range'),
    ('survey: [8, 6]', 'not laid out as a house file'),
    ('survey: nope', 'not laid out as a house file'),
    ('lines: [1]', 'not laid out as a house file'),
    ('defaults: {wall: 0.2}', "defaults: unknown key 'wall'"),
    ('defaults: [1]', 'not laid out as a house file'),
    ('defaults: {ext_wall: thick}', 'not laid out as a house file'),
    ('house: [1]', 'not laid out as a house file'),
    ('house: {front: up}', 'house.front: use one of north, east, south, west'),
    ('parts: [1]', None),
    ('levels: [attic]', 'no level called'),
    ('outline: [1]', 'outline: a mapping'),
    ('outline: {sheets: [nope]}', 'outline.sheets: list sheets by their id (have g)'),
    ('outline: {sheets: g}', 'outline.sheets: list sheets by their id'),
])
def test_a_name_that_cannot_be_worked_out_says_which(head, why):
    text = head + '\nsheets: [{id: g, envelope: [[0, 0], [4, 0], [4, 4], [0, 4]]}]\n'
    if why is None:
        model.loads(text)                           # nothing uses a part: nothing to say
        return
    with pytest.raises(ConfigError) as e:
        model.loads(text)
    assert why in str(e.value)


def test_defaults_change_the_thicknesses_and_the_leaves():
    h = model.loads('defaults: {ext_wall: 0.25, int_wall: 0.075, leaves: {std: 726}, frame: 60, going: 0.25}\n' + ROOM
                    + '    openings: [{door: std, wall: north}, {door: std, wall: south, pair: true}]\n'
                    + '    stairs: [{path: [[2, 2], [2, 4]]}]\n')
    fl = h['sheets'][0]
    assert (h['names']['EW'], h['names']['IW']) == (0.25, 0.075)
    assert fl['envelope']['t'] == [0.25]*4
    assert [o['width'] for o in fl['openings']] == [pytest.approx(0.786), pytest.approx(2*0.726 + 0.06 + 0.01)]
    assert fl['stairs'][0]['going'] == 0.25
    with pytest.raises(ConfigError, match='unknown door leaf'):
        model.loads('defaults: {leaves: {std: 726}}\nlines: {A: op("wide")}\n' + ROOM)


@pytest.mark.parametrize('leaf, mm', [('cloak', 686), ('std', 762), ('wide', 838)])
def test_a_leaf_name_is_its_width_and_a_frame(leaf, mm):
    fl = sheet('    openings: [{door: %s, wall: north}, {door: %s, wall: south, pair: true}]\n' % (leaf, leaf))
    single, pair = fl['openings']
    assert single['width'] == pytest.approx((mm + 80)/1000.0) and single['leaf'] == leaf and not single['pair']
    assert pair['width'] == pytest.approx((2*mm + 80 + 10)/1000.0) and pair['pair']
    assert model.loads('lines: {A: "op(\'%s\')", B: "op(\'%s\', pair=True)"}\n' % (leaf, leaf) + ROOM)['names']['B'] == pair['width']


# ---- sheets, levels, what a sheet changes

def test_a_sheet_has_a_title_a_tab_and_a_level_of_its_own_by_default():
    h = model.loads("""
levels: [ground, first]
sheets:
  - {id: ground, envelope: [[0, 0], [4, 0], [4, 4], [0, 4]]}
  - {id: first, envelope: [[0, 0], [4, 0], [4, 4], [0, 4]], title: UPSTAIRS, tab: Up}
  - {id: loft-option, level: first, scheme: B, changes: first, demolition: false, envelope: [[0, 0], [4, 0], [4, 4], [0, 4]]}
""")
    g, f, o = h['sheets']
    assert (g['title'], g['tab'], g['level'], g['scheme'], g['changes'], g['demolition']) == \
        ('GROUND FLOOR', 'Ground', 'ground', None, None, True)
    assert (f['title'], f['tab']) == ('UPSTAIRS', 'Up')
    assert (o['title'], o['tab'], o['level'], o['scheme'], o['changes'], o['demolition']) == \
        ('LOFT OPTION', 'Loft Option', 'first', 'B', 'first', False)
    assert h['levels'] == ['ground', 'first']


def test_levels_left_out_are_the_sheets_that_name_none():
    h = model.loads(BOX + "  - {id: option, level: ground, envelope: [[0, 0], [W, 0], [W, D], [0, D]]}\n")
    assert h['levels'] == ['ground']


def test_sheets_may_be_written_as_a_mapping_by_id():
    h = model.loads('sheets:\n  ground: {envelope: [[0, 0], [4, 0], [4, 4], [0, 4]]}\n  first: {envelope: [[0, 0], [4, 0], [4, 4], [0, 4]]}\n')
    assert [f['id'] for f in h['sheets']] == ['ground', 'first']


@pytest.mark.parametrize('sid', ['../x', 'a/b', 'a b', '', '.hidden', '-x', 'a.b', 'a"b', '<svg>', 'a\nb', 'ground\n', 'ü'])
def test_a_sheet_id_is_a_plain_name(sid):
    """It becomes a file name and an element id."""
    with pytest.raises(ConfigError, match='letters, digits'):
        model.loads('sheets: [{id: %r, envelope: [[0, 0], [4, 0], [4, 4], [0, 4]]}]' % sid)


@pytest.mark.parametrize('sid', ['g', 'Ground', 'first-floor', 'opt_2', '2', 'A1'])
def test_a_plain_name_will_do_as_a_sheet_id(sid):
    assert model.loads('sheets: [{id: %s, envelope: [[0, 0], [4, 0], [4, 4], [0, 4]]}]' % sid)['sheets'][0]['id'] == sid


def test_two_sheets_cannot_share_an_id():
    with pytest.raises(ConfigError, match="two sheets called 'ground'"):
        model.loads(BOX + "  - {id: ground, envelope: [[0, 0], [W, 0], [W, D], [0, D]]}\n")


# ---- parts

PARTS = """
survey: {W: 8.0, D: 6.0}
parts:
  shell:
    envelope: [[0, 0], [W, 0], [W, D], [0, D]]
    notes: {summary: The shell., about: [Shell note.]}
  core:
    use: [shell]
    walls: [{id: split, from: [4, 0], to: [4, D]}]
    rooms: [{name: LEFT, at: [1, 1]}]
    notes: [Core note.]
levels: [ground, first]
sheets:
  - id: ground
    use: [core]
    rooms: [{name: RIGHT, at: [7, 1]}]
    notes: {about: [Own note.], decided: [Agreed.]}
  - id: first
    use: [core]
    walls: [{id: extra, from: [4, 3], to: [8, 3]}]
    rooms: [{name: NE, at: [7, 1]}, {name: SE, at: [7, 5]}]
"""


def test_parts_are_merged_in_order_and_shared():
    g, f = model.loads(PARTS)['sheets']
    assert [w['id'] for w in g['walls']] == ['split'] and [w['id'] for w in f['walls']] == ['split', 'extra']
    assert [r['name'] for r in g['rooms']] == ['LEFT', 'RIGHT']         # the part's, then the sheet's own
    assert [r['name'] for r in f['rooms']] == ['LEFT', 'NE', 'SE']
    assert g['envelope']['pts'] == f['envelope']['pts']
    assert g['notes']['about'] == ['Own note.', 'Core note.', 'Shell note.']    # its own lead, then each part's before what that part uses
    assert g['notes']['decided'] == ['Agreed.'] and g['notes']['summary'] == 'The shell.'
    assert f['notes']['about'] == ['Core note.', 'Shell note.']
    assert not [i for i in solve.solves(PARTS).issues() if i[1] != 'info']


@pytest.mark.parametrize('old, new, why', [
    ('use: [core]\n    rooms: [{name: RIGHT', 'use: [attic]\n    rooms: [{name: RIGHT', "sheets.ground.use: no part called 'attic'"),
    ('    use: [shell]\n', '    use: [core]\n', "parts.core.use: part 'core' uses itself"),
    ('    use: [shell]\n', '    use: [nowhere]\n', "parts.core.use: no part called 'nowhere'"),
])
def test_a_part_that_is_not_there_or_uses_itself_is_refused(old, new, why):
    with pytest.raises(ConfigError) as e:
        model.loads(PARTS.replace(old, new))
    assert why in str(e.value)


def test_parts_that_use_each_other_in_a_ring_are_refused():
    text = "parts:\n  a: {use: [b]}\n  b: {use: [c]}\n  c: {use: [a]}\nsheets: [{id: g, use: [a], envelope: [[0, 0], [4, 0], [4, 4], [0, 4]]}]\n"
    with pytest.raises(ConfigError, match='uses itself'):
        model.loads(text)


# ---- notes

def test_notes_are_grouped_and_a_plain_list_is_about_the_drawing():
    assert model.notes(None, 'w') == {'summary': '', 'decided': [], 'unconfirmed': [], 'needs': [], 'about': []}
    assert model.notes(['a', 'b'], 'w')['about'] == ['a', 'b']
    n = model.notes({'summary': 'S', 'decided': 'one', 'needs': [1, None, 'two'], 'unconfirmed': None}, 'w')
    assert (n['summary'], n['decided'], n['needs'], n['unconfirmed']) == ('S', ['one'], ['1', 'two'], [])
    for bad, why in ((5, 'expected a list or a mapping'), ('words', 'expected a list or a mapping'),
                     ({'maybe': ['x']}, "no group called 'maybe' (summary, decided, unconfirmed, needs, about)")):
        with pytest.raises(ConfigError) as e:
            model.notes(bad, 'sheets.g')
        assert 'sheets.g.notes: ' + why in str(e.value)


def test_joined_notes_keep_the_first_summary_and_every_entry():
    a = model.notes({'summary': 'A', 'about': ['a']}, 'w')
    b = model.notes({'summary': 'B', 'about': ['b'], 'needs': ['n']}, 'w')
    j = model.join_notes(a, b)
    assert (j['summary'], j['about'], j['needs']) == ('A', ['a', 'b'], ['n'])
    assert model.join_notes(None, b) is b and model.join_notes(a, None) is a
    assert model.join_notes(model.notes(['x'], 'w'), b)['summary'] == 'B'


# ---- every list in a sheet: what a wrong entry is told

@pytest.mark.parametrize('extra, why', [
    # walls
    ('walls: [{from: [1, 1]}]', "sheets.ground.walls[0]: missing 'to'"),
    ('walls: [{to: [1, 1]}]', "sheets.ground.walls[0]: missing 'from'"),
    ('walls: [{from: [1, 1], to: [nope, 1]}]', "sheets.ground.walls[0].to: unknown name 'nope'"),
    ('walls: [{from: [1, 1], to: [4, 1], t: 0}]', 'sheets.ground.walls[0].t: a wall is more than nothing'),
    ('walls: [{from: [1, 1], to: [4, 1], t: -0.1}]', 'sheets.ground.walls[0].t'),
    ('walls: [{from: [1, 1], to: [4, 1], t: thick}]', "sheets.ground.walls[0].t: unknown name 'thick'"),
    ('walls: [{from: {y: 2, wall: nope}, to: [4, 1]}]', "no wall called 'nope' yet"),
    ('walls: [{from: {y: 2}, to: [4, 1]}]', 'a point on a wall is'),
    ('walls: [{from: {x: 1, y: 2, wall: east}, to: [4, 1]}]', 'a point on a wall is'),
    ('walls: [{from: {y: 2, wall: east, near: 1}, to: [4, 1]}]', 'a point on a wall is'),
    ('walls: [{from: {y: 2, wall: east, side: e}, to: [4, 1]}]', 'east is an outside wall — use in or out'),
    ('walls: [{from: {x: 2, wall: east}, to: [4, 1]}]', 'east runs along x'),
    ('walls: [{from: {y: 20, wall: east}, to: [4, 1]}]', 'east does not reach y = 20.000'),
    ('walls: [{id: a, from: [4, 0], to: [4, D]}, {from: {y: 2, wall: a, clear: 1}, to: [8, 2]}]', 'say which `side:` of a'),
    ('walls: [{id: a, from: [4, 0], to: [4, D]}, {from: {y: 2, wall: a, side: n}, to: [8, 2]}]', "a has no 'n' side"),
    ('walls: [{id: a, from: [4, 0], to: [4, D]}, {from: {y: 2, wall: a, side: up}, to: [8, 2]}]', "a has no 'up' side"),
    ('walls: [5]', 'sheets.ground'), ('walls: 5', 'sheets.ground'), ('walls: [null]', 'sheets.ground'),
    # dividers
    ('dividers: [{from: [1, 1]}]', "sheets.ground.dividers[0]: missing 'to'"),
    ('dividers: [[1, 1]]', "sheets.ground.dividers[0]: missing 'from'"),
    # openings
    ('openings: [{wall: north}]', 'sheets.ground.openings[0]: give exactly one of door, window, opening'),
    ('openings: [{door: std, window: 1, wall: north}]', 'give exactly one of door, window, opening'),
    ('openings: [{door: huge, wall: north}]', "sheets.ground.openings[0].door: unknown name 'huge'"),
    ('openings: [{door: 0, wall: north}]', 'sheets.ground.openings[0].door: an opening is more than nothing'),
    ('openings: [{window: -1.2, wall: north}]', 'sheets.ground.openings[0].window'),
    ('openings: [{door: std}]', 'sheets.ground.openings[0]: name the wall, or give at: [x, y]'),
    ('openings: [{door: std, at: centre}]', 'name the wall, or give at: [x, y]'),
    ('openings: [{door: std, at: {from_start: 1}}]', 'name the wall, or give at: [x, y]'),
    ('openings: [{door: std, wall: north, at: left}]', 'sheets.ground.openings[0].at: use centre, [x, y], from_start or from_end'),
    ('openings: [{door: std, wall: north, at: {from_middle: 1}}]', '.at: use centre, [x, y], from_start or from_end'),
    ('openings: [{door: std, wall: north, at: 3}]', '.at: use centre'),
    ('openings: [{door: std, wall: north, at: {from_start: nope}}]', "sheets.ground.openings[0].at: unknown name 'nope'"),
    ('openings: [{door: std, wall: north, at: [1]}]', 'sheets.ground.openings[0].at: expected a point'),
    ('openings: [{door: std, wall: north, style: revolving}]', "sheets.ground.openings[0].style: unknown style 'revolving'"),
    ('openings: [5]', 'sheets.ground'), ('openings: nope', 'sheets.ground'),
    # rooms
    ('rooms: [{at: [1, 1]}]', "sheets.ground.rooms[0]: missing 'name'"),
    ('rooms: [{name: A}]', "sheets.ground.rooms[0]: missing 'at'"),
    ('rooms: [{name: A, at: [1]}]', 'sheets.ground.rooms[0].at: expected a point'),
    ('rooms: [{name: A, at: [5, 5], label: up}]', 'sheets.ground.rooms[0].label: use true, false or one of north, east, south, west'),
    ('rooms: [{name: A, at: [5, 5], label: 5}]', 'sheets.ground.rooms[0].label'),
    ('rooms: [{name: A, at: [5, 5], expect: {width: 3}}]', 'sheets.ground.rooms[0].expect: give any of w, h and area'),
    ('rooms: [{name: A, at: [5, 5], expect: [3]}]', 'sheets.ground.rooms[0].expect: give any of w, h and area'),
    ('rooms: [{name: A, at: [5, 5], expect: {w: nope}}]', "sheets.ground.rooms[0].expect.w: unknown name 'nope'"),
    ('rooms: [{name: A, at: [5, 5], dx: left}]', "sheets.ground.rooms[0].dx: unknown name 'left'"),
    ('rooms: [{name: A, at: [5, 5], rot: left}]', "sheets.ground.rooms[0].rot: unknown name 'left'"),
    ('rooms: [5]', 'sheets.ground'),
    # zones
    ('zones: [{name: Z}]', "sheets.ground.zones[0]: missing 'rooms'"),
    ('zones: [{rooms: [ROOM]}]', "sheets.ground.zones[0]: missing 'name'"),
    ('zones: [{name: Z, rooms: []}]', 'sheets.ground.zones[0].rooms: list the rooms the zone takes in'),
    ('zones: [{name: Z, rooms: ROOM}]', 'list the rooms the zone takes in'),
    ('zones: [{name: Z, rooms: [ROOM], label: up}]', 'sheets.ground.zones[0].label'),
    # stairs
    ('stairs: [{id: s}]', "sheets.ground.stairs[0]: missing 'path'"),
    ('stairs: [{path: [[1, 1]]}]', 'sheets.ground.stairs[0].path: a stair needs a foot and a head'),
    ('stairs: [{path: [[2, 2], [2, 4]], treads: [3, 4]}]', 'sheets.ground.stairs[0].treads: one value per leg (1)'),
    ('stairs: [{path: [[2, 2], [2, 4]], width: [1, 1]}]', 'sheets.ground.stairs[0].width: one value per leg (1)'),
    ('stairs: [{path: [[2, 2], [2, 4]], width: 0}]', 'sheets.ground.stairs[0].width: a flight is some way wide'),
    ('stairs: [{path: [[2, 2], [2, 4]], treads: [-3]}]', 'sheets.ground.stairs[0].treads: none, or up to 60'),
    ('stairs: [{path: [[2, 2], [2, 4]], treads: [100000]}]', 'sheets.ground.stairs[0].treads: none, or up to 60'),
    ('stairs: [{path: [[2, 2], [2, 4]], going: 0}]', 'sheets.ground.stairs[0].going: a tread is some way deep'),
    ('stairs: [{path: [[2, 2], [2, 4]], going: -0.2}]', 'sheets.ground.stairs[0].going'),
    ('stairs: [{path: [[2, 2], [2, 4]], cut_risers: x}]', "sheets.ground.stairs[0].cut_risers: unknown name 'x'"),
    ('stairs: [{path: [[2, 2], [2, 4], [4, 4]], turns: []}]', 'sheets.ground.stairs[0].turns: one per corner (1)'),
    ('stairs: [{path: [[2, 2], [2, 4], [4, 4]], turns: [spiral]}]', 'sheets.ground.stairs[0].turns: use landing or {winders: n}'),
    ('stairs: [{path: [[2, 2], [2, 4], [4, 4]], turns: [{winders: 100000}]}]', 'up to six winders'),
    ('stairs: [{path: [[2, 2], [2, 4], [4, 4]], turns: [{winders: -2}]}]', 'up to six winders'),
    ('stairs: [{ref: nope.main}]', "sheets.ground.stairs[0].ref: no stair 'nope.main' on an earlier sheet"),
    ('stairs: [{ref: ground.main}]', "no stair 'ground.main' on an earlier sheet"),          # its own sheet is not earlier
    ('stairs: [{ref: 5}]', 'no stair 5 on an earlier sheet'),
    ('stairs: [5]', 'sheets.ground'),
    # areas, solids, labels, gone, dims
    ('areas: [{rect: [[1, 1], [2, 2]], style: carpet}]', "sheets.ground.areas[0].style: no area style 'carpet' (have outdoor, below, new, zone, fitting)"),
    ('areas: [{style: below}]', "sheets.ground.areas[0]: missing 'points'"),
    ('areas: [{points: [[1, 1], [2, 2]]}]', 'sheets.ground.areas[0].points: a shape needs at least three points'),
    ('areas: [{rect: [[1, 1]]}]', 'sheets.ground: not laid out as a sheet is'),
    ('areas: [{rect: [[1, 1], [2, 2]], label: A, rot: left}]', "sheets.ground.areas[0].rot: unknown name 'left'"),
    ('areas: [5]', 'sheets.ground'),
    ('solids: [{points: [[1, 1], [2, 2]]}]', 'sheets.ground.solids[0].points: a shape needs at least three points'),
    ('solids: [{}]', "sheets.ground.solids[0]: missing 'points'"),
    ('labels: [{text: hi}]', "sheets.ground.labels[0]: missing 'at'"),
    ('labels: [{at: [1, 1]}]', "sheets.ground.labels[0]: missing 'text'"),
    ('labels: [{at: [1, 1], text: hi, style: huge}]', "sheets.ground.labels[0].style: no text style 'huge' (have name, small, mini, note, zone)"),
    ('labels: [{at: [1, 1], text: "{nope}"}]', "sheets.ground.labels[0]: unknown name 'nope'"),
    ('labels: [{at: [1, 1], text: "{W:>30}"}]', 'sheets.ground.labels[0]: format'),
    ('labels: [{at: [1, 1], text: hi, rot: sideways}]', "sheets.ground.labels[0].rot: unknown name 'sideways'"),
    ('gone: [[[1, 1], [nope, 2]]]', "sheets.ground.gone[0]: unknown name 'nope'"),
    ('gone: [5]', 'sheets.ground'),
    ('dims: [{from: [1, 1]}]', "sheets.ground.dims[0]: missing 'to'"),
    ('dims: [{from: [1, 1], to: [3, 1], text: "{nope}"}]', "sheets.ground.dims[0]: unknown name 'nope'"),
    ('dims: [{from: [1, 1], to: [3, 1], style: loud}]', "sheets.ground.dims[0].style: no dimension style 'loud' (have soft, calc)"),
    # fittings
    ('fittings: [{sofa: 2, at: [1, 1]}]', 'sheets.ground.fittings[0]: give exactly one of basin, bath,'),
    ('fittings: [{bath: 1.7, sink: true, wall: north}]', 'give exactly one of'),
    ('fittings: [{bath: 1.7}]', 'name the `wall:` its back is against, or say which way it is `facing:`'),
    ('fittings: [{bath: 0, wall: north}]', 'sheets.ground.fittings[0].bath: a fitting is more than nothing'),
    ('fittings: [{bath: 1.7, wall: north, depth: -1}]', 'sheets.ground.fittings[0].depth: a fitting is more than nothing'),
    ('fittings: [{bath: big, wall: north}]', "sheets.ground.fittings[0].bath: unknown name 'big'"),
    ('fittings: [{bath: 1.7, wall: north, side: up}]', "sheets.ground.fittings[0].side: use a compass point, not 'up'"),
    ('fittings: [{bath: 1.7, wall: north, corner: left}]', "sheets.ground.fittings[0].corner: use a compass point, not 'left'"),
    ('fittings: [{bath: 1.7, facing: in, at: [3, 3]}]', "sheets.ground.fittings[0].facing: use a compass point, not 'in'"),
    ('fittings: [{bath: 1.7, facing: e}]', 'name the wall, or give at: [x, y]'),
    ('fittings: [{bath: 1.7, wall: north, at: nowhere}]', 'sheets.ground.fittings[0].at: use centre'),
    ('fittings: [5]', 'sheets.ground'),
    # the sheet itself
    ('level: attic', 'sheets.ground.level: no level called'),
    ('changes: ground', "sheets.ground.changes: no earlier sheet called 'ground'"),
    ('use: [nope]', "sheets.ground.use: no part called 'nope'"),
    ('use: 5', 'sheets.ground'),
    ('notes: 5', 'sheets.ground.notes: expected a list or a mapping'),
    ('notes: {maybe: [x]}', "sheets.ground.notes: no group called 'maybe'"),
])
def test_what_is_wrong_in_a_sheet_is_said_with_where_it_is(extra, why):
    with pytest.raises(ConfigError) as e:
        model.loads(ROOM + '    ' + extra + '\n')
    assert why in str(e.value), str(e.value)


@pytest.mark.parametrize('env, why', [
    ('[{at: [0, 0], t: -1}, [4, 0], [4, 4], [0, 4]]', 'envelope[0].t: a wall is more than nothing'),
    ('[{at: [0, 0], t: 0}, [4, 0], [4, 4], [0, 4]]', 'envelope[0].t: a wall is more than nothing'),        # no wall is `open: true`
    ('{t: 0, points: [[0, 0], [4, 0], [4, 4], [0, 4]]}', 'envelope.t: a wall is more than nothing'),
    ('[{t: 0.2}, [4, 0], [4, 4], [0, 4]]', "envelope[0]: missing 'at'"),
    ('[[0, 0, thick], [4, 0], [4, 4], [0, 4]]', "envelope[0].t: unknown name 'thick'"),
    ('[[0, 0], [4, 0]]', 'at least three points'),
    ('[[0, 0]]', 'at least three points'),
    ('[]', 'at least three points'),
    ('[{at: [0, 0], rise: 1, radius: 9}, [4, 0], [4, 4], [0, 4]]', 'envelope[0]: give one of rise, radius and via'),
    ('[{at: [0, 0], radius: 1}, [4, 0], [4, 4], [0, 4]]', 'envelope[0].radius: 1.000 is too tight for ends 4.000 apart'),
    ('[{at: [0, 0], via: [2, 0]}, [4, 0], [4, 4], [0, 4]]', 'cannot run straight through'),
    ('[{at: [0, 0], rise: nope}, [4, 0], [4, 4], [0, 4]]', "envelope[0].rise: unknown name 'nope'"),
    ('[{at: [0, 0], rise: 1}, {at: [0, 0], rise: 1}]', 'a curve needs two ends — draw a circle as two halves'),
])
def test_what_is_wrong_in_an_envelope_is_said_with_where_it_is(env, why):
    with pytest.raises(ConfigError) as e:
        model.loads('sheets: [{id: g, envelope: %s}]' % env)
    assert 'sheets.g.' + why in str(e.value) or why in str(e.value), str(e.value)
    assert 'sheets.g' in str(e.value)


def test_an_envelope_point_may_carry_a_thickness_three_ways():
    fl = model.loads('sheets: [{id: g, envelope: {t: 0.2, points: [[0, 0, 0.5], {at: [4, 0], t: 0.4, id: east}, [4, 4], [0, 4]]}}]')['sheets'][0]
    assert fl['envelope']['t'] == [0.5, 0.4, 0.2, 0.2] and fl['envelope']['ids'] == [None, 'east', None, None]
    assert fl['envelope']['open'] == [False]*4


def test_an_envelope_reads_the_same_whichever_way_round_it_is_written():
    a = solve.solves('sheets: [{id: g, unlabelled: ok, envelope: [[0, 0], [5, 0], [5, 4], [0, 4]]}]').sheet('g').plan
    b = solve.solves('sheets: [{id: g, unlabelled: ok, envelope: [[0, 0], [0, 4], [5, 4], [5, 0]]}]').sheet('g').plan
    assert a.gross == b.gross == 20.0 and a.internal == pytest.approx(b.internal) == pytest.approx(4.4*3.4)


# ---- the traps CLAUDE.md warns of: each says something a person can act on

def test_a_comma_inside_a_flow_list_is_said_to_be_a_point_of_the_wrong_size():
    with pytest.raises(ConfigError, match=r"expected a point \[x, y\], got \[4, \"op\('wide'\", 'pair=True\)/2\"\]|expected a point"):
        model.loads(ROOM + "    walls: [{from: [4, op('wide', pair=True)/2], to: [4, 6]}]\n")


def test_yaml_reading_on_and_off_as_booleans_is_said_not_swallowed():
    with pytest.raises(ConfigError, match='a point on a wall is'):
        model.loads(ROOM + "    walls: [{from: {y: 2, on: east}, to: [4, 2]}]\n")
    with pytest.raises(ConfigError, match='expected a number'):
        model.loads(ROOM.replace('W: 8.0', 'W: on'))


def test_a_string_with_a_brace_at_the_start_must_be_quoted_and_says_so():
    with pytest.raises(ConfigError):
        model.loads(ROOM + "    notes: [{ROOM_w} wide]\n")
    s = solve.solves(ROOM + "    notes: ['{ROOM_w:.2f} wide']\n")
    assert s.sheet('ground').info['groups'][0][2] == ['7.40 wide']


def test_a_private_house_and_its_front_are_read_from_house():
    h = model.loads('house: {name: The Elms, private: yes, front: south, front_note: the lane}\n' + ROOM)
    assert (h['name'], h['private'], h['front'], h['front_note']) == ('The Elms', True, 'south', 'the lane')
    assert model.loads(ROOM, '/x/y/elms.yaml')['name'] == 'elms' and model.loads(ROOM)['private'] is False
    assert model.loads('house: {name: 42}\n' + ROOM)['name'] == '42'


def test_a_house_with_no_name_is_called_by_its_folder(tmp_path):
    for folder, text in (('mill-lane', BOX), ('mill-lane-2', 'house: {name: ""}\n' + BOX)):
        d = tmp_path / folder
        d.mkdir()
        (d / 'house.yaml').write_text(text)
        assert solve.solve(str(d)).house['name'] == folder
    (tmp_path / 'barn.yaml').write_text(BOX)
    assert solve.solve(str(tmp_path / 'barn.yaml')).house['name'] == 'barn'


# ---- a sheet that is another sheet and more, and what a sheet leaves out

FAMILY = """
survey: {W: 8.0, D: 6.0}
lines: {MID: W/2, HY: D/2}
parts:
  core:
    walls:
      - {id: split, from: [MID, 0], to: [MID, D]}
      - {id: cross, from: [MID, HY], to: [W, HY]}
      - {from: [3, 0], to: [3, 1.2]}
    openings:
      - {door: std, wall: split, at: [MID, 1.5], swing: e, id: split_door}
      - {door: std, wall: cross, at: centre, swing: s}
      - {window: 1.2, at: [2.0, 0]}
    fittings:
      - {basin: true, wall: cross, side: s, at: centre}
    rooms:
      - {name: LEFT, at: [1, 1]}
      - {name: RIGHT, at: [7, 1]}
      - {name: PANTRY, id: P, at: [7, 5]}
levels: [ground]
sheets:
  - id: ground
    title: AS BUILT
    scheme: as-built
    use: [core]
    envelope: [[0, 0], [W, 0], [W, D], [0, D]]
    notes: {summary: As it stands., decided: [The split stays.]}
  - id: open
    extends: ground
    changes: ground
    omit: [cross, PANTRY]
    walls:
      - {id: nib, from: [6, 0], to: [6, 1.0]}
  - id: opener
    extends: open
    omit: [nib, {opening: split_door}]
    notes: {summary: With less still.}
"""


def test_a_sheet_extends_another_and_adds_to_it():
    h = model.loads(FAMILY.replace('    omit: [cross, PANTRY]\n', '').replace("    omit: [nib, {opening: split_door}]\n", ''))
    ground, more, most = h['sheets']
    assert [w['id'] for w in more['walls']] == ['split', 'cross', 'w2', 'nib'] and more['envelope'] == ground['envelope']
    assert [r['name'] for r in more['rooms']] == ['LEFT', 'RIGHT', 'PANTRY'] and len(more['openings']) == 3
    assert (more['extends'], more['changes'], more['level'], ground['extends']) == ('ground', 'ground', 'ground', None)
    assert (most['extends'], most['changes'], most['level']) == ('open', 'ground', 'ground')        # what it changes comes with it
    # what a sheet says of itself is its own
    assert (more['title'], more['tab'], more['scheme']) == ('OPEN', 'Open', None) and more['notes']['summary'] == '' and more['notes']['decided'] == []
    assert most['notes']['summary'] == 'With less still.' and ground['notes']['decided'] == ['The split stays.']
    assert [w['where'] for w in more['openings']] == ['sheets.open.openings[%d]' % i for i in range(3)]


def test_a_sheet_leaves_out_walls_rooms_and_openings_by_name():
    ground, more, most = model.loads(FAMILY)['sheets']
    assert [w['id'] for w in ground['walls']] == ['split', 'cross', 'w2']
    assert [w['id'] for w in more['walls']] == ['split', 'w2', 'nib']           # the wall with no id keeps the name it had
    assert [(o['kind'], o['wall']) for o in more['openings']] == [('door', 'split'), ('window', None)]      # cross took its door
    assert more['fittings'] == [] and [r['name'] for r in more['rooms']] == ['LEFT', 'RIGHT']
    assert [w['id'] for w in most['walls']] == ['split', 'w2'] and len(ground['fittings']) == 1
    assert [o['kind'] for o in most['openings']] == ['window'] and [o['id'] for o in more['openings']] == ['split_door', None]
    s = solve.solves(FAMILY)
    assert [i for i in s.issues() if i[1] != 'info'] == []
    after = s.sheet('open')
    assert after.base.id == 'ground' and after.demolition is not None           # the wall left out comes down, like any other
    x0, y0, x1, y1 = after.demolition.bounds
    assert (round(x0, 2), round(x1, 2)) == (4.05, 7.7) and abs((y0 + y1)/2 - 3.0) < 0.01
    assert [r['name'] for r in after.plan.rooms] == ['LEFT', 'RIGHT'] and round(after.plan.rooms[1]['h'], 2) == 5.4


@pytest.mark.parametrize('was, now, why', [
    ('omit: [cross, PANTRY]', 'omit: [cross, PANTRY, nowhere]', r"sheets.open.omit\[2\]: nothing called 'nowhere' on this sheet"),
    ('omit: [cross, PANTRY]', 'omit: cross', 'sheets.open.omit: a list of ids'),
    ('omit: [cross, PANTRY]', 'omit: [{wall: PANTRY}]', r"sheets.open.omit\[0\]: nothing called 'PANTRY'"),
    ('omit: [cross, PANTRY]', 'omit: [{window: x}]', r'sheets.open.omit\[0\]: a name, or one of \{wall: ...\}'),
    ('omit: [cross, PANTRY]', 'omit: [{wall: cross, room: P}]', r'sheets.open.omit\[0\]: a name, or one of'),
    ('omit: [cross, PANTRY]', 'omit: [nib2]', "nothing called 'nib2'"),
    ('omit: [cross, PANTRY]', 'omit: [cross]', 'PANTRY and RIGHT are the same space'),
    ('extends: open', 'extends: nowhere', "sheets.opener.extends: no earlier sheet called 'nowhere'"),
    ('extends: open', 'extends: opener', "sheets.opener.extends: no earlier sheet called 'opener'"),
    ('extends: ground\n', 'extends: opener\n', "sheets.open.extends: no earlier sheet called 'opener'"),
    ('  core:\n', '  core:\n    omit: [split]\n', 'parts.core.omit: a sheet says that'),
    ('  core:\n', '  core:\n    extends: ground\n', 'parts.core.extends: a sheet says that'),
])
def test_what_is_wrong_with_omit_or_extends_is_said(was, now, why):
    assert FAMILY.count(was) == 1
    with pytest.raises(ValueError, match=why):
        s = solve.solves(FAMILY.replace(was, now))
        raise ValueError(' | '.join(m for _, lv, m in s.issues() if lv == 'error'))


def test_a_room_is_left_out_by_its_id_or_its_name_and_a_kind_tells_two_apart():
    for word in ('P', 'PANTRY', '{room: P}', '{room: PANTRY}'):
        h = model.loads(FAMILY.replace('omit: [cross, PANTRY]', 'omit: [cross, %s]' % word))
        assert [r['name'] for r in h['sheets'][1]['rooms']] == ['LEFT', 'RIGHT']
    both = FAMILY.replace('{name: LEFT, at: [1, 1]}', '{name: LEFT, id: split, at: [1, 1]}')
    one = model.loads(both.replace('omit: [cross, PANTRY]', 'omit: [cross, PANTRY, {room: split}]'))['sheets'][1]
    assert [w['id'] for w in one['walls']] == ['split', 'w2', 'nib'] and [r['name'] for r in one['rooms']] == ['RIGHT']
    two = model.loads(both.replace('omit: [cross, PANTRY]', 'omit: [cross, PANTRY, split]')
                      .replace("omit: [nib, {opening: split_door}]", 'omit: [nib]'))['sheets'][1]
    assert [w['id'] for w in two['walls']] == ['w2', 'nib'] and [r['name'] for r in two['rooms']] == ['RIGHT']
    path = FAMILY.replace('- {id: cross, from: [MID, HY], to: [W, HY]}', '- {id: cross, path: [[MID, HY], [6, HY], [W, HY]]}') \
                 .replace('wall: cross, at: centre, swing: s', 'wall: cross.0, at: centre, swing: s').replace('wall: cross, side: s, at: centre', 'wall: cross.1, side: s, at: centre')
    legs = model.loads(path)['sheets']
    assert [w['id'] for w in legs[0]['walls']] == ['split', 'cross.0', 'cross.1', 'w2']
    assert [w['id'] for w in legs[1]['walls']] == ['split', 'w2', 'nib'] and len(legs[1]['openings']) == 2 and legs[1]['fittings'] == []
