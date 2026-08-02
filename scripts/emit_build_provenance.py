#!/usr/bin/env python3
"""
emit_build_provenance.py — checksums and a machine-readable build provenance record for
the published site payload (notes#32 "Audit-mandated provenance additions": *checksums and
a small machine-readable build provenance record are emitted*).

`verify_source_provenance.py` proves, at build time, that the payload came from the exact
`extracted/PIN` commit. That proof then evaporates: the deployed site carries no evidence
of it, so a reader — or a later audit — cannot check what they were served. This script
writes that evidence next to the payload:

  site/data/build-provenance.json   what was built, from which commit, with which counts,
                                    and the SHA-256 of every published file
  site/data/SHA256SUMS              the same digests in `sha256sum -c` format

Both are emitted into the payload directory and published with it, so verification needs
nothing but the deployed site:

    cd site && sha256sum -c data/SHA256SUMS

Design notes
------------

* **Coverage is the whole published tree, not just the data.** Both artifact steps publish
  `site/`, which is `index.html`, `app.js`, `styles.css`, `robots.txt` and the vendored
  KaTeX bundle as well as `site/data/*.json`. Hashing only the data would leave the code
  that renders it unverifiable while the README claimed otherwise — the digests here are
  therefore taken over `site/**`, with paths relative to `site/`.
* **The record excludes itself and SHA256SUMS.** A file cannot contain its own digest, and
  a checksum file that lists itself is a self-reference an auditor has to special-case.
* **Stale outputs are removed before anything else.** A workspace reused across builds
  would otherwise keep the previous run's record and digests when this run refuses to
  write, leaving evidence that describes a payload that is no longer there.
* **CI context is recorded when present, and its absence is stated rather than faked.**
  A local build says `"ci": null`; it does not invent a run id. The point of the record is
  to be trustworthy about provenance, so guessing is the one thing it must not do.
* **`built_at` comes from the payload, not from this script's clock.** `build_site_data.py`
  already stamps the build; re-stamping here would produce two timestamps that drift apart
  and leave a reader unsure which describes the artifact.

Usage:
    python3 scripts/emit_build_provenance.py
    python3 scripts/emit_build_provenance.py --site-data site/data --pin-file extracted/PIN

Exits non-zero if the payload is missing, unparseable, or disagrees with `extracted/PIN`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SITE_DATA = REPO_ROOT / 'site' / 'data'
DEFAULT_PIN_FILE = REPO_ROOT / 'extracted' / 'PIN'

PROVENANCE_NAME = 'build-provenance.json'
SUMS_NAME = 'SHA256SUMS'

SOURCE_REPO = 'https://github.com/uda-lab/leray-hopf'
SCHEMA_VERSION = 1


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def ci_context() -> dict | None:
    """GitHub Actions context, or None when not running in CI.

    Deliberately reports None rather than partial guesses: a provenance record that
    invents a run id is worse than one that admits it was built locally.
    """
    run_id = os.environ.get('GITHUB_RUN_ID')
    if not run_id:
        return None
    repo = os.environ.get('GITHUB_REPOSITORY', '')
    return {
        'repository': repo or None,
        'workflow': os.environ.get('GITHUB_WORKFLOW') or None,
        'run_id': run_id,
        'run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT') or None,
        'run_url': f'https://github.com/{repo}/actions/runs/{run_id}' if repo else None,
        'notes_commit': os.environ.get('GITHUB_SHA') or None,
        'ref': os.environ.get('GITHUB_REF') or None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--site-data', default=str(DEFAULT_SITE_DATA))
    parser.add_argument('--pin-file', default=str(DEFAULT_PIN_FILE))
    parser.add_argument('--site-root', default=None,
                        help='published tree to hash (default: the parent of --site-data)')
    args = parser.parse_args()

    site_data = Path(args.site_data).resolve()
    pin_file = Path(args.pin_file).resolve()
    site_root = Path(args.site_root).resolve() if args.site_root else site_data.parent

    if not site_data.is_dir():
        print(f'ERROR: payload directory not found: {site_data}', file=sys.stderr)
        return 1

    # Clear stale evidence as soon as the payload directory is known — BEFORE any other
    # validation. Every check below can return early, and each such return used to leave the
    # previous run's record and digests in place, so a later packaging step could publish
    # evidence describing an older payload.
    for stale in (site_data / PROVENANCE_NAME, site_data / SUMS_NAME):
        if stale.exists():
            stale.unlink()

    if not site_root.is_dir():
        print(f'ERROR: site root not found: {site_root}', file=sys.stderr)
        return 1
    if not pin_file.is_file():
        print(f'ERROR: pin file not found: {pin_file}', file=sys.stderr)
        return 1

    pin = pin_file.read_text(encoding='utf-8').strip()

    nodes_path = site_data / 'nodes.json'
    if not nodes_path.is_file():
        print(f'ERROR: nodes.json not found in {site_data} — run build_site_data.py first',
              file=sys.stderr)
        return 1
    try:
        nodes = json.loads(nodes_path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        print(f'ERROR: nodes.json is not valid JSON: {exc}', file=sys.stderr)
        return 1

    # The payload must already agree with the PIN. verify_source_provenance.py is the gate
    # that enforces this; re-checking here keeps the record from attesting to a mismatch it
    # could have detected — a provenance file that records the wrong commit is worse than
    # no provenance file.
    payload_pin = nodes.get('pin')
    if payload_pin != pin:
        print(f'ERROR: nodes.json pin ({payload_pin!r}) does not match {pin_file} ({pin!r}) '
              f'— refusing to write a provenance record for a mismatched payload',
              file=sys.stderr)
        return 1

    # sources.json must agree too. Checking only nodes.json would let a standalone run
    # attest to the right commit while the source text shipped alongside came from another
    # one — precisely the drift the frontend guard exists to catch at runtime, so the
    # build-time record must not certify it.
    sources_path = site_data / 'sources.json'
    if sources_path.is_file():
        try:
            sources_pin = json.loads(sources_path.read_text(encoding='utf-8')).get('pin')
        except json.JSONDecodeError as exc:
            print(f'ERROR: sources.json is not valid JSON: {exc}', file=sys.stderr)
            return 1
        if sources_pin != pin:
            print(f'ERROR: sources.json pin ({sources_pin!r}) does not match {pin_file} '
                  f'({pin!r}) — refusing to attest to a payload whose two halves disagree',
                  file=sys.stderr)
            return 1

    # Everything published — the artifact steps upload the whole site/ tree, not just the
    # data — except the two files this script itself produces.
    self_written = {(site_data / PROVENANCE_NAME).resolve(), (site_data / SUMS_NAME).resolve()}
    payload_files = sorted(
        p for p in site_root.rglob('*')
        if p.is_file() and p.resolve() not in self_written
        and not any(part.startswith('.') for part in p.relative_to(site_root).parts)
    )
    if not payload_files:
        print(f'ERROR: no publishable files found under {site_root}', file=sys.stderr)
        return 1

    files_record = [
        {'name': str(p.relative_to(site_root)), 'bytes': p.stat().st_size,
         'sha256': sha256_of(p)}
        for p in payload_files
    ]

    record = {
        'schema_version': SCHEMA_VERSION,
        'description': (
            'Build provenance for the leray-hopf-notes static site payload. '
            'Verify with: cd site && sha256sum -c data/SHA256SUMS'
        ),
        'source': {
            'repository': SOURCE_REPO,
            'pin': pin,
            'commit_url': f'{SOURCE_REPO}/commit/{pin}',
        },
        'payload': {
            'built_at': nodes.get('built_at'),
            'universe_source': nodes.get('universe_source'),
            'decl_count': nodes.get('decl_count'),
            'annotated_count': nodes.get('annotated_count'),
            'source_count': nodes.get('source_count'),
            'has_source': nodes.get('has_source'),
            'proof_status_counts': nodes.get('proof_status_counts'),
        },
        'files': files_record,
        'ci': ci_context(),
    }

    provenance_path = site_data / PROVENANCE_NAME
    provenance_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2, sort_keys=False) + '\n',
        encoding='utf-8')

    sums_path = site_data / SUMS_NAME
    sums_path.write_text(
        ''.join(f'{f["sha256"]}  {f["name"]}\n' for f in files_record), encoding='utf-8')

    print(f'Wrote {provenance_path.name} and {sums_path.name} for PIN {pin} '
          f'({len(files_record)} published files under {site_root})')
    for f in files_record[:6]:
        print(f'  {f["sha256"][:16]}…  {f["name"]} ({f["bytes"]} bytes)')
    if len(files_record) > 6:
        print(f'  … and {len(files_record) - 6} more')
    if record['ci'] is None:
        print('  ci: null (local build — no GITHUB_RUN_ID in environment)')
    else:
        print(f'  ci: {record["ci"]["run_url"]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
