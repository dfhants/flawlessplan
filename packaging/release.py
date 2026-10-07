#!/usr/bin/env python3
"""Set the version everywhere it is written, ready to tag.

    python3 packaging/release.py 0.2.0

pyproject.toml says what version this is. The plugin, the desktop
installer's manifest and the install line in the README repeat it — and the
plugin and the README pin what they fetch to the tag `v<version>`, so
nobody is ever handed a commit that was not released. This rewrites them
all; tests/test_release.py fails if they ever disagree.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = 'https://github.com/dfhants/flawlessplan'
PLUGIN = os.path.join(ROOT, 'plugin', '.claude-plugin', 'plugin.json')
BUNDLE = os.path.join(ROOT, 'packaging', 'mcpb', 'manifest.json')


def current():
    return re.search(r'^version = "([^"]+)"', open(os.path.join(ROOT, 'pyproject.toml')).read(), re.M).group(1)


def pin(version):
    """Where installs fetch from: this repository at that release's tag."""
    return 'git+%s@v%s' % (REPO, version)


def places():
    """(file, the version or pin it carries) for everything that repeats it."""
    plugin, bundle = json.load(open(PLUGIN)), json.load(open(BUNDLE))
    readme = re.search(r'uv tool install (git\+[^\s`]+)', open(os.path.join(ROOT, 'README.md')).read())
    return [('plugin.json version', plugin['version']),
            ('plugin.json fetches', next(a for a in plugin['mcpServers']['flawlessplan']['args'] if a.startswith('git+'))),
            ('mcpb manifest version', bundle['version']),
            ('README install line', readme.group(1) if readme else None)]


def write(version):
    if not re.match(r'^\d+\.\d+\.\d+$', version):
        sys.exit('give a version like 0.2.0')
    path = os.path.join(ROOT, 'pyproject.toml')
    text = open(path).read()
    open(path, 'w').write(re.sub(r'^version = "[^"]+"', 'version = "%s"' % version, text, count=1, flags=re.M))
    for path in (PLUGIN, BUNDLE):
        data = json.load(open(path))
        data['version'] = version
        if path == PLUGIN:
            args = data['mcpServers']['flawlessplan']['args']
            args[:] = [pin(version) if a.startswith('git+') else a for a in args]
        with open(path, 'w') as fh:
            json.dump(data, fh, indent=2)
            fh.write('\n')
    path = os.path.join(ROOT, 'README.md')
    text = open(path).read()
    open(path, 'w').write(re.sub(r'(uv tool install )git\+[^\s`]+', lambda m: m.group(1) + pin(version), text))


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    write(sys.argv[1])
    v = sys.argv[1]
    print('version %s written. Then:\n'
          '  .venv/bin/python -m pytest -q tests\n'
          '  git commit -am "Release %s" && git tag v%s && git push origin main v%s\n'
          '  python3 packaging/mcpb/build.py\n'
          '  gh release create v%s dist/flawlessplan.mcpb --title v%s --generate-notes\n'
          'The release deploys the website: .github/workflows/site.yml.' % (v, v, v, v, v, v))
