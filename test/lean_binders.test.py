#!/usr/bin/env python3
"""
lean_binders.test.py — the binder extractor must be able to FAIL.

This helper is what the #74 waves use to check that every hypothesis in a Lean type is
reflected in the corpus prose. It has now been wrong twice, and both times it failed
SILENTLY — it reported "no hypotheses" for a declaration that had several, so the audit it
backs passed for the wrong reason:

* wave 8: the header was split at the first `:=`, and a docstring containing
  `gg t := ‖u(t) − u(τ(cell t))‖` truncated it to nothing.
* wave 9: same split, but truncated by a NAMED ARGUMENT `(𝕜 := ℝ)` written inside a
  binder — the narrower form of the same defect.
* wave 9 review: a line comment in the header (`-- assumptions:`) had its colon read as
  the conclusion delimiter — the same silent-nothing outcome from a third direction.

Both regressions are pinned below. A verification tool whose green output is trusted has to
have a demonstrated failure case of its own.

Run: python3 test/lean_binders.test.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from lean_binders import binders  # noqa: E402

CHECKS: list[str] = []


def check(label: str, cond: bool, detail: str = '') -> None:
    CHECKS.append(label)
    print(f'  {"ok " if cond else "FAIL"} {label}')
    if not cond:
        if detail:
            print(f'       {detail}')
        sys.exit(1)


def test_plain_binders() -> None:
    src = '''private theorem foo (n : ℕ) (hn : 0 < n) (x : ℝ) : n = n := by rfl'''
    check('plain binders are found', binders(src) == ['n', 'hn', 'x'], str(binders(src)))


def test_docstring_containing_assignment() -> None:
    """wave 8 regression: `:=` inside the docstring truncated the header to nothing."""
    src = '''/-- Route: `gg t := ‖u(t) − u(τ(cell t))‖`; see below. -/
private theorem bar (T : ℝ) (hT : 0 < T) (m : ℕ) (hm : 0 < m) (B : ℝ)
    (hsum : B ≤ B) : True := by trivial'''
    got = binders(src)
    check('a docstring containing := does not blind the extractor',
          got == ['T', 'hT', 'm', 'hm', 'B', 'hsum'], str(got))


def test_named_argument_inside_a_binder() -> None:
    """wave 9 regression: `(𝕜 := ℝ)` inside a binder truncated everything after it."""
    src = '''private theorem baz (hν : 0 < ν)
    (hweak : ∀ z, Tendsto f atTop (𝓝 (inner (𝕜 := ℝ) a z)))
    (hInt : IntervalIntegrable g volume 0 T) : True := by trivial'''
    got = binders(src)
    check('a named argument inside a binder does not truncate the header',
          got == ['hν', 'hweak', 'hInt'], str(got))
    check('specifically, the binder AFTER the named argument is still found',
          'hInt' in got, str(got))



def test_line_comment_containing_a_colon() -> None:
    """wave 9 review regression: a colon inside a comment was read as the conclusion."""
    src = '''private theorem f -- assumptions:
    (h : P) : P := by trivial'''
    got = binders(src)
    check('a line comment with a colon does not blind the extractor', got == ['h'], str(got))


def test_block_comment_in_the_header() -> None:
    src = '''private theorem g /- note: uses := here -/ (a : ℕ) (ha : 0 < a) : True := by trivial'''
    got = binders(src)
    check('a block comment with a colon and := is ignored', got == ['a', 'ha'], str(got))


def test_nested_block_comments() -> None:
    """Lean block comments nest; a non-greedy regex would stop at the first `-/`."""
    src = '''private theorem h /- outer /- inner : -/ still comment : -/ (x : ℕ) : True := by trivial'''
    got = binders(src)
    check('nested block comments are consumed as one', got == ['x'], str(got))


def test_grouped_binder_names_are_split() -> None:
    """`(x y : α)` is ordinary Lean; returning the string "x y" makes a by-name lookup
    miss both variables."""
    src = '''private theorem k (u v : L2VF) (hu hv : P u) : True := by trivial'''
    got = binders(src)
    check('grouped binders yield one name per variable',
          got == ['u', 'v', 'hu', 'hv'], str(got))


def test_stops_at_the_conclusion() -> None:
    """Binders end at the top-level `:`; parenthesised types in the conclusion are not binders."""
    src = '''private theorem qux (u : L2VF) (hu : P u) :
    ∀ (v : L2VF), Q (f v) (g v) := by trivial'''
    got = binders(src)
    check('parenthesised groups after the conclusion colon are not collected',
          got == ['u', 'hu'], str(got))


def test_implicit_and_instance_binders_are_not_collected_as_hypotheses() -> None:
    src = '''private theorem quux {n : ℕ} [Fact (0 < n)] (hn : n ≠ 0) : True := by trivial'''
    got = binders(src)
    check('only explicit parenthesised binders are returned', got == ['hn'], str(got))


def test_no_declaration_yields_nothing() -> None:
    check('a fragment with no declaration yields no binders', binders('-- just a comment') == [])


def main() -> None:
    test_plain_binders()
    test_docstring_containing_assignment()
    test_named_argument_inside_a_binder()
    test_line_comment_containing_a_colon()
    test_block_comment_in_the_header()
    test_nested_block_comments()
    test_grouped_binder_names_are_split()
    test_stops_at_the_conclusion()
    test_implicit_and_instance_binders_are_not_collected_as_hypotheses()
    test_no_declaration_yields_nothing()
    print(f'\nAll {len(CHECKS)} lean_binders checks passed.')


if __name__ == '__main__':
    main()
