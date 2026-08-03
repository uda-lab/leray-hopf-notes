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

* **Coverage is the whole published tree, not just the data — dotfiles included.** Both artifact steps publish
  `site/`, which is `index.html`, `app.js`, `styles.css`, `robots.txt` and the vendored
  KaTeX bundle as well as `site/data/*.json`. Hashing only the data would leave the code
  that renders it unverifiable while the README claimed otherwise — the digests here are
  therefore taken over `site/**`, with paths relative to `site/`.
* **The record's own `files` list excludes itself and SHA256SUMS** — a file cannot contain
  its own digest. `SHA256SUMS`, however, *does* cover the record: listing another file is
  not self-reference, and leaving it out would make the provenance record the one published
  file a verifier could not detect a change to.
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
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# The provenance gate owns the payload-coverage rules; this script reuses them rather than
# keeping a second, drifting copy (see the call site below).
sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_source_provenance as _verify  # noqa: E402
DEFAULT_SITE_DATA = REPO_ROOT / 'site' / 'data'
DEFAULT_PIN_FILE = REPO_ROOT / 'extracted' / 'PIN'

PROVENANCE_NAME = 'build-provenance.json'
SUMS_NAME = 'SHA256SUMS'

# Same shape the workflow's read-pin step and validate.py require. Equality alone is not
# enough here: an empty or malformed PIN matched against an equally malformed payload pin
# passes both checks, and the record then carries an invalid `source.pin` and a commit URL
# that resolves to nothing — evidence that looks authoritative and points nowhere.
PIN_PATTERN = re.compile(r'^[0-9a-f]{40}$')

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
    parser.add_argument('--lean-root', default=None,
                        help='pinned leray-hopf checkout; when given, embedded source text '
                             'is verified against it before the record is written')
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
    # The payload being validated must be part of the tree being hashed. Otherwise the
    # record would attest to counts and pins read from one directory while the digests
    # describe an entirely different one.
    if not site_data.is_relative_to(site_root):
        print(f'ERROR: --site-data ({site_data}) is not inside --site-root ({site_root}) '
              f'— the validated payload must be part of the hashed tree', file=sys.stderr)
        return 1
    if not pin_file.is_file():
        print(f'ERROR: pin file not found: {pin_file}', file=sys.stderr)
        return 1

    pin = pin_file.read_text(encoding='utf-8').strip()
    if not PIN_PATTERN.match(pin):
        print(f'ERROR: {pin_file} is not a 40-character lowercase-hex commit SHA: '
              f'{_verify.safe_pin(pin)} '
              f'— refusing to write a provenance record naming an invalid commit',
              file=sys.stderr)
        return 1

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
        print(f'ERROR: nodes.json pin ({_verify.safe_pin(payload_pin)}) does not match '
              f'{pin_file} ({_verify.safe_pin(pin)}) '
              f'— refusing to write a provenance record for a mismatched payload',
              file=sys.stderr)
        return 1

    # sources.json must agree too — and rather than reimplement the coverage rules here,
    # reuse the gate that already owns them. Three rounds of review found this file
    # re-deriving `verify_source_provenance.py`'s checks one at a time (pin equality, then
    # the map's presence, then its size, then its keys), each time leaving the next gap
    # open. Two copies of the same rules also drift. In CI the verifier runs immediately
    # before this script; calling it here closes the documented standalone path with the
    # same logic instead of an ever-growing imitation of it.
    source_text_verified = False
    sources_path = site_data / 'sources.json'
    claims_source = (
        bool(nodes.get('has_source'))
        or bool(nodes.get('source_count'))
        or (isinstance(nodes.get('nodes'), list)
            and any(isinstance(n, dict) and n.get('has_source')
                    for n in nodes.get('nodes')))
    )
    if claims_source and not sources_path.is_file():
        print(f'ERROR: nodes.json claims embedded source (has_source='
              f'{_verify.safe(nodes.get("has_source"))}, '
              f'source_count={_verify.safe(nodes.get("source_count"))}) '
              f'but {sources_path} is missing — refusing to attest to an incomplete payload',
              file=sys.stderr)
        return 1

    if sources_path.is_file():
        try:
            sources_doc = json.loads(sources_path.read_text(encoding='utf-8'))
        except json.JSONDecodeError as exc:
            print(f'ERROR: sources.json is not valid JSON: {exc}', file=sys.stderr)
            return 1
        gate_failures: list[str] = []
        gate_passes: list[str] = []
        _verify.check_pin_consistency(pin, nodes, sources_doc, gate_failures, gate_passes)
        _verify.check_source_coverage(nodes, sources_doc, gate_failures, gate_passes)
        source_text_verified = False
        if args.lean_root:
            # The checkout itself has to be the pinned one, clean and detached, before its
            # contents mean anything: verifying text against a checkout at some other commit
            # and then recording `source_text_verified: true` would attest to the wrong
            # thing with more confidence than before.
            lean_root = Path(args.lean_root)
            _verify.check_pin_match(lean_root, pin, gate_failures, gate_passes)
            _verify.check_clean_detached(lean_root, gate_failures, gate_passes)
            _verify.check_source_text_matches_checkout(
                lean_root, nodes, sources_doc, gate_failures, gate_passes)
            source_text_verified = not gate_failures
        if gate_failures:
            print('ERROR: the payload does not satisfy the provenance coverage checks, so '
                  'there is nothing here worth attesting to:', file=sys.stderr)
            for f in gate_failures:
                print(f'  {f}', file=sys.stderr)
            return 1

    # Everything published — the artifact steps upload the whole site/ tree, not just the
    # data — except the two files this script itself produces.
    self_written = {(site_data / PROVENANCE_NAME).resolve(), (site_data / SUMS_NAME).resolve()}
    # Dotfiles are hashed too. `site/data/.gitkeep` already ships, and a Pages tree can
    # carry `.nojekyll`; excluding them would mean the artifact contains bytes no digest
    # covers, while the record claims whole-tree coverage.
    payload_files = sorted(
        p for p in site_root.rglob('*')
        if p.is_file() and p.resolve() not in self_written
    )
    if not payload_files:
        print(f'ERROR: no publishable files found under {site_root}', file=sys.stderr)
        return 1

    # A newline or backslash in a name would produce a SHA256SUMS that `sha256sum -c`
    # cannot parse — the file would read as two entries, or as an escaped one. Nothing in a
    # static site legitimately needs such a name, so refuse rather than emit a broken
    # checksum file that still looks authoritative.
    for p in payload_files:
        rel_name = str(p.relative_to(site_root))
        if '\n' in rel_name or '\\' in rel_name:
            print(f'ERROR: published filename contains a newline or backslash: '
                  f'{rel_name.encode("unicode_escape").decode()!r} — refusing to write a '
                  f'checksum file it would corrupt', file=sys.stderr)
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
        # Says what was actually checked. Without --lean-root the embedded text cannot be
        # compared to the pinned commit, and a record that stayed silent about that would
        # imply a guarantee it never made. CI always passes it.
        'source_text_verified': source_text_verified,
        'files': files_record,
        'ci': ci_context(),
    }

    provenance_path = site_data / PROVENANCE_NAME
    provenance_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2, sort_keys=False) + '\n',
        encoding='utf-8')

    # SHA256SUMS covers the provenance record too. Only a file containing its OWN digest is
    # a self-reference — SHA256SUMS listing build-provenance.json is not, and without it the
    # record is the one published file `sha256sum -c` could not detect a change to, which is
    # a poor property for the artifact whose whole job is to be evidence. The record is
    # therefore written first, then hashed into the digest file.
    sums_path = site_data / SUMS_NAME
    provenance_rel = str(provenance_path.relative_to(site_root))
    sums_lines = [f'{f["sha256"]}  {f["name"]}\n' for f in files_record]
    sums_lines.append(f'{sha256_of(provenance_path)}  {provenance_rel}\n')
    sums_path.write_text(''.join(sorted(sums_lines, key=lambda l: l.split('  ', 1)[1])),
                         encoding='utf-8')

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
