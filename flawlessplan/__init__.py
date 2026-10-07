"""Flawlessplan: floor plans for any house, drawn from a YAML description of it."""
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version('flawlessplan')
except PackageNotFoundError:            # run from a checkout that was never installed
    __version__ = '0+unknown'
