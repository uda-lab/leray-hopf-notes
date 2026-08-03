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
import os
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


# GitHub Actions sets these in every step, so a test that reads the ambient environment
# behaves differently locally and in CI. emit_build_provenance.py's CI-context branch keys
# off GITHUB_RUN_ID, so each scenario states the environment it means instead of inheriting
# one — this test asserted "ci is None" and passed locally while failing in CI.
CI_ENV_VARS = ('GITHUB_RUN_ID', 'GITHUB_REPOSITORY', 'GITHUB_WORKFLOW',
               'GITHUB_RUN_ATTEMPT', 'GITHUB_SHA', 'GITHUB_REF')


def run(script: Path, *args: str, ci_env: dict[str, str] | None = None) -> tuple[int, str]:
    """Run a script with a deliberately-controlled CI environment.

    `ci_env=None` means "a local build": every GitHub Actions variable is stripped.
    Passing a dict means "running in CI" with exactly those values.
    """
    env = {k: v for k, v in os.environ.items() if k not in CI_ENV_VARS}
    env.update(ci_env or {})
    proc = subprocess.run([sys.executable, str(script), *args],
                          capture_output=True, text=True, env=env)
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
    'GitHub token (legacy ghp_)': 'ghp_' + 'A' * 30,
    'GitHub token (fine-grained github_pat_)': 'github_pat_' + '1A2B3C4D5E' * 8 + 'abcdef',
    'OpenAI key (legacy sk-)': 'sk-' + 'B' * 32,
    'OpenAI key (project sk-proj-)': 'sk-proj-' + 'A' * 48,
    'OpenAI key (service account sk-svcacct-)': 'sk-svcacct-' + 'B' * 40,
    'AWS key id (long-term AKIA)': 'AKIA' + 'C' * 16,
    'AWS key id (STS temporary ASIA)': 'ASIA' + 'C' * 16,
    'PEM private key': '-----BEGIN RSA PRIVATE KEY-----',
    'home path': '/home/vscode/notes/secret.md',
    'workspace path': '/workspaces/leray-hopf-notes/local',
    'tmp path': '/tmp/claude-1000/transcript.jsonl',
    'assistant session URL': 'https://claude.ai/code/session_016UU',
    'agent config dir': '/home/x/.claude/projects/foo',
    'credential assignment': 'api_key: "' + 'D' * 20 + '"',
    'Windows path (uppercase drive)': r'C:\Users\bob\notes',
    'Windows path (lowercase drive)': r'c:\Users\bob\secret.txt',
    'JWT': 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.' + 'x' * 43,
    'credentials in URL': 'postgres://user:pw@db.internal:5432/app',
    'HTTP basic auth in URL': 'https://bob:hunter2@example.com/x',
    'email address': 'someone@example.com',
    'internal .local host': 'https://internal.uda-lab.local:8443/admin',
    'private IPv4': 'reachable at 10.0.0.5 from the runner',
    'concatenated credentials': 'AKIA' + 'C' * 16 + 'sk-' + 'D' * 32,
    'system path /etc': '/etc/passwd',
    'system path /opt': '/opt/private/config',
    'system path /var': '/var/lib/app/token',
    'Google API key ending in hyphen': 'AIza' + 'a' * 34 + '-',
    'Slack app-level token': 'xapp-1-A1234567890-1234567890-abcdefABCDEF1234567890abcdef',
    'Slack webhook URL': 'https://hooks.slack.com/services/T0000/B0000/abcdefghijklmnop',
    'secret in query parameter': 'https://api.example.com/v1?token=' + 'Z' * 32,
    'singular /workspace/ path': '/workspace/leray-hopf-notes/private.txt',
    'codex session path': '/root/.codex/sessions/secret.jsonl',
    'root home path': '/root/secrets.env',
}

# Shapes the scan knowingly does NOT catch. Pinned so the documented limits stay honest:
# if a future pattern starts catching one of these, the docstring must stop disclaiming it.
DOCUMENTED_LIMITS = {
    'base64-encoded credential': 'dXNlcjpzdXBlcnNlY3JldHBhc3N3b3JkMTIz',
    'SSH key body without header': 'AAAAB3NzaC1yc2EAAAADAQABAAABgQ' + 'C' * 40,
    'arbitrary internal DNS name': 'db.prod.internal.example',
}

# Content that MUST NOT trip the scan — all of it really appears in this corpus.
LEGITIMATE_PROBES = {
    'LaTeX function type': r'$f:\mathbb R\to H$ が連続である。',
    'LaTeX index map': r'狭義単調な $\varphi:\mathbb N\to\mathbb N$ をとる。',
    'LaTeX viscous pairing': r'$\int\nabla u:\nabla u$ は $H^1$ の外では発散する。',
    'review-round prose': 'Codex Gate round 3 の指摘で修正した設計記録。',
    'the word password': 'password という語を含む一般的な散文。',
    'issue citation': 'leray-hopf issue #229（PR #231）で二段階に修正された。',
    'URL containing /etc/': 'https://example.com/etc/faq を参照。',
    'three-component version': 'バージョン 10.2.3 で導入された。',
    'out-of-range dotted value': '10.999.999.999 は住所ではない。',
    'octet 256': '10.256.0.1 も同様である。',
    'five-component dotted value': '10.1.2.3.4 は住所ではない。',
    'five-component 192.168': '192.168.1.2.3 も同様。',
    'address glued to a word': 'バージョン 10.0.0.5beta を参照。',
    'address glued by underscore': '識別子 10.0.0.5_foo を用いる。',
    'semver prerelease suffix': 'バージョン 10.0.0.5-beta を参照。',
    'semver build metadata': 'バージョン 10.0.0.5+meta を参照。',
    'dot-suffixed identifier': '識別子 10.0.0.5.beta を参照。',
    'dotted hostname-like value': '値 192.168.1.2.example を参照。',
    'over-long AIza token': 'AIza' + 'a' * 40 + ' は鍵ではない。',
    'over-long AKIA identifier': 'AKIA' + 'C' * 17 + ' は識別子である。',
    'section number': '第 172.16 節ではなく 172.16 章を参照。',
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



def test_findings_do_not_leak_neighbouring_secrets() -> None:
    """Findings go to a public Actions log precisely when a real credential is present.

    The context window around a match used to be printed verbatim, so two adjacent tokens
    each disclosed the other — the diagnostic leaked what the gate had just refused to
    publish (adversarial review, PR #135).
    """
    first, second = 'ghp_' + 'A' * 30, 'ghp_' + 'B' * 30
    with tempfile.TemporaryDirectory() as td:
        data = make_payload(Path(td), extra_prose=f'{first} and {second}')
        code, out = run(SCAN, '--site-data', str(data))
    check('two adjacent credentials are still detected', code != 0, out)
    check('no credential body appears verbatim in the diagnostics',
          'A' * 20 not in out and 'B' * 20 not in out, out)
    check('the diagnostic shows a redaction placeholder instead', 'redacted:' in out, out)



def test_adjacent_credentials_are_fully_redacted() -> None:
    """Cropping the context before redacting could begin the window inside a neighbouring
    credential, cutting off the prefix its pattern needs; and pattern redaction alone can
    leave a long opaque tail when a token contains a character its class excludes. Both
    printed a credential body into the public log (adversarial review)."""
    cases = {
        'split by underscore': 'ghp_' + 'A' * 36 + 'ghp_' + 'B' * 36,
        'separated by prose': 'ghp_' + 'A' * 30 + ' and ' + 'ghp_' + 'B' * 30,
        'different schemes concatenated': 'AKIA' + 'C' * 16 + 'sk-' + 'D' * 32,
        # A body split by a delimiter the pattern excludes: the tail is only reachable by
        # the opaque-run scrub, and cropping through it used to leave a sub-threshold
        # fragment the scrub no longer recognised.
        'body split by a delimiter': 'password=' + 'A' * 20 + '.' + 'B' * 24,
        # Each sub-run below the opaque-run threshold, separated by delimiters the run
        # charset excludes — only consuming the whole value as one match covers this.
        'body split into sub-threshold runs':
            'password=' + 'A' * 20 + '.' + 'B' * 19 + '_' + 'C' * 19,
    }
    for label, payload in cases.items():
        with tempfile.TemporaryDirectory() as td:
            # Also put it in `file`, which reaches the scaffold diagnostic — a separate
            # code path from the pattern excerpt, and one that leaked independently.
            data = make_payload(Path(td), extra_prose=payload,
                                node_file=f'/workspace/{payload}/Scratch/Foo.lean')
            code, out = run(SCAN, '--site-data', str(data))
        check(f'adjacent credentials detected: {label}', code != 0, out)
        check(f'no credential body printed verbatim: {label}',
              not any(ch * 15 in out for ch in 'ABCD'), out)


def test_scan_rejects_scaffold_source() -> None:
    with tempfile.TemporaryDirectory() as td:
        data = make_payload(Path(td), node_file='LerayHopf/Scratch/R3ShapeGate.lean')
        code, out = run(SCAN, '--site-data', str(data))
    check('scan rejects a declaration sourced from a Scratch/ module', code != 0, out)
    check('scaffold failure names the offending module', 'Scratch' in out, out)



def test_scaffold_diagnostic_is_redacted() -> None:
    """The scaffold line goes to the same public log as the pattern findings, so masking one
    while printing the other verbatim would defeat the redaction (adversarial review)."""
    with tempfile.TemporaryDirectory() as td:
        data = make_payload(Path(td), node_file='/workspace/private/Scratch/Secret.lean')
        code, out = run(SCAN, '--site-data', str(data))
    check('a scaffold path that is also a local path is rejected', code != 0, out)
    check('the scaffold diagnostic does not print the local path verbatim',
          '/workspace/private' not in out, out)
    check('the scaffold diagnostic shows a redaction placeholder', 'redacted:' in out, out)


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
        check('record reports no CI context for a local build', record['ci'] is None,
              repr(record['ci']))

        names = {f['name'] for f in record['files']}
        check('record covers the payload files (site-relative names)',
              {'data/nodes.json', 'data/sources.json', 'data/coverage.json'} <= names,
              repr(sorted(names)))
        check('record does not list itself', 'build-provenance.json' not in names)
        check('record does not list SHA256SUMS', 'SHA256SUMS' not in names)

        sums = (data / 'SHA256SUMS').read_text(encoding='utf-8')
        check('SHA256SUMS lists every recorded file',
              all(f['name'] in sums and f['sha256'] in sums for f in record['files']))

        verify = subprocess.run(['sha256sum', '-c', 'data/SHA256SUMS'], cwd=data.parent,
                                capture_output=True, text=True)
        check('sha256sum -c verifies the emitted checksums', verify.returncode == 0,
              verify.stdout + verify.stderr)


def test_emit_records_ci_context_when_in_ci() -> None:
    """The CI branch was previously untested — and the local-build assertion silently
    depended on the ambient environment, so it passed locally and failed in Actions."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        data = make_payload(root)
        code, out = run(EMIT, '--site-data', str(data),
                        '--pin-file', str(root / 'extracted' / 'PIN'),
                        ci_env={
                            'GITHUB_RUN_ID': '12345',
                            'GITHUB_REPOSITORY': 'uda-lab/leray-hopf-notes',
                            'GITHUB_WORKFLOW': 'CI',
                            'GITHUB_RUN_ATTEMPT': '2',
                            'GITHUB_SHA': 'f' * 40,
                            'GITHUB_REF': 'refs/heads/main',
                        })
        check('emit succeeds under a CI environment', code == 0, out)
        record = json.loads((data / 'build-provenance.json').read_text(encoding='utf-8'))
        ci = record['ci']
        check('CI context is recorded when GITHUB_RUN_ID is set', ci is not None, repr(ci))
        check('CI context carries the run id', ci['run_id'] == '12345', repr(ci))
        check('CI context builds a resolvable run URL',
              ci['run_url'] == 'https://github.com/uda-lab/leray-hopf-notes/actions/runs/12345',
              repr(ci))
        check('CI context records the notes commit that built it',
              ci['notes_commit'] == 'f' * 40, repr(ci))


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
        site = data.parent
        recorded = {f['name'] for f in record['files']}
        shipped = {str(q.relative_to(site)) for q in site.rglob('*')
                   if q.is_file() and q.name not in ('build-provenance.json', 'SHA256SUMS')}
        check('every shipped file has a recorded digest', recorded == shipped,
              f'recorded={sorted(recorded)} shipped={sorted(shipped)}')

        verify = subprocess.run(['sha256sum', '-c', 'data/SHA256SUMS'], cwd=site,
                                capture_output=True, text=True)
        check('sha256sum -c verifies all of them', verify.returncode == 0,
              verify.stdout + verify.stderr)


def test_emit_refuses_sources_pin_mismatch() -> None:
    """Validating only nodes.json let a standalone run attest to the right commit while the
    source text beside it came from another (adversarial review, PR #135)."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        data = make_payload(root, pin='a' * 40)
        sources = json.loads((data / 'sources.json').read_text(encoding='utf-8'))
        sources['pin'] = 'b' * 40
        (data / 'sources.json').write_text(json.dumps(sources), encoding='utf-8')
        code, out = run(EMIT, '--site-data', str(data),
                        '--pin-file', str(root / 'extracted' / 'PIN'))
        wrote = (data / 'build-provenance.json').exists()
    check('emit refuses when sources.json pin disagrees', code != 0, out)
    check('no record written for a half-mismatched payload', not wrote)


def test_emit_clears_stale_outputs() -> None:
    """A reused workspace must not keep the previous run's evidence when this run refuses."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        data = make_payload(root, pin='a' * 40)
        (data / 'build-provenance.json').write_text('{"stale": true}', encoding='utf-8')
        (data / 'SHA256SUMS').write_text('deadbeef  nodes.json\n', encoding='utf-8')
        (root / 'extracted' / 'PIN').write_text('d' * 40, encoding='utf-8')
        code, out = run(EMIT, '--site-data', str(data),
                        '--pin-file', str(root / 'extracted' / 'PIN'))
        record_left = (data / 'build-provenance.json').exists()
        sums_left = (data / 'SHA256SUMS').exists()
    check('emit still refuses a mismatched payload', code != 0, out)
    check('a stale provenance record does not survive a refusal', not record_left)
    check('stale SHA256SUMS do not survive a refusal', not sums_left)


def test_emit_hashes_the_whole_published_tree() -> None:
    """Both artifact steps publish site/, not site/data — hashing only the data left
    index.html, app.js, styles.css and the vendored KaTeX bundle unverifiable while the
    README claimed a digest for every published file."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        data = make_payload(root)
        site = data.parent
        (site / 'index.html').write_text('<!doctype html>', encoding='utf-8')
        (site / 'app.js').write_text('// app', encoding='utf-8')
        (site / 'vendor' / 'katex').mkdir(parents=True)
        (site / 'vendor' / 'katex' / 'katex.min.js').write_text('//k', encoding='utf-8')
        code, out = run(EMIT, '--site-data', str(data),
                        '--pin-file', str(root / 'extracted' / 'PIN'))
        check('emit succeeds over a full site tree', code == 0, out)

        record = json.loads((data / 'build-provenance.json').read_text(encoding='utf-8'))
        names = {f['name'] for f in record['files']}
        for expected in ('index.html', 'app.js', 'vendor/katex/katex.min.js',
                         'data/nodes.json', 'data/sources.json'):
            check(f'digest covers {expected}', expected in names, repr(sorted(names)))

        verify = subprocess.run(['sha256sum', '-c', 'data/SHA256SUMS'], cwd=site,
                                capture_output=True, text=True)
        check('sha256sum -c verifies from the site root', verify.returncode == 0,
              verify.stdout + verify.stderr)



def test_emit_clears_stale_outputs_on_early_return() -> None:
    """Cleanup must happen before ANY validation that can return early — a bad --pin-file
    used to leave the previous run's evidence in place for a later packaging step to
    publish (adversarial review)."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        data = make_payload(root)
        (data / 'build-provenance.json').write_text('{"stale": true}', encoding='utf-8')
        (data / 'SHA256SUMS').write_text('deadbeef  data/nodes.json\n', encoding='utf-8')
        code, out = run(EMIT, '--site-data', str(data),
                        '--pin-file', str(root / 'does-not-exist'))
        record_left = (data / 'build-provenance.json').exists()
        sums_left = (data / 'SHA256SUMS').exists()
    check('emit fails on a missing pin file', code != 0, out)
    check('stale record is cleared even on an early return', not record_left)
    check('stale SHA256SUMS is cleared even on an early return', not sums_left)



def test_emit_hashes_dotfiles() -> None:
    """`site/data/.gitkeep` already ships and a Pages tree may carry `.nojekyll`; excluding
    dotfiles would mean the artifact contains bytes no digest covers while the record claims
    whole-tree coverage (adversarial review)."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        data = make_payload(root)
        (data / '.gitkeep').write_text('', encoding='utf-8')
        (data.parent / '.nojekyll').write_text('', encoding='utf-8')
        code, out = run(EMIT, '--site-data', str(data),
                        '--pin-file', str(root / 'extracted' / 'PIN'))
        check('emit succeeds with dotfiles present', code == 0, out)
        record = json.loads((data / 'build-provenance.json').read_text(encoding='utf-8'))
        names = {f['name'] for f in record['files']}
    check('data/.gitkeep is hashed', 'data/.gitkeep' in names, repr(sorted(names)))
    check('.nojekyll is hashed', '.nojekyll' in names, repr(sorted(names)))



def test_emit_refuses_when_sources_json_is_missing() -> None:
    """A payload claiming embedded source must ship it. Skipping validation when the file is
    absent let a standalone run attest to a payload whose source half was simply missing."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        data = make_payload(root)
        (data / 'sources.json').unlink()
        code, out = run(EMIT, '--site-data', str(data),
                        '--pin-file', str(root / 'extracted' / 'PIN'))
        wrote = (data / 'build-provenance.json').exists()
    check('emit refuses when sources.json is missing but claimed', code != 0, out)
    check('no record is written for an incomplete payload', not wrote)




def test_emit_honours_per_node_source_claims() -> None:
    """A payload can carry has_source:false at the top level while individual nodes claim
    embedded source; those nodes' text still has to exist (adversarial review)."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        data = make_payload(root)
        nodes = json.loads((data / 'nodes.json').read_text(encoding='utf-8'))
        nodes['has_source'] = False
        nodes['source_count'] = 0
        nodes['nodes'][0]['has_source'] = True
        (data / 'nodes.json').write_text(json.dumps(nodes, ensure_ascii=False),
                                         encoding='utf-8')
        (data / 'sources.json').unlink()
        code, out = run(EMIT, '--site-data', str(data),
                        '--pin-file', str(root / 'extracted' / 'PIN'))
        wrote = (data / 'build-provenance.json').exists()
    check('emit refuses when a NODE claims source but sources.json is gone', code != 0, out)
    check('no record written for that payload', not wrote)



def test_emit_requires_site_data_inside_site_root() -> None:
    """The validated payload must be part of the hashed tree, or the record attests to
    counts and pins from one directory while the digests describe another."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        data = make_payload(root)
        other = root / 'unrelated'
        other.mkdir()
        (other / 'index.html').write_text('<!doctype html>', encoding='utf-8')
        code, out = run(EMIT, '--site-data', str(data), '--site-root', str(other),
                        '--pin-file', str(root / 'extracted' / 'PIN'))
        wrote = (data / 'build-provenance.json').exists()
    check('emit refuses a --site-data outside --site-root', code != 0, out)
    check('no record written in that case', not wrote)



def test_emit_requires_a_sources_map() -> None:
    """A pin alone is not a payload: a sources.json with the right pin but no `sources`
    object would be attested as a complete build while shipping no source text."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        data = make_payload(root)
        pin = (root / 'extracted' / 'PIN').read_text(encoding='utf-8').strip()
        (data / 'sources.json').write_text(json.dumps({'pin': pin}), encoding='utf-8')
        code, out = run(EMIT, '--site-data', str(data),
                        '--pin-file', str(root / 'extracted' / 'PIN'))
        wrote = (data / 'build-provenance.json').exists()
    check('emit refuses a sources.json with no sources map', code != 0, out)
    check('no record written for a source-less payload', not wrote)



def test_emit_delegates_coverage_checks_to_the_verifier() -> None:
    """The emitter reuses verify_source_provenance.py's coverage rules instead of keeping a
    second copy. Three review rounds found it re-deriving them one at a time — pin equality,
    then the map's presence, then its size, then its keys — each fix leaving the next gap
    open, and two copies of the same rules drift anyway.
    """
    pin = 'a' * 40

    def payload(nodes_extra, sources_obj):
        root = Path(tempfile.mkdtemp())
        data = root / 'site' / 'data'
        data.mkdir(parents=True)
        (root / 'extracted').mkdir()
        (root / 'extracted' / 'PIN').write_text(pin, encoding='utf-8')
        nodes = {'pin': pin, 'has_source': True, 'source_count': 1, 'decl_count': 1,
                 'nodes': [{'slug': 'x', 'has_source': True}]}
        nodes.update(nodes_extra)
        (data / 'nodes.json').write_text(json.dumps(nodes), encoding='utf-8')
        (data / 'sources.json').write_text(json.dumps(sources_obj), encoding='utf-8')
        (data / 'coverage.json').write_text('{}', encoding='utf-8')
        return root, data

    cases = {
        'empty map': ({}, {'pin': pin, 'source_count': 1, 'sources': {}}),
        'short map': ({'source_count': 2, 'decl_count': 2},
                      {'pin': pin, 'source_count': 2, 'sources': {'x': 'y'}}),
        'mismatched slugs': ({}, {'pin': pin, 'source_count': 1, 'sources': {'WRONG': 'y'}}),
        'non-integer count': ({'source_count': '1'},
                              {'pin': pin, 'source_count': '1', 'sources': {'x': 'y'}}),
        'boolean count': ({'source_count': True},
                          {'pin': pin, 'source_count': True, 'sources': {'x': 'y'}}),
        'stale sources pin': ({}, {'pin': 'b' * 40, 'source_count': 1, 'sources': {'x': 'y'}}),
    }
    for label, (nodes_extra, sources_obj) in cases.items():
        root, data = payload(nodes_extra, sources_obj)
        code, out = run(EMIT, '--site-data', str(data),
                        '--pin-file', str(root / 'extracted' / 'PIN'))
        wrote = (data / 'build-provenance.json').exists()
        check(f'emit refuses a payload the coverage gate rejects: {label}', code != 0, out)
        check(f'no record written: {label}', not wrote)

    root, data = payload({}, {'pin': pin, 'source_count': 1, 'sources': {'x': 'y'}})
    code, out = run(EMIT, '--site-data', str(data),
                    '--pin-file', str(root / 'extracted' / 'PIN'))
    check('emit still accepts a coherent payload', code == 0, out)


def test_emit_rejects_malformed_pin() -> None:
    """Equality is not enough: an empty or malformed PIN matched against an equally
    malformed payload pin passes both checks, and the record then carries an invalid
    `source.pin` and a commit URL resolving to nothing — authoritative-looking evidence
    pointing nowhere (adversarial review)."""
    for label, pin in (('empty', ''), ('too short', 'abc'), ('uppercase', 'A' * 40),
                       ('non-hex', 'z' * 40)):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = make_payload(root, pin=pin)
            code, out = run(EMIT, '--site-data', str(data),
                            '--pin-file', str(root / 'extracted' / 'PIN'))
            wrote = (data / 'build-provenance.json').exists()
        check(f'emit rejects a malformed PIN: {label}', code != 0, out)
        check(f'no record written for a malformed PIN: {label}', not wrote)



def test_sha256sums_covers_the_provenance_record() -> None:
    """Only a file containing its OWN digest is a self-reference. Leaving the record out of
    SHA256SUMS made it the one published file a verifier could not detect a change to — a
    poor property for the artifact whose whole job is to be evidence (adversarial review)."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        data = make_payload(root)
        site = data.parent
        code, out = run(EMIT, '--site-data', str(data),
                        '--pin-file', str(root / 'extracted' / 'PIN'))
        check('emit succeeds', code == 0, out)

        sums = (data / 'SHA256SUMS').read_text(encoding='utf-8')
        check('SHA256SUMS lists the provenance record',
              'data/build-provenance.json' in sums, sums)
        check('SHA256SUMS does not list itself', 'data/SHA256SUMS' not in sums, sums)

        record = json.loads((data / 'build-provenance.json').read_text(encoding='utf-8'))
        names = {f['name'] for f in record['files']}
        check("the record's own file list still excludes itself",
              'data/build-provenance.json' not in names and 'data/SHA256SUMS' not in names,
              repr(sorted(names)))

        clean = subprocess.run(['sha256sum', '-c', 'data/SHA256SUMS'], cwd=site,
                               capture_output=True, text=True)
        check('verification passes on an untouched tree', clean.returncode == 0,
              clean.stdout + clean.stderr)

        # Tamper with the record itself — the case that was previously undetectable.
        doc = json.loads((data / 'build-provenance.json').read_text(encoding='utf-8'))
        doc['tampered'] = True
        (data / 'build-provenance.json').write_text(json.dumps(doc), encoding='utf-8')
        tampered = subprocess.run(['sha256sum', '-c', 'data/SHA256SUMS'], cwd=site,
                                  capture_output=True, text=True)
    check('verification detects tampering with the provenance record',
          tampered.returncode != 0, tampered.stdout + tampered.stderr)


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



# ------------------------------------------------- citation / release-link suppression

def test_release_link_suppressed_on_citation_pin_mismatch() -> None:
    """A stale CITATION.cff would keep advertising the previous release while the payload
    was built from a newer commit, pointing readers at an attestation for source they are
    not looking at. A build warning nobody reads is not protection (adversarial review)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'bsd_issue32', REPO_ROOT / 'scripts' / 'build_site_data.py')
    bsd = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bsd)

    real_pin = (REPO_ROOT / 'extracted' / 'PIN').read_text(encoding='utf-8').strip()
    warnings: list = []
    agreeing = bsd.read_citation_meta(real_pin, warnings)
    check('release metadata is emitted when CITATION.cff agrees with the PIN',
          bool(agreeing.get('source_version')), repr(agreeing))
    check('no warning when they agree', not warnings, repr(warnings))

    warnings = []
    mismatched = bsd.read_citation_meta('9' * 40, warnings)
    check('release version is suppressed when CITATION.cff disagrees with the PIN',
          mismatched.get('source_version') == '', repr(mismatched))
    check('release date is suppressed too',
          mismatched.get('source_date_released') == '', repr(mismatched))
    check('the mismatch is still warned about', len(warnings) == 1, repr(warnings))


def main() -> None:
    test_scan_accepts_clean_payload()
    test_scan_detects_leaks()
    test_scan_ignores_legitimate_content()
    test_documented_limits_stay_documented()
    test_findings_do_not_leak_neighbouring_secrets()
    test_adjacent_credentials_are_fully_redacted()
    test_scan_rejects_scaffold_source()
    test_scaffold_diagnostic_is_redacted()
    test_scan_requires_core_payloads()
    test_scan_covers_files_added_later()
    test_emit_writes_record_and_sums()
    test_emit_records_ci_context_when_in_ci()
    test_emit_covers_every_published_file()
    test_emit_refuses_pin_mismatch()
    test_emit_refuses_sources_pin_mismatch()
    test_emit_refuses_when_sources_json_is_missing()
    test_emit_rejects_malformed_pin()
    test_emit_honours_per_node_source_claims()
    test_emit_requires_site_data_inside_site_root()
    test_emit_requires_a_sources_map()
    test_emit_delegates_coverage_checks_to_the_verifier()
    test_emit_clears_stale_outputs()
    test_emit_clears_stale_outputs_on_early_return()
    test_emit_hashes_the_whole_published_tree()
    test_emit_hashes_dotfiles()
    test_sha256sums_covers_the_provenance_record()
    test_emitted_record_passes_the_scan()
    test_release_link_suppressed_on_citation_pin_mismatch()
    print(f'\nAll {len(CHECKS)} notes#32 payload-hardening checks passed.')


if __name__ == '__main__':
    main()
