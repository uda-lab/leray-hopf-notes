#!/usr/bin/env python3
"""
lean_binders.py — extract a Lean declaration's explicit binder names.

Used by the notes#74 waves to check mechanically that every hypothesis present in a Lean
type is reflected in the corpus prose. Its output is treated as evidence, so the ways it can
be WRONG matter more than the ways it can be right — and every failure it has had so far was
silent: it returned "no binders" for a declaration that had several, so the audit it backs
passed for the wrong reason.

Three such regressions, all pinned in `test/lean_binders.test.py`:

* wave 8 — the header was split at the first `:=`; a docstring containing
  `gg t := ‖u(t) − u(τ(cell t))‖` truncated it to nothing.
* wave 9 — the same split, truncated instead by a NAMED ARGUMENT `(𝕜 := ℝ)` written inside
  a binder, hiding every binder after it (`hInt`, an integrability hypothesis).
* wave 9 review — a line comment inside the header (`-- assumptions:`) had its colon read
  as the conclusion delimiter, again returning nothing.

The first two motivated replacing the split with a balanced-paren scan; the third motivated
stripping comments before scanning at all. Comments are removed first, then binders are read
as parenthesised groups up to the top-level `:` that introduces the conclusion.
"""

from __future__ import annotations

import re

__all__ = ['binders', 'strip_comments']


def strip_comments(src: str) -> str:
    """Remove Lean block comments (`/- … -/`, which nest) and line comments (`-- …`).

    Done before any scanning: a colon inside a comment is not a conclusion delimiter, and a
    `:=` inside one is not an assignment. Block comments nest in Lean, so a depth counter is
    needed — a non-greedy regex would stop at the first `-/` and leave the tail of an outer
    comment behind.
    """
    out: list[str] = []
    i, depth, n = 0, 0, len(src)
    while i < n:
        if src.startswith('/-', i):
            depth += 1
            i += 2
            continue
        if src.startswith('-/', i) and depth:
            depth -= 1
            i += 2
            continue
        if depth:
            i += 1
            continue
        if src.startswith('--', i):
            end = src.find('\n', i)
            i = n if end == -1 else end          # keep the newline itself
            continue
        out.append(src[i])
        i += 1
    return ''.join(out)


DECL_HEAD = re.compile(
    r'\b(?:private\s+|protected\s+|noncomputable\s+|partial\s+)*'
    r'(?:theorem|lemma|def|abbrev|instance|example)\s+(\S+)')


def binders(src: str) -> list[str]:
    """Explicit binder names, in source order.

    Only explicit `( … : … )` binders are returned; implicit `{ … }` and instance `[ … ]`
    binders are skipped on purpose, since the audit this feeds is about hypotheses a reader
    must see stated. Grouped binders (`(x y : α)`, ordinary Lean) yield one name per
    variable — returning the raw string `"x y"` would make a lookup by name miss both.
    """
    src = strip_comments(src)
    m = DECL_HEAD.search(src)
    if not m:
        return []

    i, depth, n = m.end(), 0, len(src)
    out: list[str] = []
    cur, capturing = '', False
    while i < n:
        ch = src[i]
        if ch in '([{':
            depth += 1
            if depth == 1:
                cur, capturing = '', ch == '('
                i += 1
                continue
        elif ch in ')]}':
            depth -= 1
            if depth == 0:
                if capturing and ':' in cur:
                    out.extend(cur.split(':', 1)[0].split())
                capturing = False
                i += 1
                continue
        elif depth == 0 and ch == ':':
            break                                # the conclusion starts here
        if depth == 1 and capturing:
            cur += ch
        i += 1
    return out
