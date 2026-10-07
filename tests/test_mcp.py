# -*- coding: utf-8 -*-
"""The tools an agent is given: called directly, and once through a real
client over stdio, on a copy of a house so the ones that write can be tried."""
import asyncio
import json
import os
import re
import shutil
import sys
import pytest

HERE = os.path.dirname(__file__)
ROOT = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, ROOT)
from flawlessplan import mcp_server as mcp
from flawlessplan.workspace import Workspace


def test_a_client_can_list_and_call_the_tools(houses):
    """The server as an agent meets it: started as a process, spoken to
    over stdio by the SDK's own client."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def talk():
        params = StdioServerParameters(command=sys.executable, args=['-m', 'flawlessplan', 'mcp'], cwd='/',
                                       env=dict(os.environ, PYTHONPATH=ROOT, FLAWLESSPLAN_WORKSPACE=str(houses.parent)))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                hello = await session.initialize()
                tools = await session.list_tools()
                listed = await session.call_tool('list_houses', {})
                where = await session.call_tool('at', {'house': 'bungalow', 'sheet': 'infill', 'x': 3.0, 'y': 7.5})
                bad = await session.call_tool('check', {'house': '../etc'})
                return hello, tools, listed, where, bad

    hello, tools, listed, where, bad = asyncio.run(talk())
    assert 'written down once' in hello.instructions
    assert [t.name for t in tools.tools] == [name for _, name, _ in mcp.TOOLS]
    assert 'house' in [t for t in tools.tools if t.name == 'check'][0].input_schema['required']
    said = ' '.join(c.text for c in listed.content)
    assert '"bungalow"' in said and '"cottage"' in said and not listed.is_error
    assert where.content[0].text.startswith('room GARDEN ROOM [GARDEN]')
    assert bad.is_error and 'no house called' in bad.content[0].text


def test_reading_tools_answer_in_the_house_files_names(houses):
    assert mcp.at('bungalow', 'infill', 3.0, 7.5).startswith('room GARDEN ROOM [GARDEN]')
    rep = mcp.sheet_report('bungalow', 'infill')['sheets'][0]
    assert rep['changes'] == 'ground' and rep['gained'] == 18.0
    assert mcp.measurements('bungalow')['survey']['infill_d'] == {'value': 3.0, 'status': 'assumed'}


def test_a_measurement_is_changed_where_it_is_written(houses):
    path = str(houses / 'bungalow' / 'house.yaml')
    got = mcp.set_measurement('bungalow', 'infill_d', 3.5)
    assert got['was'] == 3.0 and 'sheets.infill.gross: 94.0 → 97.0' in got['changed'] and not got['issues']
    text = open(path).read()
    assert 'infill_d: {value: 3.5, status: assumed}    # how far south' in text      # the comment stays
    with pytest.raises(mcp.ToolError, match='worked out in `lines`'):
        mcp.set_measurement('bungalow', 'YI', 9.0)
    assert mcp.set_measurement('bungalow', 'infill_d', 4.5)['issues']                # the file's own `require` speaks
    with pytest.raises(mcp.ToolError, match='would not solve'):
        mcp.set_measurement('bungalow', 'main_w', 0)
    assert 'main_w: 10.0' in open(path).read()                                       # and the file is put back


def test_a_note_moves_between_groups(houses):
    note = [t for t in mcp.sheet_report('bungalow', 'infill')['sheets'][0]['notes']['unconfirmed']][0]
    assert mcp.settle_note('bungalow', 'infill', note) == 'moved from unconfirmed to decided'
    notes = mcp.sheet_report('bungalow', 'infill')['sheets'][0]['notes']
    assert note not in notes['unconfirmed'] and len(notes['unconfirmed']) == 1 and notes['decided'][-1] == note
    assert mcp.settle_note('bungalow', 'infill', note, 'needs') == 'moved from decided to needs'


def test_the_pages_can_be_shown_from_the_tools(houses):
    """`show` builds the workspace and serves it from the tool's own
    process, so an owner with no terminal still gets pages that save."""
    import urllib.request
    said = mcp.show('cottage')
    url = said.split()[0]
    assert url.startswith('http://localhost:') and url.endswith('/cottage/')
    assert b'<title>Cottage</title>' in urllib.request.urlopen(url + 'index.html').read()
    put = urllib.request.Request(url + 'marks.json', data=b'[{"type": "note", "sheet": "ground", "x": 1, "y": 1, "text": "hi", "ts": 1}]',
                                 method='PUT', headers={'Content-Type': 'application/json'})
    assert urllib.request.urlopen(put).status == 204
    assert os.path.exists(str(houses / 'cottage' / 'marks.json'))
    assert 'written "hi"' in mcp.marks('cottage')[0]


def test_a_page_that_is_shown_follows_every_change_the_tools_make(houses):
    """Nobody has to remember to draw it again: each tool that writes a
    house file redraws its pages, and the page is told it is behind."""
    import json, urllib.request
    url = mcp.show('cottage').split()[0]
    page = lambda: urllib.request.urlopen(url + 'index.html').read().decode()
    stamp = lambda: json.loads(urllib.request.urlopen(url + 'stamp').read())
    seen = [stamp()]
    assert seen[0] and stamp() == seen[0]                           # the same while nothing is changed
    def moved():
        seen.append(stamp())
        return seen[-1] != seen[-2]
    mcp.edit_house('cottage', 'name: LIVING', 'name: SCULLERY')
    assert moved() and 'SCULLERY' in page() and 'LIVING' not in page()
    mcp.write_house('cottage', mcp.read_house('cottage')['text'].replace('SCULLERY', 'PANTRY'))
    assert moved() and 'PANTRY' in page()
    mcp.add_to_house('cottage', 'sheets.ground.notes.decided', 'The pantry stays.')
    assert moved() and 'The pantry stays.' in page()
    drawn = lambda name: open(str(houses.parent / 'build' / 'bungalow' / name)).read()
    before = drawn('report.json')
    mcp.set_measurement('bungalow', 'main_w', 10.4)
    assert drawn('report.json') != before
    note = mcp.sheet_report('bungalow', 'infill')['sheets'][0]['notes']['unconfirmed'][0]
    before = drawn('infill.md')
    mcp.settle_note('bungalow', 'infill', note)
    assert drawn('infill.md') != before
    with pytest.raises(mcp.ToolError):                              # a change that is refused leaves the page as it was
        mcp.edit_house('cottage', 'PANTRY', '{')
    assert not moved()
    mcp.write_house('lodge', mcp.read_house('cottage')['text'])     # a house that is new is drawn, and in the index
    assert 'lodge/' in urllib.request.urlopen(url.replace('cottage/', 'index.html')).read().decode()
    assert json.loads(urllib.request.urlopen(url.replace('cottage', 'lodge') + 'stamp').read())
    assert json.loads(urllib.request.urlopen(url.replace('cottage', 'nowhere') + 'stamp').read()) is None


def test_nothing_is_drawn_for_a_workspace_whose_pages_were_never_made(houses):
    mcp.edit_house('cottage', 'name: LIVING', 'name: SCULLERY')
    assert not os.path.exists(str(houses.parent / 'build'))


def test_a_house_can_be_made_into_a_file_to_send(houses):
    out = mcp.share('bungalow')
    assert out == str(houses.parent / 'build' / 'bungalow' / 'bungalow-plans.html')
    html = open(out).read()
    assert '<title>Bungalow</title>' in html and html.count('role="tabpanel"') == 3
    with pytest.raises(mcp.ToolError):
        mcp.share('nowhere')


def test_a_workspace_starts_with_the_examples(tmp_path):
    ws = Workspace(str(tmp_path / 'mine'))
    made = ws.init()
    assert ws.names() == ['bungalow', 'cottage'] and any(p.endswith('.mcp.json') for p in made)
    assert ws.init() == []                                    # and is left alone the second time
    with pytest.raises(ValueError, match='no house called'):
        ws.house('../etc')


def test_check_holds_a_house_to_its_snapshot(tmp_path, capsys):
    from flawlessplan import cli
    ws = Workspace(str(tmp_path))
    ws.init()
    assert cli.main(['-w', str(tmp_path), 'check', 'cottage']) == 0
    path = os.path.join(ws.house('cottage'), 'house.yaml')
    text = open(path).read()
    open(path, 'w').write(text.replace('[3.5, 0], to: [3.5, 7.5]', '[3.8, 0], to: [3.8, 7.5]', 1))
    assert cli.main(['-w', str(tmp_path), 'check', 'cottage']) == 1
    assert 'snapshot: error' in capsys.readouterr().out


def test_an_empty_folder_can_be_set_up_from_the_tools(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp, 'WS', Workspace(str(tmp_path)))
    assert mcp.list_houses() == []
    assert 'cottage' in mcp.init_workspace()
    assert [h['house'] for h in mcp.list_houses()] == ['bungalow', 'cottage']
    assert mcp.init_workspace().startswith('already a workspace')


L_HOUSE = """house: {name: Ell, private: true}
survey:
  W: 9.0
  D: 8.0
  wing_w: {value: 4.0, status: assumed}
  main_d: 5.0
lines:
  HW: IW/2
sheets:
  - id: ground
    envelope: [[0, 0], [W, 0], [W, D], [W - wing_w, D], [W - wing_w, main_d], [0, main_d]]
    rooms:
      - {name: LIVING, at: [2, 2]}
"""


def test_a_house_is_made_and_changed_with_nothing_but_the_tools(houses):
    """An agent with no folder to write in: the guide says how, and the
    file is written, read and edited through the tools."""
    said = mcp.guide()
    assert '# Starting a house' in said and '| `envelope` |' in said and 'name: Bungalow' in said
    got = mcp.write_house('ell', L_HOUSE)
    assert got['did'] == 'made' and got['sheets'] == ['ground'] and got['changed'] == []
    assert 'ell' in [h['house'] for h in mcp.list_houses()] and mcp.read_house('ell')['text'] == L_HOUSE
    wall = "    walls:\n      - {id: split, from: [W - wing_w, 0], to: [W - wing_w, main_d]}\n    rooms:\n"
    got = mcp.edit_house('ell', '    rooms:\n', wall)
    assert got['did'] == 'edited' and any('no room in it' in i for i in got['issues'])
    got = mcp.edit_house('ell', 'at: [2, 2]}\n', 'at: [2, 2]}\n      - {name: KITCHEN, at: [7, 6]}\n')
    assert any(c.startswith('sheets.ground.rooms') for c in got['changed']) and not got['issues']
    assert mcp.write_house('ell', L_HOUSE)['did'] == 'replaced'


def test_a_house_file_that_does_not_solve_is_not_kept(houses):
    with pytest.raises(mcp.ToolError, match='would not solve'):
        mcp.write_house('broken', 'sheets: [{id: ground, envelope: [[0, 0], [NOWHERE, 0]]}]')
    assert not os.path.exists(str(houses / 'broken'))
    with pytest.raises(mcp.ToolError, match='would not solve'):
        mcp.write_house('broken', 'house: [unclosed')
    with pytest.raises(mcp.ToolError, match='will not do as a house name'):
        mcp.write_house('../elsewhere', L_HOUSE)
    before = mcp.read_house('cottage')['text']
    with pytest.raises(mcp.ToolError, match='would not solve'):
        mcp.edit_house('cottage', 'envelope: [[0, 0], [9, 0], [9, 7.5], [0, 7.5]]      # outer', 'envelope: [[0, 0]]  # outer')
    with pytest.raises(mcp.ToolError, match='2 times'):
        mcp.edit_house('cottage', 'envelope: [[0, 0], [9, 0], [9, 7.5], [0, 7.5]]', 'x')
    with pytest.raises(mcp.ToolError, match='nothing in the file'):
        mcp.edit_house('cottage', 'not in there', 'x')
    assert mcp.read_house('cottage')['text'] == before


def test_the_readme_points_to_what_the_guide_says_of_a_house_file():
    """The keys are written once, in the package, where the guide tool
    reads them; the README and the reference send a reader there."""
    from flawlessplan.page import ASSETS
    assert os.path.exists(os.path.join(ASSETS, 'house-file.md'))
    for doc, link in (('README.md', '(flawlessplan/assets/house-file.md)'), ('docs/reference.md', '(../flawlessplan/assets/house-file.md)')):
        assert link in open(os.path.join(ROOT, doc)).read(), doc


TRACED = """survey:
  W: 8.0
  sit_w: 14'4"
  sit_d: {value: 12'8", status: traced}
parts:
  shell: {envelope: [[0, 0], [W, 0], [W, 6], [0, 6]]}
levels: [ground, first]
sheets:
  - id: ground
    use: [shell]
    walls: [{id: split, from: [4.72, 0], to: [4.72, 6]}]
    rooms:
      - {name: SITTING, at: [1, 1], expect: {w: sit_w, h: sit_d}}
      - {name: KITCHEN, at: [7, 1], expect: {w: 2.93}}
  - id: first
    use: [shell]
    unlabelled: ok
"""


def test_a_room_is_held_to_the_figure_it_was_given(houses):
    """Feet and inches are kept as written, a part holds an envelope, and
    a room that does not read its quoted size is said to — once, by the
    checks, not by whoever reads the report."""
    got = mcp.write_house('traced', TRACED)
    assert got['issues'] == ['ground: warn sheets.ground.rooms[0]: SITTING reads 5.40 deep, '
                             'given as sit_d = 3.86 — 1.54 over']
    survey = mcp.measurements('traced')['survey']
    assert survey['sit_w'] == {'value': 4.3688, 'status': 'given', 'written': '14\'4"'}
    assert survey['sit_d']['status'] == 'traced' and 'written' not in survey['W']
    rep = mcp.sheet_report('traced', brief=True)
    assert rep['total'] == {'sheets': ['ground', 'first'], 'gross': 96.0, 'internal': 79.92}
    assert sorted(rep['sheets'][0]) == ['changes', 'extends', 'gross', 'hidden', 'id', 'internal', 'issues', 'level', 'rooms', 'scheme', 'zones']
    assert mcp.sheet_report('bungalow')['total']['sheets'] == ['ground']        # as it stands: not the proposal
    with pytest.raises(mcp.ToolError, match='any of w, h and area'):
        mcp.edit_house('traced', 'expect: {w: 2.93}', 'expect: {width: 2.93}')


def test_what_an_edit_changed_includes_what_is_not_measured(houses):
    mcp.write_house('traced', TRACED)
    stair = "    unlabelled: ok\n    stairs: [{id: main, path: [[6, 1], [6, 4]], treads: [12]}]\n"
    assert mcp.edit_house('traced', '    unlabelled: ok\n', stair)['changed'] == ['sheets.first.stairs: 0 → 1']
    got = mcp.edit_house('traced', 'path: [[6, 1], [6, 4]]', 'path: [[6, 1], [6, 3.7]]')['changed']
    assert got == ['sheets.first.stairs[0].path[1][1]: 4.0 → 3.7']
    got = mcp.edit_house('traced', '    unlabelled: ok\n', '    unlabelled: ok\n    notes: {unconfirmed: [The stair is a guess.]}\n')
    assert got['changed'] == ['sheets.first.notes.unconfirmed: 0 → 1']


def test_a_whole_sheet_can_be_seen(houses):
    said, picture = mcp.crop('cottage', 'ground')
    assert said == 'cottage · ground · the whole sheet' and os.path.getsize(picture.path) > 10000
    with pytest.raises(mcp.ToolError, match='leave all four out'):
        mcp.crop('cottage', 'ground', 1.0, 1.0)


# ---- what a tool is told when it is given something wrong

from conftest import ROOM
from test_cli import BROKEN


@pytest.mark.parametrize('case', sorted(BROKEN))
def test_a_broken_house_file_is_not_kept_and_is_said_as_a_refusal(houses, case):
    """Through the tool as the protocol calls it: a refusal, never a crash."""
    before = mcp.read_house('cottage')['text']
    for call in (lambda: mcp.write_house('broken', BROKEN[case]), lambda: mcp.write_house('cottage', BROKEN[case])):
        with pytest.raises(mcp.ToolError, match='not changed — the house would not solve: .+') as e:
            mcp._quiet(call)()
        assert len(str(e.value)) < 700 and 'Traceback' not in str(e.value)
    assert mcp.read_house('cottage')['text'] == before and not os.path.exists(str(houses / 'broken'))
    os.makedirs(str(houses / 'broken'))                     # and one that got there some other way
    open(str(houses / 'broken' / 'house.yaml'), 'w').write(BROKEN[case])
    for tool in (mcp.check, mcp.sheet_report, mcp.measurements, mcp.share, lambda h: mcp.at(h, 'ground', 1, 1),
                 lambda h: mcp.crop(h, 'ground'), lambda h: mcp.set_measurement(h, 'W', 9), lambda h: mcp.settle_note(h, 'ground', 'x')):
        with pytest.raises(mcp.ToolError):
            mcp._quiet(tool)('broken')
    listed = dict((h['house'], h) for h in mcp.list_houses())
    assert 'error' in listed['broken'] and 'sheets' in listed['cottage']        # listed, with what is wrong with it
    assert mcp.read_house('broken')['text'] == BROKEN[case]                             # and it can still be read, to be put right


def test_the_pages_are_shown_of_every_house_that_can_be_drawn(houses):
    os.makedirs(str(houses / 'broken'))
    open(str(houses / 'broken' / 'house.yaml'), 'w').write(BROKEN['divide'])
    said = mcp._quiet(mcp.show)()
    assert said.startswith('http://localhost:') and 'not built: ' in said and said.rstrip().endswith('broken')
    assert os.path.exists(str(houses.parent / 'build' / 'cottage' / 'index.html'))


def test_every_tool_is_wrapped_so_the_protocol_is_never_printed_on(houses, capsys):
    app = mcp.make()
    assert capsys.readouterr().out == ''
    got = mcp._quiet(mcp.sheet_report)('cottage')
    assert got['house'] == 'Cottage' and capsys.readouterr().out == ''
    mcp._quiet(mcp.show)('cottage')                         # builds, and the build prints
    io = capsys.readouterr()
    assert io.out == ''
    assert mcp._quiet(mcp.check).__name__ == 'check' and mcp._quiet(mcp.check).__doc__ == mcp.check.__doc__


@pytest.mark.parametrize('name, value, why', [
    ('nowhere', 3.0, "no measurement called 'nowhere' in survey"),
    ('YI', 3.0, 'YI is worked out in `lines`'),
    ('EW', 0.2, "no measurement called 'EW'"),
    ('infill_d', float('nan'), 'would not solve'),
    ('infill_d', float('inf'), 'would not solve'),
    ('main_w', -4.0, 'would not solve'),
    ('main_w', 0.0, 'would not solve'),
])
def test_a_measurement_that_cannot_be_set_leaves_the_file_as_it_was(houses, name, value, why):
    before = mcp.read_house('bungalow')['text']
    with pytest.raises(mcp.ToolError, match=why):
        mcp.set_measurement('bungalow', name, value)
    assert mcp.read_house('bungalow')['text'] == before


def test_a_measurement_not_written_as_a_plain_number_is_left_to_be_edited_by_hand(houses):
    mcp.write_house('traced', ROOM.replace('survey: {W: 8.0, D: 6.0}', 'survey:\n  W: 8.0\n  D: 6.0\n  sit_w: 14\'4"\n  wide: {value: 2 + 2, status: assumed}'))
    for name in ('sit_w', 'wide'):
        with pytest.raises(mcp.ToolError, match='%s is not written as a plain number in survey; edit it by hand' % name):
            mcp.set_measurement('traced', name, 4.0)
    flow = mcp.write_house('flow', ROOM)                     # survey written on one line
    with pytest.raises(mcp.ToolError, match='survey is not written as a block'):
        mcp.set_measurement('flow', 'W', 9.0)
    assert mcp.read_house('flow')['text'] == ROOM


def test_setting_a_measurement_to_what_it_is_changes_nothing(houses):
    got = mcp.set_measurement('bungalow', 'infill_d', 3.0)
    assert got['was'] == got['now'] == 3.0 and got['changed'] == ['nothing in any sheet depends on it'] and not got['issues']
    assert 'expected.json is not updated' in got['note']
    small = mcp.set_measurement('bungalow', 'infill_d', 3.25)
    assert small['now'] == 3.25 and 'infill_d: {value: 3.25, status: assumed}' in mcp.read_house('bungalow')['text']


def test_a_note_that_is_not_there_or_a_group_that_is_not_one_is_refused(houses):
    before = mcp.read_house('bungalow')['text']
    note = mcp.sheet_report('bungalow', 'infill')['sheets'][0]['notes']['unconfirmed'][0]
    for args, why in ((('bungalow', 'infill', 'No such note.'), 'no notes read exactly that'),
                      (('bungalow', 'infill', note, 'maybe'), "no group called 'maybe'"),
                      (('bungalow', 'attic', note), "no sheet called 'attic'"),
                      (('bungalow', 'infill', ''), 'notes read exactly that')):
        with pytest.raises((mcp.ToolError, ValueError), match=why):
            mcp.settle_note(*args)
    assert mcp.read_house('bungalow')['text'] == before
    assert mcp.settle_note('bungalow', 'infill', note, 'unconfirmed') == 'already under unconfirmed'
    assert mcp.read_house('bungalow')['text'] == before


def test_a_note_is_moved_as_the_report_shows_it_or_as_the_file_writes_it(houses):
    mcp.write_house('noted', ROOM + "    notes:\n      unconfirmed:\n        - 'The room is {ROOM_w:.2f} wide.'\n        - Another.\n")
    assert mcp.settle_note('noted', 'ground', 'The room is 7.40 wide.') == 'moved from unconfirmed to decided'
    assert mcp.settle_note('noted', 'ground', 'The room is {ROOM_w:.2f} wide.', 'needs') == 'moved from decided to needs'
    notes = mcp.sheet_report('noted')['sheets'][0]['notes']
    assert notes == {'summary': '', 'unconfirmed': ['Another.'], 'needs': ['The room is 7.40 wide.']}
    assert "'The room is {ROOM_w:.2f} wide.'" in mcp.read_house('noted')['text']        # still written once, still worked out


@pytest.mark.parametrize('box', [(1.0, None, None, None), (1.0, 1.0, 3.0, None), (3.0, 1.0, 1.0, 3.0), (1.0, 3.0, 3.0, 1.0),
                                 (1.0, 1.0, 1.0, 3.0), (None, None, None, 2.0)])
def test_a_box_half_given_or_inside_out_is_refused(houses, box):
    with pytest.raises(mcp.ToolError, match='give the box as x0 < x1 and y0 < y1'):
        mcp.crop('cottage', 'ground', *box)
    assert not os.path.exists(str(houses.parent / 'build' / 'cottage'))


def test_a_close_picture_says_what_it_is_of(houses):
    said, picture = mcp.crop('cottage', 'ground', 2.8, 4.0, 6.0, 7.5)
    assert said == 'cottage · ground · x 2.80–6.00, y 4.00–7.50 m' and open(picture.path, 'rb').read(4) == b'\x89PNG'
    for sheet, why in (('attic', "no sheet called 'attic'"), ('outline', "no sheet called 'outline'")):
        with pytest.raises(ValueError, match=why):
            mcp.crop('cottage', sheet)


def test_at_answers_a_point_a_radius_and_a_box_whichever_way_round(houses):
    point = mcp.at('cottage', 'ground', 1.5, 1.5)
    assert point.startswith('room ') and '\n' not in point
    assert mcp.at('cottage', 'ground', 1.5, 1.5, radius=8).startswith(point) and mcp.at('cottage', 'ground', 1.5, 1.5, radius=8).count('\n') > 5
    assert mcp.at('cottage', 'ground', 0, 0, x1=9, y1=7.5) == mcp.at('cottage', 'ground', 9, 7.5, x1=0, y1=0)
    assert mcp.at('cottage', 'ground', -50, -50) == 'outside the building'
    assert mcp.at('cottage', 'ground', 1.5, 1.5, x1=3.0) == point               # half a box is a point


def test_a_report_can_be_of_one_sheet_or_brief(houses):
    whole = mcp.sheet_report('cottage')
    assert [f['id'] for f in whole['sheets']] == ['ground', 'first'] and whole['source'].endswith('cottage/house.yaml')
    one = mcp.sheet_report('cottage', 'first')
    assert [f['id'] for f in one['sheets']] == ['first'] and one['total'] == whole['total']
    brief = mcp.sheet_report('cottage', brief=True)
    assert 'source' not in brief and all('openings' not in f and 'notes' not in f and 'rooms' in f for f in brief['sheets'])
    with pytest.raises(mcp.ToolError, match="no sheet called 'attic'"):
        mcp.sheet_report('cottage', 'attic')
    said = mcp.check('cottage')
    assert said == 'nothing found' or all(': info ' in line for line in said.split('\n'))


def test_check_gives_the_worst_first(houses):
    mcp.write_house('gap', ROOM + "      - {name: OTHER, at: [7, 5]}\n    walls: [{id: stub, from: [4, 0], to: [4, 3]}]\n")
    said = mcp.check('gap').split('\n')
    assert said[0].startswith('ground: error') and 'the same space' in said[0] and said[-1].startswith('ground: info')


def test_a_private_house_is_listed_drawn_and_sent_on_this_machine_only(houses):
    mcp.write_house('secret', 'house: {name: Secret Lodge, private: true}\n' + ROOM)
    assert 'secret' in [h['house'] for h in mcp.list_houses()]
    assert open(mcp.share('secret')).read().count('<title>Secret Lodge</title>') == 1      # the owner's to send
    url = mcp.show('secret')
    assert url.split()[0].endswith('/secret/') and os.path.isdir(str(houses.parent / 'build' / 'secret'))
    assert not os.path.exists(str(houses.parent / 'public'))                               # nothing here hosts anything


def test_show_serves_one_workspace_once_however_often_it_is_asked(houses):
    a, b = mcp.show().split()[0], mcp.show('cottage').split()[0]
    assert b == a + 'cottage/' and len(mcp.PAGES) == 1
    with pytest.raises(mcp.ToolError, match='no house called'):
        mcp.show('nowhere')


def test_marks_come_back_as_the_brief_and_each_picture_it_speaks_of(houses):
    assert mcp.marks('cottage') == ['nothing drawn on cottage yet']
    json.dump([{'type': 'pen', 'sheet': 'ground', 'ts': 1000, 'pts': [[2, 2], [2.5, 2.5], [3, 2]]}], open(str(houses / 'cottage' / 'marks.json'), 'w'))
    brief, *rest = mcp.marks('cottage')
    assert '## How to read this' in brief and len(rest) == 4                    # two pictures, each with its path before it
    assert rest[0].endswith('ground-1.png') and rest[2].endswith('ground-sheet.png') and os.path.exists(rest[1].path)


def test_marks_built_in_are_closed_and_no_longer_sent(houses):
    dest = str(houses / 'cottage' / 'marks.json')
    json.dump([{'type': 'pen', 'sheet': 'ground', 'ts': 1759800000000, 'pts': [[2, 2], [2.5, 2.5], [3, 2]]},
               {'type': 'note', 'sheet': 'first', 'ts': 1759800005000, 'x': 4, 'y': 4, 'text': 'smaller'}], open(dest, 'w'))
    assert len(mcp.marks('cottage')) == 9 and len(mcp.marks('cottage', sheet='first')) == 5
    tool = lambda fn: mcp._quiet(fn)                                 # as the protocol calls it: a refusal, said
    with pytest.raises(mcp.ToolError, match="no mark called 'm1'"):
        tool(mcp.resolve_marks)('cottage', ['m1'], 'done')
    with pytest.raises(mcp.ToolError, match="no sheet called 'attic'"):
        tool(mcp.resolve_marks)('cottage', ['mmgfvhedc'], 'done', ['attic'])
    with pytest.raises(mcp.ToolError, match="no sheet called 'attic'"):
        tool(mcp.marks)('cottage', sheet='attic')
    assert mcp.resolve_marks('cottage', ['mmgfvhedc'], 'The door is hung the other way.', ['ground', 'first']) \
        == 'mmgfvhedc: resolved, applied to ground, first'
    brief, *rest = mcp.marks('cottage')
    assert len(rest) == 4 and 'mmgfvhedc' not in brief and '1 mark already resolved is left out' in brief
    assert mcp.marks('cottage', sheet='ground') == ['cottage, sheet ground: nothing still open — 1 resolved (ask for resolved marks to see them)']
    brief, *rest = mcp.marks('cottage', include_resolved=True, sheet='ground')
    assert len(rest) == 4 and 'The door is hung the other way. — applied to `ground`, `first`' in brief
    mcp.resolve_marks('cottage', ['mmgfvhi88'], 'Made smaller.')
    assert mcp.marks('cottage') == ['cottage: nothing still open — 2 resolved (ask for resolved marks to see them)']
    assert mcp.resolve_marks('cottage', ['mmgfvhi88'], '', reopen=True) == 'mmgfvhi88: opened again'
    assert len(mcp.marks('cottage')) == 5


def test_an_edit_that_makes_one_room_of_two_says_what_is_still_standing_in_it(houses):
    plain = mcp.edit_house('cottage', 'name: LIVING', 'name: SITTING')
    assert 'still_standing' not in plain
    # a house of two rooms parted by two walls in line, one with the door: take the other out
    two = """
survey: {W: 8.0, D: 6.0}
lines: {MID: W/2, HY: D/2}
sheets:
  - id: ground
    envelope: [[0, 0], [W, 0], [W, D], [0, D]]
    walls:
      - {id: split, from: [MID, 0], to: [MID, HY]}
      - {id: rest, from: [MID, HY], to: [MID, D]}
    openings:
      - {door: std, wall: split, at: centre, swing: e}
    rooms:
      - {name: LEFT, at: [1, 1]}
      - {name: RIGHT, at: [7, 1]}
  - id: after
    level: ground
    changes: ground
    envelope: [[0, 0], [W, 0], [W, D], [0, D]]
    walls:
      - {id: split, from: [MID, 0], to: [MID, HY]}
      - {id: rest2, from: [MID, HY], to: [MID, D]}
    openings:
      - {door: std, wall: split, at: centre, swing: e}
    rooms:
      - {name: LEFT, at: [1, 1]}
      - {name: RIGHT, at: [7, 1]}
"""
    mcp.write_house('two', two)
    out = mcp.edit_house('two', "      - {id: rest2, from: [MID, HY], to: [MID, D]}\n", '')
    assert out['still_standing'] == ['after: still standing inside LEFT (LEFT, RIGHT were apart): wall split; the door in split at (4.00, 1.50)']
    assert any('after: warn wall split has LEFT on both its faces' in i for i in out['issues'])
    again = mcp.edit_house('two', 'name: LEFT, at: [1, 1]}\n      - {name: RIGHT, at: [7, 1]}\n  - id: after', 'name: LEFT, at: [1, 1]}\n  - id: after')
    assert 'still_standing' not in again            # said when it happens, and after that by check
    mcp.write_house('two', two)
    whole = mcp.write_house('two', two.replace("      - {id: rest, from: [MID, HY], to: [MID, D]}\n", ''))
    assert whole['still_standing'] == ['ground: still standing inside LEFT (LEFT, RIGHT were apart): wall split; the door in split at (4.00, 1.50)']


def test_an_edit_must_name_one_passage_and_only_one(houses):
    before = mcp.read_house('cottage')['text']
    for old, why in (('', 'nothing in the file reads exactly that'), ('zzz not there', 'nothing in the file reads exactly that'),
                     ('envelope', r'that is in the file \d+ times')):
        with pytest.raises(mcp.ToolError, match=why):
            mcp.edit_house('cottage', old, 'x')
    assert mcp.read_house('cottage')['text'] == before
    same = mcp.edit_house('cottage', before.split('\n')[0], before.split('\n')[0])
    assert same['did'] == 'edited' and same['changed'] == [] and mcp.read_house('cottage')['text'] == before


def test_an_agent_puts_sheets_in_order_and_hides_them_and_cannot_bin_one(houses):
    text = mcp.read_house('bungalow')['text']
    mcp.write_house('bungalow', text + '  - id: bare\n    level: ground\n    envelope: [[0, 0], [5, 0], [5, 5], [0, 5]]\n    unlabelled: ok\n')
    v = mcp.read_house('bungalow')['version']
    out = mcp.order_sheets('bungalow', ['bare', 'ground', 'infill'], version=v)
    assert out['house'] == 'bungalow' and out['sheets'] == ['bare', 'ground', 'infill'] and out['version'] != v
    assert [s['id'] for s in mcp.list_houses()[0]['sheets']] == ['bare', 'ground', 'infill']
    with pytest.raises(mcp.ToolError, match='infill must come after ground'):
        mcp.order_sheets('bungalow', ['infill', 'ground'])
    with pytest.raises(mcp.ToolError, match='is not as it was at version'):
        mcp.hide_sheet('bungalow', 'bare', version=v)
    hid = mcp.hide_sheet('bungalow', 'bare')
    assert hid['did'] == 'hidden' and [(s['id'], s['hidden']) for s in mcp.list_houses()[0]['sheets']] == [('bare', True), ('ground', False), ('infill', False)]
    assert 'BARE' not in open(mcp.share('bungalow')).read() and mcp.check('bungalow')                # not sent; still checked
    assert mcp.sheet_report('bungalow', 'bare')['sheets'][0]['hidden'] is True
    assert mcp.hide_sheet('bungalow', 'bare', hidden=False)['did'] == 'shown again'
    assert not [name for _, name, _ in mcp.TOOLS if 'bin' in name]                               # binning is the owner's, on the page


def test_an_edit_lists_the_subs_with_a_figure_in_them_on_rooms_it_resized(houses):
    """A line under a room's name that says a size by hand goes stale when
    the room changes; nothing can tell if it has, so it is put in front of
    whoever made the change."""
    text = mcp.read_house('bungalow')['text']
    mcp.write_house('bungalow', text.replace("- {name: LIVING, at: [EW + living_w/2, YS/2]}",
                                             '- {name: LIVING, at: [EW + living_w/2, YS/2], sub: "plus 3.00 × 2.75 return"}')
                    .replace("- {name: KITCHEN, at: [(LIVING_E + main_w)/2, 2.0]}",
                             '- {name: KITCHEN, at: [(LIVING_E + main_w)/2, 2.0], sub: "{area:.1f} m² with its 2 doors"}'))
    out = mcp.set_measurement('bungalow', 'living_w', 5.0)
    assert 'check_subs' not in out                                          # set_measurement answers in its own words
    out = mcp.edit_house('bungalow', 'LIVING_E: EW + living_w + HW', 'LIVING_E: EW + living_w + HW + 0.2')
    assert out['check_subs'][0] == ('ground: LIVING says "plus 3.00 × 2.75 return" — a figure written by hand, '
                                    'and the room has changed: check it still holds')
    assert out['check_subs'][1].startswith('ground: KITCHEN says "{area:.1f} m² with its 2 doors"')         # as written: the 2 is by hand
    assert [c.split(':')[1].strip().split(' says')[0] for c in out['check_subs']] == ['LIVING', 'KITCHEN', 'LIVING', 'KITCHEN']
    plain = mcp.edit_house('bungalow', 'with its 2 doors', 'with its doors')
    assert 'check_subs' not in plain                                        # no room moved
    out = mcp.edit_house('bungalow', 'LIVING_E: EW + living_w + HW + 0.2', 'LIVING_E: EW + living_w + HW + 0.4')
    assert [c.split(':')[1].strip().split(' says')[0] for c in out['check_subs']] == ['LIVING', 'LIVING']       # a figure from a name follows the plan
    gone = mcp.edit_house('bungalow', "      - {name: BEDROOM, at: [(WING_W + main_w)/2, YS + wing_d/2], size: small}\n", '')
    assert len(gone['check_subs']) == 2 and 'ground: LIVING says' in gone['check_subs'][0]     # a room fewer: any of them may be meant


def test_the_page_is_opened_on_a_sheet(houses):
    url = mcp.show('bungalow', 'infill').split()[0]
    assert url.endswith('/bungalow/#infill')
    import urllib.request
    assert 'function named()' in urllib.request.urlopen(url.split('#')[0] + 'index.html').read().decode()
    with pytest.raises(ValueError, match="no sheet called 'attic'"):
        mcp.show('bungalow', 'attic')
    with pytest.raises(mcp.ToolError, match='name the house whose sheet it is'):
        mcp.show(sheet='infill')
    mcp.hide_sheet('bungalow', 'infill')
    with pytest.raises(mcp.ToolError, match='infill is hidden: it has no tab to open on'):
        mcp.show('bungalow', 'infill')


def test_what_was_built_is_set_beside_what_was_drawn(houses):
    """Marks drawn on one sheet, resolved, and shown on another they were applied to."""
    json.dump([{'type': 'pen', 'sheet': 'ground', 'ts': 1759800000000, 'pts': [[2, 2], [2.5, 2.5], [3, 2]]},
               {'type': 'note', 'sheet': 'ground', 'ts': 1759800005000, 'x': 3, 'y': 3, 'text': 'wider'}], open(str(houses / 'bungalow' / 'marks.json'), 'w'))
    mcp.resolve_marks('bungalow', ['mmgfvhedc', 'mmgfvhi88'], 'Made wider.', ['ground', 'infill'])
    said, png = mcp.crop('bungalow', 'infill', mark_ids=['mmgfvhedc', 'mmgfvhi88'])
    assert said == 'bungalow · infill · what was built, beside what was drawn: marks mmgfvhedc, mmgfvhi88'
    svg = open(str(png.path)[:-4] + '.svg').read()
    assert 'WHAT WAS BUILT: THE DRAWING AS IT IS NOW' in svg and 'WHAT WAS DRAWN: THE SAME VIEW, WITH THE INK' in svg
    assert svg.count('<polyline') == 1 and '>wider</text>' in svg and '#D0199B' in svg and '#8A9590' not in svg    # the ink in its own colour
    assert 'x 1.25–3.75, y 1.25–3.75 m' in svg                             # framed round the marks
    said, png = mcp.crop('bungalow', 'infill', 1, 1, 5, 5, mark_ids=['mmgfvhedc'])
    assert said == 'bungalow · infill · x 1.00–5.00, y 1.00–5.00 m' and 'WHAT WAS BUILT' in open(str(png.path)[:-4] + '.svg').read()
    plain = open(str(mcp.crop('bungalow', 'ground', 1, 1, 5, 5, marks=True)[1].path)[:-4] + '.svg').read()
    assert '<polyline' not in plain and 'WHAT WAS BUILT' not in plain          # resolved: not on a crop that asks for the open ones
    with pytest.raises(ValueError, match="no mark called 'nope'"):
        mcp.crop('bungalow', 'infill', mark_ids=['nope'])


def test_the_sheet_a_sheet_extends_is_listed_and_reported(houses):
    text = mcp.read_house('bungalow')['text']
    mcp.write_house('bungalow', text + '  - id: bare\n    extends: infill\n    omit: [wing_old]\n    unlabelled: ok\n')
    listed = [h for h in mcp.list_houses() if h['house'] == 'bungalow'][0]['sheets']
    assert [(s['id'], s['changes'], s['extends']) for s in listed] == [('ground', None, None), ('infill', 'ground', None), ('bare', 'ground', 'infill')]
    rep = mcp.sheet_report('bungalow', 'bare')['sheets'][0]
    assert rep['extends'] == 'infill' and rep['changes'] == 'ground' and 'wing_old' not in [o['wall'] for o in rep['openings']]
    assert 'wing_old' in [o['wall'] for o in mcp.sheet_report('bungalow', 'infill')['sheets'][0]['openings']]


def test_several_passages_are_changed_at_once_and_solved_once(houses):
    """A name, the line stepped off it and the wall on that line: none of
    the three solves without the others, in any order they could be made."""
    text = mcp.read_house('bungalow')['text']
    assert 'LARDER_X' not in text and 'larder_w' not in text and text.count('\nsurvey:\n') == 1 and text.count('\nlines:\n') == 1
    walls = [ln for ln in text.split('\n') if ln.strip() == 'walls:'][0] + '\n'
    first = text[text.index(walls):].split('\n')[1] + '\n'               # the first wall of the first list of them
    assert text.count(first) == 1
    edits = [{'old': first, 'new': first + first[:len(first) - len(first.lstrip())] + '- {id: larder_w, from: [LARDER_X, 0.3], to: [LARDER_X, 1.0]}\n'},
             {'old': '\nlines:\n', 'new': '\nlines:\n  LARDER_X: larder_in + 0.5\n'},
             {'old': '\nsurvey:\n', 'new': '\nsurvey:\n  larder_in: 1.0\n'}]
    for one in edits[:2]:
        with pytest.raises(mcp.ToolError, match='would not solve'):
            mcp.edit_house('bungalow', one['old'], one['new'])
    v = mcp.read_house('bungalow')['version']
    out = mcp.edit_house('bungalow', edits=edits, version=v)
    assert out['did'] == 'edited' and out['version'] != v
    assert mcp.measurements('bungalow')['lines']['LARDER_X'] == 1.5
    assert 'larder_w' in mcp.read_house('bungalow')['text'] and any('larder_w' in c for c in out['issues'] + [mcp.check('bungalow')])
    with pytest.raises(mcp.ToolError, match='already in it once'):          # tried again with the version it had
        mcp.edit_house('bungalow', edits=edits, version=v)
    # a later edit works on what an earlier one wrote
    two = mcp.edit_house('bungalow', edits=[{'old': 'larder_in: 1.0', 'new': 'larder_in: 1.2'}, {'old': 'larder_in: 1.2', 'new': 'larder_in: 1.4'}])
    assert mcp.measurements('bungalow')['survey']['larder_in']['value'] == 1.4 and two['version'] != out['version']


@pytest.mark.parametrize('edits, why', [
    ([{'old': 'name: LIVING', 'new': 'name: SITTING'}, {'old': 'name: LIVING', 'new': 'name: LOUNGE'}],
     r'edits\[1\]: nothing in the file reads exactly that: .* \(as the edits before it leave the file\)'),
    ([{'old': 'name: LIVING', 'new': 'name: SITTING'}, {'old': 'levels: [ground, first]', 'new': 'levels: [ground'}], 'would not solve'),
    ([{'old': 'name: NOWHERE', 'new': 'x'}], r'edits\[0\]: nothing in the file reads exactly that: give a passage that is there exactly once, '
                                             r'with enough round it to be the only one$'),
    ([{'old': 'name', 'new': 'x'}], r'edits\[0\]: that is in the file \d+ times'),
    ([{'old': '', 'new': 'x'}], r'edits\[0\]: nothing in the file'),
    ([], 'list of {old, new}'), ('name: LIVING', 'list of {old, new}'), ([{'old': 'a'}], 'list of {old, new}'),
    ([{'old': 'a', 'new': 'b', 'also': 'c'}], 'list of {old, new}'), ([{'old': 'a', 'new': 7}], 'list of {old, new}'), ([['a', 'b']], 'list of {old, new}'),
    ([{'old': 'name: LIVING', 'new': 'x' * 400001}], 'too long'),
])
def test_edits_are_all_kept_or_none(houses, edits, why):
    before = mcp.read_house('cottage')
    with pytest.raises(mcp.ToolError, match=why):
        mcp.edit_house('cottage', edits=edits)
    assert mcp.read_house('cottage') == before


def test_an_edit_is_one_passage_or_a_list_of_them_not_both_and_not_neither(houses):
    for args, kw in ((('cottage',), {}), (('cottage', 'name: LIVING'), {}), (('cottage',), {'new': 'x'})):
        with pytest.raises(mcp.ToolError, match='give `old` and `new`, or `edits`: a list'):
            mcp.edit_house(*args, **kw)
    with pytest.raises(mcp.ToolError, match='not both'):
        mcp.edit_house('cottage', 'name: LIVING', 'name: SITTING', edits=[{'old': 'name: HALL', 'new': 'name: LOBBY'}])
    assert 'SITTING' not in mcp.read_house('cottage')['text']


def test_a_house_file_is_kept_as_it_was_written(houses):
    text = '# a comment at the top\n' + ROOM + '# and one at the end, with no newline after it'
    assert mcp.write_house('kept', text)['did'] == 'made'
    assert mcp.read_house('kept')['text'] == text + '\n'            # a file ends in a newline; nothing else is touched
    assert mcp.write_house('kept', text + '\n')['changed'] == []
    assert sorted(os.listdir(str(houses / 'kept'))) == ['house.yaml']


def test_the_instructions_say_how_to_start_and_what_not_to_do():
    said = mcp.INSTRUCTIONS
    for must in ('call `guide` first', 'written down once', 'set_measurement', 'say back to the owner', 'x east and y south',
                 'close it with `resolve_marks` in the same turn'):
        assert must in said
    assert [name for _, name, _ in mcp.TOOLS] == ['list_houses', 'guide', 'init_workspace', 'check', 'report', 'show', 'share',
                                                 'measurements', 'at', 'crop', 'marks', 'resolve_marks', 'set_measurement', 'read_house',
                                                 'write_house', 'edit_house', 'add_to_house', 'order_sheets', 'hide_sheet', 'settle_note']


def test_only_a_note_in_a_group_can_be_settled(houses):
    mcp.write_house('listed', ROOM + "    notes:\n      - Just a note in a plain list.\n      - 'key: value'\n")
    with pytest.raises(mcp.ToolError, match="that line is not a note in a group \\(it is under 'notes'\\)"):
        mcp.settle_note('listed', 'ground', 'Just a note in a plain list.')
    mcp.write_house('odd', ROOM + "    notes:\n      about:\n        - \"an 'odd' one\"\n        - Plain.\n    labels:\n      - {at: [2, 2], text: Plain.}\n")
    assert mcp.settle_note('odd', 'ground', "an 'odd' one") == 'moved from about to decided'
    assert mcp.settle_note('odd', 'ground', 'Plain.') == 'moved from about to decided'
    assert mcp.sheet_report('odd')['sheets'][0]['notes'] == {'summary': '', 'decided': ["an 'odd' one", 'Plain.']}


def test_a_picture_that_was_not_made_is_said_not_handed_over(tmp_path):
    with pytest.raises(mcp.ToolError, match='no picture was made of gone.png'):
        mcp._png(str(tmp_path / 'gone.png'))


def test_a_house_that_did_not_solve_can_be_replaced_by_one_that_does(houses):
    os.makedirs(str(houses / 'mended'))
    open(str(houses / 'mended' / 'house.yaml'), 'w').write('a: [')
    got = mcp.write_house('mended', ROOM)
    assert got['did'] == 'replaced' and got['changed'] == [] and got['sheets'] == ['ground']      # nothing to compare it with


# ---- one more entry, and writing over what was read

def test_an_entry_is_added_to_a_list_without_quoting_what_is_there(houses):
    mcp.write_house('ell', L_HOUSE)
    got = mcp.add_to_house('ell', 'sheets.ground.walls', '{id: split, from: [5, 0], to: [5, main_d]}')
    assert got['did'] == 'added' and got['to'] == 'sheets.ground.walls' and "sheets.ground.rooms[0].shape: 'irregular' → 'rect'" in got['changed']
    assert any('no room in it' in i for i in got['issues'])                     # the list was not there, and is begun
    assert '    walls:\n      - {id: split, from: [5, 0], to: [5, main_d]}\n' in mcp.read_house('ell')['text']
    got = mcp.add_to_house('ell', 'sheets.ground.rooms', '- {name: KITCHEN, at: [7, 6]}')      # its dash is not needed, and does no harm
    assert not got['issues'] and '      - {name: LIVING, at: [2, 2]}\n      - {name: KITCHEN, at: [7, 6]}\n' in mcp.read_house('ell')['text']
    assert mcp.add_to_house('ell', 'lines', 'MID: W/2')['changed'] == []
    assert '  HW: IW/2\n  MID: W/2\nsheets:' in mcp.read_house('ell')['text']
    mcp.add_to_house('ell', 'sheets.ground.notes.decided', 'The wall between them stays.')
    mcp.add_to_house('ell', 'sheets.ground.notes.decided', '"Quoted: it has a colon."')
    assert mcp.sheet_report('ell', 'ground')['sheets'][0]['notes']['decided'] == ['The wall between them stays.', 'Quoted: it has a colon.']
    mcp.add_to_house('ell', 'sheets.ground.openings', 'wall: split\ncentre: 2\ndoor: std')    # an entry written over several lines
    assert '      - wall: split\n        centre: 2\n        door: std\n' in mcp.read_house('ell')['text']
    assert [o['wall'] for o in mcp.sheet_report('ell', 'ground')['sheets'][0]['openings']] == ['split']


def test_a_new_name_is_one_line_more_and_nothing_else_moves(houses):
    mcp.write_house('ell', L_HOUSE)
    got = mcp.add_to_house('ell', 'survey', 'spare: 1.25')
    now = mcp.read_house('ell')['text']
    assert got['changed'] == [] and mcp.measurements('ell')['survey']['spare']['value'] == 1.25
    assert now == L_HOUSE.replace('  main_d: 5.0\n', '  main_d: 5.0\n  spare: 1.25\n')


@pytest.mark.parametrize('to, entry, why', [
    ('sheets.ground.rooms', '{name: NOWHERE}', 'would not solve'),
    ('sheets.attic.walls', '{from: [0, 0], to: [1, 1]}', 'nothing in the file is laid out as `sheets.attic`'),
    ('nothing', '{a: 1}', 'nothing in the file is laid out as `nothing`'),
    ('survey', 'W: 12', 'a name that is there already is changed, not added'),
    ('sheets.ground.envelope', '[4, 4]', 'nothing in the file is laid out as `sheets.ground.envelope`'),
    ('sheets.ground.rooms', '{name: A, at: [1, 1]}\n- {name: B, at: [7, 6]}', 'did not go in as one new entry'),
    ('sheets.ground.rooms', '', 'say where it goes'),
    ('', '{a: 1}', 'say where it goes'),
    ('house', 'x: 1', 'nothing in the file is laid out as `house`'),
])
def test_what_cannot_be_added_as_one_entry_is_refused_and_nothing_changes(houses, to, entry, why):
    mcp.write_house('ell', L_HOUSE)
    with pytest.raises(mcp.ToolError, match=re.escape(why)):
        mcp.add_to_house('ell', to, entry)
    assert mcp.read_house('ell')['text'] == L_HOUSE


def test_a_list_level_with_its_key_and_a_sheet_given_by_name_are_added_to(houses):
    level = ("sheets:\n- id: g\n  envelope: [[0, 0], [8, 0], [8, 6], [0, 6]]\n  rooms:\n  - {name: A, at: [1, 1]}\n"
             "  # what comes after\n- id: up\n  level: g\n  envelope: [[0, 0], [8, 0], [8, 6], [0, 6]]\n  unlabelled: ok\n")
    mcp.write_house('level', level)
    mcp.add_to_house('level', 'sheets.g.walls', '{id: w, from: [4, 0], to: [4, 6]}')
    mcp.add_to_house('level', 'sheets.g.rooms', '{name: B, at: [7, 1]}')
    assert mcp.read_house('level')['text'] == level.replace("  # what comes after\n", "  - {name: B, at: [7, 1]}\n  walls:\n    - {id: w, from: [4, 0], to: [4, 6]}\n  # what comes after\n")
    named = "sheets:\n  g:\n    envelope: [[0, 0], [8, 0], [8, 6], [0, 6]]\n    rooms:\n      - {name: A, at: [1, 1]}\n"
    mcp.write_house('named', named)
    mcp.add_to_house('named', 'sheets.g.labels', '{at: [4, 3], text: hello}')
    assert mcp.read_house('named')['text'] == named + "    labels:\n      - {at: [4, 3], text: hello}\n"


def test_a_change_given_the_version_it_writes_over_is_refused_when_the_file_has_moved_on(houses):
    made = mcp.write_house('ell', L_HOUSE)
    read = mcp.read_house('ell')
    assert read == {'house': 'ell', 'version': made['version'], 'text': L_HOUSE} and re.match(r'^[0-9a-f]{10}\Z', read['version'])
    room = ('at: [2, 2]}\n', 'at: [2, 2]}\n      - {name: KITCHEN, at: [7, 6]}\n')
    one = mcp.edit_house('ell', room[0], room[1], version=read['version'])
    assert one['version'] != read['version'] and one['version'] == mcp.read_house('ell')['version']
    # the same call again, as after a time-out: the passage is still there once, and would be written twice
    with pytest.raises(mcp.ToolError, match='not as it was at version %s .it is now %s., and what this writes is already in it once' % (read['version'], one['version'])):
        mcp.edit_house('ell', room[0], room[1], version=read['version'])
    assert mcp.read_house('ell')['text'].count('KITCHEN') == 1
    with pytest.raises(mcp.ToolError, match=r'not as it was at version \w+ .it is now \w+.\. Read it again'):
        mcp.add_to_house('ell', 'sheets.ground.walls', '{id: split, from: [5, 0], to: [5, main_d]}', version=read['version'])
    with pytest.raises(mcp.ToolError, match='not as it was'):
        mcp.write_house('ell', L_HOUSE, version=read['version'])
    with pytest.raises(mcp.ToolError, match='already in it once'):
        mcp.add_to_house('ell', 'sheets.ground.rooms', '{name: KITCHEN, at: [7, 6]}', version=read['version'])
    assert mcp.read_house('ell')['version'] == one['version']
    two = mcp.add_to_house('ell', 'sheets.ground.walls', '{id: split, from: [5, 0], to: [5, main_d]}', version=one['version'])
    assert mcp.write_house('ell', L_HOUSE, version=two['version'])['version'] == read['version']        # the same text is the same version
    assert mcp.set_measurement('ell', 'W', 9.5)['version'] == mcp.read_house('ell')['version']
    with pytest.raises(mcp.ToolError, match='no house nowhere-yet for that to be a version of'):
        mcp.write_house('nowhere-yet', L_HOUSE, version=read['version'])
    assert 'nowhere-yet' not in [h['house'] for h in mcp.list_houses()]


def test_a_change_with_no_version_is_made_as_it_always_was(houses):
    mcp.write_house('ell', L_HOUSE)
    assert mcp.edit_house('ell', 'name: Ell', 'name: Elm')['did'] == 'edited' and mcp.write_house('ell', L_HOUSE)['did'] == 'replaced'
