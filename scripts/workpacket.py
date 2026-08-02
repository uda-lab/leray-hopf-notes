#!/usr/bin/env python3
"""
workpacket.py — work-packet generator for leray-hopf-notes translation workers.

Given a chapter or module filter, emits a self-contained markdown packet to stdout:
  - List of un-annotated declarations matching the filter
  - For each: metadata (file/line/kind/signature/doc/deps when decls.json available)
  - Lean source snippet (read from leray-hopf checkout using file+lines)
  - Ready-to-fill YAML skeleton

Workers read ONLY this packet — they never need to walk leray-hopf themselves.

Usage:
    python3 scripts/workpacket.py --chapter capstone-r3 [--lean-root /path/to/leray-hopf]
    python3 scripts/workpacket.py --module LerayHopf.R3.GalerkinODECapstone [--lean-root ...]
    python3 scripts/workpacket.py --chapter spaces --limit 20
    python3 scripts/workpacket.py --chapter compactness --tier full  # only theorem-like decls

Options:
    --lean-root PATH     leray-hopf checkout path (default: /workspaces/leray-hopf)
    --limit N            emit at most N declarations (default: unlimited)
    --tier full|gloss    pre-select tier for skeleton (default: auto based on kind)
    --include-annotated  include already-annotated declarations (default: skip)
    --all                emit all un-annotated regardless of chapter/module
"""

import argparse
import json
import re
import sys
from pathlib import Path
from textwrap import indent

try:
    import yaml
    HAS_YAML = True
except ImportError:
    sys.exit('ERROR: PyYAML required. pip install pyyaml')

REPO_ROOT = Path(__file__).parent.parent
CORPUS_DIR = REPO_ROOT / 'corpus'
EXTRACTED_DIR = REPO_ROOT / 'extracted'
DEFAULT_LEAN_ROOT = Path('/workspaces/leray-hopf')

# Chapter → module path heuristics (used when decls.json not available)
CHAPTER_MODULE_PATTERNS: dict[str, list[str]] = {
    'capstone-r3':     ['R3/GalerkinODECapstone', 'R3/SolutionInterfaces', 'R3Capstone'],
    'capstone-torus':  ['Torus/GalerkinODECapstone', 'Torus/SolutionInterfaces', 'Torus/Capstone'],
    'spaces':          ['DivergenceFree', 'Leray', 'FunctionSpaces', 'EvolutionTriple',
                        'R3/Domain', 'R3/DivergenceFree', 'SobolevTorus', 'Torus/Domain'],
    'projections-galerkin': ['GalerkinProjection', 'VelocityGalerkin', 'Torus/GalerkinScheme',
                             'R3/GalerkinScheme', 'R3/GalerkinBasisH1', 'R3/SchwartzDivFreeBasis'],
    'ode':             ['Torus/GalerkinODESolve', 'R3/GalerkinODE', 'R3/GalerkinODESolve',
                        'R3/GalerkinODEExistence', 'R3/GalerkinCurveBounds'],
    'energy':          ['EnergyEstimate', 'EnergySkeleton', 'H1Sigma', 'R3/Regularity',
                        'Torus/TraceEnergy', 'Torus/EnergyConvection'],
    'compactness':     ['RellichEmbedding', 'R3/FrechetKolmogorov', 'R3/SpatialCompactness',
                        'R3/SpacetimePrecompact', 'R3/ArzelaAscoliTime', 'Torus/ModeCompactness',
                        'Torus/ModeTail', 'R3/GalerkinTimeModulus'],
    'limit-passage':   ['R3/LimitPassage', 'R3/AubinLionsLimitPassage', 'R3/AubinLionsAssembly',
                        'Torus/AubinLionsAssembly', 'Torus/LimitPassage'],
    'bochner':         ['Bochner'],
    'galerkin-generic': ['Galerkin/'],
    'misc':            [],
}

THEOREM_KINDS = {'theorem', 'lemma'}


def load_universe() -> tuple[list[dict], str]:
    decls_path = EXTRACTED_DIR / 'decls.json'
    fallback_path = EXTRACTED_DIR / 'names-fallback.json'
    if decls_path.exists():
        with open(decls_path, encoding='utf-8') as f:
            return json.load(f), 'decls.json'
    if fallback_path.exists():
        with open(fallback_path, encoding='utf-8') as f:
            return json.load(f), 'names-fallback.json'
    return [], '(none)'


def load_annotated_names() -> tuple[set[str], set[tuple[str, str]]]:
    """Return (annotated names, annotated (name, file) keys).

    A name alone cannot identify an annotation when the display name is ambiguous: two
    private helpers in different modules share it, so treating "this name is annotated" as
    "both declarations are annotated" hides the second one from every future work packet.
    The keyed set mirrors `validate.py`'s `keyed_universe` and is what `is_annotated` uses
    for ambiguous names (notes#7, notes#120).
    """
    names: set[str] = set()
    keys: set[tuple[str, str]] = set()
    for fpath in CORPUS_DIR.rglob('*.yaml'):
        try:
            with open(fpath, encoding='utf-8') as f:
                doc = yaml.safe_load(f)
            if isinstance(doc, dict) and 'name' in doc:
                names.add(doc['name'])
                keys.add((doc['name'], doc.get('file') or ''))
        except (yaml.YAMLError, OSError):
            pass
    return names, keys


def ambiguous_names_in(universe: list[dict], universe_source: str) -> set[str]:
    """Display names carried by more than one declaration (notes#7, notes#120).

    Only the authoritative universe counts. `names-fallback.json` is a static text scan and
    is deliberately left un-refreshed, so it carries duplicates that are not real collisions
    — currently nine "ambiguous" names against the authoritative two. Trusting those would
    make the generator offer module-qualified skeletons for declarations that are actually
    unique, and their existing corpus entries (which correctly omit `file`) would stop being
    recognised as annotated, so saving either skeleton produces a duplicate annotation.

    `validate.py` takes the same position: `load_name_universe` returns an empty collision
    map on the fallback path. Diverging from that is what makes the two disagree.
    """
    if universe_source != 'decls.json':
        return set()
    counts: dict[str, int] = {}
    for decl in universe:
        counts[decl['name']] = counts.get(decl['name'], 0) + 1
    return {name for name, count in counts.items() if count > 1}


def is_annotated(decl: dict, annotated_names: set[str],
                 annotated_keys: set[tuple[str, str]],
                 ambiguous_names: set[str]) -> bool:
    """Whether THIS declaration already has an annotation.

    For an ambiguous display name the match must include the defining file — `file` is
    required on those corpus entries (notes#7), so the pair identifies the declaration.
    For an unambiguous name `file` is optional in the corpus, so the name alone decides.
    """
    name = decl['name']
    if name in ambiguous_names:
        return (name, decl.get('file', '')) in annotated_keys
    return name in annotated_names


def module_matches_chapter(file_path: str, chapter: str) -> bool:
    patterns = CHAPTER_MODULE_PATTERNS.get(chapter, [])
    if not patterns:
        return False
    for pat in patterns:
        if pat in file_path:
            return True
    return False


def module_matches_filter(file_path: str, module_filter: str) -> bool:
    # Convert Lean module name (dots) to path (slashes)
    as_path = module_filter.replace('.', '/')
    return as_path in file_path or file_path.endswith(as_path + '.lean')


def read_lean_snippet(lean_root: Path, file_path: str,
                      line_start: int, line_end: int | None,
                      context: int = 30) -> str:
    """Read lines from lean_root/file_path around line_start."""
    full_path = lean_root / file_path
    if not full_path.exists():
        return f'(source not found: {file_path})'
    try:
        lines = full_path.read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        return f'(could not read: {file_path})'

    # line_start is 1-indexed
    if not isinstance(line_start, int):
        return f'(no line info for: {file_path})'
    start = max(0, line_start - 1)
    if isinstance(line_end, int):
        # line_end is 1-indexed inclusive; convert to a 0-based inclusive index
        end = min(len(lines) - 1, line_end - 1)
    else:
        # Heuristic: read up to `context` lines or until next top-level declaration
        end = start
        decl_start_re = re.compile(
            r'^(?:@\[|private |protected |noncomputable |partial |unsafe )'
            r'*(?:theorem|lemma|def|structure|instance|abbrev|end\s|namespace\s)\b'
        )
        for i in range(start + 1, min(len(lines), start + context + 1)):
            if i > start + 2 and decl_start_re.match(lines[i]):
                break
            end = i

    snippet_lines = lines[start : end + 1]
    return '\n'.join(snippet_lines)


CORPUS_ROOT_NAMESPACE = 'LerayHopf'


def corpus_path_for(decl: dict, ambiguous_names: set[str] | None = None) -> str:
    """Where a new annotation for `decl` should be saved (notes#120).

    The corpus is FLAT — everything lives directly in `corpus/LerayHopf/`. This function
    used to emit `corpus/<module/path>/<simple-name>.yaml`, i.e. the nested layout
    `corpus/README.md` wrongly documented, which is how the drift kept regenerating itself:
    every work packet instructed its author to create a directory that does not exist.

    The slug is the declaration name minus the `LerayHopf.` root namespace. When the display
    name is ambiguous (the same `name` on more than one declaration, as happens for private
    helpers in different modules), a flat corpus cannot give both the same filename, so the
    slug is prefixed with the defining module path flattened onto dots.
    """
    name = decl['name']
    slug = name[len(CORPUS_ROOT_NAMESPACE) + 1:] if name.startswith(
        CORPUS_ROOT_NAMESPACE + '.') else name

    if ambiguous_names and name in ambiguous_names:
        module = decl.get('file', '').removesuffix('.lean')
        if module.startswith(CORPUS_ROOT_NAMESPACE + '/'):
            module = module[len(CORPUS_ROOT_NAMESPACE) + 1:]
        if module:
            slug = f"{module.replace('/', '.')}.{name.split('.')[-1]}"

    return f'corpus/{CORPUS_ROOT_NAMESPACE}/{slug}.yaml'


def yaml_skeleton(decl: dict, chapter: str, tier: str | None,
                  ambiguous_names: set[str] | None = None) -> str:
    name = decl['name']
    kind = decl.get('kind', 'theorem')
    if tier is None:
        tier = 'full' if kind in THEOREM_KINDS else 'gloss'

    corpus_path = corpus_path_for(decl, ambiguous_names)

    lines = [
        f'# Save to: {corpus_path}',
        f'name: {name}',
    ]
    # `validate.py` REQUIRES `file` when the display name is ambiguous (notes#7) — without
    # it the entry cannot say which of the same-named declarations it annotates, and fails
    # validation outright. Emitting the module-qualified path but leaving `file` for the
    # author to discover would hand them a skeleton that is invalid the moment it is saved.
    if ambiguous_names and name in ambiguous_names and decl.get('file'):
        lines.append(f'file: {decl["file"]}')
    lines += [
        f'tier: {tier}',
        'statement_ja: |',
        '  # TODO: 日本語で主張を記述',
    ]
    if tier == 'full' and kind in THEOREM_KINDS:
        lines += [
            'proof_ja: |',
            '  # TODO: 証明の日本語叙述（教科書調）',
        ]
    lines += [
        'gap:',
        '  level: none  # none | mild | large',
        '  # note: |  # level=large のとき必須（数学的な formalization gap の説明に限定；issue/PR/Codex 等は provenance へ）',
        '# provenance: |  # 任意。issue/PR 番号・Codex・campaign 等の開発プロセス履歴はここに書く（notes#69）',
        f'chapter: {chapter}',
        'tags: []',
    ]
    return '\n'.join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--chapter', metavar='CHAPTER',
                       help='Chapter id (e.g. capstone-r3)')
    group.add_argument('--module', metavar='MODULE',
                       help='Lean module path (e.g. LerayHopf.R3.GalerkinODECapstone)')
    group.add_argument('--all', action='store_true',
                       help='Emit all un-annotated declarations')
    parser.add_argument('--lean-root', default=str(DEFAULT_LEAN_ROOT),
                        help='Path to leray-hopf checkout')
    parser.add_argument('--limit', type=int, default=None,
                        help='Maximum number of declarations to emit')
    parser.add_argument('--tier', choices=['full', 'gloss'], default=None,
                        help='Override tier in YAML skeletons')
    parser.add_argument('--include-annotated', action='store_true',
                        help='Include already-annotated declarations')
    args = parser.parse_args()

    if not args.chapter and not args.module and not args.all:
        parser.error('Specify --chapter, --module, or --all')

    lean_root = Path(args.lean_root)
    universe, universe_source = load_universe()
    if not universe:
        sys.exit('ERROR: no name universe found. Run scripts/count_decls.py first.')

    if args.include_annotated:
        annotated_names, annotated_keys = set(), set()
    else:
        annotated_names, annotated_keys = load_annotated_names()
    chapter_label = args.chapter or args.module or 'all'

    ambiguous_names = ambiguous_names_in(universe, universe_source)

    # Filter universe
    candidates = []
    for decl in universe:
        name = decl['name']
        if not args.include_annotated and is_annotated(
                decl, annotated_names, annotated_keys, ambiguous_names):
            continue
        file_path = decl.get('file', '')
        if args.all:
            candidates.append(decl)
        elif args.chapter:
            if module_matches_chapter(file_path, args.chapter):
                candidates.append(decl)
        elif args.module:
            if module_matches_filter(file_path, args.module):
                candidates.append(decl)

    if args.limit:
        candidates = candidates[:args.limit]

    # Header
    print(f'# Work Packet: {chapter_label}')
    print()
    print(f'**Universe:** {universe_source}  ')
    print(f'**Declarations in packet:** {len(candidates)}  ')
    print(f'**Already annotated (skipped):** {len(annotated_names)}  ')
    print()
    print('For each declaration below: fill in the YAML skeleton and save it.')
    print('Validate with: `python3 scripts/validate.py`')
    print()
    print('---')
    print()

    for i, decl in enumerate(candidates, 1):
        name = decl['name']
        kind = decl.get('kind', '?')
        file_path = decl.get('file', '?')
        line = decl.get('startLine', decl.get('line', '?'))
        line_end = decl.get('endLine', decl.get('line_end'))

        print(f'## {i}. `{name}`')
        print()
        print(f'- **Kind:** `{kind}`')
        print(f'- **File:** `{file_path}:{line}`')

        # Extra metadata from decls.json
        if 'signature' in decl:
            print(f'- **Signature:**')
            print()
            print('  ```lean')
            print(indent(decl['signature'], '  '))
            print('  ```')
        if 'doc' in decl and decl['doc']:
            print(f'- **Doc:** {decl["doc"]}')
        if 'deps' in decl and decl['deps']:
            dep_list = ', '.join(f'`{d}`' for d in decl['deps'][:10])
            if len(decl['deps']) > 10:
                dep_list += f' … (+{len(decl["deps"]) - 10} more)'
            print(f'- **Deps:** {dep_list}')

        print()

        # Lean source snippet
        snippet = read_lean_snippet(lean_root, file_path, line, line_end)
        print('### Lean source')
        print()
        print('```lean')
        print(snippet)
        print('```')
        print()

        # YAML skeleton
        print('### YAML skeleton')
        print()
        print('```yaml')
        print(yaml_skeleton(decl, chapter_label, args.tier, ambiguous_names))
        print('```')
        print()
        print('---')
        print()


if __name__ == '__main__':
    main()
