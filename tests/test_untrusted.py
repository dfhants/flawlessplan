# -*- coding: utf-8 -*-
"""A house file is treated as untrusted when it is drawn: its text is
escaped wherever it lands, it cannot name a path, and nothing in it can
keep a build busy. Only `public/` is hosted, but a file that is sent or a
page that is opened is somebody's browser all the same."""
import json
import os
import re
import time
import xml.etree.ElementTree as ET
import pytest

from conftest import BOX, ROOM
from flawlessplan import cli, mcp_server as mcp, model, page, solve
from flawlessplan.model import ConfigError

# each would do something if it reached a page as it is written
SCRIPT = '</script><script>alert(1)</script>'
IMG = '<img src=x onerror=alert(2)>'
ATTR = '" onmouseover="alert(3)" x="'
SVG = '</text><svg onload=alert(4)>'
CDATA = ']]><script>alert(5)</script>'
ENTITY = '&lt;script&gt;alert(6)&lt;/script&gt; &amp; <b>'
ALL = [SCRIPT, IMG, ATTR, SVG, CDATA, ENTITY]
RAW = ['<script>alert(', '<img src=x', 'onmouseover="alert(3)"', '<svg onload', '<b>']


def q(text):
    """A string as YAML will read it back unchanged."""
    return json.dumps(text)


def nasty(payload):
    """A house with `payload` everywhere a house file takes words."""
    p = q(payload)
    return """
house: {name: %(p)s, front: south, front_note: %(p)s}
survey: {W: 8.0, D: 6.0}
levels: [ground, %(lvl)s]
outline: {notes: {summary: %(p)s, about: [%(p)s]}}
sheets:
  - id: ground
    title: %(p)s
    tab: %(p)s
    scheme: %(p)s
    envelope: [{at: [0, 0], id: %(p)s}, [W, 0], [W, D], [0, D]]
    walls:
      - {id: %(pw)s, from: [4, 0], to: [4, D]}
    openings:
      - {door: std, wall: %(pw)s, at: centre, id: %(p)s}
    rooms:
      - {name: %(p)s, id: %(p)s, at: [1, 1], sub: %(p)s}
      - {name: OTHER, at: [7, 1], label: east, sub: %(p)s}
    zones:
      - {name: %(p)s, rooms: [OTHER], sub: %(p)s}
    stairs:
      - {id: %(p)s, path: [[6, 5], [6, 3]], label: %(p)s}
    areas:
      - {rect: [[8, 0], [10, 2]], style: outdoor, label: %(p)s, sub: %(p)s}
      - {rect: [[8, 3], [10, 5]], style: below, label: %(p)s, sub: %(p)s, rot: -90}
    labels:
      - {at: [2, 5], text: %(p)s}
    dims:
      - {from: [0, 7], to: [W, 7], text: %(p)s}
    fittings:
      - {unit: true, wall: env.2, at: {from_start: 0.5}, label: %(p)s}
    require:
      - {that: 'W > 100', message: %(p)s}
    notes:
      summary: %(p)s
      decided: [%(p)s]
      unconfirmed: [%(p)s]
      needs: [%(p)s]
      about: [%(p)s]
  - id: upper
    level: %(lvl)s
    envelope: [[0, 0], [W, 0], [W, D], [0, D]]
    unlabelled: ok
""" % {'p': p, 'pw': q('w ' + payload), 'lvl': q('L ' + payload)}


def built(ws, text, name='nasty'):
    """Every file a build writes for a house, by its path under build/."""
    os.makedirs(os.path.join(ws.houses, name))
    with open(os.path.join(ws.houses, name, 'house.yaml'), 'w') as fh:
        fh.write(text)
    cli.build_all(ws)
    cli.build_all(ws, public=True)
    out = {}
    for root in (ws.build, ws.public):
        for d, _, fs in os.walk(root):
            for f in fs:
                if f.endswith(('.html', '.svg', '.md', '.json', '.webmanifest')) and name in os.path.join(d, f) or f == 'index.html':
                    with open(os.path.join(d, f), encoding='utf-8') as fh:
                        out[os.path.relpath(os.path.join(d, f), ws.root)] = fh.read()
    return out


def without_our_own(html):
    """A page less the scripts and styles the engine put there itself."""
    return re.sub(r'<(script|style)\b[^>]*>.*?</\1>', '', html, flags=re.S)


def made_of(html):
    """Every (tag, attribute) a browser would find in a page."""
    from html.parser import HTMLParser
    found = set()

    class Reader(HTMLParser):
        def handle_starttag(self, tag, attrs):
            found.update([(tag, None)] + [(tag, k) for k, _ in attrs])
    Reader().feed(html)
    return found


@pytest.mark.parametrize('payload', ALL)
def test_words_in_a_house_file_are_words_wherever_they_land(ws, payload):
    plain = solve.solves(nasty('plain'))
    ours = made_of(page.markup('plain', plain.sheets, root='../', send='x.html')) | made_of(page.share('plain', plain.sheets)) \
        | made_of(page.index([(n, solve.solve(ws.house(n))) for n in ws.names()] + [('nasty', plain)])) \
        | set().union(*[made_of(s.svg()) for s in plain.sheets])
    files = built(ws, nasty(payload))
    pages = [f for f in files if f.endswith(('.html', '.svg'))]
    assert len([f for f in pages if 'nasty' in f]) == 2*(3 + 2) and len(files) > 16      # each sheet, the page, the one to send; twice
    for f in pages:
        for raw in RAW:
            assert raw not in without_our_own(files[f]), '%s reaches %s as markup' % (raw, f)
        assert files[f].count('<script') <= 2 and '<script' not in without_our_own(files[f])
        assert made_of(files[f]) <= ours, (f, made_of(files[f]) - ours)    # no tag and no attribute the words brought with them
        assert not [a for _, a in made_of(files[f]) if a and a.startswith('on')]
    for f in files:
        if f.endswith('.svg'):
            ET.fromstring(files[f])                                     # still one well-formed drawing
    rep = json.loads(files['build/nasty/report.json'])
    assert rep['house'] == payload and rep['sheets'][0]['rooms'][0]['name'] == payload    # and as data it is what was written


@pytest.mark.parametrize('payload', ALL)
def test_what_a_page_hands_its_own_script_cannot_end_the_script(ws, payload):
    files = built(ws, nasty(payload))
    plain = solve.solves(nasty('plain'))
    for f, ours in (('build/nasty/index.html', page.markup('plain', plain.sheets, root='../', send='nasty-plans.html')),
                    ('build/nasty/nasty-plans.html', page.share('plain', plain.sheets))):
        assert files[f].count('<script') == ours.count('<script') >= 1          # as many scripts as the page has of its own
        assert files[f].count('</script>') == ours.count('</script>') == ours.count('<script')
        assert files[f].count('<!--') == ours.count('<!--')
    labels = re.search(r'LABEL=(\{.*?\});', files['build/nasty/index.html'])
    assert json.loads(labels.group(1))['ground'] == payload                     # and its script is handed the words whole


def test_a_name_that_looks_like_a_place_in_the_template_is_only_a_name(ws):
    """The page is filled in once through: what is put in is not read again."""
    for token in ('__JS__', '__STAGES__', '__INFOS__', '__ICON__', '__SEND__', '__HOME__', '__FONTS__', '__CSS__', '__KEYS__',
                  '__LABELS__', '__VIEW__', '__HOUSES__', '__TITLE__', '__TABS__', '__SHEETS__', '__DRAWING__', '__NOPE__'):
        s = solve.solves(nasty(token))
        for html in (page.markup(s.house['name'], s.sheets, root='../', send='x.html'), page.share(s.house['name'], s.sheets),
                     page.index([('nasty', s)])):
            assert html.count('<script') == html.count('</script>') <= 2 and html.count('<title>') == 1
            assert html.count(token) >= 3 and len(html) < 400000         # there as written, and nothing was pasted in its place
            assert '<title>%s</title>' % token in html or 'Flawlessplan' in html


def test_a_house_file_cannot_put_a_class_or_an_attribute_on_the_drawing():
    for extra, why in (("dims: [{from: [0, 7], to: [8, 7], style: '\"><script>alert(1)</script>'}]", 'no dimension style'),
                       ("labels: [{at: [2, 2], text: hi, rot: '0)\"><script>alert(1)</script><g x=\"('}]", 'rot'),
                       ("labels: [{at: [2, 2], text: hi, style: 'note\" onload=\"alert(1)'}]", 'no text style'),
                       ("areas: [{rect: [[1, 1], [2, 2]], style: 'below\" onload=\"alert(1)'}]", 'no area style'),
                       ("areas: [{rect: [[1, 1], [2, 2]], label: A, rot: '0 0 0)\" onload=\"alert(1)'}]", 'rot'),
                       ("rooms: [{name: A, at: [1, 1], rot: '\" onload=\"alert(1)'}]", 'rot'),
                       ("rooms: [{name: A, at: [1, 1], label: '\" onload=\"alert(1)'}]", 'label'),
                       ("openings: [{door: std, wall: north, style: 'swing\" onload=\"alert(1)'}]", 'unknown style')):
        with pytest.raises(ConfigError, match=why):
            model.loads(ROOM + '    ' + extra + '\n')
    svg = solve.solves(ROOM + "    labels: [{at: [2, 2], text: hi, rot: 12.5}]\n").sheet('ground').svg()
    assert 'transform="rotate(12.5 200 200)"' in svg                    # a turn is a number, and is written as one


def test_every_class_in_a_drawing_is_one_the_engine_wrote(ws):
    files = built(ws, nasty(ATTR))
    from flawlessplan import labels, render
    known = set(render.AREAS) | {v[1] for v in render.AREAS.values()} | set(render.TEXT.values()) | set(labels.CH) | {
        'floor', 'wall', 'gone', 'new', 'zone', 'edge', 'fitting', 'fitline', 'stair', 'stairline', 'arrow', 'arrowhead', 'win', 'dr',
        'swing', 'fold', 'leader', 'dimline', 'dimtext', 'dimtext soft', 'dimtext calc', 'compass', 'northarrow', 'front', 'note',
        'grid', 'grid5', 'env', 'sheetname', 'caption', 'figure', 'rmname small'}
    for f in files:
        if f.endswith('.svg'):
            assert set(re.findall(r'class="([^"]*)"', files[f])) <= known, f
            assert set(re.findall(r'<(\w+)', without_our_own(files[f]))) <= {'svg', 'rect', 'path', 'line', 'text', 'circle', 'g', 'defs', 'clipPath'}


# ---- a house file cannot name a path

@pytest.mark.parametrize('sid', ['../../escaped', '/tmp/escaped', '..', 'a/b', 'con\x00', 'x.svg', '~', 'C:\\x', 'ground\n', '-rf'])
def test_a_sheet_id_cannot_name_a_path(ws, sid):
    with pytest.raises(ConfigError, match='letters, digits'):
        model.loads('sheets: [{id: %s, envelope: [[0, 0], [4, 0], [4, 4], [0, 4]]}]' % q(sid))


def test_a_build_writes_inside_its_own_folder_and_nowhere_else(ws, tmp_path):
    before = sorted(os.listdir(str(tmp_path.parent)))
    files = built(ws, nasty('../../../../escaped'))
    made = sorted(os.path.relpath(os.path.join(d, f), ws.root) for d, _, fs in os.walk(ws.root) for f in fs)
    assert not [f for f in made if 'escaped' in f] and sorted(os.listdir(str(tmp_path.parent))) == before
    assert sorted(os.listdir(os.path.join(ws.build, 'nasty'))) == ['ground.md', 'ground.svg', 'index.html', 'nasty-plans.html',
                                                                   'outline.md', 'outline.svg', 'report.json', 'upper.md', 'upper.svg']
    assert 'href="nasty-plans.html" download' in files['build/nasty/index.html']       # named for its folder, not its house: name


def test_a_folder_whose_name_will_not_do_is_not_a_house(ws, capsys):
    for name in ('my house', '"><script>alert(1)</script>', '.hidden', 'a.b'):
        os.makedirs(os.path.join(ws.houses, name))
        open(os.path.join(ws.houses, name, 'house.yaml'), 'w').write(ROOM)
    assert ws.names() == ['bungalow', 'cottage']
    assert cli.main(['-w', ws.root, 'build', '--quiet']) == 0 and cli.main(['-w', ws.root, 'build', '--public', '--quiet']) == 0
    index = open(os.path.join(ws.build, 'index.html')).read()
    assert '<script>alert(1)' not in index and '2 houses' in index
    assert cli.main(['-w', ws.root, 'check', 'my house']) == 1 and 'no house called' in capsys.readouterr().err


def test_a_house_cannot_be_written_outside_the_houses_folder(houses, tmp_path):
    before = sorted(os.path.relpath(os.path.join(d, f), str(tmp_path)) for d, _, fs in os.walk(str(tmp_path)) for f in fs)
    for name in ('../escaped', '..', '/tmp/escaped', 'a/b', '.hidden', '', 'x y', 'cottage/../../escaped', 'escaped\n', '~', '-x'):
        for call in (lambda: mcp.write_house(name, ROOM), lambda: mcp.read_house(name)['text'], lambda: mcp.edit_house(name, 'a', 'b'),
                     lambda: mcp.check(name), lambda: mcp.share(name), lambda: mcp.marks(name), lambda: mcp.crop(name, 'ground'),
                     lambda: mcp.set_measurement(name, 'W', 1), lambda: mcp.measurements(name), lambda: mcp.sheet_report(name),
                     lambda: mcp.at(name, 'ground', 1, 1), lambda: mcp.settle_note(name, 'ground', 'x'), lambda: mcp.show(name)):
            with pytest.raises(mcp.ToolError):
                call()
    after = sorted(os.path.relpath(os.path.join(d, f), str(tmp_path)) for d, _, fs in os.walk(str(tmp_path)) for f in fs)
    assert [f for f in after if f not in before and not f.startswith('build')] == []
    assert not os.path.exists(str(tmp_path.parent / 'escaped')) and not os.path.exists('/tmp/escaped/house.yaml')


# ---- a house file is data: reading one runs nothing

@pytest.mark.parametrize('text', [
    '!!python/object/apply:os.system ["touch %s"]',
    'a: !!python/object/new:os.system ["touch %s"]',
    'a: !!python/name:os.system\nb: "%s"',
    '!!python/object/apply:subprocess.check_output [["touch", "%s"]]',
    'survey: {W: !!python/object/apply:builtins.eval ["open(\'%s\', \'w\')"]}',
])
def test_yaml_that_asks_to_run_something_is_refused(tmp_path, text):
    marker = str(tmp_path / 'ran')
    with pytest.raises(ConfigError, match='not YAML that can be read'):
        model.loads(text % marker)
    assert not os.path.exists(marker)


@pytest.mark.parametrize('expr', [
    '__import__("os").system("touch %s")', 'open("%s", "w")', '().__class__.__base__.__subclasses__()', 'exec("import os")',
    'eval("1")', 'globals()', 'getattr(W, "real")', '(lambda: 1)()', 'W.__class__', 'compile("1", "", "eval")', 'breakpoint()',
])
def test_an_expression_can_reach_nothing_but_arithmetic(tmp_path, expr):
    marker = str(tmp_path / 'ran')
    src = expr % marker if '%s' in expr else expr
    for text in (ROOM + 'lines: {A: %s}\n' % q(src), ROOM + '    notes: [%s]\n' % q('{%s}' % src),
                 ROOM.replace('at: [1, 1]', 'at: [1, %s]' % q(src)), ROOM + '    require: [{that: %s}]\n' % q(src + ' > 1')):
        with pytest.raises(ValueError):
            solve.solves(text)
    assert not os.path.exists(marker)


# ---- nothing in a house file can keep a build busy

def within(seconds, text):
    """Solve `text`, or be told it will not solve — either way, soon."""
    start = time.time()
    try:
        s = solve.solves(text)
        [sh.svg() for sh in s.sheets]
        said = 'solved'
    except ValueError as e:
        said = str(e)
    assert time.time() - start < seconds, 'took %.1f s' % (time.time() - start)
    return said


@pytest.mark.parametrize('expr', ['9**9**9', '9**9**9**9', '(9**16)**16', '2**(2**(2**(2**(2**2))))', '10**16 * 10**16 * 10**16',
                                  '"a" * 10**12', '1e308 * 1e308', 'round(1e308, 300)', 'int(1e308) ** 2', '-(-(-(-(9**99))))',
                                  'hypot(' + ', '.join(['1e154']*200) + ')', 'max(' + ', '.join(['1']*5000) + ')'])
def test_an_expression_cannot_run_away(expr):
    said = within(5, ROOM + 'lines: {A: %s}\n' % q(expr))
    assert said == 'solved' or said.startswith('lines.A: ')


def test_brackets_or_a_sum_past_all_reason_are_answered_and_not_a_crash():
    for expr in ('(' * 5000 + '1' + ')' * 5000, '+'.join(['1'] * 60000), '-' * 20000 + '1', 'W' + '*W' * 20000):
        said = within(20, ROOM + 'lines: {A: %s}\n' % q(expr))
        assert said == 'solved' or (said.startswith('lines.A: ') and len(said) < 400), said[:200]


def test_a_format_cannot_pad_a_note_to_a_million_columns():
    for spec in ('>1000000', '1000000', '.1000000f', '01000000', ',', '^999999', '1000000.1f', '{W}'):
        said = within(5, ROOM + '    notes: [%s]\n' % q('{W:%s}' % spec))
        assert said.startswith('sheet ground: format') or said == 'solved'
        assert said != 'solved' or len(solve.solves(ROOM + '    notes: [%s]\n' % q('{W:%s}' % spec)).sheet('ground').info['groups'][0][2][0]) < 50


def test_an_envelope_of_a_thousand_corners_is_drawn():
    import math
    ring = ', '.join('[%.4f, %.4f]' % (20 + 20*math.cos(2*math.pi*i/1000), 20 + 20*math.sin(2*math.pi*i/1000)) for i in range(1000))
    said = within(60, "sheets:\n  - id: g\n    envelope: [%s]\n    rooms: [{name: ROUND, at: [20, 20]}]\n" % ring)
    assert said == 'solved'


def test_hundreds_of_walls_and_thousands_of_notes_are_answered():
    walls = ''.join("      - {from: [%g, 0], to: [%g, 6]}\n" % (0.3 + 0.024*i, 0.3 + 0.024*i) for i in range(300))
    said = within(60, ROOM + "    unlabelled: ok\n    walls:\n" + walls)
    assert said == 'solved' or said.startswith('sheet ground: ')
    notes = ''.join("      - 'Note {W:.2f} number %d'\n" % i for i in range(3000))
    assert within(20, ROOM + "    notes:\n" + notes) == 'solved'


def test_parts_that_use_each_other_a_long_way_down_are_answered():
    chain = ''.join('  p%d: {use: [p%d]}\n' % (i, i + 1) for i in range(3000)) + '  p3000: {}\n'
    said = within(20, 'parts:\n' + chain + ROOM + '    use: [p0]\n')
    assert said == 'solved' or 'nested too deep' in said or 'not laid out' in said
    wide = ''.join('  p%d: {notes: [n%d]}\n' % (i, i) for i in range(3000))
    assert within(20, 'parts:\n' + wide + ROOM + '    use: [%s]\n' % ', '.join('p%d' % i for i in range(3000))) == 'solved'


def test_yaml_that_swells_as_it_is_read_is_answered():
    """A billion laughs: nine levels of nine aliases each is 387 million strings once flattened. It is never flattened."""
    bomb = 'a0: &a0 [x, x, x, x, x, x, x, x, x]\n' + ''.join(
        'a%d: &a%d [%s]\n' % (i, i, ', '.join(['*a%d' % (i - 1)]*9)) for i in range(1, 10))
    for use in ('', '    notes: *a9\n', '    walls: *a9\n', '    rooms: *a9\n'):
        said = within(20, bomb + ROOM + use)
        assert 'too much to be a house file' in said, said[:300]


def test_a_tool_will_not_take_a_house_file_past_all_reason(houses):
    with pytest.raises(mcp.ToolError, match='too long to be a house file'):
        mcp.write_house('huge', ROOM + '# ' + 'x' * mcp.LONGEST)
    with pytest.raises(mcp.ToolError, match='too long to be a house file'):
        mcp.edit_house('cottage', mcp.read_house('cottage')['text'].split('\n')[0], '# ' + 'x' * mcp.LONGEST)
    assert not os.path.exists(str(houses / 'huge')) and len(mcp.read_house('cottage')['text']) < 20000
