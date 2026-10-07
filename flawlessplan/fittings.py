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
         'boiler': (0.45, 0.35), 'cylinder': (0.50, 0.50), 'wardrobe': (1.2, 0.60), 'unit': (0.60, 0.60)}
LETTER = {'boiler': 'B'}
ORDER = ('worktop', 'oven')     # drawn first, in this order: a sink sits in a worktop, a hob over an oven


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


def symbol(kind, w, d, label=None):
    """A fitting's drawing: ('fill', points) for its body, ('line', points,
    closed) for what is drawn on it, ('text', (a, b), words)."""
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
        out += [('line', _soft(-h+0.05, 0.06, -0.02, d-0.06, 0.06), True)]
        out += [('line', [(h*k, 0.08), (h*k, d-0.08)], False) for k in (0.25, 0.5, 0.75)]
    elif kind == 'hob':
        r = min(w, d)*0.15
        out += [('line', _oval(a, b, r, r, 16), True) for a in (-w/4.0, w/4.0) for b in (d*0.27, d*0.73)]
    elif kind == 'oven':
        out += [('line', _rect(-h+0.08, 0.08, h-0.08, d-0.08), True)]
    elif kind == 'cylinder':
        out = [('fill', _oval(0, d/2.0, h, d/2.0))]
    elif kind == 'wardrobe':
        out += [('line', [(-h, 0), (h, d)], False)]
    words = label if label is not None else LETTER.get(kind)
    if words:
        out.append(('text', (0, d/2.0), str(words)))
    return out
