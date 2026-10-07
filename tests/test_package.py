# -*- coding: utf-8 -*-
"""What is installed is the `flawlessplan` folder and nothing beside it:
every file the code opens must be in there, and in git, or an install
from a tag draws nothing."""
import json
import os
import re
import subprocess
import pytest

from conftest import ROOT
from flawlessplan import icons, mcp_server as mcp, page
from flawlessplan.workspace import EXAMPLES, Workspace

PACKAGE = os.path.join(ROOT, 'flawlessplan')


def tracked():
    try:
        out = subprocess.run(['git', 'ls-files', 'flawlessplan'], cwd=ROOT, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        pytest.skip('no git here')
    if out.returncode or not out.stdout.strip():
        pytest.skip('not a git checkout')
    return set(out.stdout.split('\n'))


def opened_by_the_code():
    """Every asset a module names: asset('page.css'), the shared files, the guide's two."""
    names = set(page.SHARED) - {'fonts'}
    for mod in ('page.py', 'cli.py', 'mcp_server.py'):
        src = open(os.path.join(PACKAGE, mod)).read()
        names |= set(re.findall(r"asset\('([^']+)'\)", src)) | set(re.findall(r"ASSETS, '([^']+)'", src))
        names |= set(re.findall(r"'([\w-]+\.md)'", src)) if mod == 'mcp_server.py' else set()
    names |= {'fonts/%s.woff2' % n for n in ('archivo', 'plex-mono-400', 'plex-mono-500')}
    return names - {'fonts'}


def test_every_file_the_code_opens_is_in_the_package_and_in_git():
    names = opened_by_the_code()
    assert {'page.html', 'page.css', 'page.js', 'view.js', 'share.html', 'share.css', 'share.js', 'index.html', 'index.css',
            'icon.svg', 'vercel.json', 'new-house.md', 'house-file.md', 'manifest.webmanifest'} <= names
    for name in names:
        assert os.path.isfile(os.path.join(page.ASSETS, name)), name
    files = tracked()
    for name in names:
        assert 'flawlessplan/assets/' + name in files, '%s is not in git: an install from a tag would not have it' % name


def test_nothing_in_assets_is_left_unused():
    used = opened_by_the_code() | {'fonts/README.txt'}
    there = {os.path.relpath(os.path.join(d, f), page.ASSETS) for d, _, fs in os.walk(page.ASSETS) for f in fs if not f.startswith('.')}
    assert there == used, 'unused: %s; missing: %s' % (sorted(there - used), sorted(used - there))


def test_the_examples_ship_whole_and_with_nothing_drawn_on_them():
    files = tracked()
    assert sorted(os.listdir(EXAMPLES)) == ['bungalow', 'cottage'] and os.path.commonpath([EXAMPLES, PACKAGE]) == PACKAGE
    for name in os.listdir(EXAMPLES):
        mine = sorted(f for f in files if f.startswith('flawlessplan/examples/%s/' % name))
        assert mine == ['flawlessplan/examples/%s/%s' % (name, f) for f in ('expected.json', 'house.yaml')]
        # serving this repo draws on the examples where they lie: what is drawn must never be committed with them
        ignored = subprocess.run(['git', 'check-ignore', '-q', 'flawlessplan/examples/%s/marks.json' % name], cwd=ROOT)
        assert ignored.returncode == 0, 'flawlessplan/examples/*/marks.json is not in .gitignore'
        text = open(os.path.join(EXAMPLES, name, 'house.yaml')).read()
        assert 'private: true' not in text                  # they are on the website; a real home would not be


def test_the_package_is_the_one_folder_the_wheel_packs():
    project = open(os.path.join(ROOT, 'pyproject.toml')).read()
    assert 'packages = ["flawlessplan"]' in project and 'flawlessplan = "flawlessplan.cli:main"' in project
    for need in ('PyYAML', 'shapely', 'resvg', 'mcp'):
        assert need.lower() in project.lower(), need
    assert re.search(r'requires-python = ">=3\.10"', project)
    for mod in os.listdir(PACKAGE):
        if mod.endswith('.py'):
            src = open(os.path.join(PACKAGE, mod)).read()
            assert not re.search(r"os\.pardir|dirname\(os\.path\.dirname\(__file__|join\([^)\n]*'\.\.'", src), '%s reaches outside the package' % mod


def test_nothing_in_the_engine_knows_where_houses_live():
    """Anything that needs to know asks workspace.Workspace."""
    for mod in os.listdir(PACKAGE):
        if mod.endswith('.py') and mod not in ('workspace.py',):
            src = open(os.path.join(PACKAGE, mod)).read()
            assert not re.search(r"""join\([^)\n]*['"](houses|build|public)['"]""", src), mod
    assert Workspace('/x').houses == '/x/houses' and Workspace('/x').build == '/x/build' and Workspace('/x').public == '/x/public'


def test_the_icons_are_the_ones_the_drawing_makes(tmp_path, monkeypatch, capsys):
    before = dict((name, open(os.path.join(icons.ASSETS, name), 'rb').read()) for name, _, _ in icons.SIZES)
    monkeypatch.setattr(icons, 'ASSETS', str(tmp_path))
    with open(str(tmp_path / 'icon.svg'), 'w') as fh:
        fh.write(page.asset('icon.svg'))
    icons.make()
    for name, size, _ in icons.SIZES:
        made = open(str(tmp_path / name), 'rb').read()
        assert made[:8] == b'\x89PNG\r\n\x1a\n' and int.from_bytes(made[16:20], 'big') == int.from_bytes(made[20:24], 'big') == size
        kept = before[name]                                 # the bytes differ from one resvg to the next: the size must not
        assert kept[:8] == made[:8] and kept[16:24] == made[16:24], '%s is not %d square: run python3 -m flawlessplan.icons' % (name, size)
    assert capsys.readouterr().out.count('.png') == 4
    assert 'scale(0.8)' in icons.maskable(page.asset('icon.svg')) and icons.maskable(page.asset('icon.svg')).endswith('</g></svg>')


def test_the_manifest_names_icons_that_are_installed(tmp_path):
    page.install(str(tmp_path))
    manifest = json.load(open(str(tmp_path / 'manifest.webmanifest')))
    for icon in manifest['icons']:
        assert os.path.isfile(str(tmp_path / icon['src'])), icon
    assert sorted(os.listdir(str(tmp_path / 'fonts'))) == ['archivo.woff2', 'plex-mono-400.woff2', 'plex-mono-500.woff2']
    page.install(str(tmp_path))                             # and again, over what is there


def test_the_guide_carries_the_procedure_the_keys_and_both_examples():
    said = mcp.guide()
    for part in (page.asset('new-house.md'), page.asset('house-file.md'), open(os.path.join(EXAMPLES, 'cottage', 'house.yaml')).read()):
        assert part in said
    assert said.count('## Example: ') == 2 and len(said) < 60000


def test_the_skills_point_at_things_that_are_there():
    for skill in ('new-house', 'read-marks'):
        text = open(os.path.join(ROOT, 'plugin', 'skills', skill, 'SKILL.md')).read()
        assert text.startswith('---\nname: %s\n' % skill) and 'description:' in text.split('---')[1]
    market = json.load(open(os.path.join(ROOT, '.claude-plugin', 'marketplace.json')))
    for plugin in market['plugins']:
        assert os.path.isdir(os.path.join(ROOT, plugin['source'])) if isinstance(plugin.get('source'), str) else True
    bundle = json.load(open(os.path.join(ROOT, 'packaging', 'mcpb', 'manifest.json')))
    entry = bundle['server']['entry_point']
    assert os.path.isfile(os.path.join(ROOT, 'packaging', 'mcpb', entry)) and entry in bundle['server']['mcp_config']['args']
    assert bundle['server']['mcp_config']['env'] == {'FLAWLESSPLAN_WORKSPACE': '${user_config.workspace}'}
    assert 'mcp_server' in open(os.path.join(ROOT, 'packaging', 'mcpb', entry)).read()


def test_the_tools_and_the_command_line_are_the_ones_the_docs_name():
    claude = open(os.path.join(ROOT, 'CLAUDE.md')).read()
    for _, name, about in mcp.TOOLS:
        assert '`%s`' % name in claude or name in ('list_houses', 'init_workspace', 'show'), name
        assert len(about) > 60 and about[0].isupper()
    for mod in sorted(os.listdir(PACKAGE)):
        if mod.endswith('.py') and not mod.startswith('__'):
            assert 'flawlessplan/%s' % mod in claude, '%s is not in the list of files in CLAUDE.md' % mod


def test_the_page_hides_what_is_resolved_and_asks_before_it_deletes():
    """What the page does with a mark's life, held where it is written:
    the page itself is tried in a browser."""
    from flawlessplan import page
    js, css = page.asset('page.js'), page.asset('page.css')
    for must in ('m.status==="resolved"', 'Show resolved (', 'Delete for good?', 'm.id="m"+m.ts.toString(36)',
                 'applied to ', 'clear(openMarks(),"every sheet")', 'now.split(".")[0]===drawn.split(".")[0]'):
        assert must in js, must
    assert '.draw .done .mk-pen' in css and '.marklist' in css
