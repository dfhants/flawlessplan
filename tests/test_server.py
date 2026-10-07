# -*- coding: utf-8 -*-
"""The pages over HTTP: what is served, what is saved and where, and
everything a request from somewhere else is refused. This is the one part
of flawlessplan that writes a file because something on the network asked."""
import http.client
import json
import os
import threading
import pytest

from flawlessplan import cli, server
from flawlessplan.workspace import Workspace

NOTE = [{'type': 'note', 'sheet': 'ground', 'x': 1.5, 'y': 2.5, 'text': 'the WC is smaller', 'ts': 1}]


@pytest.fixture(scope='module')
def running(tmp_path_factory):
    """The example workspace, built once and served for every test here."""
    ws = Workspace(str(tmp_path_factory.mktemp('served')))
    ws.init()
    cli.build_all(ws)
    srv = server.start(ws, 0)
    thread = threading.Thread(target=srv.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
    thread.start()
    yield ws, srv.server_address[1]
    srv.shutdown()
    srv.server_close()
    thread.join(5)


@pytest.fixture
def served(running):
    """The same, with nothing drawn on it: (workspace, port)."""
    ws, port = running
    for name in ws.names():
        if os.path.exists(ws.marks(name)):
            os.remove(ws.marks(name))
    return ws, port


def ask(port, method, path, body=None, **headers):
    """One request, written out header by header so any of them can be wrong."""
    c = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
    try:
        c.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        head = {'Host': '127.0.0.1:%d' % port}
        if body is not None:
            body = body if isinstance(body, bytes) else json.dumps(body).encode('utf-8')
            head.update({'Content-Type': 'application/json', 'Content-Length': str(len(body))})
        head.update((k.replace('_', '-'), v) for k, v in headers.items())
        for k, v in head.items():
            if v is not None:
                c.putheader(k, v)
        try:
            c.endheaders(body)
        except (BrokenPipeError, ConnectionResetError):
            pass                                    # refused before it was all sent: the answer may still be there
        try:
            r = c.getresponse()
        except (http.client.HTTPException, ConnectionError):
            return None, b'', {}                    # hung up on
        return r.status, r.read(), dict((k.lower(), v) for k, v in r.getheaders())
    finally:
        c.close()


def everything_under(root):
    return sorted(os.path.relpath(os.path.join(d, f), root) for d, _, fs in os.walk(root) for f in fs)


# ---- what is served

def test_the_pages_are_served_and_never_from_the_browsers_cache(served):
    ws, port = served
    for path, inside in (('/', b'cottage/index.html'), ('/index.html', b'cottage/index.html'),
                         ('/cottage/', b'<title>Cottage</title>'), ('/cottage/ground.svg', b'<svg'),
                         ('/cottage/report.json', b'"rooms"'), ('/cottage/cottage-plans.html', b'<title>Cottage</title>')):
        status, body, head = ask(port, 'GET', path)
        assert status == 200 and inside in body, path
        assert head['cache-control'] == 'no-store'          # a rebuilt sheet must be the one that is seen
    assert ask(port, 'GET', '/nowhere.html')[0] == 404
    status, body, _ = ask(port, 'HEAD', '/cottage/index.html')
    assert status == 200 and body == b''


def test_either_name_for_this_machine_will_do(served):
    ws, port = served
    for host in ('127.0.0.1:%d' % port, 'localhost:%d' % port):
        assert ask(port, 'GET', '/cottage/', Host=host)[0] == 200
        for origin in ('http://127.0.0.1:%d' % port, 'http://localhost:%d' % port):
            assert ask(port, 'PUT', '/cottage/marks.json', NOTE, Host=host, Origin=origin)[0] == 204


def test_only_what_was_built_is_served(served):
    """build/ is the root: a house file, and anything else beside it, is not."""
    ws, port = served
    open(os.path.join(ws.root, 'secret.txt'), 'w').write('not for serving')
    for path in ('/../secret.txt', '/..%2fsecret.txt', '/%2e%2e/secret.txt', '/cottage/../../secret.txt',
                 '/../houses/cottage/house.yaml', '/houses/cottage/house.yaml', '//etc/passwd', '/..\\secret.txt',
                 '/cottage/..%2f..%2fhouses/cottage/house.yaml', '/.%2e/.%2e/secret.txt'):
        status, body, _ = ask(port, 'GET', path)
        assert b'not for serving' not in body and b'survey:' not in body and b'root:' not in body, path
        assert status in (301, 400, 404), path


# ---- what is saved

def test_marks_are_saved_in_the_houses_folder_and_come_back(served):
    ws, port = served
    assert ask(port, 'GET', '/cottage/marks.json') [:2] == (200, b'[]')        # nothing drawn yet
    status, body, head = ask(port, 'PUT', '/cottage/marks.json', NOTE)
    assert (status, body) == (204, b'')
    dest = os.path.join(ws.houses, 'cottage', 'marks.json')
    assert json.load(open(dest)) == NOTE                                       # beside the house, where a rebuild leaves it
    assert not os.path.exists(os.path.join(ws.build, 'cottage', 'marks.json'))
    status, body, head = ask(port, 'GET', '/cottage/marks.json')
    assert status == 200 and json.loads(body) == NOTE
    assert head['content-type'] == 'application/json' and head['cache-control'] == 'no-store'
    assert ask(port, 'GET', '/cottage/marks.json?v=123')[1] == body            # a query does not hide it
    cli.build_all(ws)
    assert json.load(open(dest)) == NOTE
    assert ask(port, 'PUT', '/cottage/marks.json', [])[0] == 204 and json.load(open(dest)) == []


def test_a_mark_resolved_while_a_page_was_open_stays_resolved_and_the_page_is_told(served):
    """A page holds the whole list and sends it back; what an agent closed
    meanwhile is not opened again by that, and the stamp says to read again."""
    from flawlessplan import marks
    ws, port = served
    stamp = lambda: json.loads(ask(port, 'GET', '/cottage/stamp')[1])
    drawn = [dict(NOTE[0], ts=1759800005000), {'type': 'pen', 'sheet': 'ground', 'ts': 1759800009000, 'pts': [[5, 4], [6, 5]]}]
    assert ask(port, 'PUT', '/cottage/marks.json', drawn)[0] == 204
    before = stamp()
    assert before.count('.') == 1 and stamp() == before
    marks.resolve(ws.marks('cottage'), ['mmgfvhi88'], 'made smaller', ['ground'], ['ground', 'first'])
    after = stamp()
    assert after != before and after.split('.')[0] == before.split('.')[0]      # the same page, other marks
    assert ask(port, 'PUT', '/cottage/marks.json', drawn + [dict(NOTE[0], ts=7)])[0] == 204
    got = json.loads(ask(port, 'GET', '/cottage/marks.json')[1])
    assert got[0]['status'] == 'resolved' and got[0]['how'] == 'made smaller' and got[0]['applied'] == ['ground']
    assert got[1:] == [drawn[1], dict(NOTE[0], ts=7)] and stamp() == after
    assert ask(port, 'PUT', '/cottage/marks.json', drawn[1:])[0] == 204        # the owner deletes it: gone for good
    assert json.loads(ask(port, 'GET', '/cottage/marks.json')[1]) == drawn[1:] and stamp() == before
    open(ws.marks('cottage'), 'w').write('{not json')
    assert stamp() == before.split('.')[0] + '.' and ask(port, 'PUT', '/cottage/marks.json', drawn)[0] == 204


# ---- what the page does to the sheets is a change to the house file

@pytest.fixture
def sheets(served):
    """The served workspace with the bungalow's file put back after: (port, a way to read the file, its version)."""
    from flawlessplan import edit
    ws, port = served
    path = os.path.join(ws.house('bungalow'), 'house.yaml')
    kept = open(path).read()
    yield port, (lambda: open(path).read()), (lambda: edit.version(open(path).read()))
    open(path, 'w').write(kept)
    edit.redraw(ws.house('bungalow'), ws)


def test_the_page_hides_shows_and_bins_a_sheet_through_the_house_file(sheets):
    port, text, version = sheets
    page = lambda: ask(port, 'GET', '/bungalow/index.html')[1].decode()
    stamp = lambda: ask(port, 'GET', '/bungalow/stamp')[1]
    before, drawn = text(), stamp()
    assert 'id="tab-infill"' in page() and 'VERSION="%s"' % version() in page()
    status, body, head = ask(port, 'POST', '/bungalow/sheets', {'version': version(), 'hide': 'infill'})
    out = json.loads(body)
    assert status == 200 and head['content-type'] == 'application/json' and out['did'] == 'hidden' and out['version'] == version()
    assert '  - id: infill\n    hidden: true\n' in text() and 'id="tab-infill"' not in page() and stamp() != drawn   # and the page is told
    assert 'VERSION="%s"' % version() in page() and '"id": "infill", "label": "Infill"' in page()
    # the page that asked is now behind: what it asks next with the version it had is refused, and it is drawn again
    status, body, _ = ask(port, 'POST', '/bungalow/sheets', {'version': out['version'][::-1], 'bin': 'infill'})
    assert status == 409 and 'is not as it was at version' in json.loads(body)['error'] and 'hidden: true' in text()
    status, body, _ = ask(port, 'POST', '/bungalow/sheets', {'version': version(), 'hide': 'ground'})
    assert status == 409 and json.loads(body)['error'] == 'not changed — ground is the only sheet showing: a house shows at least one'
    status, body, _ = ask(port, 'POST', '/bungalow/sheets', {'version': version(), 'bin': 'ground'})
    assert status == 409 and 'ground is not hidden: hide a sheet before binning it' in json.loads(body)['error']
    assert ask(port, 'POST', '/bungalow/sheets', {'version': version(), 'show': 'infill'})[0] == 200 and text() == before
    assert ask(port, 'POST', '/bungalow/sheets', {'version': version(), 'hide': 'infill'})[0] == 200
    status, body, _ = ask(port, 'POST', '/bungalow/sheets', {'version': version(), 'bin': 'infill'})
    assert status == 200 and json.loads(body)['sheets'] == ['ground'] and 'id: infill' not in text() and 'infill' not in page()


def test_the_page_puts_sheets_in_order_and_is_told_why_not(sheets):
    port, text, version = sheets
    status, body, _ = ask(port, 'POST', '/bungalow/sheets', {'version': version(), 'order': ['infill', 'ground']})
    assert status == 409 and json.loads(body)['error'] == 'not changed — infill must come after ground, which is the sheet it changes'
    kept = text()
    status, body, _ = ask(port, 'POST', '/bungalow/sheets', {'version': version(), 'order': ['ground', 'infill']})
    assert status == 200 and json.loads(body)['did'] == 'nothing: it is so already' and text() == kept


@pytest.mark.parametrize('body, code', [
    ({'hide': 'infill'}, 400), ({'version': '', 'hide': 'infill'}, 400), ({'version': 5, 'hide': 'infill'}, 400),
    ({'version': 'x'}, 400), ({'version': 'x', 'hide': 'infill', 'bin': 'infill'}, 400), ({'version': 'x', 'hide': ['infill']}, 400),
    ({'version': 'x', 'order': 'ground'}, 400), ({'version': 'x', 'order': ['ground', 5]}, 400), ({'version': 'x', 'hide': None}, 400),
    ([{'version': 'x', 'hide': 'infill'}], 400), ('hide infill', 400), (b'{not json', 400), (b'', 400), (b' ' * 70000, 400),
    ({'version': 'x', 'hide': 'infill'}, 409), ({'version': 'x', 'hide': '../cottage'}, 409),
])
def test_a_change_to_the_sheets_that_is_not_one_is_refused_and_nothing_is_written(sheets, body, code):
    port, text, version = sheets
    before = text()
    assert ask(port, 'POST', '/bungalow/sheets', body)[0] == code and text() == before


@pytest.mark.parametrize('headers', [{'Host': 'evil.example'}, {'Origin': 'http://evil.example'}, {'Origin': 'null'},
                                     {'Content_Type': 'text/plain'}, {'Content_Type': 'application/x-www-form-urlencoded'}])
def test_only_this_servers_own_page_changes_a_house_file(sheets, headers):
    """A page on another site can make a browser send a form here; it cannot say it is JSON, or that it came from us."""
    port, text, version = sheets
    before = text()
    assert ask(port, 'POST', '/bungalow/sheets', {'version': version(), 'hide': 'infill'}, **headers)[0] == 403 and text() == before


@pytest.mark.parametrize('path, code', [('/nowhere/sheets', 400), ('/bungalow/sheets/', 405), ('/sheets', 405), ('/bungalow/marks.json', 405),
                                        ('/bungalow/house.yaml', 405), ('/../bungalow/sheets', 405), ('/bungalow/sheets?x=1', 409)])
def test_sheets_are_changed_for_a_house_that_is_there_and_nowhere_else(sheets, path, code):
    port, text, version = sheets
    before = text()
    assert ask(port, 'POST', path, {'version': 'x', 'hide': 'infill'})[0] == code and text() == before


def test_each_house_keeps_its_own_marks(served):
    ws, port = served
    ask(port, 'PUT', '/cottage/marks.json', NOTE)
    assert ask(port, 'GET', '/bungalow/marks.json')[1] == b'[]'
    assert not os.path.exists(ws.marks('bungalow'))


def test_what_is_written_is_what_was_sent_whatever_is_in_it(served):
    """Text with markup in it, other alphabets, and nothing the server
    reads or acts on: it is the owner's writing and is kept as it came."""
    ws, port = served
    odd = [{'type': 'note', 'sheet': 'ground', 'x': 1, 'y': 1, 'ts': 2,
            'text': '</script><script>alert(1)</script> “quoted” — ñ 日本語 \u2028 \x00'},
           {'type': 'pen', 'sheet': '../../x', 'pts': [[0, 0], [1e308, -1e308]], 'ts': 'soon'}, 7, None, 'words', {}]
    assert ask(port, 'PUT', '/cottage/marks.json', odd)[0] == 204
    assert json.loads(ask(port, 'GET', '/cottage/marks.json')[1]) == odd
    assert json.load(open(ws.marks('cottage'), encoding='utf-8')) == odd


def test_many_saves_at_once_leave_one_whole_file(served):
    ws, port = served
    sent = [[dict(NOTE[0], text='save %d' % i, ts=i)] * 200 for i in range(24)]
    got = []
    threads = [threading.Thread(target=lambda b=b: got.append(ask(port, 'PUT', '/cottage/marks.json', b)[0])) for b in sent]
    [t.start() for t in threads]
    [t.join(20) for t in threads]
    assert got == [204] * 24
    assert json.load(open(ws.marks('cottage'))) in sent                        # one of them, whole
    assert sorted(os.listdir(os.path.join(ws.houses, 'cottage'))) == ['expected.json', 'house.yaml', 'marks.json']


# ---- what is refused

@pytest.mark.parametrize('headers', [
    {'Host': 'evil.example'}, {'Host': 'evil.example:8765'}, {'Host': 'localhost'}, {'Host': '127.0.0.1'},
    {'Host': 'localhost:1'}, {'Host': '[::1]:8765'}, {'Host': None}, {'Host': ''},
    {'Origin': 'http://evil.example'}, {'Origin': 'null'}, {'Origin': ''}, {'Origin': 'https://localhost:PORT'},
    {'Origin': 'http://localhost:PORT.evil.example'}, {'Origin': 'http://localhost'}, {'Origin': 'http://LOCALHOST:PORT/'},
    {'Origin': 'file://'},
])
def test_a_request_meant_for_somewhere_else_is_refused(served, headers):
    """A page on another site can make a browser send a request here. It
    cannot make it name this server as the host, or say it came from it."""
    ws, port = served
    headers = dict((k, v.replace('PORT', str(port)) if v else v) for k, v in headers.items())
    before = everything_under(ws.root)
    for method, body in (('GET', None), ('HEAD', None), ('PUT', NOTE)):
        for path in ('/cottage/marks.json', '/cottage/index.html', '/'):
            status, said, _ = ask(port, method, path, body, **headers)
            assert status == 403 and said == b'', (method, path)
    assert everything_under(ws.root) == before


@pytest.mark.parametrize('kind', ['text/plain', 'application/x-www-form-urlencoded', 'multipart/form-data',
                                  'text/json', '', None, 'application/jsonp', 'application/json-seq'])
def test_only_json_is_saved(served, kind):
    """The three kinds a form or a no-cors fetch can send from another site
    are among these: a save needs a kind that makes the browser ask first."""
    ws, port = served
    assert ask(port, 'PUT', '/cottage/marks.json', NOTE, Content_Type=kind)[0] == 403
    assert not os.path.exists(ws.marks('cottage'))


def test_json_with_a_charset_is_json(served):
    ws, port = served
    assert ask(port, 'PUT', '/cottage/marks.json', NOTE, Content_Type='application/json; charset=utf-8')[0] == 204
    assert ask(port, 'PUT', '/cottage/marks.json', NOTE, Content_Type=' application/json ;charset=utf-8')[0] == 204


@pytest.mark.parametrize('body', [b'', b'not json', b'{"a": 1}', b'"words"', b'7', b'null', b'true', b'[1, 2',
                                  b'\xff\xfe\x00', b'[NaN]garbage', b'[' * 100000])
def test_what_is_not_a_list_of_marks_is_not_saved(served, body):
    ws, port = served
    assert ask(port, 'PUT', '/cottage/marks.json', body)[0] == 400
    assert not os.path.exists(ws.marks('cottage'))


def test_a_save_that_fails_leaves_what_was_there(served):
    ws, port = served
    ask(port, 'PUT', '/cottage/marks.json', NOTE)
    for body in (b'not json', b'{}', b''):
        assert ask(port, 'PUT', '/cottage/marks.json', body)[0] == 400
    assert json.load(open(ws.marks('cottage'))) == NOTE
    assert not [f for f in everything_under(ws.root) if f.endswith('.tmp')]


@pytest.mark.parametrize('length', ['-1', '-99999', '0', 'abc', '1e3', '', '99999999999999999999', str((4 << 20) + 1)])
def test_a_length_that_is_none_or_too_much_is_refused(served, length):
    ws, port = served
    status = ask(port, 'PUT', '/cottage/marks.json', b'[]', Content_Length=length)[0]
    assert status == 400
    assert not os.path.exists(ws.marks('cottage'))
    assert ask(port, 'GET', '/cottage/')[0] == 200             # and the server is still there


def test_the_most_that_will_be_saved_is_saved(served):
    ws, port = served
    pad = b'[' + b' ' * ((4 << 20) - 2) + b']'
    assert len(pad) == server.Handler.LIMIT and ask(port, 'PUT', '/cottage/marks.json', pad)[0] == 204
    assert ask(port, 'PUT', '/cottage/marks.json', NOTE)[0] == 204
    assert ask(port, 'PUT', '/cottage/marks.json', pad + b' ')[0] in (400, None)       # refused, or hung up on, unread
    assert json.load(open(ws.marks('cottage'))) == NOTE


@pytest.mark.parametrize('path', [
    '/nowhere/marks.json', '/marks.json', '//marks.json', '/cottage/sub/marks.json', '/../cottage/marks.json',
    '/cottage/../marks.json', '/%2e%2e/marks.json', '/cottage%2f..%2f../marks.json', '/./marks.json', '/../marks.json',
    '/..%2f..%2fetc/marks.json', '/cottage/marks.json/', '/cottage/marks.jsonx', '/cottage/Marks.json',
    '/cottage/house.yaml', '/cottage/expected.json', '/cottage/index.html', '/cottage/', '/', '/cot%20tage/marks.json',
    '/cottage\\..\\marks.json', '/cottage/marks.json%00', '/cottage/marks.json#x', '/.git/marks.json', '/c:/marks.json',
])
def test_marks_are_saved_for_a_house_that_is_there_and_nowhere_else(served, path):
    ws, port = served
    os.makedirs(os.path.join(ws.root, 'etc'), exist_ok=True)
    before = everything_under(ws.root)
    outside = sorted(os.listdir(os.path.dirname(ws.root)))
    status = ask(port, 'PUT', path, NOTE)[0]
    assert status in (400, 404)
    assert everything_under(ws.root) == before
    assert sorted(os.listdir(os.path.dirname(ws.root))) == outside


def test_other_methods_do_nothing(served):
    ws, port = served
    before = everything_under(ws.root)
    for method in ('POST', 'DELETE', 'PATCH', 'OPTIONS', 'TRACE', 'CONNECT'):
        assert ask(port, method, '/cottage/marks.json', NOTE)[0] in (405, 501), method
    assert everything_under(ws.root) == before


def test_it_listens_on_this_machine_only(ws):
    srv = server.start(ws, 0)
    try:
        assert srv.server_address[0] == '127.0.0.1'
    finally:
        srv.server_close()


def test_a_workspace_can_be_served_from_a_thread_on_any_free_port(ws):
    cli.build_all(ws)
    a, b = server.background(ws), server.background(ws)
    assert a != b and a.startswith('http://localhost:') and a.endswith('/')
    port = int(a.rsplit(':', 1)[1].strip('/'))
    assert ask(port, 'GET', '/bungalow/')[0] == 200


def test_serving_makes_the_folder_it_serves(tmp_path):
    ws = Workspace(str(tmp_path / 'new'))
    srv = server.start(ws, 0)
    try:
        assert os.path.isdir(ws.build)
    finally:
        srv.server_close()
