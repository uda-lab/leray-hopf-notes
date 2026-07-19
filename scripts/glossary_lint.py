#!/usr/bin/env python3
"""
glossary_lint.py — corpus translation linter for leray-hopf-notes.

Uses scripts/glossary.py to parse docs/GLOSSARY.md (Markdown table with columns:
  English term | 日本語訳 | Lean 識別子例 | 備考 | forbidden)

For each corpus/**/*.yaml:
  - Detects occurrences of known-bad (forbidden) translations in statement_ja /
    proof_ja / gap.note / provenance / tags (notes#105: gap.note and provenance/tags
    reach the public screen too, so they are in scope, not just statement_ja/proof_ja
    as before).

Forbidden-translation findings (known-bad regressions, e.g. 証人/目撃者 for
"witness") are now a HARD ERROR unconditionally (exit 1), independent of --strict.
This is the regression guard notes#105 requires: a reintroduced forbidden term must
fail CI, not just print a warning nobody reads. --strict is kept as a CLI flag for
forward compatibility with any future soft-warning checks added to this script; it
has no effect on forbidden-translation findings, which always gate.

Allowlist (notes#105): quotations / meta-discussion of a forbidden term should stay
legal (e.g. a declaration *about* the English word itself, or a historical note that
must name the old wrong translation to explain a fix). Two escape hatches:
  1. Backtick-quoted spans (`` `...` ``) are excluded from forbidden-term matching —
     the corpus's own supported-markdown subset (docs#prose_lint D5) only allows
     `code`/**strong**/[[ref]] inline, so backticks are the one way to quote a literal
     string in corpus prose; a forbidden term inside backticks is being named, not used.
  2. scripts/glossary_lint_allowlist.json: an explicit, PR-reviewable per-file,
     per-term override for cases backticking doesn't cover. Empty by default — every
     entry must justify itself in code review.

Exit code: 1 if any forbidden-translation finding remains after backtick/allowlist
exemption. Otherwise 0.

Usage:
    python3 scripts/glossary_lint.py
    python3 scripts/glossary_lint.py --strict
    python3 scripts/glossary_lint.py --corpus corpus/LerayHopf/R3/  # specific subtree
"""

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    sys.exit('ERROR: PyYAML required. pip install pyyaml')

sys.path.insert(0, str(Path(__file__).parent))
from glossary import parse_glossary  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
GLOSSARY_PATH = REPO_ROOT / 'docs' / 'GLOSSARY.md'
CORPUS_DIR = REPO_ROOT / 'corpus'
ALLOWLIST_PATH = REPO_ROOT / 'scripts' / 'glossary_lint_allowlist.json'

BACKTICK_SPAN_RE = re.compile(r'`[^`]*`')


def load_allowlist(path: Path | None = None) -> dict[str, set[str]]:
    """Parse scripts/glossary_lint_allowlist.json: {relative_file_path: [terms]}."""
    p = path or ALLOWLIST_PATH
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError) as exc:
        print(f'WARNING: could not parse {p}: {exc}', file=sys.stderr)
        return {}
    return {k: set(v) for k, v in raw.get('allow', {}).items()}


def strip_backtick_spans(text: str) -> str:
    """Remove backtick-quoted code spans so terms only quoted/named there don't
    trigger the forbidden-term check (see module docstring, escape hatch 1)."""
    return BACKTICK_SPAN_RE.sub(' ', text)


def load_corpus(corpus_root: Path) -> list[tuple[Path, dict]]:
    docs = []
    for fpath in sorted(corpus_root.rglob('*.yaml')):
        try:
            with open(fpath, encoding='utf-8') as f:
                doc = yaml.safe_load(f)
            if isinstance(doc, dict):
                docs.append((fpath, doc))
        except (yaml.YAMLError, OSError):
            pass
    return docs


PUBLIC_TEXT_FIELDS = ('statement_ja', 'proof_ja')  # gap.note, provenance, tags below


def get_text_fields(doc: dict) -> str:
    """Concatenate every public-facing text field that could carry a forbidden
    translation: statement_ja / proof_ja / gap.note / provenance / tags
    (notes#105 — the earlier version only scanned statement_ja/proof_ja, missing
    gap.note entirely, which is where most of the notes#105 findings lived)."""
    parts = []
    for field in PUBLIC_TEXT_FIELDS:
        val = doc.get(field)
        if isinstance(val, str):
            parts.append(val)
    gap = doc.get('gap')
    if isinstance(gap, dict) and isinstance(gap.get('note'), str):
        parts.append(gap['note'])
    prov = doc.get('provenance')
    if isinstance(prov, str):
        parts.append(prov)
    tags = doc.get('tags')
    if isinstance(tags, list):
        parts.append(' '.join(str(t) for t in tags))
    return ' '.join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--strict', action='store_true',
                        help='Reserved for future soft-warning checks; forbidden-'
                             'translation findings always gate regardless of this flag')
    parser.add_argument('--corpus', default=None,
                        help='Lint only this subdirectory (default: entire corpus/)')
    args = parser.parse_args()

    corpus_root = Path(args.corpus) if args.corpus else CORPUS_DIR
    if not corpus_root.is_dir():
        sys.exit(f'ERROR: corpus directory not found: {corpus_root}')

    glossary = parse_glossary(GLOSSARY_PATH)
    if not glossary:
        print('WARNING: empty or missing glossary — no linting performed')
        return

    corpus = load_corpus(corpus_root)
    if not corpus:
        print(f'No corpus files found under {corpus_root}. Nothing to lint.')
        return

    allowlist = load_allowlist()
    findings: list[str] = []

    for fpath, doc in corpus:
        raw_text = get_text_fields(doc)
        if not raw_text.strip():
            continue
        rel = str(fpath.relative_to(REPO_ROOT))
        text = strip_backtick_spans(raw_text)  # escape hatch 1: backtick quoting
        allowed_here = allowlist.get(rel, set())  # escape hatch 2: explicit override

        for entry in glossary:
            english = entry['english']
            japanese = entry['japanese']
            forbidden = entry['forbidden']

            for bad in forbidden:
                if not bad or bad in allowed_here:
                    continue
                if bad in text:
                    findings.append(
                        f'ERROR [{rel}]: '
                        f'forbidden translation "{bad}" for "{english}" '
                        f'(use: {japanese})'
                    )

    # Summary
    if findings:
        print(f'{len(findings)} glossary finding(s):')
        for f in findings:
            print(f'  {f}')
        sys.exit(1)
    else:
        n = len(corpus)
        print(f'OK — {n} corpus file(s) checked, no glossary violations.')


if __name__ == '__main__':
    main()
