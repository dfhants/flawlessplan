# -*- coding: utf-8 -*-
"""A house file changed by its one way in, and what the page does to a
house's sheets: their order, which are hidden, one binned — each a change
to the text of the file that leaves every remark in it where it was."""
import os
import pytest
import yaml

from flawlessplan import cli, edit, page, report, solve
from flawlessplan.model import ConfigError

HOUSE = """# three ways to lay out one box
survey: {W: 8.0, D: 6.0}

levels: [ground, first]

sheets:
  # the ground floor, as it is
  - id: ground
    envelope: [[0, 0], [W, 0], [W, D], [0, D]]
    rooms:
      - {name: ROOM, at: [1, 1]}
    stairs:
      - {id: main, path: [[2, 2], [2, 5]], cut_risers: 6}

  # upstairs: shows the stair from below
  - id: first
    envelope: [[0, 0], [W, 0], [W, D], [0, D]]
    stairs:
      - {ref: ground.main, show: above}
    unlabelled: ok

  # one proposal
  - id: open
    level: ground
    changes: ground
    envelope: [[0, 0], [W, 0], [W, D], [0, D]]
    unlabelled: ok

  - id: wider     # and another, of nothing else
    level: ground
    title: WIDER
    envelope: [[0, 0], [W + 1, 0], [W + 1, D], [0, D]]
    unlabelled: ok
  # the last remark of the sheets

# what is said of the outline
outline:
  notes: [The outline.]
"""


@pytest.fixture
def house(ws):
    dest = os.path.join(ws.houses, 'box')
    os.makedirs(dest)
    with open(os.path.join(dest, 'house.yaml'), 'w') as fh:
        fh.write(HOUSE)
    return dest


def text(house):
    return open(os.path.join(house, 'house.yaml')).read()


def ids(house):
    return [s.id for s in solve.solve(house).plans()]


def test_sheets_are_put_in_order_among_the_places_they_hold(house, ws):
    out = edit.order_sheets(house, ['wider', 'open'], ws=ws)
    assert out['did'] == 'put in order' and out['sheets'] == ['ground', 'first', 'wider', 'open'] == ids(house)
    assert out['version'] == edit.version(text(house)) and out['issues'] == []
    now = text(house)
    # each sheet's remarks went with it, the gaps stayed where gaps were, and nothing else moved
    assert '  - id: wider     # and another, of nothing else\n' in now and now.index('# one proposal\n  - id: open') > now.index('- id: wider')
    assert now.count('\n\n') == HOUSE.count('\n\n') and sorted(now.split('\n')) == sorted(HOUSE.split('\n'))
    assert now.endswith('  # the last remark of the sheets\n\n# what is said of the outline\noutline:\n  notes: [The outline.]\n')
    assert now.index('unlabelled: ok\n\n  # one proposal') > 0
    out = edit.order_sheets(house, ['wider', 'ground', 'first', 'open'], ws=ws)        # every one named: that order
    assert ids(house) == ['wider', 'ground', 'first', 'open']
    assert text(house).index('  - id: wider     # and another') < text(house).index('  # the ground floor, as it is\n  - id: ground')
    assert text(house).startswith('# three ways to lay out one box\nsurvey:') and 'sheets:\n  - id: wider' in text(house)
    again = edit.order_sheets(house, ['wider', 'ground'], ws=ws)
    assert again['did'] == 'nothing: it is so already' and again['changed'] == []
    assert yaml.safe_load(text(house))['outline'] == {'notes': ['The outline.']}


@pytest.mark.parametrize('order, why', [
    (['open', 'ground', 'first'], 'open must come after ground, which is the sheet it changes'),
    (['first', 'ground'], 'first must come after ground, which is where its stair is drawn'),
    (['ground', 'nowhere'], "no sheet called 'nowhere'"), ([], 'give the sheets to put in order'),
    (['ground', 'ground'], 'each once'), ('ground', 'give the sheets to put in order'), (['outline', 'ground'], "no sheet called 'outline'"),
])
def test_an_order_that_cannot_be_is_refused_and_says_why(house, ws, order, why):
    with pytest.raises(edit.Refused, match=why):
        edit.order_sheets(house, order, ws=ws)
    assert text(house) == HOUSE


def test_a_sheet_is_hidden_and_shown_again(house, ws):
    out = edit.hide_sheet(house, 'open', ws=ws)
    assert (out['did'], out['sheet'], out['hidden']) == ('hidden', 'open', True)
    assert '  # one proposal\n  - id: open\n    hidden: true\n    level: ground\n' in text(house)
    s = solve.solve(house)
    assert [(p.id, p.hidden) for p in s.sheets] == [('outline', False), ('ground', False), ('first', False), ('open', True), ('wider', False)]
    assert [p.id for p in s.shown()] == ['outline', 'ground', 'first', 'wider'] and s.sheet('open').plan is not None     # still solved
    assert edit.hide_sheet(house, 'open', ws=ws)['did'] == 'nothing: it is so already'
    assert edit.hide_sheet(house, 'open', False, ws=ws)['did'] == 'shown again' and text(house) == HOUSE
    assert edit.hide_sheet(house, 'open', False, ws=ws)['did'] == 'nothing: it is so already'
    for sid in ('ground', 'first', 'open'):
        edit.hide_sheet(house, sid, ws=ws)
    with pytest.raises(edit.Refused, match='wider is the only sheet showing'):
        edit.hide_sheet(house, 'wider', ws=ws)
    with pytest.raises(edit.Refused, match="no sheet called 'attic'"):
        edit.hide_sheet(house, 'attic', ws=ws)
    assert [i for i in solve.solve(house).issues() if i[1] == 'error'] == []     # a hidden sheet may still be changed by another


def test_a_hidden_sheet_has_no_tab_is_not_sent_and_is_still_drawn_and_reported(house, ws):
    edit.hide_sheet(house, 'wider', ws=ws)
    rep, s = cli.build_house(house, ws=ws, quiet=True)
    out = os.path.join(ws.build, 'box')
    assert os.path.exists(os.path.join(out, 'wider.svg')) and 'wider' in [f['id'] for f in rep['sheets']]
    assert [f['hidden'] for f in rep['sheets']] == [False, False, False, True]
    html, sent = open(os.path.join(out, 'index.html')).read(), open(os.path.join(out, 'box-plans.html')).read()
    assert 'id="tab-wider"' not in html and 'id="cv-wider"' not in html and 'WIDER' not in sent and 'id="tab-open"' in sent
    assert 'var HIDDEN=[{"id": "wider", "label": "Wider"}], MOVABLE=["ground", "first", "open"], VERSION="%s";' % edit.version(text(house)) in html
    assert 'Wider' not in page.index([('box', s)]) and '3 sheets' in page.index([('box', s)])
    assert 'WIDER' not in ''.join(s.sheets[0].lines) and len(s.sheets[0].info['figures']) == 1       # nor on the outline: one outline shows
    edit.hide_sheet(house, 'wider', False, ws=ws)
    assert 'WIDER' in ''.join(solve.solve(house).sheets[0].lines)


def test_a_sheet_is_binned_only_when_hidden_and_nothing_needs_it(house, ws):
    with pytest.raises(edit.Refused, match='wider is not hidden: hide a sheet before binning it'):
        edit.bin_sheet(house, 'wider', ws=ws)
    edit.hide_sheet(house, 'ground', ws=ws)
    with pytest.raises(edit.Refused, match=r'ground cannot be binned while first \(a stair `ref`\), open \(`changes:`\) depend on it'):
        edit.bin_sheet(house, 'ground', ws=ws)
    edit.hide_sheet(house, 'ground', False, ws=ws)
    edit.hide_sheet(house, 'wider', ws=ws)
    kept = text(house)
    with pytest.raises(edit.Refused, match='is not as it was at version'):
        edit.bin_sheet(house, 'wider', 'abc', ws=ws)
    assert text(house) == kept
    out = edit.bin_sheet(house, 'wider', edit.version(kept), ws=ws)
    assert out['did'] == 'binned' and out['sheets'] == ['ground', 'first', 'open'] == ids(house)
    assert 'wider' not in text(house) and 'and another' not in text(house)             # its own remark went with it
    assert text(house).endswith('    unlabelled: ok\n  # the last remark of the sheets\n\n# what is said of the outline\noutline:\n  notes: [The outline.]\n')
    with pytest.raises(edit.Refused, match="no sheet called 'wider'"):
        edit.bin_sheet(house, 'wider', ws=ws)


def test_a_sheet_another_extends_or_the_outline_lists_is_not_binned(house, ws):
    open(os.path.join(house, 'house.yaml'), 'w').write(
        HOUSE.replace('    title: WIDER\n', '    title: WIDER\n    extends: open\n').replace('outline:\n', 'outline:\n  sheets: [ground, open]\n'))
    edit.hide_sheet(house, 'open', ws=ws)
    with pytest.raises(edit.Refused, match=r'open cannot be binned while wider \(`extends:`\), the outline sheet \(`outline.sheets`\) depend on it'):
        edit.bin_sheet(house, 'open', ws=ws)
    with pytest.raises(edit.Refused, match='wider must come after open, which is the sheet it extends'):
        edit.order_sheets(house, ['wider', 'open'], ws=ws)
    assert edit.depends(solve.solve(house)) == {'ground': [], 'first': [('ground', 'a stair `ref`')],
                                                'open': [('ground', 'changes')], 'wider': [('ground', 'changes'), ('open', 'extends')]}


@pytest.mark.parametrize('was, now', [
    ('sheets:\n  # the ground floor, as it is\n  - id: ground\n', 'sheets:\n  - {id: tiny, level: ground, envelope: [[0, 0], [4, 0], [4, 4], [0, 4]], unlabelled: ok}\n  - id: ground\n'),
])
def test_a_sheet_written_on_one_line_is_moved_and_binned_and_hidden_by_hand(house, ws, was, now):
    open(os.path.join(house, 'house.yaml'), 'w').write(HOUSE.replace(was, now))
    before = text(house)
    assert edit.order_sheets(house, ['ground', 'tiny'], ws=ws)['sheets'][:2] == ['ground', 'tiny']
    with pytest.raises(edit.Refused, match='make this change in the house file itself'):
        edit.hide_sheet(house, 'tiny', ws=ws)
    assert yaml.safe_load(text(house))['sheets'][1]['id'] == 'tiny' and len(text(house)) == len(before)


def test_sheets_not_written_as_a_list_of_blocks_are_left_to_be_changed_by_hand(house, ws):
    as_map = "survey: {W: 8.0, D: 6.0}\nsheets:\n  ground:\n    envelope: [[0, 0], [W, 0], [W, D], [0, D]]\n    unlabelled: ok\n" \
             "  other:\n    level: ground\n    envelope: [[0, 0], [W, 0], [W, D], [0, D]]\n    unlabelled: ok\nlevels: [ground]\n"
    flow = "sheets: [{id: a, envelope: [[0, 0], [4, 0], [4, 4], [0, 4]], unlabelled: ok}, {id: b, level: a, envelope: [[0, 0], [4, 0], [4, 4], [0, 4]], unlabelled: ok}]\n"
    for body in (as_map, flow):
        open(os.path.join(house, 'house.yaml'), 'w').write(body)
        assert solve.solve(house)
        for change in (lambda: edit.order_sheets(house, ['other', 'ground'], ws=ws), lambda: edit.hide_sheet(house, 'ground', ws=ws),
                       lambda: edit.bin_sheet(house, 'ground', ws=ws)):
            with pytest.raises(edit.Refused, match='make this change in the house file itself'):
                change()
        assert text(house) == body


def test_hidden_is_true_or_false_and_not_every_sheet(house):
    with pytest.raises(ConfigError, match='sheets.open.hidden: true or false, not'):
        solve.solves(HOUSE.replace('    changes: ground\n', '    changes: ground\n    hidden: maybe\n'))
    with pytest.raises(ConfigError, match='every sheet is `hidden: true`'):
        solve.solves("sheets:\n  - {id: a, hidden: true, envelope: [[0, 0], [1, 0], [1, 1]]}\n")


def test_a_change_goes_in_whole_or_not_at_all_and_the_pages_follow(house, ws):
    cli.build_all(ws)
    page_ = lambda: open(os.path.join(ws.build, 'box', 'index.html')).read()
    assert 'id="tab-wider"' in page_()
    edit.hide_sheet(house, 'wider', ws=ws)
    assert 'id="tab-wider"' not in page_()                              # drawn again, without being asked
    before, drawn = text(house), page_()
    with pytest.raises(edit.Refused, match='would not solve'):
        edit.rewrite(os.path.join(house, 'house.yaml'), before.replace('levels: [ground, first]', 'levels: [ground]'), ws)
    assert text(house) == before and page_() == drawn
    was, after, solved = edit.rewrite(os.path.join(house, 'house.yaml'), before.replace('name: ROOM', 'name: HALL'), ws)
    assert edit.moved(was, after, solved)['changed'] == ["sheets.ground.rooms[0].name: 'ROOM' → 'HALL'"]
    assert report.state(after)['sheets']['ground']['rooms'][0]['name'] == 'HALL' and 'HALL' in page_()
    with pytest.raises(edit.Refused, match='already in it once'):
        edit.same(text(house), 'abcdef', 'name: HALL')
    assert edit.same(text(house), edit.version(text(house))) is None and edit.same(text(house), None) is None
