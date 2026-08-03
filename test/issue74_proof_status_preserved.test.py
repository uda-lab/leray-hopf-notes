#!/usr/bin/env python3
"""
issue74_proof_status_preserved.test.py — a declaration with an unfinished proof must keep
saying so.

`build_site_data.py` treats a missing `proof_status` as `verified`. So dropping the field
does not fail any existing check — it silently promotes an unfinished proof to "done" on
every site surface that shows proof status.

That is exactly what happened: the notes#74 Wave 12 rewrite of
`timeConv_prod_integrable.yaml` regenerated the file from a template that carried only
`name`/`file`/`chapter`, discarding `proof_status: contains-sorry` and the `sorry`
disclosure in `gap.note`. Codex caught it in review; nothing in CI would have.

This pins the declarations currently known to carry an unfinished proof. A future edit that
drops the field, or that drops the disclosure from the prose, fails here.

Adding a declaration to this list is correct when a new `sorry` appears upstream; REMOVING
one is only correct when a repin actually discharges the `sorry` — not when a file is
reformatted.

Run: python3 test/issue74_proof_status_preserved.test.py
"""

import sys
from pathlib import Path

import yaml

CORPUS = Path(__file__).resolve().parents[1] / 'corpus' / 'LerayHopf'

# Declarations whose upstream proof contains a `sorry` at the pinned commit.
UNFINISHED = {
    'isWeakTimeDeriv_primitive.yaml',
    'timeConv_prod_integrable.yaml',
    'timeMollification_exists.yaml',
    'w1pTime_continuous_in_H.yaml',
    'w1pTime_lineExtension.yaml',
    'weakTimeDerivℝ_even_reflection.yaml',
}

CHECKS: list[str] = []


def check(label: str, cond: bool, detail: str = '') -> None:
    CHECKS.append(label)
    print(f'  {"ok " if cond else "FAIL"} {label}')
    if not cond:
        if detail:
            print(f'       {detail}')
        sys.exit(1)


def main() -> None:
    present = {p.name for p in CORPUS.glob('*.yaml')
               if 'proof_status' in yaml.safe_load(p.read_text(encoding='utf-8'))}

    missing = sorted(UNFINISHED - present)
    check('every declaration with an unfinished proof still declares proof_status',
          not missing, f'lost the field: {missing}')

    extra = sorted(present - UNFINISHED)
    check('no unexpected declaration claims a non-default proof_status',
          not extra,
          f'{extra} — if a new sorry appeared upstream, add it to UNFINISHED; '
          f'if a repin discharged one, remove it')

    for name in sorted(UNFINISHED):
        doc = yaml.safe_load((CORPUS / name).read_text(encoding='utf-8'))
        check(f'{name} is marked contains-sorry',
              doc.get('proof_status') == 'contains-sorry', str(doc.get('proof_status')))
        prose = (doc.get('gap') or {}).get('note', '') + (doc.get('statement_ja') or '')
        check(f'{name} discloses the unfinished proof in its prose',
              'sorry' in prose,
              'the reader of this page must be told the proof is incomplete')

    print(f'\nAll {len(CHECKS)} notes#74 proof-status checks passed.')


if __name__ == '__main__':
    main()
