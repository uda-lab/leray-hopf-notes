#!/usr/bin/env python3
"""Regression checks for notes#32 payload hardening — the leak scan and the build
provenance record.

Both scripts are gates: they exist to refuse a bad payload. A gate that cannot fail is
worse than no gate, so most of what is checked here is that they *do* fail on planted
defects, and — equally important — that they do **not** fail on the real payload's
legitimate content.

The false-positive half is not hypothetical. The corpus is full of mathematical prose that
naive leak rules mistake for paths: a `[A-Za-z]:\\\\` "Windows drive" rule matches
`$f:\\mathbb R$`, `$\\varphi:\\mathbb N$` and `$\\int\\nabla u:\\nabla u$` — six hits in the
real payload, every one legitimate. Likewise the corpus deliberately cites review rounds
and issue numbers, so a scan for "agent prose" in the loose sense would fail every build on
content the owner has already approved for publication. Those cases are pinned below.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCAN = REPO_ROOT / 'scripts' / 'scan_generated_payload.py'
EMIT = REPO_ROOT / 'scripts' / 'emit_build_provenance.py'

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


def run(script: Path, *args: str) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, str(script), *args],
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def make_payload(root: Path, *, pin: str = 'a' * 40, extra_prose: str | None = None,
                 node_file: str = 'LerayHopf/R3/Foo.lean') -> Path:
    """A minimal but structurally faithful site/data directory."""
    data = root / 'site' / 'data'
    data.mkdir(parents=True, exist_ok=True)
    node = {
        'slug': 'LerayHopf.foo', 'name': 'LerayHopf.foo', 'file': node_file,
        'startLine': 1, 'endLine': 2, 'has_source': True,
        'corpus': {'statement_ja': extra_prose or '主張。'},
    }
    nodes = {
        'pin': pin, 'built_at': '2026-08-02T00:00:00Z',
        'universe_source': 'extracted/decls.json',
        'decl_count': 1, 'annotated_count': 1, 'source_count': 1, 'has_source': True,
        'proof_status_counts': {'verified': 1},
        'source_payload': 'sources.json', 'nodes': [node],
    }
    (data / 'nodes.json').write_text(json.dumps(nodes, ensure_ascii=False), encoding='utf-8')
    (data / 'sources.json').write_text(
        json.dumps({'pin': pin, 'source_count': 1,
                    'sources': {'LerayHopf.foo': 'theorem foo : True := trivial'}},
                   ensure_ascii=False), encoding='utf-8')
    (data / 'coverage.json').write_text(json.dumps({'annotated': 1, 'total': 1}),
                                        encoding='utf-8')
    (root / 'extracted').mkdir(parents=True, exist_ok=True)
    (root / 'extracted' / 'PIN').write_text(pin, encoding='utf-8')
    return data


# --------------------------------------------------------------------------- scan

LEAK_PROBES = {
    'GitHub token': 'ghp_' + 'A' * 30,
    'OpenAI key': 'sk-' + 'B' * 32,
    'AWS key id': 'AKIA' + 'C' * 16,
    'PEM private key': '-----BEGIN RSA PRIVATE KEY-----',
    'home path': '/home/vscode/notes/secret.md',
    'workspace path': '/workspaces/leray-hopf-notes/local',
    'tmp path': '/tmp/claude-1000/transcript.jsonl',
    'assistant session URL': 'https://claude.ai/code/session_016UU',
    'agent config dir': '/home/x/.claude/projects/foo',
    'credential assignment': 'api_key: "' + 'D' * 20 + '"',
    'Windows path': r'C:\Users\bob\notes',
    'JWT': 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.' + 'x' * 43,
    'credentials in URL': 'postgres://user:pw@db.internal:5432/app',
    'HTTP basic auth in URL': 'https://bob:hunter2@example.com/x',
    'email address': 'someone@example.com',
    'internal .local host': 'https://internal.uda-lab.local:8443/admin',
    'private IPv4': 'reachable at 10.0.0.5 from the runner',
}

# Shapes the scan knowingly does NOT catch. Pinned so the documented limits stay honest:
# if a future pattern starts catching one of these, the docstring must stop disclaiming it.
DOCUMENTED_LIMITS = {
    'base64-encoded credential': 'dXNlcjpzdXBlcnNlY3JldHBhc3N3b3JkMTIz',
    'SSH key body without header': 'AAAAB3NzaC1yc2EAAAADAQABAAABgQ' + 'C' * 40,
}

# Content that MUST NOT trip the scan — all of it really appears in this corpus.
LEGITIMATE_PROBES = {
    'LaTeX function type': r'$f:\mathbb R\to H$ が連続である。',
    'LaTeX index map': r'狭義単調な $\varphi:\mathbb N\to\mathbb N$ をとる。',
    'LaTeX viscous pairing': r'$\int\nabla u:\nabla u$ は $H^1$ の外では発散する。',
    'review-round prose': 'Codex Gate round 3 の指摘で修正した設計記録。',
    'the word password': 'password という語を含む一般的な散文。',
    'issue citation': 'leray-hopf issue #229（PR #231）で二段階に修正された。',
}


def test_scan_accepts_clean_payload() -> None:
    with tempfile.TemporaryDirectory() as td:
        data = make_payload(Path(td))
        code, out = run(SCAN, '--site-data', str(data))
    check('scan accepts a clean payload', code == 0, out)


def test_scan_detects_leaks() -> None:
    for label, payload in LEAK_PROBES.items():
        with tempfile.TemporaryDirectory() as td:
            data = make_payload(Path(td), extra_prose=f'説明。{payload}')
            code, _ = run(SCAN, '--site-data', str(data))
        check(f'scan detects planted leak: {label}', code != 0)


def test_scan_ignores_legitimate_content() -> None:
    for label, payload in LEGITIMATE_PROBES.items():
        with tempfile.TemporaryDirectory() as td:
            data = make_payload(Path(td), extra_prose=payload)
            code, out = run(SCAN, '--site-data', str(data))
        check(f'scan does NOT fire on legitimate content: {label}', code == 0, out)


def test_documented_limits_stay_documented() -> None:
    """The docstring disclaims these shapes; pin that so the disclaimer stays truthful.

    If a future pattern starts catching one of them, this check fails and forces the
    docstring to be updated — the disclaimer is part of the contract, not a hedge.
    """
    for label, payload in DOCUMENTED_LIMITS.items():
        with tempfile.TemporaryDirectory() as td:
            data = make_payload(Path(td), extra_prose=f'説明。{payload}')
            code, _ = run(SCAN, '--site-data', str(data))
        check(f'documented limit still applies (not caught): {label}', code == 0)


def test_scan_rejects_scaffold_source() -> None:
    with tempfile.TemporaryDirectory() as td:
        data = make_payload(Path(td), node_file='LerayHopf/Scratch/R3ShapeGate.lean')
        code, out = run(SCAN, '--site-data', str(data))
    check('scan rejects a declaration sourced from a Scratch/ module', code != 0, out)
    check('scaffold failure names the offending module', 'Scratch' in out, out)


def test_scan_requires_core_payloads() -> None:
    with tempfile.TemporaryDirectory() as td:
        data = make_payload(Path(td))
        (data / 'sources.json').unlink()
        code, out = run(SCAN, '--site-data', str(data))
    check('scan fails when a required payload file is missing', code != 0, out)


def test_scan_covers_files_added_later() -> None:
    """The scan globs *.json rather than a fixed list, so a payload file added in future
    (build-provenance.json, size-report.json, …) is covered without editing the scanner."""
    with tempfile.TemporaryDirectory() as td:
        data = make_payload(Path(td))
        (data / 'extra-payload.json').write_text(
            json.dumps({'note': '/home/vscode/leaked/path/'}), encoding='utf-8')
        code, out = run(SCAN, '--site-data', str(data))
    check('scan covers a newly added payload file', code != 0, out)


# ---------------------------------------------------------------- provenance record

def test_emit_writes_record_and_sums() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        data = make_payload(root, pin='c' * 40)
        code, out = run(EMIT, '--site-data', str(data),
                        '--pin-file', str(root / 'extracted' / 'PIN'))
        check('emit_build_provenance succeeds on a consistent payload', code == 0, out)

        record = json.loads((data / 'build-provenance.json').read_text(encoding='utf-8'))
        check('record pins the source commit', record['source']['pin'] == 'c' * 40)
        check('record carries payload counts', record['payload']['decl_count'] == 1)
        check('record reports no CI context for a local build', record['ci'] is None)

        names = {f['name'] for f in record['files']}
        check('record covers the payload files',
              {'nodes.json', 'sources.json', 'coverage.json'} <= names, repr(names))
        check('record does not list itself', 'build-provenance.json' not in names)
        check('record does not list SHA256SUMS', 'SHA256SUMS' not in names)

        sums = (data / 'SHA256SUMS').read_text(encoding='utf-8')
        check('SHA256SUMS lists every recorded file',
              all(f['name'] in sums and f['sha256'] in sums for f in record['files']))

        verify = subprocess.run(['sha256sum', '-c', 'SHA256SUMS'], cwd=data,
                                capture_output=True, text=True)
        check('sha256sum -c verifies the emitted checksums', verify.returncode == 0,
              verify.stdout + verify.stderr)


def test_emit_covers_every_published_file() -> None:
    """Every file that ships must have a digest.

    This is an ordering trap as much as a coding one: `site_data_size_report.py` writes
    `site/data/size-report.json`, so emitting checksums before that step would publish a
    file with no digest. The workflow therefore runs the size report first — and this check
    pins the property, so a future reordering cannot quietly reopen the hole.
    """
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        data = make_payload(root)
        (data / 'size-report.json').write_text(json.dumps({'total': {'raw': 1}}),
                                               encoding='utf-8')
        (data / 'future-payload.json').write_text(json.dumps({'x': 1}), encoding='utf-8')
        code, out = run(EMIT, '--site-data', str(data),
                        '--pin-file', str(root / 'extracted' / 'PIN'))
        check('emit succeeds with extra payload files present', code == 0, out)

        record = json.loads((data / 'build-provenance.json').read_text(encoding='utf-8'))
        recorded = {f['name'] for f in record['files']}
        shipped = {p.name for p in data.iterdir()
                   if p.is_file() and p.name not in ('build-provenance.json', 'SHA256SUMS')}
        check('every shipped payload file has a recorded digest', recorded == shipped,
              f'recorded={sorted(recorded)} shipped={sorted(shipped)}')

        verify = subprocess.run(['sha256sum', '-c', 'SHA256SUMS'], cwd=data,
                                capture_output=True, text=True)
        check('sha256sum -c verifies all of them', verify.returncode == 0,
              verify.stdout + verify.stderr)


def test_emit_refuses_pin_mismatch() -> None:
    """A provenance record that attests to the wrong commit is worse than none."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        data = make_payload(root, pin='c' * 40)
        (root / 'extracted' / 'PIN').write_text('d' * 40, encoding='utf-8')
        code, out = run(EMIT, '--site-data', str(data),
                        '--pin-file', str(root / 'extracted' / 'PIN'))
        record_written = (data / 'build-provenance.json').exists()
        sums_written = (data / 'SHA256SUMS').exists()
    check('emit refuses when nodes.json pin disagrees with extracted/PIN', code != 0, out)
    check('no provenance record is written on refusal', not record_written)
    check('no SHA256SUMS is written on refusal', not sums_written)


def test_emitted_record_passes_the_scan() -> None:
    """The two gates run back to back in CI; the record must not trip the scanner."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        data = make_payload(root)
        run(EMIT, '--site-data', str(data), '--pin-file', str(root / 'extracted' / 'PIN'))
        code, out = run(SCAN, '--site-data', str(data))
    check('the emitted provenance record passes the leak scan', code == 0, out)
    check('the scan reports having covered the record', 'build-provenance.json' in out, out)


def main() -> None:
    test_scan_accepts_clean_payload()
    test_scan_detects_leaks()
    test_scan_ignores_legitimate_content()
    test_documented_limits_stay_documented()
    test_scan_rejects_scaffold_source()
    test_scan_requires_core_payloads()
    test_scan_covers_files_added_later()
    test_emit_writes_record_and_sums()
    test_emit_covers_every_published_file()
    test_emit_refuses_pin_mismatch()
    test_emitted_record_passes_the_scan()
    print(f'\nAll {len(CHECKS)} notes#32 payload-hardening checks passed.')


if __name__ == '__main__':
    main()
