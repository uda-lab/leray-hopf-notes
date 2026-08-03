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

The comparison is on the `contains-sorry` VALUE, not on the presence of the field: the
schema also permits `verified`, `scaffold`, `retired` and `invalid-statement`, and a test
keyed on presence would fail the first time any of those is set for an unrelated entry.

Two sets are pinned. `DIRECT` holds declarations whose own proof body contains a literal
`sorry`. `TRANSITIVE` holds the public theorems that call one of those in their proof — the
schema counts those as `contains-sorry` too ("directly or via a sorry-dependent private
helper"), and they were being shown as verified until notes#146.

The transitive set is NOT a closure. It was found by scanning same-file callers, which is
sound here because the sorry-bearing declarations are private or file-local, but it does not
generalise: `decls.json`'s `uses` does not record private helpers, so a real closure cannot
be computed from the data this repo has. notes#146 tracks that gap.

Run: python3 test/issue74_proof_status_preserved.test.py
"""

import sys
from pathlib import Path

import yaml

CORPUS = Path(__file__).resolve().parents[1] / 'corpus' / 'LerayHopf'

# Declarations whose upstream proof contains a `sorry` at the pinned commit.
DIRECT = {
    'isWeakTimeDeriv_primitive.yaml',
    'timeConv_prod_integrable.yaml',
    'timeMollification_exists.yaml',
    'w1pTime_continuous_in_H.yaml',
    'w1pTime_lineExtension.yaml',
    'weakTimeDerivℝ_even_reflection.yaml',
}

# Public theorems whose proofs call one of the above (notes#146). Each must say so in its
# prose as well: a reader of the declaration page has no other way to learn it.
TRANSITIVE = {
    'timeConvL2_weakDeriv_comm.yaml': 'timeConv_prod_integrable',
    'timeMollification_of_w1pTime.yaml': 'timeMollification_exists',
    'w1pTime_continuous_in_Vprime.yaml': 'isWeakTimeDeriv_primitive',
}

UNFINISHED = DIRECT | set(TRANSITIVE)

CHECKS: list[str] = []


def check(label: str, cond: bool, detail: str = '') -> None:
    CHECKS.append(label)
    print(f'  {"ok " if cond else "FAIL"} {label}')
    if not cond:
        if detail:
            print(f'       {detail}')
        sys.exit(1)


def main() -> None:
    # Only `contains-sorry` is compared. `proof_status` also legitimately carries
    # `verified`, `scaffold`, `retired` and `invalid-statement` (see
    # docs/schemas/corpus.schema.json); keying on "has the field at all" would make this
    # test fail the first time someone sets one of those for an unrelated reason.
    marked = {p.name for p in CORPUS.glob('*.yaml')
              if yaml.safe_load(p.read_text(encoding='utf-8')).get('proof_status')
              == 'contains-sorry'}

    missing = sorted(UNFINISHED - marked)
    check('every declaration with an unfinished proof still declares contains-sorry',
          not missing,
          f'lost the marking: {missing} — a missing proof_status defaults to verified in '
          f'build_site_data.py, so the site would present an unfinished proof as complete')

    extra = sorted(marked - UNFINISHED)
    check('no unlisted declaration is marked contains-sorry',
          not extra,
          f'{extra} — if a new sorry appeared upstream, add it to UNFINISHED')

    for name in sorted(UNFINISHED):
        doc = yaml.safe_load((CORPUS / name).read_text(encoding='utf-8'))
        check(f'{name} is marked contains-sorry',
              doc.get('proof_status') == 'contains-sorry', str(doc.get('proof_status')))
        prose = ((doc.get('gap') or {}).get('note', '') or '') + (doc.get('statement_ja') or '')
        check(f'{name} discloses the unfinished proof in its prose',
              'sorry' in prose,
              'the reader of this page must be told the proof is incomplete')

    for name, dep in sorted(TRANSITIVE.items()):
        prose = ((yaml.safe_load((CORPUS / name).read_text(encoding='utf-8')).get('gap') or {})
                 .get('note', '') or '')
        check(f'{name} names the declaration it inherits the sorry from',
              dep in prose,
              f'must name `{dep}` so the reader can follow the dependency')

    print(f'\nAll {len(CHECKS)} notes#74 proof-status checks passed.')


if __name__ == '__main__':
    main()
