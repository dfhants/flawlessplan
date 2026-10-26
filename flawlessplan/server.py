# -*- coding: utf-8 -*-
"""The pages over HTTP, saving what is drawn on them.

Serves a workspace's build/ and, for each house, <house>/marks.json — read
and written in the house's own folder, outside build/, so a rebuild does
not lose what was drawn. A page sends the whole list; a mark an agent has
resolved meanwhile is kept resolved. <house>/stamp stands for a house's page as it is
drawn now: an open page asks for it, and loads itself again when it changes.
<house>/sheets takes what the page does to the sheets themselves, which are
changes to the house file and go the way every change to it goes (edit.py).
"""
import hashlib
import http.server
import json
import os
import re
import threading
import urllib.request
from . import edit
from .solve import solve
from . import marks as ink
from .workspace import Workspace


FIRST = 8765                    # the port a workspace is first offered


class Handler(http.server.SimpleHTTPRequestHandler):
    WHO = '/_flawlessplan'          # which workspace this is: for a second process to find the first
    MARK = re.compile(r'^/([\w-]+)/marks\.json$')
    STAMP = re.compile(r'^/([\w-]+)/stamp$')
    SHEETS = re.compile(r'^/([\w-]+)/sheets$')
    FILES = threading.Lock()    # one change to a house file at a time
    LIMIT = 4 << 20
    LOCK = ink.LOCK             # one writer: requests are threaded, and saves come in bursts
    ws = None                   # the workspace served; set by start()

    def marks_file(self):
        m = self.MARK.match(self.path.split('?')[0])
        return m and self.ws.marks(m.group(1))

    def stamp(self):
        """A few characters that stand for a house's page as it is in
        build/ now, or None where this is not a request for them."""
        m = self.STAMP.match(self.path.split('?')[0])
        if not m:
            return None
        try:
            with open(os.path.join(self.ws.build, m.group(1), 'index.html'), 'rb') as fh:
                page = hashlib.sha256(fh.read()).hexdigest()[:10]
        except OSError:
            return b'null'
        try:                    # and after a dot, for which of its marks are resolved: the page reads those again
            done = ink.state(ink.load(self.ws.marks(m.group(1))))
        except ValueError:
            done = ''
        return json.dumps(page + '.' + done).encode()

    def reply(self, code, body=b''):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        if not self.marks_file() and not self.STAMP.match(self.path.split('?')[0]):   # a rebuilt sheet must not come back from the browser's cache
            self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def ours(self):
        """Whether a request was meant for this server. A page on another
        site can make the browser send one here; it cannot make it name us
        as the host, or say it came from us."""
        port = self.server.server_address[1]
        here = ('localhost:%d' % port, '127.0.0.1:%d' % port)
        origin = self.headers.get('Origin')
        return self.headers.get('Host') in here and (origin is None or origin in ['http://' + h for h in here])

    def do_GET(self):
        if not self.ours():
            return self.reply(403)
        dest, stamp = self.marks_file(), self.stamp()
        if stamp:
            return self.reply(200, stamp)
        if self.path.split('?')[0] == self.WHO:
            return self.reply(200, json.dumps({'workspace': self.ws.root}).encode('utf-8'))
        if not dest:
            return super().do_GET()
        self.reply(200, open(dest, 'rb').read() if os.path.exists(dest) else b'[]')

    def do_HEAD(self):
        return super().do_HEAD() if self.ours() else self.reply(403)

    def do_PUT(self):
        dest = self.marks_file()
        try:
            size = int(self.headers.get('Content-Length') or 0)
        except ValueError:
            size = 0
        if not self.ours() or self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
            return self.reply(403)                  # what is saved here is later read as the owner's own marks
        if not dest or not 0 < size <= self.LIMIT or not os.path.isdir(os.path.dirname(dest)):
            return self.reply(400)
        try:
            marks = json.loads(self.rfile.read(size).decode('utf-8'))
        except (ValueError, RecursionError):
            return self.reply(400)
        if not isinstance(marks, list):
            return self.reply(400)
        with self.LOCK:
            try:                # a mark resolved since the page read them stays resolved
                stored = ink.load(dest)
                marks = ink.keep(stored, marks)
            except ValueError:
                stored = []
            self.place(os.path.dirname(dest), stored, marks)
            ink.save(dest, marks)
        self.reply(204)

    def place(self, folder, stored, marks):
        """A comment new to the store is given the house version it was
        made on and what it is on, and that version of the house file is
        kept, so the drawing it was made on can be set beside the drawing
        as it is now. A house that does not solve gives none of it."""
        if not any(isinstance(m, dict) and m.get('type') in ('note', 'box') and 'context' not in m for m in marks):
            return
        try:
            path = os.path.join(folder, 'house.yaml')
            with open(path) as fh:
                text = fh.read()
            version = edit.version(text)
            solved = solve(path)
        except (OSError, ValueError):
            return
        ink.attach(marks, stored, dict((p.id, p) for p in solved.plans()), version)
        if any(isinstance(m, dict) and m.get('version') == version and m.get('type') in ('note', 'box') for m in marks):
            ink.remember(folder, version, text)

    def do_POST(self):
        """What the page does to a house's sheets — their order, one
        hidden or shown again, one binned — made in the house file the way
        an agent's tools change it: refused if the file is not the one the
        page was drawn from, kept only if the house still solves, and the
        pages drawn again. Answers with the file's new version, or 409 and
        why not."""
        m = self.SHEETS.match(self.path.split('?')[0])
        try:
            size = int(self.headers.get('Content-Length') or 0)
        except ValueError:
            size = 0
        if not self.ours() or self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
            return self.reply(403)
        if not m:
            return self.reply(405)
        if not 0 < size <= 65536:
            return self.reply(400)
        try:
            ask = json.loads(self.rfile.read(size).decode('utf-8'))
            house = self.ws.house(m.group(1))
        except (ValueError, RecursionError):
            return self.reply(400)
        said = ask.get('version') if isinstance(ask, dict) else None
        does = [k for k in ('order', 'hide', 'show', 'bin') if isinstance(ask, dict) and k in ask]
        if len(does) != 1 or not isinstance(said, str) or not said:
            return self.reply(400)                  # the page says which file it means: there is no writing blind from here
        what = ask[does[0]]
        if not (isinstance(what, list) and all(isinstance(i, str) for i in what) if does[0] == 'order' else isinstance(what, str)):
            return self.reply(400)
        with self.FILES:
            try:
                if does[0] == 'order':
                    out = edit.order_sheets(house, what, said, self.ws)
                elif does[0] == 'bin':
                    out = edit.bin_sheet(house, what, said, self.ws)
                else:
                    out = edit.hide_sheet(house, what, does[0] == 'hide', said, self.ws)
            except ValueError as e:                 # edit.Refused, and whatever a house file gets wrong
                if 'is not as it was at version' in str(e):
                    try:                            # the page is behind the file: draw it again, and it will follow
                        edit.redraw(house, self.ws)
                    except ValueError:
                        pass
                return self.reply(409, json.dumps({'error': str(e)}).encode('utf-8'))
        self.reply(200, json.dumps(out, ensure_ascii=False).encode('utf-8'))

    def log_message(self, fmt, *args):
        if self.command in ('PUT', 'POST'):
            super().log_message(fmt, *args)


def start(ws=None, port=None):
    """A server for a workspace, not yet running. Port 0 takes any free
    one; None, the workspace's own: chosen once and kept in its settings,
    so a page left open finds its server again after a restart. Only if
    that one is taken is another used, for this time."""
    ws = ws or Workspace()
    os.makedirs(ws.build, exist_ok=True)
    kind = type('Handler', (Handler,), {'ws': ws})
    make = lambda p: http.server.ThreadingHTTPServer(('127.0.0.1', p), lambda *a, **k: kind(*a, directory=ws.build, **k))
    if port is not None:
        return make(port)
    kept = ws.settings().get('port')
    chosen = isinstance(kept, int) and not isinstance(kept, bool) and 0 < kept < 65536
    try:
        srv = make(kept if chosen else FIRST)
    except OSError:                         # taken, by something else: another port for this time
        srv = make(0)
    if not chosen:                          # the first time: whichever it got is the workspace's from now on
        ws.remember(port=srv.server_address[1])
    return srv


def serving(ws, port):
    """Whether this workspace is already served on a port, by another process."""
    try:
        with urllib.request.urlopen('http://localhost:%d%s' % (port, Handler.WHO), timeout=1) as r:
            return json.loads(r.read().decode('utf-8')).get('workspace') == ws.root
    except (OSError, ValueError, AttributeError):
        return False


def background(ws=None):
    """Serve a workspace from a thread on its own port; returns its URL.
    For a process that has other work to do, such as the agent tools. Where
    another process serves this workspace on its port already, that one is
    the address, and nothing more is started."""
    ws = ws or Workspace()
    kept = ws.settings().get('port')
    if isinstance(kept, int) and serving(ws, kept):
        return 'http://localhost:%d/' % kept
    srv = start(ws)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return 'http://localhost:%d/' % srv.server_address[1]


def serve(ws=None, port=None):
    """Serve a workspace's build/ on localhost until interrupted: on its
    own port, unless another is given."""
    ws = ws or Workspace()
    with start(ws, port) as srv:
        print('http://localhost:%d/  —  marks are saved in %s/<house>/marks.json' % (srv.server_address[1], ws.houses))
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
