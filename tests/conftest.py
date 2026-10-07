# -*- coding: utf-8 -*-
"""What the tests share: one small made-up plan, a way to solve a plan
from its text, and a workspace of the example houses to write in."""
import os
import pathlib
import sys
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
from flawlessplan import model, geom
from flawlessplan.workspace import Workspace

BOX = """
survey: {W: 8.0, D: 6.0}
lines: {MID: W/2}
sheets:
  - id: ground
    envelope: [[0, 0], [W, 0], [W, D], [0, D]]
    walls:
      - {id: split, from: [MID, 0], to: [MID, D]}
    openings:
      - {door: std, wall: split, at: centre, swing: e}
      - {window: 1.2, at: [2.0, 0]}
    rooms:
      - {name: LEFT, at: [1, 1]}
      - {name: RIGHT, at: [7, 1]}
"""

# one room and nothing else: for a test that adds the one thing it is about
ROOM = """
survey: {W: 8.0, D: 6.0}
sheets:
  - id: ground
    envelope: [{at: [0, 0], id: north}, {at: [W, 0], id: east}, {at: [W, D], id: south}, {at: [0, D], id: west}]
    rooms:
      - {name: ROOM, at: [1, 1]}
"""


def plan(text, floor=0):
    house = model.loads(text)
    return geom.Plan(house['sheets'][floor], house), house


def said(p, level=None):
    """What a plan's checks found, as one string to look in."""
    return ' | '.join(m for lv, m in p.issues if level is None or lv == level)


@pytest.fixture
def ws(tmp_path):
    """A workspace with the two example houses in it."""
    w = Workspace(str(tmp_path))
    w.init()
    return w


@pytest.fixture
def houses(ws, monkeypatch):
    """The same, with the agent's tools pointed at it; its houses folder."""
    from flawlessplan import mcp_server as mcp
    monkeypatch.setattr(mcp, 'WS', ws)
    monkeypatch.setattr(mcp, 'PAGES', {})
    return pathlib.Path(ws.houses)
