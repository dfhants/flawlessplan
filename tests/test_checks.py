# -*- coding: utf-8 -*-
"""What the checks found that drawing Woodland Grove from an agent's plan
did not: what leads where, rooms no door reaches, doors that clash, stairs
against Approved Document K; and the fittings, garage doors, compass,
source underlay and comments that came of it."""
import json
import os
import pytest
from conftest import BOX
from flawlessplan import cli, geom, marks, model, render, report, solve, stairs

ROOMS = """survey: {W: 8.0, D: 6.0}
%s
sheets:
  - id: ground
    envelope: [{at: [0, 0], id: north}, {at: [W, 0], id: east}, {at: [W, D], id: south}, {at: [0, D], id: west}]
    walls:
      - {id: split, from: [4, 0], to: [4, D]}
      - {id: cup, from: [0, 4], to: [4, 4]}
    openings:
      - {door: std, wall: split, at: [4, 1.2], swing: e, hinge: n}
      - {door: std, wall: south, at: [6, D], swing: n, hinge: e}
      - {window: 1.2, wall: north, at: [2, 0]}
      - {window: 1.2, wall: south, at: [7.2, D]}
%s    rooms:
      - {name: A, at: [1, 1]}
      - {name: B, at: [7, 1]}
      - {name: C, at: [1, 5]}
"""


def house(top='', more=''):
    return solve.solves(ROOMS % (top, more))


def said(s, level=None):
    return [m for _, lv, m in s.issues() if level in (None, lv)]


def test_the_report_says_what_each_opening_joins():
    rep = report.report(house())['sheets'][0]['connections']
    assert rep[0] == {'kind': 'door', 'style': 'swing', 'wall': 'split', 'rooms': ['A', 'B'], 'into': 'B', 'hinge': 'north',
                      'text': 'A - B, door 0.84 m in split, hinged north, swings into B'}
    assert rep[1]['rooms'] == ['B', 'outside'] and rep[1]['hinge'] == 'east'
    assert rep[2] == {'kind': 'window', 'wall': 'north', 'room': 'A', 'side': 'north', 'text': 'A - window 1.20 m, north wall'}
    assert rep[3]['room'] == 'B' and rep[3]['side'] == 'south'


def test_a_room_no_door_reaches_is_reported():
    s = house()
    assert said(s) == ['sheets.ground.rooms[2]: no door leads to C from the front door']
    s = house(more='      - {door: cloak, wall: cup, at: [1, 4], swing: s}\n')
    assert not said(s)                                  # through A, which the hall door reaches


def test_connections_are_held_to_what_the_source_shows():
    top = """connections:
  - [A, B]
  - {door: [B, outside], into: B, hinge: n}
  - {window: A, side: north}
  - {window: B, side: east}
  - [A, C]
  - [B, C]"""
    got = said(house(top))
    assert 'connections[1]: the door between B and outside is hung on its east side, not its north (sheets.ground.openings[1])' in got
    assert 'connections[3]: the window in B looks south, not east (sheets.ground.openings[3])' in got
    assert 'connections[4]: no way through between A and C' in got and 'connections[5]: no way through between B and C' in got
    got = said(house(top.replace('[A, B]', '[C, B]')))
    assert 'connections[0]: the door is drawn between A and B, not C and B (sheets.ground.openings[0])' in got
    got = said(house('connections: [[A, B], {window: A, side: n}, {door: [B, outside]}]'))
    assert any('openings[3]: the window in B, looking south is not in `connections`' in m for m in got)
    assert said(house('connections: [[A, D]]'), 'error') == ['connections[0]: no as-built sheet has a room called D']


@pytest.mark.parametrize('bad, why', [
    ('connections: [[A]]', 'name the two rooms'),
    ('connections: [{window: A}]', 'side: the way the window looks'),
    ('connections: [{door: [A, B], into: C}]', 'into: C is not one of the rooms'),
    ('connections: [{door: [A, B], hinge: up}]', 'hinge: the side its hinge is on'),
    ('connections: [{door: [A, B], side: n}]', 'a door takes into, hinge'),
])
def test_a_connection_that_cannot_be_read_says_why(bad, why):
    with pytest.raises(model.ConfigError, match=why):
        house(bad)


def test_two_doors_that_swing_into_each_other_are_reported():
    s = house(more='      - {door: std, wall: north, at: [4.9, 0], swing: s, hinge: w}\n')
    assert any('swing into each other' in m for m in said(s))


def test_a_stair_is_held_to_approved_document_k_and_its_well_worked_out():
    s = solve.solves(STAIR)
    rep = report.report(s)['sheets'][0]['stairs']
    assert rep == [{'id': 'main', 'risers': 14, 'riser': 0.2036, 'going': 0.2462, 'pitch': 39.6, '2R+G': 0.6533}]
    assert not said(s)
    g = s.sheet('first').stairs[0]
    assert g['well_from'] == 1 and g['void'] is None and g['rail']         # one tread has floor over it
    assert g['head'][1] == (-0.0, 1.0)                                      # the arrow points down the flight
    steep = solve.solves(STAIR.replace('height: 2.85', 'height: 3.4'))
    assert any('steeper than 42°' in m for m in said(steep)) and any('outside 550–700' in m for m in said(steep))
    given = solve.solves(STAIR.replace('treads: 13,', 'treads: 13, riser: 0.19,'))
    assert any('14 risers of 190 mm climb 2.660 m, and the ground level is 2.850 m high' in m for m in said(given))
    plain = solve.solves(STAIR.replace('levels: [{id: ground, height: 2.85}, {id: first, height: 2.4, floor_depth: 0.25}]',
                                       'levels: [ground, first]'))
    assert plain.sheet('first').stairs[0]['void'] is not None and report.report(plain)['sheets'][0]['stairs'] == []


STAIR = """survey: {W: 6.0, D: 6.0}
levels: [{id: ground, height: 2.85}, {id: first, height: 2.4, floor_depth: 0.25}]
sheets:
  - id: ground
    envelope: [{at: [0, 0], id: north}, {at: [W, 0], id: east}, {at: [W, D], id: south}, {at: [0, D], id: west}]
    walls: [{id: hw, from: [2, 0], to: [2, D]}]
    openings:
      - {door: std, wall: south, at: [1, D], swing: n}
      - {door: std, wall: hw, at: [2, 1], swing: e}
    rooms: [{name: HALL, at: [1, 1]}, {name: LIVING, at: [4, 3]}]
    stairs:
      - {id: main, path: [[1, 5.3], [1, 2.1]], width: 0.9, treads: 13, cut_risers: 6}
  - id: first
    envelope: [{at: [0, 0], id: north}, {at: [W, 0], id: east}, {at: [W, D], id: south}, {at: [0, D], id: west}]
    walls: [{id: hw, from: [2, 0], to: [2, D]}]
    openings: [{door: std, wall: hw, at: [2, 1], swing: e}]
    rooms: [{name: LANDING, at: [1, 1]}, {name: BED, at: [4, 3]}]
    stairs: [{ref: ground.main}]
"""


def test_a_level_says_how_high_it_is():
    h = model.loads(STAIR)
    assert h['heights'] == {'ground': {'height': 2.85, 'floor_depth': None}, 'first': {'height': 2.4, 'floor_depth': 0.25}}
    with pytest.raises(model.ConfigError, match=r'levels\[0\]: a level is its id'):
        model.loads(STAIR.replace('{id: ground, height: 2.85}', '{id: ground, tall: 2.85}'))


def test_a_garage_door_and_a_round_cylinder_and_a_fireplace():
    s = solve.solves(BOX.replace("- {window: 1.2, at: [2.0, 0]}", "- {door: 2.4, wall: env.2, at: [6, 6], style: up}\n"
                                 "      - {door: 2.4, wall: env.2, at: [2, 6], style: roller}") + """    fittings:
      - {cylinder: 0.45, at: [7, 2], facing: s}
      - {fireplace: 1.4, depth: 0.4, wall: env.0, side: in, at: [2, 0], hearth: [1.2, 0.5], opening: [0.6, 0.3]}
""")
    sh = s.sheet('ground')
    assert sh.svg().count('class="overhead"') == 2
    cyl, fire = sh.plan.fittings
    assert (cyl['w'], cyl['d']) == (0.45, 0.45)
    left = [r for r in sh.plan.rooms if r['name'] == 'LEFT'][0]
    assert left['area'] == pytest.approx(3.65*5.4 - 1.4*0.4 + 0.6*0.3, abs=0.02)      # the breast is not floor; its opening is
    assert fire['breast'].area == pytest.approx(1.4*0.4 - 0.6*0.3, abs=0.01) and not [m for m in said(s) if 'fireplace' in m]
    with pytest.raises(model.ConfigError, match='only a fireplace has'):
        model.loads(BOX + "    fittings: [{sink: true, wall: env.0, hearth: [1, 1]}]\n")


def test_true_north_turns_the_compass():
    plain = solve.solves(BOX).sheet('ground').svg()
    turned = solve.solves(BOX.replace('survey:', 'house: {north: -45}\nsurvey:')).sheet('ground').svg()
    assert 'rotate(' not in [ln for ln in plain.split('\n') if 'northarrow' in ln and 'path' in ln][0]
    assert 'class="northarrow" transform="rotate(315 ' in turned


def test_a_key_the_engine_does_not_read_is_said():
    s = solve.solves(BOX.replace('survey:', 'house: {name: X, nort: 45}\nsurvey:')
                     .replace('{name: LEFT, at: [1, 1]}', '{name: LEFT, at: [1, 1], widht: 3}'))
    assert said(s, 'warn') == ['house: `nort` is not a key the engine reads, so it does nothing',
                               'sheets.ground.rooms[0]: `widht` is not a key the engine reads, so it does nothing']


PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x02\x00\x00\x00\x01\x08\x06\x00\x00\x00\xf4"\x7f\x8a\x00\x00'
       b'\x00\x10IDATx\x9cc\xf8\xcf\xc0\xf0\x9f\x81\x01\x00\x07\xfe\x02\xfe\xa7\xdd\x0e\x1a\x00\x00\x00\x00IEND\xaeB`\x82')


def test_a_source_drawing_is_set_under_a_crop_and_on_the_page_but_never_sent(tmp_path):
    folder = tmp_path / 'traced'
    folder.mkdir()
    (folder / 'agent.png').write_bytes(PNG)
    (folder / 'house.yaml').write_text(BOX.replace('    envelope:', '    underlay: {image: agent.png, scale: 0.25, at: [1, 2]}\n    envelope:'))
    s = solve.solve(str(folder))
    u, data = cli.source(s, s.sheet('ground'))
    tag = render.underlay(u, data)
    assert render.picture_size(data) == (2, 1) and 'x="100" y="200" width="800" height="400"' in tag and 'base64' in tag
    out = tmp_path / 'build'
    cli.build_house(str(folder), str(out / 'traced'), quiet=True)
    page = (out / 'traced' / 'index.html').read_text()
    assert 'href="source-ground.png"' in page and 'id="source"' in page and (out / 'traced' / 'source-ground.png').exists()
    assert '<image' not in (out / 'traced' / 'traced-plans.html').read_text()             # not in what is sent
    cli.build_house(str(folder), str(out / 'public'), quiet=True, public=True)
    assert 'source-ground' not in (out / 'public' / 'index.html').read_text() and not (out / 'public' / 'source-ground.png').exists()
    for bad in ('../agent.png', '/etc/passwd.png', 'agent.gif'):
        with pytest.raises(model.ConfigError, match='a .png or .jpg'):
            model.loads(BOX.replace('    envelope:', '    underlay: {image: "%s", scale: 1}\n    envelope:' % bad))


def test_a_comment_is_a_pin_or_a_box_numbered_among_every_mark():
    drawn = [{'type': 'pen', 'ts': 1, 'pts': [[1, 1], [2, 2]], 'status': 'resolved'},
             {'type': 'box', 'ts': 2, 'box': [3, 3, 2, 1], 'text': 'this door'},
             {'type': 'note', 'ts': 3, 'x': 1, 'y': 1, 'text': 'smaller'}]
    S = marks.strokes(drawn, 'g')
    assert [(s['n'], s['kind']) for s in S] == [(2, 'box'), (3, 'note')]
    assert S[0]['pts'] == [(2, 1), (3, 1), (3, 3), (2, 3)]
    svg = '\n'.join(marks.ink(S, 4.0))
    assert 'this door' not in svg and 'smaller' not in svg and '<polygon' in svg


def test_what_a_comment_is_on_is_read_off_the_plan_when_it_is_made():
    s = solve.solves(BOX)
    sheets = dict((p.id, p) for p in s.plans())
    sent = [{'type': 'note', 'sheet': 'ground', 'ts': 5, 'x': 3.9, 'y': 3.0, 'text': 'a'},
            {'type': 'box', 'sheet': 'ground', 'ts': 6, 'box': [3, 1, 5, 5], 'text': 'b', 'version': 'older'},
            {'type': 'pen', 'sheet': 'ground', 'ts': 7, 'pts': [[1, 1], [2, 2]]}]
    marks.attach(sent, [], sheets, 'abc')
    assert sent[0]['version'] == 'abc' and sent[0]['room'] == ['LEFT'] and any('door' in c for c in sent[0]['context'])
    assert 'context' not in sent[1] and sent[1]['version'] == 'older'       # nothing is read off a plan it was not made on
    assert 'version' not in sent[2]


def test_a_reply_resolves_a_mark_and_the_owner_s_reply_opens_it_again(tmp_path):
    path = str(tmp_path / 'marks.json')
    marks.save(path, [{'type': 'note', 'ts': 1, 'x': 1, 'y': 1, 'text': 'smaller', 'id': 'a'}])
    marks.resolve(path, ['a'], 'made it 1.1 m')
    m, = marks.load(path)
    assert m['status'] == 'resolved' and [r['by'] for r in m['replies']] == ['agent'] and m['replies'][0]['text'] == 'made it 1.1 m'
    page = dict(m)                                   # the page, before it saw the reply
    for k in ('status', 'resolved', 'how', 'replies'):
        page.pop(k)
    assert marks.keep([m], [page])[0]['status'] == 'resolved' and marks.keep([m], [page])[0]['replies'] == m['replies']
    back = dict(m, replies=m['replies'] + [{'by': 'owner', 'text': 'still too big', 'ts': m['resolved'] + 1}])
    for k in marks.LIFE:
        back.pop(k, None)
    kept, = marks.keep([m], [back])
    assert 'status' not in kept and [r['by'] for r in kept['replies']] == ['agent', 'owner']


def test_a_comment_made_on_an_older_version_is_shown_on_it_beside_the_drawing_now(tmp_path):
    old = solve.solves(BOX)
    now = solve.solves(BOX.replace('at: centre, swing: e', 'at: [MID, 4.5], swing: e'))
    drawn = [{'type': 'note', 'sheet': 'ground', 'ts': 5, 'x': 3.9, 'y': 3.0, 'text': 'swing it west', 'version': 'v1',
              'context': ['door 0.84 m wide in wall split'], 'replies': [{'by': 'owner', 'text': 'please', 'ts': 6}]}]
    out = str(tmp_path / 'marks')
    text = marks.brief(now.house, now.sheets, drawn, out, cli.rasterise, now='v2', then=lambda v: old if v == 'v1' else None)
    assert '  on: door 0.84 m wide in wall split' in text and 'made on version `v1`; the house file is now `v2`' in text
    assert '  the owner replied' in text and ': please' in text
    pic = open(os.path.join(out, 'ground-1.svg')).read()
    assert 'MADE ON: VERSION V1, WITH THE INK' in pic and 'AS IT IS NOW: VERSION V2, WITH THE INK' in pic and 'swing it west' in pic


# ---- the second round: ids, sources, overruns, mark states, looks, dry runs

def test_a_proposal_extends_the_as_built_and_leaves_out_a_fitting_and_an_area_by_id():
    text = BOX + """    fittings: [{bath: true, wall: env.0, side: in, at: [2, 0], id: old_bath}]
    areas: [{rect: [[5, 1], [6, 2]], style: fitting, label: STORE, id: store}]
  - id: new
    extends: ground
    omit: [old_bath, {area: store}]
"""
    s = solve.solves(text)
    assert len(s.sheet('ground').plan.fittings) == 1 and s.sheet('new').plan.fittings == []
    assert s.sheet('new').plan.spec['areas'] == [] and s.sheet('ground').plan.spec['areas'][0]['id'] == 'store'


def test_an_element_says_where_it_came_from():
    s = solve.solves(BOX.replace("{name: LEFT, at: [1, 1]}", "{name: LEFT, at: [1, 1], source: assumed}")
                     .replace("swing: e}", "swing: e, id: hall_door, source: as-drawn-wrong}"))
    rep = report.report(s)['sheets'][0]['sources']
    assert rep == [{'where': 'sheets.ground.openings[0]', 'source': 'as-drawn-wrong', 'id': 'hall_door'},
                   {'where': 'sheets.ground.rooms[0]', 'source': 'assumed', 'id': None}]
    assert said(s, 'info')[0] == 'sheets.ground.openings[0] (hall_door) is drawn as the source has it, which is known to be wrong'
    with pytest.raises(model.ConfigError, match=r'rooms\[0\].source: one of traced, assumed, as-drawn-wrong'):
        model.loads(BOX.replace("{name: LEFT, at: [1, 1]}", "{name: LEFT, at: [1, 1], source: guessed}"))


def test_a_fitting_that_does_not_fit_says_by_how_much():
    s = solve.solves(BOX + "    fittings: [{bath: 2.0, wall: env.0, side: in, at: {from_start: 2.0}}]\n")
    assert any('the bath runs into a wall by 0.' in m and '(it is 2.00 × 0.70 m)' in m for m in said(s, 'warn'))
    s = solve.solves(BOX + "    fittings: [{unit: true, at: [7.8, 3], facing: e}]\n")
    assert any('is not all inside the building — it stands 0.' in m for m in said(s, 'warn'))


def test_the_guide_gives_every_fitting_its_usual_size():
    from flawlessplan import fittings, page
    guide = page.asset('house-file.md')
    for kind, (w, d) in fittings.KINDS.items():
        assert '| `%s` | %.2f | %.2f |' % (kind, w, d) in guide, kind


def test_a_reply_may_block_a_mark_or_ask_and_the_owner_s_reply_opens_it(tmp_path):
    path = str(tmp_path / 'marks.json')
    marks.save(path, [{'type': 'note', 'ts': 1, 'x': 1, 'y': 1, 'text': 'curved stair', 'id': 'a', 'sheet': 'g'},
                      {'type': 'note', 'ts': 2, 'x': 2, 'y': 2, 'text': 'bigger?', 'id': 'b', 'sheet': 'g'}])
    assert marks.resolve(path, ['a'], 'curved stairs are not drawn yet', state='blocked') == ['a: blocked']
    assert marks.resolve(path, ['b'], 'bigger by how much?', state='question') == ['b: question']
    with pytest.raises(ValueError, match="resolved, blocked or question, not 'later'"):
        marks.resolve(path, ['a'], 'x', state='later')
    got = marks.load(path)
    assert [m['status'] for m in got] == ['blocked', 'question'] and got[0]['replies'][0]['state'] == 'blocked'
    assert marks.strokes(got, 'g') == [] and [s['state'] for s in marks.strokes(got, 'g', done=True)] == ['blocked', 'question']
    back = dict(got[1], replies=got[1]['replies'] + [{'by': 'owner', 'text': 'half a metre', 'ts': got[1]['resolved'] + 1}])
    for k in marks.LIFE:
        back.pop(k, None)
    kept = marks.keep(got, [got[0], back])
    assert kept[0]['status'] == 'blocked' and 'status' not in kept[1]               # the answered question is open again
    s = solve.solves(BOX.replace('id: ground', 'id: g'))
    text = marks.brief(s.house, s.sheets, kept, str(tmp_path / 'out'), cli.rasterise)
    assert '1 mark waiting on the owner — blocked, or a question asked — is left out until they reply' in text
    assert 'the owner replied' in text and ': half a metre' in text


def test_a_mark_is_resolved_only_on_a_look_after_the_change(ws):
    path = ws.find('bungalow')
    marks.save(ws.marks('bungalow'), [{'type': 'note', 'ts': 1, 'x': 1, 'y': 1, 'text': 'wider', 'id': 'w', 'sheet': 'ground'}])
    with pytest.raises(ValueError, match='a mark is resolved on a look'):
        cli.resolve(path, ['w'], 'done', ws=ws)
    before = cli.look(path, 'check', ws)
    text = open(os.path.join(path, 'house.yaml')).read()
    open(os.path.join(path, 'house.yaml'), 'w').write(text.replace('main_w: 10.0', 'main_w: 10.5'))
    with pytest.raises(ValueError, match='was of version .*, and the house file is now'):
        cli.resolve(path, ['w'], 'done', checked=before, ws=ws)
    with pytest.raises(ValueError, match="no look called 'look-nope'"):
        cli.resolve(path, ['w'], 'done', checked='look-nope', ws=ws)
    png = cli.crop(path, 'ground', (1, 1, 3, 3), ws=ws)
    assert cli.resolve(path, ['w'], 'made wider', checked=cli.LOOKED[png], ws=ws) == ['w: resolved']
    assert cli.resolve(path, ['w'], 'needs a curved wall', state='blocked', ws=ws) == ['w: blocked (it was resolved; now as this says)']


def test_a_failing_line_is_named_and_a_whole_text_kept_to_be_put_right(houses):
    from flawlessplan import edit, mcp_server as mcp
    got = mcp.read_house('cottage')
    bad = got['text'].replace('{name: LIVING, at: [1.9, 3.75]}', '{name: LIVING, at: [1.9, 3.75], expect: {wide: 3}}')
    assert bad != got['text']
    line = [i for i, ln in enumerate(bad.split('\n'), 1) if 'expect: {wide' in ln][0]
    with pytest.raises(mcp.ToolError, match=r'expect: give any of w, h and area \(line %d\)' % line):
        mcp.edit_house('cottage', '{name: LIVING, at: [1.9, 3.75]}', '{name: LIVING, at: [1.9, 3.75], expect: {wide: 3}}', dry_run=True)
    assert not os.path.exists(edit.draft(str(houses / 'cottage' / 'house.yaml')))       # a dry run keeps nothing
    with pytest.raises(mcp.ToolError, match='kept as the draft'):
        mcp.write_house('cottage', bad, version=got['version'])
    assert mcp.read_house('cottage')['text'] == got['text']                            # the house is as it was
    done = mcp.edit_house('cottage', 'expect: {wide: 3}', 'expect: {w: 3.15}', draft=True)
    assert done['did'] == 'made from its draft' and 'w: 3.15' in mcp.read_house('cottage')['text']
    assert not os.path.exists(edit.draft(str(houses / 'cottage' / 'house.yaml')))
    dry = mcp.write_house('cottage', got['text'], dry_run=True)
    assert dry['did'] == 'would be replaced' and 'w: 3.15' in mcp.read_house('cottage')['text']
    with pytest.raises(mcp.ToolError, match='has no draft'):
        mcp.edit_house('cottage', 'a', 'b', draft=True)


def test_the_line_a_fault_names_is_found_through_the_parts_a_sheet_uses():
    from flawlessplan import edit
    text = """survey: {W: 8.0}
parts:
  core:
    rooms:
      - {name: A, at: [1, 1]}
sheets:
  - id: ground
    use: [core]
    rooms:
      - {name: B, at: [7, 1]}
"""
    assert edit.line_of(text, 'sheets.ground.rooms[1]: whatever') == 10           # after the part's one
    assert edit.line_of(text, 'sheets.ground.rooms[0]: whatever') == 5
    assert edit.line_of(text, 'sheet ground: sheets.ground.rooms[1]: x') == 10
    assert edit.line_of(text, 'survey.W: x') == 1 and edit.line_of(text, 'nothing here') is None
