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
from . import edit
from . import marks as ink
from .workspace import Workspace


class Handler(http.server.SimpleHTTPRequestHandler):
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
                marks = ink.keep(ink.load(dest), marks)
            except ValueError:
                pass
            ink.save(dest, marks)
        self.reply(204)

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


def start(ws=None, port=8765):
    """A server for a workspace, not yet running. Port 0 takes any free one."""
    ws = ws or Workspace()
    os.makedirs(ws.build, exist_ok=True)
    kind = type('Handler', (Handler,), {'ws': ws})
    return http.server.ThreadingHTTPServer(('127.0.0.1', port), lambda *a, **k: kind(*a, directory=ws.build, **k))


def background(ws=None):
    """Serve a workspace from a thread, on any free port; returns its URL.
    For a process that has other work to do, such as the agent tools."""
    srv = start(ws, 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return 'http://localhost:%d/' % srv.server_address[1]


def serve(ws=None, port=8765):
    """Serve a workspace's build/ on localhost until interrupted."""
    ws = ws or Workspace()
    with start(ws, port) as srv:
        print('http://localhost:%d/  —  marks are saved in %s/<house>/marks.json' % (port, ws.houses))
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
