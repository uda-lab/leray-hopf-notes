#!/usr/bin/env python3
"""
scan_generated_payload.py — fail-closed leak scan of the generated site payload
(notes#32 "Audit-mandated provenance additions": *generated artifact is scanned for
secrets, local paths, agent/session prose, unintended scaffold source*).

The published payload embeds verbatim Lean source and the whole annotation corpus, so it
is the one artifact where a stray absolute path, a credential, or a build-agent transcript
would actually become public. That scan was performed by hand once (issue #32 comment,
2026-07-16) and never again; this script makes it a gate that runs on every build.

What it looks for, and — just as importantly — what it does not
---------------------------------------------------------------

Every pattern here was calibrated against a real source-enabled build rather than written
from imagination, because the payload is full of mathematical prose that trips naive rules:

* **A Windows-drive rule of the shape `[A-Za-z]:\\\\` matches LaTeX, not paths.** The corpus
  contains `$f:\\mathbb R\\to H$`, `$\\varphi:\\mathbb N$`, `$\\int\\nabla u:\\nabla u$` — six
  hits in the current payload, every one legitimate mathematics. The drive-letter pattern
  below therefore requires an uppercase letter *and* a following path segment.
* **"Agent prose" is scoped to machine-generated session artifacts**, not to human-written
  provenance. The corpus deliberately cites issues, PRs and review rounds (`Codex Gate`,
  `codex review` and similar appear in upstream docstrings by design — see the 2026-07-16
  audit comment, which classified them as intentional design records whose publication is
  an owner decision, already taken). Flagging those would fail every build on content the
  owner has approved, and would teach the next author to disable the scan. What is flagged
  is unambiguous leakage: session ids, transcript paths, agent home directories.
* **Scaffold source** is checked structurally: no declaration may be sourced from a
  `Scratch/` module. Those are outside the extraction universe by design, so their presence
  would mean the universe or the reader had gone wrong, not merely that prose looked odd.

Known limits — deliberately not covered
---------------------------------------

This is a pattern scan, not a secret-detection engine, and saying so beats implying
completeness. It will not catch a credential that carries no recognisable marker:

* **base64-encoded secrets.** An opaque base64 blob is indistinguishable from legitimate
  encoded data by shape alone; a rule broad enough to catch it would fire on anything.
* **a bare key body with its header stripped** (e.g. an SSH public-key body without
  `ssh-rsa`), for the same reason.
* **high-entropy strings in general.** An entropy heuristic on a payload this size, full of
  Lean identifiers and LaTeX, produces far more noise than signal.

Every pattern below was verified to produce zero hits on a real source-enabled build before
being added — a rule that fires on legitimate content is worse than no rule, because the
first person it inconveniences will simply switch the gate off.

Usage:
    python3 scripts/scan_generated_payload.py
    python3 scripts/scan_generated_payload.py --site-data site/data

Exits non-zero (fail closed) listing every finding with its file and a redacted excerpt;
exits 0 with a per-check PASS line otherwise.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SITE_DATA = REPO_ROOT / 'site' / 'data'

# Payload files that get published. A file listed here but missing is a hard failure:
# "not there, so nothing to scan" is exactly how a scan silently stops covering things.
REQUIRED_PAYLOADS = ('nodes.json', 'sources.json', 'coverage.json')

# (label, compiled pattern). Ordered roughly by severity.
LEAK_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # --- credentials -------------------------------------------------------------
    ('GitHub token', re.compile(r'\bgh[pousr]_[A-Za-z0-9]{20,}')),
    ('OpenAI-style key', re.compile(r'\bsk-[A-Za-z0-9]{20,}')),
    ('AWS access key id', re.compile(r'\bAKIA[0-9A-Z]{16}\b')),
    ('Google API key', re.compile(r'\bAIza[0-9A-Za-z_-]{35}\b')),
    ('Slack token', re.compile(r'\bxox[abprs]-[0-9A-Za-z-]{10,}')),
    ('PEM private key', re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----')),
    ('Bearer credential', re.compile(r'(?i)\bauthorization\s*:\s*bearer\s+[A-Za-z0-9._-]{20,}')),
    ('JWT', re.compile(r'\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}')),
    # Credentials embedded in a URL's userinfo — covers `postgres://user:pw@host/db`,
    # `https://user:token@host/…`, and the rest of that family in one rule.
    ('credentials in URL', re.compile(r'://[^\s/@:"\\]+:[^\s/@"\\]+@')),
    ('email address', re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')),
    ('internal .local host', re.compile(r'\bhttps?://[A-Za-z0-9.-]+\.local\b')),
    ('private IPv4 address',
     re.compile(r'\b(?:10|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b')),
    # Assignment shapes: a credential-ish key, then a long opaque value. The quote is
    # optional and may be backslash-escaped, because these files are JSON — an embedded
    # `api_key: "…"` is stored as `api_key: \"…\"`, and requiring a bare quote character
    # made this pattern miss the very shape it exists to catch. The 16-char opaque-value
    # floor is what keeps it off prose that merely contains the word "password".
    ('credential assignment',
     re.compile(r'(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|passwd|password)'
                r'\s*[:=]\s*\\?["\']?[A-Za-z0-9/+=_-]{16,}')),

    # --- local filesystem paths --------------------------------------------------
    ('home directory path', re.compile(r'/home/[A-Za-z0-9._-]+/')),
    ('macOS home path', re.compile(r'/Users/[A-Za-z0-9._-]+/')),
    ('container workspace path', re.compile(r'/workspaces/[A-Za-z0-9._-]+')),
    ('tmp path', re.compile(r'/tmp/[A-Za-z0-9._/-]+')),
    ('macOS temp path', re.compile(r'/var/folders/[A-Za-z0-9._/+-]+')),
    ('CI runner path', re.compile(r'/runner/_work/[A-Za-z0-9._/-]+')),
    # Uppercase drive letter AND a path segment — `f:\mathbb` and friends must not match.
    ('Windows path', re.compile(r'\b[A-Z]:\\{1,2}(?:Users|Windows|Program|Temp)\b')),

    # --- agent / session artifacts ------------------------------------------------
    # Machine-generated session identity, NOT human-authored provenance prose.
    ('agent session id', re.compile(r'(?i)\b(?:CODEX_COMPANION_)?SESSION_ID\s*[:=]')),
    ('assistant session URL', re.compile(r'https?://claude\.ai/code/session[_/]')),
    ('agent config directory', re.compile(r'/\.claude/(?:projects|plugins|shell-snapshots)/')),
    ('agent transcript path', re.compile(r'TRANSCRIPT_PATH\s*[:=]')),
    ('tool-call transcript marker', re.compile(r'<(?:function_calls|invoke name=|tool_use_id)')),
]

# Declaration source must never come from a scaffold module.
SCAFFOLD_MODULE = re.compile(r'(?:^|/)Scratch/')


def excerpt(text: str, start: int, end: int, width: int = 40) -> str:
    """A short, redacted window around a hit — enough to locate it, not to leak it."""
    lo = max(0, start - width)
    hi = min(len(text), end + width)
    hit_len = end - start
    redacted = text[start:start + 4] + '…' + f'[{hit_len} chars]'
    return (text[lo:start] + '‹' + redacted + '›' + text[end:hi]).replace('\n', ' ')


def scan_text(label: str, text: str) -> list[str]:
    findings = []
    for name, pattern in LEAK_PATTERNS:
        for m in pattern.finditer(text):
            findings.append(f'{label}: {name}: …{excerpt(text, m.start(), m.end())}…')
    return findings


def scan_scaffold_sources(nodes: dict, label: str) -> list[str]:
    findings = []
    for node in nodes.get('nodes', []):
        src_file = node.get('file') or ''
        if SCAFFOLD_MODULE.search(src_file):
            findings.append(
                f'{label}: scaffold source embedded: declaration '
                f'"{node.get("name", node.get("slug", "?"))}" is sourced from {src_file}'
            )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--site-data', default=str(DEFAULT_SITE_DATA),
                        help='directory holding the generated payload (default: site/data)')
    args = parser.parse_args()

    site_data = Path(args.site_data).resolve()
    failures: list[str] = []
    passes: list[str] = []

    if not site_data.is_dir():
        print(f'FAIL: generated payload directory not found: {site_data}', file=sys.stderr)
        print('      Run scripts/build_site_data.py first.', file=sys.stderr)
        return 1

    # Scan every JSON file that will ship, not just the three core ones: anything dropped
    # into site/data gets published, so a scan restricted to a fixed list would silently
    # stop covering each new payload (build-provenance.json, size-report.json, …).
    present = sorted(p.name for p in site_data.glob('*.json'))
    for name in REQUIRED_PAYLOADS:
        if name not in present:
            failures.append(f'{name}: required payload file is missing from {site_data}')

    for name in present:
        text = (site_data / name).read_text(encoding='utf-8')
        hits = scan_text(name, text)
        if hits:
            failures.extend(hits)
        else:
            passes.append(f'{name}: no secret / local-path / agent-session pattern '
                          f'({len(text)} chars scanned)')

    nodes_path = site_data / 'nodes.json'
    if nodes_path.is_file():
        try:
            nodes = json.loads(nodes_path.read_text(encoding='utf-8'))
        except json.JSONDecodeError as exc:
            failures.append(f'nodes.json: could not parse: {exc}')
        else:
            scaffold = scan_scaffold_sources(nodes, 'nodes.json')
            if scaffold:
                failures.extend(scaffold)
            else:
                passes.append('nodes.json: no declaration sourced from a Scratch/ module')

    for line in passes:
        print(f'PASS  {line}')
    if failures:
        print()
        print(f'{len(failures)} finding(s) — refusing to publish this payload:',
              file=sys.stderr)
        for f in failures:
            print(f'  FAIL  {f}', file=sys.stderr)
        return 1
    print(f'\nOK — generated payload scan clean ({len(passes)} checks).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
