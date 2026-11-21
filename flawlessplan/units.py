# -*- coding: utf-8 -*-
"""How a size is written. Everything is worked in metres; a house that
says `units: both` has each area given in square feet beside it, and each
room's size in feet and inches, the way a sales particular does."""

FT = 0.3048                     # metres to the foot, exactly
UNITS = ('metric', 'both')


def sqft(a):
    return a / (FT * FT)


def feet(x):
    """A length in feet and inches, to the nearest inch: 11'2"."""
    inches = int(round(x / FT * 12))
    return "%d'%d\"" % divmod(inches, 12)


def area(a, units='metric', fmt='%.1f'):
    """An area: `12.3 m²`, and `(132 sq ft)` after it when both are wanted."""
    out = (fmt + ' m²') % a
    return out + (' (%.0f sq ft)' % sqft(a) if units == 'both' else '')


def size(w, h, units='metric'):
    """A clear size: `3.40 × 2.80 m`, and the same in feet when both are wanted."""
    out = '%.2f × %.2f m' % (w, h)
    return out + (' (%s × %s)' % (feet(w), feet(h)) if units == 'both' else '')
