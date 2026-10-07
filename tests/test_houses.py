# -*- coding: utf-8 -*-
"""Every house in houses/ against the expected.json kept beside it.

The snapshot is the geometry — areas, each room as measured, where every
opening is and how wide — and anything the checks found wrong. When a
house is changed on purpose, `flawlessplan snapshot <path>`
rewrites it; read the diff before committing it.
"""
import glob
import json
import os
import sys
import pytest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, '..'))
from flawlessplan import report
from flawlessplan.solve import solve

HOUSES = sorted(glob.glob(os.path.join(HERE, '..', 'flawlessplan', 'examples', '*', 'house.yaml')))


def test_there_are_houses():
    assert HOUSES


@pytest.mark.parametrize('path', HOUSES, ids=[os.path.basename(os.path.dirname(p)) for p in HOUSES])
def test_house_matches_its_snapshot(path):
    want = os.path.join(os.path.dirname(path), 'expected.json')
    assert os.path.exists(want), 'no expected.json: run `python -m flawlessplan snapshot %s`' % os.path.dirname(path)
    got = report.snapshot(solve(path))
    diffs = report.differences(json.load(open(want)), json.loads(json.dumps(got)))
    assert not diffs, '\n'.join(diffs)


@pytest.mark.parametrize('path', HOUSES, ids=[os.path.basename(os.path.dirname(p)) for p in HOUSES])
def test_house_has_no_errors(path):
    assert not [(k, m) for k, lv, m in solve(path).issues() if lv == 'error']
