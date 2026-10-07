"""Entry point of the Claude Desktop extension: the flawlessplan tools, in
the folder the user chose when installing it."""
import os

from flawlessplan.mcp_server import serve
from flawlessplan.workspace import ENV, Workspace

# The folder comes from the extension's settings. If the app passes none, or
# passes the setting through unfilled, fall back to the default it offers.
chosen = os.environ.get(ENV, '')
if not chosen or chosen.startswith('${'):
    chosen = os.path.join(os.path.expanduser('~'), 'Documents', 'Flawlessplan')
ws = Workspace(chosen)
if not ws.names():                      # a folder just chosen: give it the examples to start from
    ws.init()
serve(ws)
