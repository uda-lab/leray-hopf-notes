#!/usr/bin/env python3
"""Regression guard for notes#119: `statement_ja` must not describe an existential
witness as if it were unique.

The corpus annotates Lean declarations whose statements are plain `∃`. Writing the
witness as 「ただ一つの …」 / 「ただ一本の …」 reads as `∃!`, which asserts uniqueness the
Lean type does not carry. notes#116 (PR #118) corrected nine such entries; notes#119
corrected the last one, `schwartz_h1_gradConv_multi`. Nothing prevented reintroduction,
so this check gates it.

Scope and discrimination — both matter, and were measured rather than assumed:

* **Scoped to `statement_ja`.** That is where a declaration states its own claim.
  `proof_ja`, `gap.note` and `provenance` legitimately discuss uniqueness as a *tool*
  (uniqueness of limits, unique continuous extension, ODE uniqueness) and are not scanned.
* **Only 「ただ一つ／一本／ひとつ」, not 「唯一の」/「一意の」.** Every one of the ten known
  defects used the former. The latter appear in `statement_ja` only as counting prose
  (「唯一の入力は…」, 「唯一の橋である」) — banning them would produce four false positives
  and teach authors to suppress the check reflexively.
* **`ただ一つの内容` is excluded.** `TimeCompactnessInput` says 「ただ一つの内容として」 of a
  structure carrying a single *field*, not of an existential witness. That is a different
  claim and a correct one.

Measured against the corpus: 10/10 known defects detected (the nine from PR #118's
`6cb8bea` plus notes#119's), 0 false positives across all `statement_ja` fields.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit('ERROR: PyYAML required. pip install pyyaml')


REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS_DIR = REPO_ROOT / 'corpus'

# 「ただ一つの／ただ一本の／ただひとつの／ただ 1 つの」 introducing a mathematical object.
# The negative lookahead spares 「ただ一つの内容」 (a structure's single field).
UNIQUENESS_DETERMINER = re.compile(r'ただ(?:一つ|一本|ひとつ|1 つ)の(?!内容)')

# Wordings taken verbatim from the defects this guard exists to catch.
KNOWN_DEFECTS = [
    '…$L^2$ 収束するような、ただ一つの Schwartz 列が存在する。',                      # notes#119
    'ただ一つの狭義単調な対角抽出 $\\delta$ が存在して、…',                          # PR #118
    'ある形式束 $F$ と**ただ一本の**曲線 $u$ が存在して、…',                          # PR #118
    '区間ごとに現れる代表元を、ただ一本の曲線 $W$ へ同定するための道具である。',      # PR #118 (no 存在)
    'ただ一本の曲線 $u$ と、その**同じ** $u$ が…を保持する。',                        # PR #118 (no 存在)
]

# Wordings that must NOT trip the guard.
KNOWN_ALLOWED = [
    'ただ一つの内容として、与えられた Galerkin 列に対する一様な時間連続モジュラスをもつ。',
    'この第三の全体性こそが、このデータが担う唯一の古典的入力である。',
    '唯一の入力は基底に束ねられた密度性の仮説であり、…',
    '狭義単調な対角抽出 $\\delta$ がとれて、**その同じ** $\\delta$ について、…',
    '単一の狭義単調な部分列が存在して、すべての半径 $k$ について…',
]

CHECKS: list[str] = []


def check(label: str, cond: bool, detail: str = '') -> None:
    CHECKS.append(label)
    if cond:
        print(f'  ok  {label}')
    else:
        print(f'  FAIL {label}')
        if detail:
            print(f'       {detail}')
        sys.exit(1)


def scan_corpus() -> list[str]:
    """Every `statement_ja` violation in the committed corpus, as display strings."""
    violations = []
    for fpath in sorted(CORPUS_DIR.rglob('*.yaml')):
        try:
            doc = yaml.safe_load(fpath.read_text(encoding='utf-8'))
        except yaml.YAMLError as exc:
            violations.append(f'{fpath.relative_to(REPO_ROOT)}: parse error: {exc}')
            continue
        if not isinstance(doc, dict):
            continue
        statement = doc.get('statement_ja')
        if not isinstance(statement, str):
            continue
        for m in UNIQUENESS_DETERMINER.finditer(statement):
            snippet = statement[m.start():m.start() + 40].replace('\n', ' ')
            violations.append(f'{fpath.relative_to(REPO_ROOT)}: 「{snippet}…」')
    return violations


def main() -> None:
    violations = scan_corpus()
    check(
        'corpus statement_ja has no uniqueness overclaim',
        not violations,
        '\n       '.join(violations),
    )

    for wording in KNOWN_DEFECTS:
        check(
            f'detects known defect: 「{wording[:28]}…」',
            bool(UNIQUENESS_DETERMINER.search(wording)),
        )

    for wording in KNOWN_ALLOWED:
        check(
            f'allows legitimate wording: 「{wording[:28]}…」',
            not UNIQUENESS_DETERMINER.search(wording),
        )

    print(f'\nAll {len(CHECKS)} notes#119 uniqueness-overclaim checks passed.')


if __name__ == '__main__':
    main()
