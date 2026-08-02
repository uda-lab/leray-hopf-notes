#!/usr/bin/env python3
"""Regression checks for notes#120 `validate.py` filename-vs-`name` consistency.

`corpus/README.md` documented a nested `corpus/<module-path>/<decl-name>.yaml` layout that
the corpus never had, and the drift survived because nothing looked at filenames at all.
`check_filename_matches_name` closes that hole as far as it can be closed.

It deliberately checks only the **last dot-component** of the filename. Two slug conventions
coexist in this corpus — the plain one (`name` minus the `LerayHopf.` prefix) and a
module-qualified one, which is *required* when two declarations share a display name because
a flat corpus cannot give them the same filename. Full equality would mean renaming every
file of the second kind; the final component is the invariant both conventions share.

Covers: the matching case, a mismatched final component, the module-qualified collision
convention, names carrying an apostrophe (`continuous_restrictToBall'` really exists), a
missing/non-string `name` (must not crash or double-report), and the committed corpus.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit('ERROR: PyYAML required. pip install pyyaml')


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATE_PATH = REPO_ROOT / 'scripts' / 'validate.py'

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


def import_script(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_corpus(path: Path, name: str | None, file: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = []
    if name is not None:
        fields.append(f'name: {name}')
    if file is not None:
        fields.append(f'file: {file}')
    fields.extend([
        'tier: gloss',
        'statement_ja: 主張。',
        'gap:',
        '  level: none',
        'chapter: misc',
    ])
    path.write_text('\n'.join(fields) + '\n', encoding='utf-8')


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def decl(id_: str, name: str, file: str, private: bool = False) -> dict:
    return {
        'id': id_, 'name': name, 'kind': 'theorem', 'private': private,
        'signature': '', 'doc': '', 'file': file,
        'startLine': 1, 'endLine': 1, 'deps': [],
    }


def run_main(module, argv: list[str]) -> tuple[int, str]:
    old_argv = sys.argv[:]
    sys.argv = [str(module.__file__), *argv]
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            try:
                module.main()
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 1
            else:
                code = 0
    finally:
        sys.argv = old_argv
    return code, out.getvalue()


def patch_validate(module, root: Path) -> None:
    module.REPO_ROOT = root
    module.CORPUS_DIR = root / 'corpus'
    module.EXTRACTED_DIR = root / 'extracted'
    module.SCHEMA_PATH = REPO_ROOT / 'docs' / 'schemas' / 'corpus.schema.json'


def run_validate_on(files: dict[str, str | None], decls: list[dict]) -> tuple[int, str]:
    """Run validate.py over a temp corpus of {filename: name-field} against `decls`."""
    module = import_script('validate_issue120', VALIDATE_PATH)
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        patch_validate(module, root)
        write_json(root / 'extracted' / 'decls.json', decls)
        (root / 'extracted' / 'PIN').write_text('a' * 40 + '\n', encoding='utf-8')
        for fname, name in files.items():
            write_corpus(root / 'corpus' / fname, name)
        return run_main(module, [])


def test_matching_filename_passes() -> None:
    code, out = run_validate_on(
        {'rellich_seq_compact.yaml': 'LerayHopf.rellich_seq_compact'},
        [decl('LerayHopf.rellich_seq_compact', 'LerayHopf.rellich_seq_compact', 'A.lean')],
    )
    check('matching filename passes', code == 0, out)


def test_mismatched_final_component_fails() -> None:
    code, out = run_validate_on(
        {'rellich_seq_compakt.yaml': 'LerayHopf.rellich_seq_compact'},
        [decl('LerayHopf.rellich_seq_compact', 'LerayHopf.rellich_seq_compact', 'A.lean')],
    )
    check('typo in filename fails', code == 1, out)
    check(
        'error names both the filename component and the expected simple name',
        'rellich_seq_compakt' in out and 'rellich_seq_compact' in out,
        out,
    )


def test_module_qualified_filename_passes() -> None:
    """The collision convention: prefix with the defining module, keep the simple name last."""
    code, out = run_validate_on(
        {
            'Bochner.StepFunctionCompactness.measurable_natFloor_real.yaml':
                'LerayHopf.measurable_natFloor_real',
        },
        [decl('_private.0.LerayHopf.measurable_natFloor_real',
              'LerayHopf.measurable_natFloor_real', 'A.lean', private=True)],
    )
    check('module-qualified filename passes', code == 0, out)


def test_suffix_disambiguation_is_rejected() -> None:
    """Suffixing spells a declaration that does not exist; prefixing is the convention."""
    code, out = run_validate_on(
        {'measurable_natFloor_real_a.yaml': 'LerayHopf.measurable_natFloor_real'},
        [decl('LerayHopf.measurable_natFloor_real',
              'LerayHopf.measurable_natFloor_real', 'A.lean')],
    )
    check('suffix-disambiguated filename is rejected', code == 1, out)


def test_apostrophe_in_name() -> None:
    """`continuous_restrictToBall'` is a real declaration; the apostrophe must survive."""
    code, out = run_validate_on(
        {"R3.ArzelaAscoliTime.continuous_restrictToBall'.yaml":
            "LerayHopf.continuous_restrictToBall'"},
        [decl("LerayHopf.continuous_restrictToBall'",
              "LerayHopf.continuous_restrictToBall'", 'A.lean')],
    )
    check('apostrophe in declaration name is handled', code == 0, out)


def test_ambiguous_name_requires_correct_module_prefix() -> None:
    """For a colliding display name the whole slug is checked: a wrong module prefix points
    the reader at the wrong declaration, so the final component alone is not enough."""
    module = import_script('validate_issue120_amb', VALIDATE_PATH)
    collisions = {'LerayHopf.measurable_natFloor_real': {
        'LerayHopf/Bochner/StepFunctionCompactness.lean',
        'LerayHopf/R3/SpacetimePrecompact.lean',
    }}
    doc = {'name': 'LerayHopf.measurable_natFloor_real',
           'file': 'LerayHopf/R3/SpacetimePrecompact.lean'}

    good = Path('corpus/LerayHopf/R3.SpacetimePrecompact.measurable_natFloor_real.yaml')
    check('correct module prefix accepted',
          module.check_filename_matches_name(doc, good, collisions) == [])

    wrong = Path('corpus/LerayHopf/R3.WrongModule.measurable_natFloor_real.yaml')
    errs = module.check_filename_matches_name(doc, wrong, collisions)
    check('wrong module prefix rejected', len(errs) == 1, repr(errs))
    check('error names the expected slug',
          'R3.SpacetimePrecompact.measurable_natFloor_real.yaml' in (errs[0] if errs else ''),
          repr(errs))

    bare = Path('corpus/LerayHopf/measurable_natFloor_real.yaml')
    check('unqualified filename rejected for an ambiguous name',
          len(module.check_filename_matches_name(doc, bare, collisions)) == 1)

    # An unambiguous name must NOT be held to the module-prefix rule.
    plain_doc = {'name': 'LerayHopf.rellich_seq_compact'}
    plain = Path('corpus/LerayHopf/rellich_seq_compact.yaml')
    check('unambiguous name is not forced to carry a module prefix',
          module.check_filename_matches_name(plain_doc, plain, collisions) == [])


def test_workpacket_generates_flat_paths() -> None:
    """The generator is what taught the nested layout to every contributor, so its output
    is pinned here too (notes#120)."""
    wp = import_script('workpacket_issue120', REPO_ROOT / 'scripts' / 'workpacket.py')
    d = decl('LerayHopf.rellich_seq_compact', 'LerayHopf.rellich_seq_compact',
             'LerayHopf/Torus/RellichEmbedding.lean')
    path = wp.corpus_path_for(d, set())
    check('generated path is a direct child of corpus/LerayHopf/',
          path == 'corpus/LerayHopf/rellich_seq_compact.yaml', path)
    check('generated path has no nested directories',
          path.count('/') == 2, path)

    namespaced = decl('LerayHopf.Bochner.GelfandTriple', 'LerayHopf.Bochner.GelfandTriple',
                      'LerayHopf/Bochner/GelfandTriple.lean')
    check('namespace is kept in the slug, not turned into a directory',
          wp.corpus_path_for(namespaced, set()) ==
          'corpus/LerayHopf/Bochner.GelfandTriple.yaml',
          wp.corpus_path_for(namespaced, set()))

    ambiguous = decl('_private.0.LerayHopf.measurable_natFloor_real',
                     'LerayHopf.measurable_natFloor_real',
                     'LerayHopf/R3/SpacetimePrecompact.lean', private=True)
    generated = wp.corpus_path_for(ambiguous, {'LerayHopf.measurable_natFloor_real'})
    check('ambiguous name gets the module-qualified slug',
          generated ==
          'corpus/LerayHopf/R3.SpacetimePrecompact.measurable_natFloor_real.yaml',
          generated)
    check('generated collision path matches a file that really exists',
          (REPO_ROOT / generated).exists(), generated)

    # An ambiguous skeleton must carry `file`, which validate.py requires for colliding
    # names — otherwise saving the skeleton as instructed yields an invalid entry.
    skeleton = wp.yaml_skeleton(ambiguous, 'compactness', 'gloss',
                                {'LerayHopf.measurable_natFloor_real'})
    check('ambiguous skeleton emits the file field',
          'file: LerayHopf/R3/SpacetimePrecompact.lean' in skeleton, skeleton)
    plain_skeleton = wp.yaml_skeleton(d, 'compactness', 'gloss', set())
    check('unambiguous skeleton does not emit a file field',
          '\nfile:' not in plain_skeleton, plain_skeleton)


def test_generated_ambiguous_skeleton_validates() -> None:
    """End-to-end: save what the generator prints for a colliding name, and validate it."""
    wp = import_script('workpacket_issue120_e2e', REPO_ROOT / 'scripts' / 'workpacket.py')
    ambiguous = decl('_private.0.LerayHopf.measurable_natFloor_real',
                     'LerayHopf.measurable_natFloor_real',
                     'LerayHopf/R3/SpacetimePrecompact.lean', private=True)
    other = decl('_private.1.LerayHopf.measurable_natFloor_real',
                 'LerayHopf.measurable_natFloor_real',
                 'LerayHopf/Bochner/StepFunctionCompactness.lean', private=True)
    amb = {'LerayHopf.measurable_natFloor_real'}

    skeleton = wp.yaml_skeleton(ambiguous, 'compactness', 'gloss', amb)
    body = '\n'.join(line for line in skeleton.splitlines()
                     if not line.startswith('# Save to:'))
    body = body.replace('# TODO: 日本語で主張を記述', '主張。')
    rel = wp.corpus_path_for(ambiguous, amb)

    module = import_script('validate_issue120_e2e', VALIDATE_PATH)
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        patch_validate(module, root)
        write_json(root / 'extracted' / 'decls.json', [ambiguous, other])
        (root / 'extracted' / 'PIN').write_text('a' * 40 + '\n', encoding='utf-8')
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body + '\n', encoding='utf-8')
        code, out = run_main(module, [])
    check('generated ambiguous skeleton validates as saved', code == 0, out)


def test_missing_name_does_not_crash() -> None:
    """A missing `name` is already a schema error — the filename check must not add noise
    on top of it, and must not raise."""
    module = import_script('validate_issue120_missing', VALIDATE_PATH)
    errs = module.check_filename_matches_name({}, Path('corpus/LerayHopf/whatever.yaml'))
    check('missing name yields no filename error', errs == [], repr(errs))
    errs = module.check_filename_matches_name(
        {'name': 123}, Path('corpus/LerayHopf/whatever.yaml'))
    check('non-string name yields no filename error', errs == [], repr(errs))


def test_committed_corpus_is_clean() -> None:
    module = import_script('validate_issue120_real', VALIDATE_PATH)
    violations = []
    for fpath in sorted((REPO_ROOT / 'corpus').rglob('*.yaml')):
        doc = yaml.safe_load(fpath.read_text(encoding='utf-8'))
        if isinstance(doc, dict):
            violations.extend(module.check_filename_matches_name(doc, fpath))
    check('committed corpus has no filename violations', not violations,
          '\n       '.join(violations[:5]))


def main() -> None:
    test_matching_filename_passes()
    test_mismatched_final_component_fails()
    test_module_qualified_filename_passes()
    test_suffix_disambiguation_is_rejected()
    test_apostrophe_in_name()
    test_ambiguous_name_requires_correct_module_prefix()
    test_workpacket_generates_flat_paths()
    test_generated_ambiguous_skeleton_validates()
    test_missing_name_does_not_crash()
    test_committed_corpus_is_clean()
    print(f'\nAll {len(CHECKS)} notes#120 filename-check tests passed.')


if __name__ == '__main__':
    main()
