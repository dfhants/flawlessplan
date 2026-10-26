# -*- coding: utf-8 -*-
"""What is built into a house and shown on a sales plan: the bath, the
WC, the hob, the worktop. Not furniture: nothing here can be carried out.

A fitting is a rectangle with a back, which stands against a wall or
faces a compass point. Its symbol is written once, here, in the
fitting's own terms — `a` along the back from its middle, `b` out from it
— and render sets it down wherever geom has stood the fitting.
"""
import math

# kind: (width along its back, depth out from it) where the house file gives none, in metres
KINDS = {'worktop': (1.0, 0.60), 'sink': (1.0, 0.50), 'hob': (0.60, 0.52), 'oven': (0.60, 0.60),
         'bath': (1.70, 0.70), 'shower': (0.90, 0.90), 'wc': (0.38, 0.70), 'basin': (0.50, 0.40),
         'boiler': (0.45, 0.35), 'cylinder': (0.50, 0.50), 'wardrobe': (1.2, 0.60), 'unit': (0.60, 0.60),
         'fireplace': (1.2, 0.35)}
HEARTH = 0.45                   # how far a hearth stands out in front of its breast, where none is given
OPENING = (0.55, 0.25)          # a fireplace's opening, wide and deep, where none is given
LETTER = {'boiler': 'B'}
ROUND = ('cylinder',)           # given one size, it is the diameter
ORDER = ('worktop', 'oven')     # drawn first, in this order: a sink sits in a worktop, a hob over an oven
BOWLS = (1, 1.5, 2)
DRAINERS = ('none', 'left', 'right', 'both')
RIM, GAP = 0.05, 0.04           # a sink's edge round its bowls, and between a bowl and what is next to it
BOWL = 1.1                      # a full bowl's width for its depth; a half bowl is HALF of it
HALF = 0.45
DRAIN = 0.30                    # the narrowest drainer worth drawing


def _rect(a0, b0, a1, b1):
    return [(a0, b0), (a1, b0), (a1, b1), (a0, b1)]


def _oval(a, b, ra, rb, n=28):
    return [(a + ra*math.cos(2*math.pi*i/n), b + rb*math.sin(2*math.pi*i/n)) for i in range(n)]


def _soft(a0, b0, a1, b1, r, n=5):
    """A rectangle with its corners rounded."""
    r = min(r, (a1-a0)/2.0, (b1-b0)/2.0)
    out = []
    for (ca, cb), start in (((a1-r, b1-r), 0), ((a0+r, b1-r), 90), ((a0+r, b0+r), 180), ((a1-r, b0+r), 270)):
        out += [(ca + r*math.cos(math.radians(start + 90.0*i/n)), cb + r*math.sin(math.radians(start + 90.0*i/n)))
                for i in range(n+1)]
    return out


def _sink(w, d, bowls, drain):
    """A sink's bowls and drainers, inside its top. Its bowls keep their
    shape: a drainer with no room is left off, and only then do the
    bowls get smaller. `drain` is the sides, -1 and 1 along `a`."""
    h = w/2.0
    bd = d - 2*0.06
    bw = bd*BOWL
    sizes = {1: [bw], 1.5: [bw, bw*HALF], 2: [bw, bw]}[bowls]
    drain = list(drain)
    while drain and 2*RIM + sum(sizes) + GAP*(len(sizes) - 1) + len(drain)*(GAP + DRAIN) > w + 1e-9:
        drain.pop(0)                        # of two, the one written first goes
    need = 2*RIM + sum(sizes) + GAP*(len(sizes) - 1)
    k = min(1.0, (w - 2*RIM)/(need - 2*RIM)) if need > w else 1.0
    sizes, bd = [x*k for x in sizes], bd*k
    run = sum(sizes) + GAP*(len(sizes) - 1)
    if drain == [1]:
        a = -h + RIM
    elif drain == [-1]:
        a = h - RIM - run
        sizes = sizes[::-1]                 # the half bowl is on the drainer's side
    else:
        a = -run/2.0
    b0 = (d - bd)/2.0
    out = []
    for x in sizes:
        out.append(('line', _soft(a, b0, a + x, b0 + bd, 0.06*k), True))
        a += x + GAP
    for side in drain:
        lo, hi = (run/2.0 if len(drain) == 2 else -h + RIM + run) + GAP, h - RIM
        lo, hi = (lo, hi) if side > 0 else (-hi, -lo)
        n = max(2, int((hi - lo)/0.09))
        out += [('line', [(lo + (hi-lo)*i/float(n), 0.08), (lo + (hi-lo)*i/float(n), d-0.08)], False)
                for i in range(1, n)]
    return out


def symbol(kind, w, d, label=None, bowls=1, drain=(1,), hearth=(0, 0), opening=None):
    """A fitting's drawing: ('fill', points) for its body, ('line', points,
    closed) for what is drawn on it, ('text', (a, b), words). A sink's
    `bowls` and the sides its drainers are on (`drain`) are its own."""
    h = w/2.0
    out = [('fill', _rect(-h, 0, h, d))]
    if kind == 'bath':
        out = [('fill', _rect(-h, 0, h, d)), ('line', _soft(-h+0.07, 0.07, h-0.07, d-0.07, 0.14), True),
               ('line', _oval(-h+0.24, d/2.0, 0.03, 0.03, 10), True)]
    elif kind == 'shower':
        out += [('line', [(-h, 0), (h, d)], False), ('line', [(-h, d), (h, 0)], False),
                ('line', _oval(0, d/2.0, 0.05, 0.05, 12), True)]
    elif kind == 'wc':
        tank = min(0.18, d/3.0)
        out = [('fill', _rect(-h, 0, h, tank)), ('fill', _oval(0, tank + (d-tank)/2.0, h*0.88, (d-tank)/2.0))]
    elif kind == 'basin':
        out = [('fill', _soft(-h, 0, h, d, 0.08)), ('line', _oval(0, d*0.55, h*0.68, d*0.30), True)]
    elif kind == 'sink':
        out += _sink(w, d, bowls, drain)
    elif kind == 'hob':
        r = min(w, d)*0.15
        out += [('line', _oval(a, b, r, r, 16), True) for a in (-w/4.0, w/4.0) for b in (d*0.27, d*0.73)]
    elif kind == 'oven':
        out += [('line', _rect(-h+0.08, 0.08, h-0.08, d-0.08), True)]
    elif kind == 'fireplace':
        # the breast is masonry and is drawn with the walls; here is the
        # hearth in front of it and the line of the opening's back
        hw, hd = hearth
        out = [('fill', []), ('line', _rect(-hw/2.0, d, hw/2.0, d + hd), True)]
        if opening:
            ow, od = opening
            out.append(('line', [(-ow/2.0, d - od + 0.04), (ow/2.0, d - od + 0.04)], False))
    elif kind == 'cylinder':
        out = [('fill', _oval(0, d/2.0, h, d/2.0))]
    elif kind == 'wardrobe':
        # a hanging rail down its middle with hangers on it; a box with a diagonal is a duct
        n = max(2, int((w - 0.2)/0.15))
        out += [('line', [(-h+0.06, d/2.0), (h-0.06, d/2.0)], False)]
        out += [('line', [(-h + 0.1 + (w-0.2)*i/float(n) - 0.03, d*0.25), (-h + 0.1 + (w-0.2)*i/float(n) + 0.03, d*0.75)], False)
                for i in range(n+1)]
    words = label if label is not None else LETTER.get(kind)
    if words:
        out.append(('text', (0, d/2.0), str(words)))
    return out
