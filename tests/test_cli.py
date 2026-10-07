# -*- coding: utf-8 -*-
"""The command line, each command as a person types it: what it writes,
what it prints, what it exits with — and a workspace, which is where every
command looks for houses and puts drawings."""
import json
import os
import pytest

from conftest import ROOM, ROOT
from flawlessplan import __version__, cli
from flawlessplan.workspace import Workspace, EXAMPLES

SECRET = 'house: {name: Secret Lodge, private: true}\n' + ROOM


def run(ws, *args):
    return cli.main(['-w', ws.root] + list(args))


def add(ws, name, text):
    os.makedirs(os.path.join(ws.houses, name))
    path = os.path.join(ws.houses, name, 'house.yaml')
    with open(path, 'w') as fh:
        fh.write(text)
    return path


def tree(root):
    return sorted(os.path.relpath(os.path.join(d, f), root) for d, _, fs in os.walk(root) for f in fs)


# ---- a workspace

def test_init_makes_a_workspace_and_leaves_one_alone(tmp_path, capsys):
    root = str(tmp_path / 'mine')
    assert cli.main(['init', root]) == 0
    made = capsys.readouterr().out.split('\n')
    assert sorted(os.listdir(root)) == ['.gitignore', '.mcp.json', 'CLAUDE.md', 'houses']
    assert sorted(os.listdir(os.path.join(root, 'houses'))) == ['bungalow', 'cottage']
    assert os.path.join(root, 'houses', 'cottage') in made and len([m for m in made if m]) == 5
    assert json.load(open(os.path.join(root, '.mcp.json')))['mcpServers']['flawlessplan']['args'] == ['mcp']
    assert 'houses/*/marks.json' in open(os.path.join(root, '.gitignore')).read()       # what is drawn is the owner's, not the repo's
    assert cli.main(['init', root]) == 0 and capsys.readouterr().out.strip() == 'nothing to do: already a workspace'


def test_init_touches_nothing_that_is_already_there(tmp_path):
    (tmp_path / 'CLAUDE.md').write_text('mine')
    (tmp_path / 'houses' / 'cottage').mkdir(parents=True)
    (tmp_path / 'houses' / 'cottage' / 'house.yaml').write_text('mine too')
    made = Workspace(str(tmp_path)).init()
    assert (tmp_path / 'CLAUDE.md').read_text() == 'mine'
    assert (tmp_path / 'houses' / 'cottage' / 'house.yaml').read_text() == 'mine too'
    assert sorted(os.path.basename(m) for m in made) == ['.gitignore', '.mcp.json', 'bungalow']


def test_a_bare_workspace_has_no_houses(tmp_path, capsys):
    assert cli.main(['-w', str(tmp_path), 'init', '--bare']) == 0
    assert Workspace(str(tmp_path)).names() == [] and os.path.isdir(str(tmp_path / 'houses'))
    assert cli.main(['-w', str(tmp_path), 'check', 'cottage']) == 1
    err = capsys.readouterr().err
    assert 'no house called' in err and 'try `flawlessplan init`' in err


def test_which_workspace_is_the_flag_then_the_environment_then_this_folder(tmp_path, monkeypatch):
    a, b, c = [str(tmp_path / n) for n in 'abc']
    for d in (a, b, c):
        os.makedirs(d)
    monkeypatch.chdir(c)
    monkeypatch.delenv('FLAWLESSPLAN_WORKSPACE', raising=False)
    assert os.path.realpath(Workspace().root) == os.path.realpath(c)
    monkeypatch.setenv('FLAWLESSPLAN_WORKSPACE', b)
    assert Workspace().root == b and Workspace(a).root == a
    ws = Workspace(a, houses=EXAMPLES)
    assert ws.houses == EXAMPLES and ws.names() == ['bungalow', 'cottage'] and ws.build == os.path.join(a, 'build')
    assert Workspace(a).names() == []                       # no houses folder yet: none, and no error


def test_a_workspace_lists_only_folders_that_hold_a_house(ws):
    os.makedirs(os.path.join(ws.houses, 'empty'))
    open(os.path.join(ws.houses, 'notes.txt'), 'w').write('x')
    assert ws.names() == ['bungalow', 'cottage'] and ws.every() == [ws.house('bungalow'), ws.house('cottage')]
    assert ws.marks('cottage') == os.path.join(ws.houses, 'cottage', 'marks.json')
    assert ws.find('cottage') == ws.house('cottage') and ws.find(EXAMPLES) == EXAMPLES


@pytest.mark.parametrize('name', ['..', '.', '', '../cottage', 'cottage/..', '/etc', 'a/b', 'a\\b', '-rf', '.git', 'a b',
                                  'cottage\n', 'c\x00', 'ü', '~', 'cottage/', './cottage'])
def test_a_house_name_is_a_plain_name(ws, name):
    with pytest.raises(ValueError, match='no house called'):
        ws.house(name)
    with pytest.raises(ValueError, match='will not do as a house name'):
        ws.place(name)


def test_a_new_house_may_be_given_any_plain_name(ws):
    for name in ('new', 'New-House_2', '2b', 'x'):
        assert ws.place(name) == os.path.join(ws.houses, name)
    with pytest.raises(ValueError, match='have bungalow, cottage'):
        ws.house('new')


# ---- build

def test_build_draws_everything_a_house_has(ws, capsys):
    assert run(ws, 'build', 'cottage') == 0
    out = os.path.join(ws.build, 'cottage')
    assert sorted(os.listdir(out)) == ['cottage-plans.html', 'first.md', 'first.svg', 'ground.md', 'ground.svg',
                                       'index.html', 'outline.md', 'outline.svg', 'report.json']
    said = capsys.readouterr().out
    assert said.startswith('Cottage -> ') and 'ground' in said and 'm² gross' in said and 'KITCHEN' in said
    rep = json.load(open(os.path.join(out, 'report.json')))
    assert rep['house'] == 'Cottage' and [f['id'] for f in rep['sheets']] == ['ground', 'first']
    assert open(os.path.join(out, 'ground.svg')).read().startswith('<svg') and '# GROUND FLOOR' in open(os.path.join(out, 'ground.md')).read()
    page = open(os.path.join(out, 'index.html')).read()
    assert 'href="cottage-plans.html" download' in page and 'class="home"' not in page    # built alone: no index to go back to
    assert not os.path.exists(os.path.join(ws.build, 'index.html'))


def test_build_with_no_house_draws_them_all_and_the_index(ws, capsys):
    assert run(ws, 'build') == 0
    assert sorted(os.listdir(ws.build)) == ['bungalow', 'cottage', 'fonts', 'icon-180.png', 'icon-192.png', 'icon-512.png',
                                            'icon-maskable-512.png', 'icon.svg', 'index.html', 'manifest.webmanifest']
    index = open(os.path.join(ws.build, 'index.html')).read()
    assert 'href="cottage/index.html"' in index and 'href="bungalow/index.html"' in index and '2 houses' in index
    assert 'class="home" href="../index.html"' in open(os.path.join(ws.build, 'cottage', 'index.html')).read()
    assert capsys.readouterr().out.count(' -> ') == 2       # each house's rooms as measured
    assert run(ws, 'build', '--quiet') == 0 and capsys.readouterr().out == ''
    assert not os.path.exists(os.path.join(ws.build, 'vercel.json')) and not os.path.exists(ws.public)


def test_build_png_rasterises_every_sheet(ws):
    assert run(ws, 'build', 'bungalow', '--png', '--quiet') == 0
    out = os.path.join(ws.build, 'bungalow')
    svgs = [f for f in os.listdir(out) if f.endswith('.svg')]
    assert svgs and all(open(os.path.join(out, f[:-4] + '.png'), 'rb').read(8) == b'\x89PNG\r\n\x1a\n' for f in svgs)


def test_build_out_puts_one_house_where_it_is_told(ws, tmp_path):
    out = str(tmp_path / 'elsewhere')
    assert run(ws, 'build', 'cottage', '--out', out, '--quiet') == 0
    assert 'ground.svg' in os.listdir(out) and not os.path.exists(os.path.join(ws.build, 'cottage'))
    assert run(ws, 'build', 'cottage', 'bungalow', '--out', out, '--quiet') == 0       # two houses: each to its own folder
    assert os.path.exists(os.path.join(ws.build, 'bungalow', 'ground.svg'))


def test_a_house_can_be_given_as_a_path_to_its_folder_or_its_file(ws, tmp_path, capsys):
    alone = tmp_path / 'somewhere' / 'plan.yaml'
    alone.parent.mkdir()
    alone.write_text(ROOM)
    for arg in (ws.house('cottage'), os.path.join(ws.house('cottage'), 'house.yaml'), str(alone)):
        assert run(ws, 'check', arg) == 0
    assert run(ws, 'build', str(alone), '--quiet') == 0
    assert os.path.exists(os.path.join(ws.build, 'plan', 'plan-plans.html'))           # a bare file is named for itself
    assert run(ws, 'snapshot', str(alone)) == 0 and os.path.exists(str(tmp_path / 'somewhere' / 'plan.expected.json'))


def test_quiet_prints_only_what_needs_doing_something_about(ws, capsys):
    add(ws, 'gap', ROOM + "      - {name: OTHER, at: [7, 5]}\n    walls: [{id: stub, from: [4, 0], to: [4, 3]}]\n")
    assert run(ws, 'build', 'gap', '--quiet') == 1
    out = capsys.readouterr().out
    assert 'gap: ground: error' in out and 'the same space' in out and 'ends in the open' not in out
    assert run(ws, 'check', 'gap') == 1
    assert 'gap: ground: info  wall stub ends in the open' in capsys.readouterr().out   # check says everything


# ---- what may be hosted

def test_a_private_house_is_never_in_what_is_hosted(ws, capsys):
    add(ws, 'secret', SECRET)
    assert run(ws, 'build') == 0 and 'Secret Lodge' in open(os.path.join(ws.build, 'index.html')).read()
    assert run(ws, 'build', '--public') == 0
    assert 'secret: private, left out' in capsys.readouterr().out
    assert sorted(os.listdir(ws.public)) == ['bungalow', 'cottage', 'fonts', 'icon-180.png', 'icon-192.png', 'icon-512.png',
                                             'icon-maskable-512.png', 'icon.svg', 'index.html', 'manifest.webmanifest', 'vercel.json']
    for f in tree(ws.public):
        if f.endswith(('.html', '.json', '.svg', '.md', '.webmanifest')):
            text = open(os.path.join(ws.public, f), encoding='utf-8').read()
            assert 'Secret' not in text and 'secret' not in text.replace('secretary', ''), f
    assert '2 houses' in open(os.path.join(ws.public, 'index.html')).read()


def test_a_public_build_is_emptied_first(ws):
    add(ws, 'secret', ROOM)                                 # not private yet: it is built, and hosted
    assert run(ws, 'build', '--public') == 0 and os.path.isdir(os.path.join(ws.public, 'secret'))
    os.makedirs(os.path.join(ws.public, '.vercel'))
    open(os.path.join(ws.public, '.vercel', 'project.json'), 'w').write('{}')
    open(os.path.join(ws.public, 'stale.html'), 'w').write('old')
    open(os.path.join(ws.houses, 'secret', 'house.yaml'), 'w').write(SECRET)
    assert run(ws, 'build', '--public') == 0
    left = os.listdir(ws.public)
    assert 'secret' not in left and 'stale.html' not in left               # nothing of an earlier build is left to be hosted
    assert open(os.path.join(ws.public, '.vercel', 'project.json')).read() == '{}'      # but which project it deploys to is


def test_a_public_build_is_of_every_house_or_none(ws, tmp_path):
    for extra in (['cottage'], ['--out', str(tmp_path / 'x')]):
        with pytest.raises(SystemExit) as e:
            run(ws, 'build', '--public', *extra)
        assert e.value.code == 2
    assert not os.path.exists(ws.public)


def test_a_house_that_will_not_solve_is_not_hosted_and_does_not_stop_the_rest(ws, capsys):
    add(ws, 'broken', 'sheets: [{id: g, envelope: [[0, 0], [nope, 0], [1, 1]]}]')
    assert run(ws, 'build', '--public') == 1
    assert sorted(d for d in os.listdir(ws.public) if os.path.isdir(os.path.join(ws.public, d)) and d != 'fonts') == ['bungalow', 'cottage']
    err = capsys.readouterr().err
    assert "unknown name 'nope'" in err and 'Traceback' not in err
    assert run(ws, 'build') == 1 and os.path.exists(os.path.join(ws.build, 'cottage', 'index.html'))
    assert 'broken' not in open(os.path.join(ws.build, 'index.html')).read()


# ---- check and snapshot

def test_check_is_quiet_about_a_house_that_is_right(ws, capsys):
    assert run(ws, 'check', 'cottage', 'bungalow') == 0
    out = capsys.readouterr().out
    assert 'error' not in out and 'warn' not in out


def test_check_says_what_moved_from_the_snapshot(ws, capsys):
    path = os.path.join(ws.house('bungalow'), 'house.yaml')
    text = open(path).read()
    open(path, 'w').write(text.replace('main_w: 10.0', 'main_w: 10.5'))
    assert run(ws, 'check', 'bungalow') == 1
    out = capsys.readouterr().out
    assert 'bungalow: snapshot: error sheets.ground.gross:' in out and 'expected' in out and 'found' in out
    assert run(ws, 'snapshot', 'bungalow') == 0
    assert capsys.readouterr().out.strip() == os.path.join(ws.house('bungalow'), 'expected.json')
    assert run(ws, 'check', 'bungalow') == 0


def test_a_house_with_no_snapshot_is_checked_for_problems_only(ws):
    add(ws, 'fresh', ROOM)
    assert run(ws, 'check', 'fresh') == 0 and cli.drift(ws.house('fresh')) == []
    assert run(ws, 'snapshot', 'fresh') == 0
    snap = json.load(open(os.path.join(ws.house('fresh'), 'expected.json')))
    assert snap['sheets']['ground']['rooms'] == [{'name': 'ROOM', 'w': 7.4, 'h': 5.4, 'area': 39.96, 'shape': 'rect'}]
    assert open(os.path.join(ws.house('fresh'), 'expected.json')).read().endswith('}\n')


def test_one_bad_house_among_several_is_reported_and_the_rest_checked(ws, capsys):
    assert run(ws, 'check', 'cottage', 'nowhere', 'bungalow') == 1
    io = capsys.readouterr()
    assert io.err.startswith('nowhere: no house called') and io.err.count('\n') == 1


# What a broken house file is: each of these was once a traceback from the
# command line, which catches a ConfigError or a ValueError and nothing else.
BROKEN = {
    'yaml': 'a: [',
    'tabs': 'survey:\n\tW: 1\n',
    'empty': '',
    'a-list': '- 1\n- 2\n',
    'no-sheets': 'survey: {W: 1}\n',
    'divide': ROOM.replace('W: 8.0', 'W: 8.0/0'),
    'modulo': ROOM + 'lines: {A: W % 0}\n',
    'no-arguments': ROOM + 'lines: {A: min()}\n',
    'too-few': ROOM + 'lines: {A: "centred(1, 2)"}\n',
    'overflow': ROOM + 'lines: {A: int(1e400)}\n',
    'root': ROOM + 'lines: {A: sqrt(-1)}\n',
    'nan': ROOM.replace('W: 8.0', 'W: .nan'),
    'inf': ROOM.replace('W: 8.0', 'W: .inf'),
    'grown-inf': ROOM + 'lines: {A: 1e308*10}\n',
    'survey-a-list': ROOM.replace('survey: {W: 8.0, D: 6.0}', 'survey: [8, 6]'),
    'sheets-a-number': 'sheets: 5\n',
    'walls-a-number': ROOM + '    walls: 5\n',
    'room-a-number': ROOM + '    rooms: [5]\n',
    'stair-going': ROOM + '    stairs: [{path: [[2, 2], [2, 4]], going: 0}]\n',
    'solid-crossed': ROOM + '    solids: [{points: [[1, 1], [2, 2], [2, 1], [1, 2]]}]\n',
    'outline-a-list': 'outline: [1]\n' + ROOM,
    'outline-unknown': 'outline: {sheets: [nope]}\n' + ROOM,
    'note-field': ROOM + "    notes: ['{nope} m']\n",
    'note-divide': ROOM + "    notes: {summary: '{1/0}'}\n",
    'require': ROOM + '    require: [5]\n',
    'envelope-crossed': 'sheets: [{id: g, envelope: [[0, 0], [4, 4], [4, 0], [0, 4]]}]\n',
    'python-tag': '!!python/object/apply:os.system ["true"]\n',
}


@pytest.mark.parametrize('case', sorted(BROKEN))
def test_a_broken_house_file_is_said_in_a_line_by_every_command(ws, capsys, case):
    add(ws, 'broken', BROKEN[case])
    for args in (['check', 'broken'], ['build', 'broken'], ['build', 'broken', '--quiet'], ['share', 'broken'],
                 ['crop', 'broken', 'ground'], ['crop', 'broken', 'ground', '1', '1', '3', '3'],
                 ['at', 'broken', 'ground', '1', '1'], ['snapshot', 'broken']):
        assert run(ws, *args) == 1, args
        io = capsys.readouterr()
        assert 'Traceback' not in io.err and io.err.strip(), args
        assert len(io.err.strip().split('\n')) == 1 and len(io.err) < 600, (args, io.err)
    assert not os.path.exists(os.path.join(ws.house('broken'), 'expected.json'))
    assert not os.path.exists(os.path.join(ws.build, 'broken'))


@pytest.mark.parametrize('case', ['yaml', 'divide', 'walls-a-number', 'solid-crossed', 'note-field'])
def test_a_broken_house_among_others_is_said_in_a_line_and_the_others_are_drawn(ws, capsys, case):
    add(ws, 'broken', BROKEN[case])
    for args, out in ((['build', '--quiet'], ws.build), (['build', '--public', '--quiet'], ws.public)):
        assert run(ws, *args) == 1
        err = capsys.readouterr().err
        assert 'Traceback' not in err and len(err.strip().split('\n')) == 1 and 'broken' in err
        assert not os.path.exists(os.path.join(out, 'broken')) and os.path.exists(os.path.join(out, 'cottage', 'ground.svg'))


def test_a_file_nested_past_all_reason_is_refused_and_not_a_crash(ws, capsys):
    add(ws, 'broken', 'a: ' + '[' * 3000 + ']' * 3000 + '\n')
    assert run(ws, 'check', 'broken') == 1
    err = capsys.readouterr().err
    assert 'Traceback' not in err and len(err) < 600 and ('nested too deep' in err or 'not YAML' in err)


def test_marks_on_a_broken_house_are_not_a_traceback_either(ws, capsys):
    add(ws, 'broken', BROKEN['divide'])
    open(ws.marks('broken'), 'w').write(json.dumps([{'type': 'note', 'x': 1, 'y': 1, 'text': 'hi', 'ts': 1}]))
    assert run(ws, 'marks', 'broken') == 1
    assert 'Traceback' not in capsys.readouterr().err


# ---- crop, at, share, marks

def test_crop_renders_a_box_or_the_whole_sheet(ws, tmp_path, capsys):
    assert run(ws, 'crop', 'cottage', 'ground', '2.8', '4', '6', '7.5') == 0
    png = capsys.readouterr().out.strip()
    assert png == os.path.join(ws.build, 'cottage', 'crop-ground.png') and open(png, 'rb').read(4) == b'\x89PNG'
    svg = open(png[:-4] + '.svg').read()
    assert 'viewBox="280 400 320 350"' in svg and 'width="960" height="1050"' in svg       # 3 px to the cm
    out = str(tmp_path / 'whole.svg')
    assert run(ws, 'crop', 'cottage', 'ground', '--out', out) == 0
    assert capsys.readouterr().out.strip() == out[:-4] + '.png'
    import re
    w, h = [float(v) for v in re.search(r'width="([\d.]+)" height="([\d.]+)"', open(out).read()).groups()]
    assert max(w, h) == pytest.approx(cli.WHOLE, abs=1)                                     # small enough to take in at once


@pytest.mark.parametrize('args, why', [
    (['crop', 'cottage', 'ground', '1', '2', '3'], 'give X0 Y0 X1 Y1, or nothing for the whole sheet'),
    (['crop', 'cottage', 'ground', '1'], 'give X0 Y0 X1 Y1'),
    (['crop', 'cottage', 'ground', '1', '2', '3', '4', '5'], 'give X0 Y0 X1 Y1'),
    (['crop', 'cottage', 'attic'], "no sheet called 'attic' (have ground, first)"),
    (['crop', 'cottage', 'outline'], "no sheet called 'outline'"),
    (['crop', 'nowhere', 'ground'], 'no house called'),
    (['at', 'cottage', 'ground', '1'], 'give X Y, X Y RADIUS or X0 Y0 X1 Y1'),
    (['at', 'cottage', 'ground', '1', '2', '3', '4', '5'], 'give X Y, X Y RADIUS or X0 Y0 X1 Y1'),
    (['at', 'cottage', 'attic', '1', '1'], "no sheet called 'attic'"),
    (['at', 'nowhere', 'ground', '1', '1'], 'no house called'),
    (['share', 'nowhere'], 'no house called'),
    (['marks', 'nowhere'], 'no house called'),
    (['snapshot', 'nowhere'], 'no house called'),
])
def test_a_command_given_wrong_says_how_it_is_given(ws, capsys, args, why):
    assert run(ws, *args) == 1
    io = capsys.readouterr()
    assert why in io.err and io.out == '' and 'Traceback' not in io.err


def test_at_says_what_is_at_a_point_within_a_radius_or_in_a_box(ws, capsys):
    assert run(ws, 'at', 'cottage', 'ground', '1.5', '1.5') == 0
    point = capsys.readouterr().out.strip().split('\n')
    assert point[0].startswith('room ') and 'sheets.ground.rooms' in point[0]
    assert run(ws, 'at', 'cottage', 'ground', '1.5', '1.5', '8') == 0
    wide = capsys.readouterr().out.strip().split('\n')
    assert len(wide) > len(point) and wide[:len(point)] == point           # nearest first, the further things after
    assert run(ws, 'at', 'cottage', 'ground', '0', '0', '9', '7.5') == 0
    assert capsys.readouterr().out.count('\nroom ') + 1 >= 3
    assert run(ws, 'at', 'cottage', 'ground', '-50', '-50') == 0
    assert capsys.readouterr().out.strip() == 'outside the building'


def test_share_writes_the_one_file_to_send(ws, tmp_path, capsys):
    assert run(ws, 'share', 'cottage') == 0
    dest = capsys.readouterr().out.strip()
    assert dest == os.path.join(ws.build, 'cottage', 'cottage-plans.html') and os.listdir(os.path.dirname(dest)) == ['cottage-plans.html']
    out = str(tmp_path / 'deep' / 'er' / 'send.html')
    assert run(ws, 'share', 'cottage', '--out', out) == 0 and open(out).read() == open(dest).read()
    assert cli.sent('cottage') == 'cottage-plans.html'


def test_marks_with_nothing_drawn_says_so(ws, capsys):
    assert run(ws, 'marks', 'cottage', 'bungalow') == 0
    assert capsys.readouterr().out.split('\n')[:2] == ['cottage: nothing drawn yet', 'bungalow: nothing drawn yet']
    assert cli.drawn_on(ws.house('cottage')) == []


def test_marks_lays_out_what_was_drawn_with_pictures(ws, capsys):
    drawn = [{'type': 'pen', 'sheet': 'ground', 'ts': 1000, 'pts': [[2, 2], [2.5, 2.5], [3, 2]]},
             {'type': 'note', 'sheet': 'first', 'ts': 2000, 'x': 4, 'y': 4, 'text': 'smaller <b>here</b>'}]
    json.dump(drawn, open(ws.marks('cottage'), 'w'))
    assert run(ws, 'marks', 'cottage') == 0
    brief = capsys.readouterr().out
    out = os.path.join(ws.build, 'cottage', 'marks')
    assert open(os.path.join(out, 'brief.md')).read().strip() == brief.strip()
    assert '## How to read this' in brief and 'smaller <b>here</b>' in brief
    pngs = [f for f in os.listdir(out) if f.endswith('.png')]
    assert len(pngs) >= 2 and all(os.path.getsize(os.path.join(out, f)) > 5000 for f in pngs)
    assert run(ws, 'crop', 'cottage', 'ground', '1', '1', '4', '4', '--marks') == 0
    svg = open(capsys.readouterr().out.strip()[:-4] + '.svg').read()
    assert '#D0199B' in svg and svg.count('<polyline') == 1                 # the ink, on one of the two panels


def test_marks_are_closed_from_the_command_line_and_then_left_out(ws, capsys):
    json.dump([{'type': 'pen', 'sheet': 'ground', 'ts': 1759800000000, 'pts': [[2, 2], [2.5, 2.5], [3, 2]]}], open(ws.marks('cottage'), 'w'))
    assert run(ws, 'resolve', 'cottage', 'nope', '--note', 'done') == 1 and "no mark called 'nope'" in capsys.readouterr().err
    assert run(ws, 'resolve', 'cottage', 'mmgfvhedc', '--note', 'done', '--sheets', 'ground', 'first') == 0
    assert capsys.readouterr().out.strip() == 'mmgfvhedc: resolved, applied to ground, first'
    assert run(ws, 'marks', 'cottage') == 0
    assert capsys.readouterr().out.strip() == 'cottage: nothing still open — 1 resolved (ask for resolved marks to see them)'
    assert run(ws, 'marks', 'cottage', '--all', '--sheet', 'ground') == 0 and '  resolved ' in capsys.readouterr().out
    assert run(ws, 'marks', 'cottage', '--all', '--sheet', 'first') == 0
    assert capsys.readouterr().out.strip() == 'cottage, sheet first: nothing drawn yet'
    assert run(ws, 'crop', 'cottage', 'ground', '1', '1', '4', '4', '--marks') == 0
    assert '<polyline' not in open(capsys.readouterr().out.strip()[:-4] + '.svg').read()         # ink dealt with is not on a crop
    assert run(ws, 'crop', 'cottage', 'first', '--ids', 'mmgfvhedc') == 0
    built = open(capsys.readouterr().out.strip()[:-4] + '.svg').read()
    assert built.count('<polyline') == 1 and 'WHAT WAS BUILT' in built      # asked for by name: there, on the sheet it was applied to
    assert run(ws, 'resolve', 'cottage', 'mmgfvhedc', '--reopen') == 0 and 'opened again' in capsys.readouterr().out


# ---- the command itself

def test_the_version_is_the_packages(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(['--version'])
    assert e.value.code == 0 and capsys.readouterr().out.strip() == 'flawlessplan ' + __version__


@pytest.mark.parametrize('args', [[], ['nonsense'], ['check'], ['crop', 'cottage'], ['at', 'cottage', 'ground'],
                                  ['at', 'cottage', 'ground', 'x', 'y'], ['build', '--nope'], ['serve', '--port', 'eighty']])
def test_a_command_that_is_not_one_is_refused_by_the_parser(ws, capsys, args):
    with pytest.raises(SystemExit) as e:
        run(ws, *args)
    assert e.value.code == 2 and 'usage: flawlessplan' in capsys.readouterr().err


def test_every_command_in_the_help_is_one_the_parser_has(capsys):
    with pytest.raises(SystemExit):
        cli.main(['--help'])
    said = capsys.readouterr().out
    for cmd in ('init', 'build', 'share', 'check', 'crop', 'at', 'serve', 'marks', 'snapshot', 'mcp'):
        assert cmd in said and 'flawlessplan %s' % cmd in cli.__doc__


def test_build_py_draws_the_examples_into_this_repos_build(tmp_path):
    """build.py is `flawlessplan build` over the two examples; here, what it
    hands to the command line."""
    src = open(os.path.join(ROOT, 'build.py')).read()
    assert "'--houses', os.path.join(ROOT, 'flawlessplan', 'examples'), 'build'" in src
    ws = Workspace(str(tmp_path), EXAMPLES)
    before = tree(EXAMPLES)
    assert cli.main(['--workspace', str(tmp_path), '--houses', EXAMPLES, 'build', '--quiet']) == 0
    assert sorted(d for d in os.listdir(ws.build) if os.path.isdir(os.path.join(ws.build, d)) and d != 'fonts') == ['bungalow', 'cottage']
    assert tree(EXAMPLES) == before                         # and a build leaves nothing in the package


def test_build_prints_what_it_found_under_the_sheet_it_found_it_on(ws, capsys):
    add(ws, 'gap', ROOM + "      - {name: OTHER, at: [7, 5]}\n")
    assert run(ws, 'build', 'gap') == 1
    out = capsys.readouterr().out.split('\n')
    assert ' -> ' in out[0] and out[1].split()[0] == 'ground'
    assert [ln for ln in out if ln.startswith('    error ') and 'the same space' in ln]


def test_serve_and_mcp_are_handed_the_workspace(ws, monkeypatch):
    from flawlessplan import mcp_server, server
    seen = []
    monkeypatch.setattr(server, 'serve', lambda w, port=8765: seen.append(('serve', w.root, port)))
    monkeypatch.setattr(mcp_server, 'serve', lambda w: seen.append(('mcp', w.root)))
    assert run(ws, 'serve', '--port', '9001') == 0 and run(ws, 'mcp') == 0 and run(ws, 'build', 'cottage', '--quiet', '--serve') == 0
    assert seen == [('serve', ws.root, 9001), ('mcp', ws.root), ('serve', ws.root, 8765)]


def test_python_dash_m_is_the_same_command():
    import subprocess
    import sys
    out = subprocess.run([sys.executable, '-m', 'flawlessplan', '--houses', EXAMPLES, 'check', 'cottage', 'bungalow'],
                         cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and 'error' not in out.stdout and out.stderr == ''


def test_a_new_workspace_is_not_handed_what_was_drawn_on_the_examples(tmp_path, monkeypatch):
    """Serving this repo saves marks beside the examples themselves."""
    import shutil
    from flawlessplan import workspace
    drawn_on = str(tmp_path / 'examples')
    shutil.copytree(EXAMPLES, drawn_on)
    open(os.path.join(drawn_on, 'cottage', 'marks.json'), 'w').write('[{"type": "note", "x": 1, "y": 1, "text": "mine"}]')
    open(os.path.join(drawn_on, 'cottage', '.DS_Store'), 'w').write('x')
    monkeypatch.setattr(workspace, 'EXAMPLES', drawn_on)
    ws = Workspace(str(tmp_path / 'new'))
    ws.init()
    assert sorted(os.listdir(ws.house('cottage'))) == ['expected.json', 'house.yaml'] and cli.drawn_on(ws.house('cottage')) == []
