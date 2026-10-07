# -*- coding: utf-8 -*-
"""The version is written in pyproject.toml and repeated in a few places a
build cannot fill in. They must agree, and installs must fetch that tag."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'packaging'))
import release


def test_every_place_carries_the_same_version():
    v = release.current()
    want = {'plugin.json version': v, 'plugin.json fetches': release.pin(v),
            'mcpb manifest version': v, 'README install line': release.pin(v)}
    assert dict(release.places()) == want, 'run: python3 packaging/release.py %s' % v
