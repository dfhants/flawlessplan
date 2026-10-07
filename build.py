#!/usr/bin/env python3
"""Draw the example houses into build/. Run from the project root:

    python3 build.py            # SVGs, report and markup page per house
    python3 build.py --png      # also rasterise every sheet
    python3 build.py --serve    # then serve build/, saving what is drawn on the pages

The same as `python -m flawlessplan build`, from anywhere and with whichever
python: if a .venv sits beside this file it is used. What the engine needs
is in pyproject.toml.
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
VENV = os.path.join(ROOT, '.venv', 'bin', 'python')
if os.path.exists(VENV) and os.path.realpath(sys.prefix) != os.path.realpath(os.path.join(ROOT, '.venv')):
    os.execv(VENV, [VENV] + sys.argv)

os.chdir(ROOT)
sys.path.insert(0, ROOT)
try:
    from flawlessplan import cli
except ImportError as e:
    sys.exit('%s\nSet up once with:\n  python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"' % e)

sys.exit(cli.main(['--workspace', ROOT, '--houses', os.path.join(ROOT, 'flawlessplan', 'examples'), 'build']
                  + sys.argv[1:]))
