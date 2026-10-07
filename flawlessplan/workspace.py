# -*- coding: utf-8 -*-
"""A workspace: where one person's houses are kept, and where what is drawn
from them goes.

    <workspace>/houses/<name>/house.yaml    the houses, a folder each
    <workspace>/build/                      everything drawn; for this machine
    <workspace>/public/                     `build --public`: only this is ever hosted

Every command and every tool works in one. Which one is `--workspace`, else
$FLAWLESSPLAN_WORKSPACE, else the folder the command is run in. Nothing else
in the engine knows where houses live, so a workspace that is not a folder
on this machine — a signed-in user's storage, say — is a change here only.
"""
import os
import re
import shutil

ENV = 'FLAWLESSPLAN_WORKSPACE'
EXAMPLES = os.path.join(os.path.dirname(__file__), 'examples')
NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]*\Z')     # \Z: `$` would let a name end in a newline

GITIGNORE = 'build/\npublic/\n.vercel/\nhouses/*/marks.json\n.DS_Store\n'
MCP = '{\n  "mcpServers": {\n    "flawlessplan": {"command": "flawlessplan", "args": ["mcp"]}\n  }\n}\n'
GUIDE = """# Houses drawn with flawlessplan

Each house is `houses/<name>/house.yaml`: named measurements, walls,
openings and rooms. Every room size is measured from the geometry.

- **A dimension is written down once.** `survey` is what was measured and
  `lines` is every wall line stepped off it; everything else uses those
  names. Never write a number that can be derived.
- After any change run `flawlessplan check <name>` and read what it says;
  `flawlessplan build` draws every house into `build/`.
- `flawlessplan build --serve` opens the pages, where plans can be drawn
  on; `flawlessplan marks <name>` lays out what was drawn.
- Only `public/` (from `flawlessplan build --public`) is for hosting. A
  house marked `private: true` is left out of it.

The schema is in the flawlessplan README. The same things are tools for an
agent through `flawlessplan mcp`, which `.mcp.json` here registers.
"""


class Workspace(object):
    def __init__(self, root=None, houses=None):
        self.root = os.path.abspath(root or os.environ.get(ENV) or '.')
        self.houses = os.path.abspath(houses) if houses else os.path.join(self.root, 'houses')
        self.build = os.path.join(self.root, 'build')
        self.public = os.path.join(self.root, 'public')

    def names(self):
        """The houses here, by folder name."""
        if not os.path.isdir(self.houses):
            return []
        return sorted(n for n in os.listdir(self.houses)           # a folder whose name will not do is not a house here
                      if NAME.match(n) and os.path.exists(os.path.join(self.houses, n, 'house.yaml')))

    def every(self):
        return [self.house(n) for n in self.names()]

    def house(self, name):
        """The folder of a house named as list_houses or the index gives it."""
        if not NAME.match(str(name)) or name not in self.names():
            raise ValueError('no house called %r in %s (have %s)'
                             % (name, self.root, ', '.join(self.names()) or 'none — try `flawlessplan init`'))
        return os.path.join(self.houses, name)

    def place(self, name):
        """The folder a house of that name is kept in, there yet or not."""
        if not NAME.match(str(name)):
            raise ValueError('%r will not do as a house name: letters, digits, - and _ only' % (name,))
        return os.path.join(self.houses, name)

    def find(self, arg):
        """A house given on the command line: a path, or a name in here."""
        return arg if os.path.exists(arg) else self.house(arg)

    def marks(self, name):
        return os.path.join(self.houses, name, 'marks.json')

    def init(self, examples=True):
        """Make this folder a workspace, with the example houses to start
        from. Nothing already there is touched. Returns what was made."""
        made = []
        os.makedirs(self.houses, exist_ok=True)
        for name, text in (('.gitignore', GITIGNORE), ('.mcp.json', MCP), ('CLAUDE.md', GUIDE)):
            dest = os.path.join(self.root, name)
            if not os.path.exists(dest):
                with open(dest, 'w') as fh:
                    fh.write(text)
                made.append(dest)
        for name in sorted(os.listdir(EXAMPLES)) if examples else []:
            dest = os.path.join(self.houses, name)
            if os.path.isdir(os.path.join(EXAMPLES, name)) and not os.path.exists(dest):
                # what was drawn on an example where it lies is not part of the example
                shutil.copytree(os.path.join(EXAMPLES, name), dest, ignore=shutil.ignore_patterns('marks.json', '.*'))
                made.append(dest)
        return made
