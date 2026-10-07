#!/usr/bin/env python3
"""Make dist/flawlessplan.mcpb, the one-file installer for Claude Desktop.

    python3 packaging/mcpb/build.py        # needs npx (Node), for the packer

The bundle carries the package's source, its licence and a pyproject listing what it
depends on; Claude Desktop runs it with uv, which fetches those for the
user's own machine. Nothing is compiled or signed here.
"""
import json
import os
import re
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
STAGE = os.path.join(ROOT, 'dist', 'mcpb')
OUT = os.path.join(ROOT, 'dist', 'flawlessplan.mcpb')

project = open(os.path.join(ROOT, 'pyproject.toml')).read()
version = re.search(r'^version = "([^"]+)"', project, re.M).group(1)
deps = re.search(r'^dependencies = (\[.*?\])', project, re.M).group(1)

shutil.rmtree(STAGE, ignore_errors=True)
os.makedirs(STAGE)
shutil.copytree(os.path.join(ROOT, 'flawlessplan'), os.path.join(STAGE, 'flawlessplan'),
                ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'marks.json'))
shutil.copyfile(os.path.join(HERE, 'server.py'), os.path.join(STAGE, 'server.py'))
shutil.copyfile(os.path.join(ROOT, 'LICENSE'), os.path.join(STAGE, 'LICENSE'))    # its terms go with every copy
shutil.copyfile(os.path.join(ROOT, 'flawlessplan', 'assets', 'icon-512.png'), os.path.join(STAGE, 'icon.png'))
manifest = json.load(open(os.path.join(HERE, 'manifest.json')))
manifest['version'] = version                       # one place says what version this is
with open(os.path.join(STAGE, 'manifest.json'), 'w') as fh:
    json.dump(manifest, fh, indent=2)
with open(os.path.join(STAGE, 'pyproject.toml'), 'w') as fh:
    fh.write('[project]\nname = "flawlessplan-extension"\nversion = "%s"\nrequires-python = ">=3.10"\n'
             'dependencies = %s\n' % (version, deps))
subprocess.run(['npx', '--yes', '@anthropic-ai/mcpb', 'pack', STAGE, OUT], check=True)
print(OUT)
