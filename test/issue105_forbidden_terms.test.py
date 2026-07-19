#!/usr/bin/env python3
"""Regression checks for notes#105: the forbidden-translation lint (証人/目撃者 etc.)
must actually fail CI on reintroduction, must cover gap.note/provenance/tags (not just
statement_ja/proof_ja), and must respect the two allowlist escape hatches (backtick
quoting, scripts/glossary_lint_allowlist.json) without silently swallowing everything."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def import_script(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_glossary(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# GLOSSARY\n\n"
        "| English term | 日本語訳 | Lean 識別子例 | 備考 | forbidden |\n"
        "|---|---|---|---|---|\n"
        "| witness | （文脈に応じて直接記述） | | | 「証人」、「目撃者」 |\n",
        encoding="utf-8",
    )


def write_corpus(path: Path, *, statement: str = "", proof: str = "",
                  gap_note: str = "", provenance: str = "",
                  tags: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["name: LerayHopf.dummy", "tier: full", f"statement_ja: |\n  {statement or '文。'}"]
    if proof:
        lines.append(f"proof_ja: |\n  {proof}")
    lines.append("gap:")
    lines.append("  level: mild" if gap_note else "  level: none")
    if gap_note:
        lines.append(f"  note: |\n    {gap_note}")
    if provenance:
        lines.append(f"provenance: |\n  {provenance}")
    lines.append("chapter: misc")
    if tags:
        lines.append("tags: [" + ", ".join(tags) + "]")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_main(module, argv: list[str]) -> tuple[int, str]:
    old_argv = sys.argv[:]
    sys.argv = [str(module.__file__), *argv]
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            try:
                module.main()
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
            else:
                code = 0
    finally:
        sys.argv = old_argv
    return code, out.getvalue()


def load_module(root: Path):
    mod = import_script(f"glossary_lint_{id(root)}", REPO_ROOT / "scripts" / "glossary_lint.py")
    mod.REPO_ROOT = root
    mod.GLOSSARY_PATH = root / "docs" / "GLOSSARY.md"
    mod.CORPUS_DIR = root / "corpus"
    mod.ALLOWLIST_PATH = root / "scripts" / "glossary_lint_allowlist.json"
    return mod


def test_forbidden_term_in_statement_ja_fails_without_strict() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        write_glossary(root / "docs" / "GLOSSARY.md")
        write_corpus(root / "corpus" / "a.yaml", statement="非自明性の目撃者定理。")
        mod = load_module(root)

        code, output = run_main(mod, [])  # no --strict
        assert code == 1, output
        assert "目撃者" in output


def test_forbidden_term_in_gap_note_is_caught() -> None:
    """The pre-notes#105 version of this script only scanned statement_ja/proof_ja;
    most of the notes#105 findings lived in gap.note, so this is the regression this
    fix specifically closes."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        write_glossary(root / "docs" / "GLOSSARY.md")
        write_corpus(root / "corpus" / "a.yaml", statement="文。",
                     gap_note="独立な目撃者定理として形式化されていない。")
        mod = load_module(root)

        code, output = run_main(mod, [])
        assert code == 1, output
        assert "目撃者" in output


def test_forbidden_term_in_provenance_and_tags_is_caught() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        write_glossary(root / "docs" / "GLOSSARY.md")
        write_corpus(root / "corpus" / "a.yaml", statement="文。",
                     provenance="かつて証人と呼ばれていた。")
        mod = load_module(root)
        code, output = run_main(mod, [])
        assert code == 1, output
        assert "証人" in output


def test_backtick_quoted_forbidden_term_is_exempt() -> None:
    """Meta-discussion / quoting the literal old string (e.g. explaining a fix)
    must stay legal per notes#105's allowlist requirement."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        write_glossary(root / "docs" / "GLOSSARY.md")
        write_corpus(root / "corpus" / "a.yaml", statement="文。",
                     gap_note="旧訳「`目撃者`」は禁止語である。")
        mod = load_module(root)
        code, output = run_main(mod, [])
        assert code == 0, output


def test_explicit_allowlist_entry_exempts_specific_file_and_term() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        write_glossary(root / "docs" / "GLOSSARY.md")
        write_corpus(root / "corpus" / "a.yaml", statement="文。",
                     gap_note="目撃者について論じる。")
        allowlist_path = root / "scripts" / "glossary_lint_allowlist.json"
        allowlist_path.parent.mkdir(parents=True, exist_ok=True)
        allowlist_path.write_text(
            json.dumps({"allow": {"corpus/a.yaml": ["目撃者"]}}, ensure_ascii=False),
            encoding="utf-8",
        )
        mod = load_module(root)
        code, output = run_main(mod, [])
        assert code == 0, output

        # sanity: the allowlist is per-file — a different file with the same term
        # still fails, so the escape hatch can't accidentally blanket-exempt a term.
        write_corpus(root / "corpus" / "b.yaml", statement="文。",
                     gap_note="別の目撃者について論じる。")
        code2, output2 = run_main(mod, [])
        assert code2 == 1, output2
        assert "corpus/b.yaml" in output2 and "corpus/a.yaml" not in output2


def test_witness_fused_to_japanese_noun_is_caught() -> None:
    """rev-108 finding: raw English "witness" fused directly onto a Japanese noun
    (e.g. "witness 一致計算則", "component-witness 形") is the same hybrid-coinage
    problem as well-定義性, just with a different English root -- must be a hard
    error, not silently passed through by the term-substitution table."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        write_glossary(root / "docs" / "GLOSSARY.md")
        write_corpus(root / "corpus" / "a.yaml", statement="文。",
                     proof="三つの汎関数を[[witness 一致計算則|LerayHopf.foo_eq_witness]]で書き換える。")
        mod = load_module(root)
        code, output = run_main(mod, [])
        assert code == 1, output
        assert "witness" in output.lower()


def test_witness_fusion_check_does_not_flag_wikilink_target_identifiers() -> None:
    """A [[display|LerayHopf.foo_witness]] wikilink *target* is a Lean identifier,
    not translated prose -- it must not trip the fusion check just because the
    identifier itself contains "witness" (e.g. convFormSchwartz_eq_witness)."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        write_glossary(root / "docs" / "GLOSSARY.md")
        write_corpus(root / "corpus" / "a.yaml", statement="文。",
                     proof="これを[[表示一致計算則|LerayHopf.convFormSchwartz_eq_witness]]で書き換える。")
        mod = load_module(root)
        code, output = run_main(mod, [])
        assert code == 0, output


def test_witness_fusion_allowlist_entry_exempts() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        write_glossary(root / "docs" / "GLOSSARY.md")
        write_corpus(root / "corpus" / "a.yaml", statement="文。",
                     proof="[[witness 形|LerayHopf.foo]]で書き換える。")
        allowlist_path = root / "scripts" / "glossary_lint_allowlist.json"
        allowlist_path.parent.mkdir(parents=True, exist_ok=True)
        allowlist_path.write_text(
            json.dumps({"allow": {"corpus/a.yaml": ["witness-fusion"]}}, ensure_ascii=False),
            encoding="utf-8",
        )
        mod = load_module(root)
        code, output = run_main(mod, [])
        assert code == 0, output


def test_relative_corpus_path_does_not_crash() -> None:
    """codex (PR #108 review on scripts/glossary_lint.py:168): a relative --corpus
    path (the exact form documented in the script's own usage examples,
    `--corpus corpus/LerayHopf/`) previously crashed with ValueError from
    Path.relative_to(), because rglob() on a relative corpus_root yields relative
    `fpath`s while REPO_ROOT is absolute. The default (no --corpus) invocation never
    exercised this, since CORPUS_DIR is already absolute -- hence it was invisible
    in CI, which always uses the default."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        write_glossary(root / "docs" / "GLOSSARY.md")
        write_corpus(root / "corpus" / "a.yaml", statement="正常な文。")
        mod = load_module(root)

        old_cwd = Path.cwd()
        try:
            os.chdir(root)
            code, output = run_main(mod, ["--corpus", "corpus"])
        finally:
            os.chdir(old_cwd)
        assert code == 0, output
        assert "no glossary violations" in output


def test_clean_corpus_passes() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        write_glossary(root / "docs" / "GLOSSARY.md")
        write_corpus(root / "corpus" / "a.yaml",
                     statement="\\(b\\neq 0\\) を直接示す定理。",
                     gap_note="条件を満たす具体的な対象を与える。")
        mod = load_module(root)
        code, output = run_main(mod, [])
        assert code == 0, output
        assert "no glossary violations" in output


def main() -> None:
    tests = [
        test_forbidden_term_in_statement_ja_fails_without_strict,
        test_forbidden_term_in_gap_note_is_caught,
        test_forbidden_term_in_provenance_and_tags_is_caught,
        test_backtick_quoted_forbidden_term_is_exempt,
        test_explicit_allowlist_entry_exempts_specific_file_and_term,
        test_witness_fused_to_japanese_noun_is_caught,
        test_witness_fusion_check_does_not_flag_wikilink_target_identifiers,
        test_witness_fusion_allowlist_entry_exempts,
        test_relative_corpus_path_does_not_crash,
        test_clean_corpus_passes,
    ]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\nAll {len(tests)} notes#105 forbidden-term lint checks passed.")


if __name__ == "__main__":
    main()
