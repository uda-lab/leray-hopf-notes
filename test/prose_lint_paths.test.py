#!/usr/bin/env python3
"""Regression checks for notes#128 scripts/prose_lint.py --corpus path handling.

Before the fix, `lint_doc` and the parse-error branch of `main` called
`fpath.relative_to(REPO_ROOT)` on the raw path built from `--corpus`. With a relative
`--corpus` that raised `ValueError`, so the linter crashed on any input it had something
to report about — and a clean subtree passed, which is why it stayed hidden. The same
call also crashed for an absolute `--corpus` pointing outside the repo.

Covers: relative and absolute `--corpus` with a hard finding, an out-of-repo `--corpus`,
the YAML parse-error branch (the second crash site), a symlink loop (which made the first
fix's `resolve()` raise `RuntimeError` — the same "formatting a path aborts the run" shape
as the original bug), and the clean-subtree exit-0 path.

Two kinds of check live here, and they fail for different reasons:

* **Regression checks** — relative `--corpus`, out-of-repo `--corpus`, the parse-error
  branch, and the symlink loop. These fail against the pre-fix script.
* **Compatibility checks** — absolute in-repo `--corpus`, the clean subtree, and the
  missing directory. These pass both before and after the fix on purpose: they pin the
  behaviour the fix must not disturb.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "prose_lint.py"

# A heading is a D5 hard error, so any corpus containing this file has >= 1 finding and
# therefore reaches the formatting code that used to crash.
FINDING_YAML = """\
name: LerayHopf.demo
tier: gloss
statement_ja: |
  # 見出しは D5 のハードエラー
gap:
  level: none
"""

CLEAN_YAML = """\
name: LerayHopf.demo
tier: gloss
statement_ja: |
  有界な族は全有界である。
gap:
  level: none
"""

# Unterminated flow sequence -> yaml.YAMLError, reaching the parse-error branch.
UNPARSEABLE_YAML = "name: [unclosed\n"


def import_script(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_main(module, argv: list[str]) -> tuple[int, str]:
    """Run the linter's main() with argv, returning (exit_code, combined output).

    The notes#128 crashes escape main() as exceptions rather than exit codes: ValueError
    from `relative_to`, and RuntimeError/OSError from `resolve()` on a symlink loop. They
    are caught here and turned into a distinct exit code so the check that expects them
    to be gone reports a readable FAIL, instead of the crash killing the test run itself.
    The catch is deliberately limited to that family — anything else still propagates.
    """
    old_argv = sys.argv[:]
    sys.argv = [str(module.__file__), *argv]
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            try:
                module.main()
            except SystemExit as exc:
                if isinstance(exc.code, int):
                    code = exc.code
                else:
                    # `sys.exit("message")` carries the text on the exception and exits 1;
                    # the interpreter would print it, but we catch it first, so fold it
                    # into the captured output the checks read.
                    out.write(f"\n{exc.code}")
                    code = 1
            except (ValueError, RuntimeError, OSError) as exc:
                out.write(f"\nCRASHED with {type(exc).__name__}: {exc}")
                code = -1
            else:
                code = 0
    finally:
        sys.argv = old_argv
    return code, out.getvalue()


@contextlib.contextmanager
def chdir(path: Path):
    prev = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev)


def write_corpus(root: Path, name: str, body: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(body, encoding="utf-8")


CHECKS: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    CHECKS.append(label)
    if cond:
        print(f"  ok  {label}")
    else:
        print(f"  FAIL {label}")
        if detail:
            print(f"       {detail}")
        sys.exit(1)


def test_relative_corpus_with_finding(module) -> None:
    """The notes#128 headline case: relative --corpus, inside the repo, with a finding."""
    with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tmp:
        sub = Path(tmp) / "sub"
        write_corpus(sub, "bad.yaml", FINDING_YAML)
        rel = Path(tmp).name + "/sub"
        with chdir(REPO_ROOT):
            code, out = run_main(module, ["--corpus", rel])
    check("relative --corpus with a finding does not crash", code == 1, out)
    check("relative --corpus reports the D5 heading finding", "見出し記法は非対応" in out, out)
    check(
        "relative --corpus labels the file repo-relatively",
        f"{rel}/bad.yaml" in out,
        out,
    )


def test_absolute_corpus_inside_repo_with_finding(module) -> None:
    """The path shape that already worked — it must keep working, and keep its label."""
    with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tmp:
        sub = Path(tmp) / "sub"
        write_corpus(sub, "bad.yaml", FINDING_YAML)
        code, out = run_main(module, ["--corpus", str(sub)])
        rel = sub.relative_to(REPO_ROOT)
    check("absolute in-repo --corpus with a finding does not crash", code == 1, out)
    check(
        "absolute in-repo --corpus still labels the file repo-relatively",
        f"{rel}/bad.yaml" in out,
        out,
    )


def test_absolute_corpus_outside_repo_with_finding(module) -> None:
    """Outside the repo there is no repo-relative label, so the absolute path is shown."""
    with tempfile.TemporaryDirectory() as tmp:
        sub = Path(tmp).resolve() / "sub"
        write_corpus(sub, "bad.yaml", FINDING_YAML)
        code, out = run_main(module, ["--corpus", str(sub)])
    check("out-of-repo --corpus with a finding does not crash", code == 1, out)
    check(
        "out-of-repo --corpus falls back to the absolute path",
        f"{sub}/bad.yaml" in out,
        out,
    )


def test_relative_corpus_with_parse_error(module) -> None:
    """The second crash site: the parse-error branch formats a path the same way."""
    with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tmp:
        sub = Path(tmp) / "sub"
        write_corpus(sub, "broken.yaml", UNPARSEABLE_YAML)
        rel = Path(tmp).name + "/sub"
        with chdir(REPO_ROOT):
            code, out = run_main(module, ["--corpus", rel])
    check("relative --corpus with an unparseable YAML does not crash", code == 1, out)
    check("relative --corpus reports the parse error", "parse error" in out, out)


def test_symlink_loop(module) -> None:
    """A looping symlink makes `Path.resolve()` raise RuntimeError, so the first fix for
    notes#128 traded the original ValueError for a narrower crash. Path formatting has to
    be total: the loop must surface as a reported parse error, not an aborted run."""
    with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tmp:
        sub = Path(tmp) / "sub"
        sub.mkdir(parents=True)
        (sub / "loop.yaml").symlink_to("loop.yaml")
        rel = Path(tmp).name + "/sub"
        with chdir(REPO_ROOT):
            code, out = run_main(module, ["--corpus", rel])
    check("symlink loop under a relative --corpus does not crash", code == 1, out)
    check("symlink loop is reported as a parse error", "parse error" in out, out)
    check(
        "symlink loop still gets a repo-relative label",
        f"{rel}/loop.yaml" in out,
        out,
    )


def test_relative_corpus_clean_subtree(module) -> None:
    """A clean subtree exits 0 under both --strict and plain mode (the pre-fix behaviour
    that masked the bug — it must not regress into a spurious failure)."""
    with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tmp:
        sub = Path(tmp) / "sub"
        write_corpus(sub, "clean.yaml", CLEAN_YAML)
        rel = Path(tmp).name + "/sub"
        with chdir(REPO_ROOT):
            code, out = run_main(module, ["--corpus", rel])
            code_strict, out_strict = run_main(module, ["--corpus", rel, "--strict"])
    check("relative --corpus on a clean subtree exits 0", code == 0, out)
    check("relative --corpus on a clean subtree exits 0 under --strict", code_strict == 0,
          out_strict)


def test_missing_corpus_dir_still_errors(module) -> None:
    """A nonexistent --corpus must still be rejected, not resolved into existence."""
    with chdir(REPO_ROOT):
        code, out = run_main(module, ["--corpus", "no/such/subtree"])
    check("nonexistent --corpus exits nonzero", code == 1, out)
    check("nonexistent --corpus says the directory was not found",
          "corpus directory not found" in out, out)


def main() -> None:
    module = import_script("prose_lint", SCRIPT_PATH)
    test_relative_corpus_with_finding(module)
    test_absolute_corpus_inside_repo_with_finding(module)
    test_absolute_corpus_outside_repo_with_finding(module)
    test_relative_corpus_with_parse_error(module)
    test_symlink_loop(module)
    test_relative_corpus_clean_subtree(module)
    test_missing_corpus_dir_still_errors(module)
    print(f"\nAll {len(CHECKS)} notes#128 prose_lint path checks passed.")


if __name__ == "__main__":
    main()
