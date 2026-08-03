#!/usr/bin/env python3
"""lean_binders.py — extract a Lean declaration's binder names by scanning balanced parens.

Regex-splitting the header at the first ':=' has now failed twice: once on a docstring
containing ':=' (wave 8) and once on a NAMED ARGUMENT '(𝕜 := ℝ)' inside a binder (wave 9),
which silently truncated the header and hid every binder after it. This scans instead.
"""
import re

__all__ = ["binders"]

def binders(src: str) -> list[str]:
    src = re.sub(r'/--.*?-/', '', src, flags=re.S)          # docstring first
    m = re.search(r'\b(?:private\s+)?(?:noncomputable\s+)?(?:theorem|lemma|def|abbrev)\s+(\S+)', src)
    if not m:
        return []
    i = m.end()
    depth = 0
    out, cur, capturing = [], '', False
    while i < len(src):
        ch = src[i]
        if ch in '([{':
            depth += 1
            if depth == 1:
                cur, capturing = '', (ch == '(')
                i += 1
                continue
        elif ch in ')]}':
            depth -= 1
            if depth == 0:
                if capturing and ':' in cur:
                    out.append(cur.split(':', 1)[0].strip())
                capturing = False
                i += 1
                continue
        elif depth == 0 and ch == ':':
            # top-level ':' introduces the conclusion — binders are done
            break
        if depth == 1 and capturing:
            cur += ch
        i += 1
    return [b for b in out if b]
