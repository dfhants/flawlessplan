# -*- coding: utf-8 -*-
"""Arithmetic over named measurements.

Every number in a house file may be written as an expression over the
names in its `survey` and `lines` tables — `YB - living_e_d - IW/2` — so a
dimension is written down once and everything else follows from it. This
is a small walker over Python's own syntax tree: arithmetic, names and a
fixed set of functions. Nothing else evaluates.
"""
import ast
import math
import operator
import re


class ExprError(ValueError):
    pass


def _pow(a, b):
    if abs(b) > 16 or abs(a) > 1e6:                # a house file is arithmetic on metres, not a way to hang a build
        raise ExprError('power out of range: %r ** %r' % (a, b))
    return operator.pow(a, b)


_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Pow: _pow, ast.Mod: operator.mod,
        ast.FloorDiv: operator.floordiv}
_UNARY = {ast.USub: operator.neg, ast.UAdd: operator.pos}
_CMP = {ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt,
        ast.GtE: operator.ge, ast.Eq: operator.eq, ast.NotEq: operator.ne}


_IMPERIAL = re.compile(r"""^(?:(\d+)')?\s*(?:(\d+(?:\.\d+)?)")?$""")       # 14'4", 8', 6"


def imperial(x):
    """Metres for a length written in feet and inches — 14'4", 8', 6" — or
    None if it is not one. A figure off an agent's plan is written as it
    was given, and the file keeps it."""
    m = _IMPERIAL.match(x.strip())
    if not m or not (m.group(1) or m.group(2)):
        return None
    return (int(m.group(1) or 0)*12 + float(m.group(2) or 0)) * 0.0254


def centred(a, b, w):
    """Start of a w-wide opening centred on the run from a to b."""
    return (a + b)/2.0 - w/2.0


FUNCS = {'min': min, 'max': max, 'abs': abs, 'round': round, 'int': int,
         'sqrt': math.sqrt, 'sin': math.sin, 'cos': math.cos, 'tan': math.tan,
         'radians': math.radians, 'hypot': math.hypot,
         'ceil': math.ceil, 'floor': math.floor, 'centred': centred}

_FIELD = re.compile(r'\{([^{}]+?)(?::([^{}:]+))?\}')
_SPEC = re.compile(r'^[+ ]?\d{0,2}(\.\d)?[dfg%]?$')         # a few digits and a type: no padding to a million columns


def _short(x):
    """An expression as it is quoted in an error: not a page of it."""
    x = str(x)
    return x if len(x) <= 80 else x[:60] + ' … ' + x[-12:]


class Scope(object):
    def __init__(self, names=None, funcs=None):
        self.names = dict(names or {})
        self.funcs = dict(FUNCS)
        self.funcs.update(funcs or {})

    def child(self, **extra):
        s = Scope(self.names, self.funcs)
        s.names.update(extra)
        return s

    def ev(self, x):
        """A number, or an expression that comes to one."""
        if isinstance(x, bool):
            raise ExprError('expected a number, got %r' % (x,))
        if isinstance(x, (int, float)):
            return self._finite(x, x)
        if not isinstance(x, str):
            raise ExprError('expected a number or an expression, got %r' % (x,))
        if imperial(x) is not None:
            return imperial(x)
        v = self._value(x)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ExprError('%r does not come to a number' % (x,))
        return self._finite(v, x)

    def truth(self, x):
        """A comparison, such as `landing >= width`."""
        v = self._value(str(x))
        if not isinstance(v, bool):
            raise ExprError('%r is not a comparison' % (x,))
        return v

    def _value(self, x):
        """What an expression comes to. Whatever is wrong with it — it does
        not read, it divides by nothing, a function is given what it cannot
        take — is an ExprError that names it."""
        try:
            tree = ast.parse(x.strip(), mode='eval')
        except SyntaxError as e:
            raise ExprError('cannot read %r: %s' % (_short(x), e.msg))
        except (ValueError, RecursionError, MemoryError) as e:
            raise ExprError('cannot read %r: %s' % (_short(x), e or type(e).__name__))
        try:
            return self._walk(tree.body, x)
        except ExprError:
            raise
        except (ArithmeticError, TypeError, ValueError) as e:
            raise ExprError('%r: %s' % (x, e))
        except RecursionError:
            raise ExprError('%r: too long to work out' % (_short(x),))

    @staticmethod
    def _finite(v, src):
        try:
            v = float(v)
        except OverflowError:
            v = float('inf')
        if not math.isfinite(v):
            raise ExprError('%r does not come to a number that can be measured' % (_short(src),))
        return v

    def pt(self, p):
        if not isinstance(p, (list, tuple)) or len(p) != 2:
            raise ExprError('expected a point [x, y], got %r' % (p,))
        return (self.ev(p[0]), self.ev(p[1]))

    def text(self, s):
        """Fill `{expr}` and `{expr:.2f}` fields in a string."""
        def sub(m):
            v = self.ev(m.group(1))
            if m.group(2) and not _SPEC.match(m.group(2)):
                raise ExprError('format %r not allowed in %r' % (m.group(2), str(s)))
            return format(v, m.group(2)) if m.group(2) else ('%g' % v)
        return _FIELD.sub(sub, str(s))

    def _walk(self, n, src):
        if isinstance(n, ast.Constant):
            if isinstance(n.value, (int, float, bool, str)):
                return n.value
        elif isinstance(n, ast.Name):
            if n.id in self.names:
                return self.names[n.id]
            if n.id in ('True', 'False'):
                return n.id == 'True'
            raise ExprError('unknown name %r in %r' % (n.id, src))
        elif isinstance(n, ast.BinOp) and type(n.op) in _BIN:
            a, b = self._walk(n.left, src), self._walk(n.right, src)
            if isinstance(a, str) or isinstance(b, str):    # text is for naming a leaf to op(), never for working on
                raise ExprError('not arithmetic: %r' % (src,))
            return _BIN[type(n.op)](a, b)
        elif isinstance(n, ast.UnaryOp) and type(n.op) in _UNARY:
            return _UNARY[type(n.op)](self._walk(n.operand, src))
        elif isinstance(n, ast.Compare) and len(n.ops) == 1 and type(n.ops[0]) in _CMP:
            return _CMP[type(n.ops[0])](self._walk(n.left, src), self._walk(n.comparators[0], src))
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            if n.func.id not in self.funcs:
                raise ExprError('unknown function %r in %r' % (n.func.id, src))
            args = [self._walk(a, src) for a in n.args]
            kw = dict((k.arg, self._walk(k.value, src)) for k in n.keywords)
            return self.funcs[n.func.id](*args, **kw)
        raise ExprError('not allowed in an expression: %r' % (src,))
