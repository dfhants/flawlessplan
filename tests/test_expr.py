# -*- coding: utf-8 -*-
"""Arithmetic over named measurements: what it works out, and everything
it will not do. A house file comes from anywhere, so whatever is wrong
with an expression is an ExprError and nothing else."""
import math
import pytest

from flawlessplan.expr import Scope, ExprError, imperial, centred, FUNCS

S = Scope({'W': 8.0, 'D': 6.0, 'IW': 0.1})


@pytest.mark.parametrize('src, want', [
    ('W + D', 14.0), ('W - D', 2.0), ('W * D', 48.0), ('W / D', 8/6.0), ('W ** 2', 64.0),
    ('W % 3', 2.0), ('W // 3', 2.0), ('-W', -8.0), ('+W', 8.0), ('(W + D) / 2 - IW/2', 6.95),
    ('min(W, D)', 6.0), ('max(W, D, 9)', 9.0), ('abs(D - W)', 2.0), ('round(W/3, 2)', 2.67),
    ('int(W/3)', 2.0), ('sqrt(W*2)', 4.0), ('hypot(3, 4)', 5.0), ('ceil(W/3)', 3.0), ('floor(W/3)', 2.0),
    ('sin(radians(30))', 0.5), ('cos(0)', 1.0), ('tan(radians(45))', 1.0), ('centred(0, W, 2)', 3.0),
    ('  W  ', 8.0), ('1e-3', 0.001), ('2', 2.0),
])
def test_an_expression_comes_to_a_number(src, want):
    got = S.ev(src)
    assert isinstance(got, float) and got == pytest.approx(want)


def test_every_function_offered_is_one_this_file_tries():
    tried = {'min', 'max', 'abs', 'round', 'int', 'sqrt', 'sin', 'cos', 'tan', 'radians', 'hypot',
             'ceil', 'floor', 'centred'}
    assert set(FUNCS) == tried, 'a function was added to expr.FUNCS: try it above, and what it does with bad arguments below'


def test_a_plain_number_is_itself():
    assert S.ev(3) == 3.0 and isinstance(S.ev(3), float) and S.ev(2.5) == 2.5


@pytest.mark.parametrize('src, metres', [
    ('14\'4"', (14*12 + 4)*0.0254), ("8'", 96*0.0254), ('6"', 6*0.0254), ('10\' 6.5"', 126.5*0.0254),
    (' 3\'0" ', 36*0.0254),
])
def test_feet_and_inches_are_metres(src, metres):
    assert imperial(src) == pytest.approx(metres) and S.ev(src) == pytest.approx(metres)


@pytest.mark.parametrize('src', ['', ' ', '4', '4.2', "4''", '4"3\'', "four'", 'W'])
def test_what_is_not_feet_and_inches_is_not_taken_for_them(src):
    assert imperial(src) is None


def test_centred_is_the_start_of_an_opening_in_the_middle_of_a_run():
    assert centred(2.0, 6.0, 1.0) == 3.5 and centred(6.0, 2.0, 1.0) == 3.5


def test_a_child_scope_adds_names_and_leaves_its_parent_alone():
    child = S.child(KITCHEN_w=3.2)
    assert child.ev('KITCHEN_w + W') == 11.2
    with pytest.raises(ExprError, match='unknown name'):
        S.ev('KITCHEN_w')
    child.names['W'] = 1.0
    assert S.ev('W') == 8.0


def test_a_scope_can_be_given_a_function_of_its_own():
    s = Scope({'a': 1.0}, funcs={'double': lambda x, by=2: x*by})
    assert s.ev('double(a)') == 2.0 and s.ev('double(a, by=3)') == 3.0
    assert 'double' not in FUNCS


@pytest.mark.parametrize('src, want', [('W > D', True), ('W < D', False), ('W >= 8', True), ('W <= 7.9', False),
                                       ('W == 8', True), ('W != 8', False), ('W - D >= IW', True)])
def test_a_comparison_is_true_or_false(src, want):
    assert S.truth(src) is want


@pytest.mark.parametrize('src', ['W', 'W + 1', '1', 'min(W, D)'])
def test_a_number_is_not_a_comparison(src):
    with pytest.raises(ExprError, match='not a comparison'):
        S.truth(src)


@pytest.mark.parametrize('src', ['W > D', 'True', 'W == 8'])
def test_a_comparison_is_not_a_number(src):
    with pytest.raises(ExprError, match='does not come to a number'):
        S.ev(src)


@pytest.mark.parametrize('value', [True, False, None, [1, 2], {'a': 1}, (1, 2)])
def test_what_is_not_a_number_or_text_is_refused(value):
    with pytest.raises(ExprError, match='expected a number'):
        S.ev(value)


@pytest.mark.parametrize('src', [
    '__import__("os")', '__import__("os").system("true")', 'open("/etc/passwd")', 'eval("1")', 'exec("1")',
    'W.real', 'W.__class__', '().__class__.__bases__', '[1, 2]', '[1, 2][0]', '(1, 2)', '{1: 2}', '{1}',
    'lambda: 1', '(lambda: 1)()', '[x for x in (1, 2)]', 'W if W else 1', 'W and D', 'not W', 'W or D',
    'W < D < 9', 'W is D', 'W in (1, 2)', '~1', '1 << 2', '1 | 2', '1 & 2', '1 ^ 2', 'W @ D',
    'f"{W}"', '"a" "b"', '"wide"', 'b"x"', 'None', '...', '1j', 'W := 1', '(W := 1)', '*W', 'min(*[1, 2])',
    'min(**{})', 'min.__call__(1, 2)', 'sqrt', 'W; D', 'W\nD', 'import os', 'x = 1', '', '   ', '(', '1 +',
    'nope', 'nope(1)', 'W()', '"a"*3', '3*"a"', '"a" + "b"', '"%s" % W', 'min("a", "b")',
])
def test_nothing_but_arithmetic_is_allowed(src):
    with pytest.raises(ExprError):
        S.ev(src)
    with pytest.raises(ExprError):
        S.truth(src)


# Found by trying them: each of these once came out as something other than
# an ExprError, which the command line does not catch.
BROKEN = ['1/0', 'W / (D - 6)', 'W % 0', 'W // 0', '0 ** -1', 'sqrt(-1)', 'sqrt(D - W)', 'min()', 'max()',
          'centred(1, 2)', 'centred()', 'hypot("a")', 'abs()', 'sqrt(1, 2)', 'round(W, D)', 'int(1e400)',
          'ceil(1e400)', 'floor(1e400)', 'round(1e400)', 'sin(1e400)', 'radians()', 'min(1, nope=2)',
          'round(W, ndigits=1.5)', 'int("abc")', 'abs("a")', '1e308 * 10', '-1e308 * 10', '1e400', '1e400 - 1e400',
          'W + "a"', '-"a"', 'max(1, "a")']


@pytest.mark.parametrize('src', BROKEN)
def test_what_cannot_be_worked_out_is_an_error_of_the_expression(src):
    with pytest.raises(ExprError) as e:
        S.ev(src)
    assert src in str(e.value) or repr(src) in str(e.value)        # it says which expression
    with pytest.raises(ExprError):
        S.truth(src)


@pytest.mark.parametrize('value', [float('nan'), float('inf'), float('-inf'), 10**400])
def test_a_number_that_is_not_finite_is_not_a_measurement(value):
    with pytest.raises(ExprError):
        S.ev(value)


@pytest.mark.parametrize('src', ['9**9**9', '9**99', '1e7**2', '2**-17', '(9**16)**16', '9**9**9**9**9'])
def test_a_power_cannot_be_made_to_run_away(src):
    with pytest.raises(ExprError, match='power out of range'):
        S.ev(src)


@pytest.mark.parametrize('src', ['"a" * 10**9', '10**9 * "a"', '"a" * 10**9 * 10**9', 'min("a" * 10**9, "b")',
                                 '("a" * 9**9) < "b"'])
def test_text_cannot_be_multiplied_into_a_wall_of_it(src):
    """A string is there to name a door leaf to op(), not to be worked on."""
    with pytest.raises(ExprError):
        S.ev(src)
    with pytest.raises(ExprError):
        S.truth(src)


@pytest.mark.parametrize('n', [50, 500, 5000, 100000])
def test_brackets_however_deep_are_answered(n):
    src = '(' * n + 'W' + ')' * n
    try:
        assert S.ev(src) == 8.0
    except ExprError:
        pass


@pytest.mark.parametrize('n', [500, 20000])
def test_a_sum_however_long_is_answered(n):
    src = ' + '.join(['1'] * n)
    try:
        assert S.ev(src) == n
    except ExprError:
        pass


def test_a_point_is_two_expressions():
    assert S.pt(['W/2', 3]) == (4.0, 3.0) and S.pt(('W', 'D')) == (8.0, 6.0)
    for bad in ('W', [1], [1, 2, 3], None, 7, {'x': 1}):
        with pytest.raises(ExprError, match='expected a point'):
            S.pt(bad)
    with pytest.raises(ExprError, match='unknown name'):
        S.pt(['W', 'nope'])


@pytest.mark.parametrize('src, want', [
    ('{W}', '8'), ('{W:.2f}', '8.00'), ('{W/3:.1f} m', '2.7 m'), ('{W} by {D}', '8 by 6'), ('{W:.0f}', '8'),
    ('{W:5.1f}', '  8.0'), ('{W:+.1f}', '+8.0'), ('{IW:.0%}', '10%'), ('{W:g}', '8'), ('no fields', 'no fields'),
    ('', ''), ('{W/3}', '2.66667'), ('{min(W, D)}', '6'), (12, '12'), ('100% sure', '100% sure'),
])
def test_text_has_its_fields_filled_in(src, want):
    assert S.text(src) == want


@pytest.mark.parametrize('src', ['{W:>9}', '{W:999999}', '{W:.99f}', '{W:,}', '{W:x}', '{W:s}', '{W:100.1f}',
                                 '{W:0999}', '{W:_}', '{W:#x}', '{W:^30}', '{W!r}', '{W:.2f:.2f}'])
def test_text_cannot_ask_for_a_format_that_pads_or_breaks(src):
    with pytest.raises(ExprError):
        S.text(src)


@pytest.mark.parametrize('src', ['{nope}', '{W +}', '{1/0}', '{__import__("os")}', '{W > D}', '{"a"}', '{ }'])
def test_a_field_that_cannot_be_worked_out_is_an_error(src):
    with pytest.raises(ExprError):
        S.text(src)


def test_a_field_is_filled_once_and_not_read_again():
    """What a field comes to is text, and is not looked at for more fields."""
    assert Scope({'a': 2.0}).text('{a}{a}') == '22'
    assert S.text('{{W}}') == '{8}'             # no escaping of braces: the inner field is filled
    assert S.text('{W:{D}}') == '{W:6}'         # and a format cannot be built out of another field
    assert S.text('}{') == '}{' and S.text('{') == '{' and S.text('{}') == '{}'


def test_the_answer_is_a_float_whatever_python_made_of_it():
    for src in ('int(W)', 'round(W)', 'ceil(W)', 'floor(W)', 'W // 1', '7', 'max(1, 2)'):
        assert type(S.ev(src)) is float
    assert math.isfinite(S.ev('1e308'))
