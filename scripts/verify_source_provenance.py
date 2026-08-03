#!/usr/bin/env python3
"""
verify_source_provenance.py — fail-closed provenance gate for source-enabled
site data builds (notes#32 "Audit-mandated provenance additions").

This script is the independent check that a source-enabled `build_site_data.py
--lean-root <path>` run actually embedded verbatim text from the exact,
untampered `extracted/PIN` commit — rather than the workflow (or a caller)
merely asserting that `--lean-root` points at the right place. It re-derives
every fact from disk and from `git` plumbing in the checkout itself; it does
not trust any caller-supplied claim about what the checkout is.

Checks (see notes#32 issue body, "Audit-mandated provenance additions"):

  1. `git rev-parse HEAD` inside --lean-root is byte-for-byte equal to the PIN
     read directly from --pin-file. This also covers "the builder does not
     merely trust the operator-supplied --lean-root": the equality is derived
     from git plumbing run against the checkout's actual `.git` state, not
     from a path string, a step output, or an environment variable that some
     earlier workflow step could have set incorrectly.
  2. The checkout is clean (`git status --porcelain` empty) and HEAD is
     detached (not a movable branch ref) — i.e. it is exactly the pinned
     commit, with nothing built, added, or left over from a previous run,
     and not accidentally tracking a branch pointer that could later move.
  3. `source_count == decl_count` and there are zero source-extraction
     misses. `build_site_data.py` records `source_count` as the number of
     declarations for which `SourceReader.source_for()` actually found the
     verbatim text; when a `--lean-root` build attempted extraction for every
     declaration in the universe (`decl_count`), equality of the two implies
     zero misses (hits + misses == decl_count). This is cross-checked against
     `sources.json`'s own declared `source_count`, the actual size of its
     `sources` object (which must be present and a JSON object, not merely
     absent-and-therefore-skipped), and the exact set of node slugs marked
     `has_source: true` in `nodes.json` — every sub-check is mandatory, not
     conditional on the payload already having the expected shape.
  4. `nodes.json`'s embedded `pin` field equals `sources.json`'s embedded
     `pin` field, so the two payloads the frontend joins at runtime cannot
     silently drift apart.
  5. Every embedded snippet is identical to its `file`:`startLine`-`endLine`
     range in a file the pinned commit actually tracks. "Identical" is with respect to
     line content, not raw bytes: both sides are read with universal newlines, so a CRLF
     file compares equal to the LF-normalised text the builder embeds — which is the text
     that actually ships, so this is the comparison that matters. It is stated rather than
     called byte-equality, which it is not (physical containment is not
     enough — `.git/HEAD` resolves inside the checkout and `git status` never reports
     changes under `.git`, so administrative state could otherwise be attested as
     source). The comparison is exact, with no trailing-newline normalisation. Checks 1-4 are all *bookkeeping* — commit
     equality, cleanliness, counts, keys — and a payload can satisfy every one
     of them while carrying text that commit never contained: a hand-built
     `sources.json` full of `TAMPERED SOURCE`, with correct pins and counts,
     passed all four. This check is what makes "this came from that commit" a
     statement about the bytes rather than about the metadata, and it is what
     the provenance record written afterwards actually attests to.

Usage:
    python3 scripts/verify_source_provenance.py --lean-root /path/to/leray-hopf
    python3 scripts/verify_source_provenance.py \\
        --lean-root /path/to/leray-hopf --pin-file extracted/PIN \\
        --nodes-json site/data/nodes.json --sources-json site/data/sources.json

Exits non-zero (fail closed) and prints every violated check if any check
fails; exits 0 and prints a PASS line per check otherwise.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# Failure messages here interpolate payload-supplied values (slugs, file paths) into the
# public Actions log, and this gate runs BEFORE the leak scan — so nothing downstream can
# mask them. A `file` field containing a credential or a local path would be disclosed by
# the very diagnostic that rejected it. Reuse the scanner's redactor so there is one list
# of secret shapes rather than two that drift apart.
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from scan_generated_payload import redact_all as _redact_all
except ImportError:  # pragma: no cover - scanner absent; degrade to omitting the value
    def _redact_all(fragment: str) -> str:
        return '‹value withheld: leak scanner unavailable for redaction›'


def safe(value: object) -> str:
    """A payload-supplied value, redacted, for interpolation into a failure message."""
    return _redact_all(str(value))


def run_git(lean_root: Path, *args: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        ['git', '-C', str(lean_root), *args],
        capture_output=True, text=True,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def check_pin_match(lean_root: Path, pin: str, failures: list[str], passes: list[str]) -> None:
    code, out, err = run_git(lean_root, 'rev-parse', 'HEAD')
    if code != 0:
        failures.append(
            f'pin_match: `git -C {lean_root} rev-parse HEAD` failed (not a git '
            f'checkout, or --lean-root is wrong): {err or out}'
        )
        return
    head = out
    if head != pin:
        failures.append(
            f'pin_match: --lean-root HEAD ({head}) does not equal extracted/PIN ({pin})'
        )
        return
    passes.append(f'pin_match: --lean-root HEAD == PIN ({pin})')


def check_clean_detached(lean_root: Path, failures: list[str], passes: list[str]) -> None:
    code, out, err = run_git(lean_root, 'status', '--porcelain')
    if code != 0:
        failures.append(
            f'clean_detached: `git -C {lean_root} status --porcelain` failed: {err or out}'
        )
        return
    if out:
        failures.append(
            f'clean_detached: --lean-root checkout is not clean; git status --porcelain '
            f'reported:\n{out}'
        )
        return

    code, out, err = run_git(lean_root, 'symbolic-ref', '-q', 'HEAD')
    if code == 0:
        failures.append(
            f'clean_detached: --lean-root HEAD is attached to a branch ({out}), not '
            f'detached at a fixed commit; the checkout could move underneath the build'
        )
        return
    passes.append('clean_detached: --lean-root checkout is clean and HEAD is detached')


def check_source_text_matches_checkout(lean_root: Path, nodes: dict, sources: dict,
                                       failures: list[str], passes: list[str],
                                       sample: int = 0) -> None:
    """Every embedded snippet must equal the exact file/line range in the pinned checkout.

    Until this existed the gate verified *metadata* — that HEAD equals the PIN, that the
    checkout is clean, that counts and keys line up — but never that the shipped text is
    what that commit actually says. A payload with correct pins, correct counts and
    `TAMPERED SOURCE` in every entry passed all four checks, and the provenance record
    written afterwards would then attest to it. Checking the bytes is what makes "this came
    from that commit" a statement about the content rather than about the bookkeeping.

    `sample=N` compares a deterministic subset (every k-th declaration) for a quick local
    run; the default compares all of them, which is what CI does.
    """
    nodes_list = nodes.get('nodes')
    src_map = sources.get('sources')
    if not isinstance(nodes_list, list) or not isinstance(src_map, dict):
        failures.append('source_text: nodes.json "nodes" and/or sources.json "sources" '
                        'are missing or not of the expected type')
        return

    file_cache: dict[str, list[str] | None] = {}

    root_resolved = lean_root.resolve()

    # Physical containment is not enough: `.git/HEAD` resolves inside the checkout, and
    # `git status --porcelain` never reports changes under `.git`, so a payload naming git
    # administrative state would pass every gate and be attested as "source from the pinned
    # commit". A declaration may only be sourced from a file the commit actually tracks.
    #
    # Modes matter, not just names: a tracked SYMLINK (mode 120000) such as
    # `Foo.lean -> .git/HEAD` appears in ls-tree, resolves inside the checkout, and leaves
    # `git status` clean — so reading it through the filesystem would serve git
    # administrative bytes under a legitimate-looking tracked path. Only regular file blobs
    # (100644 / 100755) may be a declaration source.
    code, tracked_out, tracked_err = run_git(lean_root, 'ls-tree', '-r', 'HEAD')
    if code != 0:
        failures.append('source_text: could not list tracked files at HEAD '
                        f'({tracked_err or tracked_out})')
        return
    tracked: set[str] = set()
    for line in tracked_out.splitlines():
        meta, _, name = line.partition('\t')
        parts = meta.split()
        if len(parts) >= 2 and parts[0] in ('100644', '100755') and parts[1] == 'blob':
            tracked.add(name)

    def lines_of(rel: str) -> list[str] | None:
        if rel not in file_cache:
            # `lean_root / rel` is NOT safe on its own: pathlib lets an absolute `rel`
            # replace the base entirely, and `..` walks out of it. A payload claiming
            # `file: /etc/hostname` or `../.git/config` would then be compared against —
            # and agree with — a file outside the pinned checkout, because the builder
            # resolves it the same way. Every provenance check would pass while the
            # artifact carried bytes from an unrelated runner file. Confine it here.
            candidate = (lean_root / rel).resolve()
            if not candidate.is_relative_to(root_resolved):
                file_cache[rel] = None
            else:
                try:
                    file_cache[rel] = candidate.read_text(
                        encoding='utf-8', errors='replace').splitlines()
                except OSError:
                    file_cache[rel] = None
        return file_cache[rel]

    def escapes_checkout(rel: str) -> bool:
        return not (lean_root / rel).resolve().is_relative_to(root_resolved)

    candidates = [n for n in nodes_list if n.get('has_source')]
    if sample and sample > 1:
        candidates = candidates[::sample]

    mismatches: list[str] = []
    compared = 0
    for node in candidates:
        slug = node.get('slug')
        embedded = src_map.get(slug)
        if embedded is None:
            mismatches.append(f'{safe(slug)}: marked has_source but absent from sources.json')
            continue
        rel, start, end = node.get('file'), node.get('startLine'), node.get('endLine')
        # `isinstance(True, int)` is True in Python, so a JSON `startLine: true` would
        # otherwise pass and select line 1.
        def is_line_no(x: object) -> bool:
            return isinstance(x, int) and not isinstance(x, bool)

        if not rel or not is_line_no(start) or not is_line_no(end):
            mismatches.append(f'{safe(slug)}: missing file/startLine/endLine for verification')
            continue
        if escapes_checkout(rel):
            mismatches.append(
                f'{safe(slug)}: file "{safe(rel)}" resolves outside the pinned checkout — '
                f'a declaration may only be sourced from within it')
            continue
        if rel not in tracked:
            mismatches.append(
                f'{safe(slug)}: file "{safe(rel)}" is not a regular tracked file at HEAD '
                f'in the pinned checkout — only a regular blob the commit actually '
                f'contains may be a source (symlinks and submodules are rejected)')
            continue
        lines = lines_of(rel)
        if lines is None:
            mismatches.append(f'{safe(slug)}: {safe(rel)} not readable in the pinned checkout')
            continue
        # A range must actually address lines. Python slicing is forgiving in exactly the
        # wrong way here: `startLine: 0, endLine: 0` slices to the empty string, which then
        # compares equal to an empty embedded snippet, so a payload naming no real
        # declaration range would pass. Out-of-range values truncate silently for the same
        # reason.
        if not (1 <= start <= end <= len(lines)):
            mismatches.append(
                f'{safe(slug)}: invalid line range {start}-{end} for {safe(rel)} '
                f'({len(lines)} lines) — must satisfy 1 <= startLine <= endLine <= EOF')
            continue
        expected = '\n'.join(lines[start - 1:end])
        # Exact comparison. Normalising trailing newlines on both sides would let a payload
        # differ from the declared range by appended/removed newlines and still be reported
        # as byte-identical — which is precisely the guarantee this check advertises.
        if embedded != expected:
            mismatches.append(f'{safe(slug)}: embedded text differs from {safe(rel)}:{start}-{end}')
        compared += 1
        if len(mismatches) >= 10:
            mismatches.append('… (further mismatches suppressed)')
            break

    if mismatches:
        failures.append('source_text: embedded source does not match the pinned checkout:\n'
                        + '\n'.join(f'    {m}' for m in mismatches))
    else:
        failures_note = f' (sampled every {sample}th)' if sample and sample > 1 else ''
        passes.append(f'source_text: all {compared} embedded snippets match their file/line '
                      f'range in the pinned checkout{failures_note}')


def check_source_coverage(nodes: dict, sources: dict, failures: list[str], passes: list[str]) -> None:
    """source_count == decl_count (zero misses), cross-checked against sources.json's own
    declared count, its actual "sources" object, and the has_source:true node slugs — so a
    stale or malformed sources.json paired with a fresh nodes.json (or vice versa) is caught
    here rather than only in pin_consistency.

    Every sub-check below is mandatory (not conditional on the payload happening to have the
    expected shape): a missing or wrong-typed field is itself a failure, not something to skip
    past. notes#32 owner review (PR #114): an earlier version only cross-checked the "sources"
    object's size when it happened to already be a dict, so a missing or non-object "sources"
    field passed as long as the declared counts matched — fail-open exactly where this gate is
    supposed to be fail-closed.
    """
    source_count = nodes.get('source_count')
    decl_count = nodes.get('decl_count')
    if source_count is None or decl_count is None:
        failures.append(
            'source_coverage: nodes.json is missing source_count and/or decl_count'
        )
        return
    # Counts must be genuine integers. `True` and `1.0` compare and `len()`-compare exactly
    # like `1`, so malformed count metadata would pass every comparison below and then be
    # copied verbatim into build-provenance.json — attested as if it had been checked.
    # (`isinstance(True, int)` is True in Python, hence the explicit bool exclusion.)
    for label, value in (('nodes.json source_count', source_count),
                         ('nodes.json decl_count', decl_count)):
        if isinstance(value, bool) or not isinstance(value, int):
            failures.append(
                f'source_coverage: {label} is not an integer: {value!r} '
                f'({type(value).__name__})'
            )
            return
    if source_count > decl_count:
        failures.append(
            f'source_coverage: source_count ({source_count}) exceeds decl_count '
            f'({decl_count}) — impossible for a valid build; nodes.json is internally '
            f'inconsistent'
        )
        return
    if source_count != decl_count:
        misses = decl_count - source_count
        failures.append(
            f'source_coverage: source_count ({source_count}) != decl_count '
            f'({decl_count}) — {misses} declaration(s) had no readable source range; '
            f're-run build_site_data.py --lean-root and inspect its '
            f'"records had no readable source range" warning'
        )
        return

    node_list = nodes.get('nodes')
    if not isinstance(node_list, list):
        failures.append('source_coverage: nodes.json "nodes" field is missing or not a list')
        return
    if len(node_list) != decl_count:
        failures.append(
            f'source_coverage: nodes.json declares decl_count={decl_count} but its '
            f'"nodes" array has {len(node_list)} entries'
        )
        return

    sources_source_count = sources.get('source_count')
    if not (sources_source_count is None
            or (isinstance(sources_source_count, int)
                and not isinstance(sources_source_count, bool))):
        failures.append(
            f'source_coverage: sources.json source_count is not an integer: '
            f'{sources_source_count!r} ({type(sources_source_count).__name__})'
        )
        return
    if sources_source_count is None:
        failures.append('source_coverage: sources.json is missing source_count')
        return
    if source_count != sources_source_count:
        failures.append(
            f'source_coverage: nodes.json source_count ({source_count}) != sources.json '
            f'source_count ({sources_source_count}) — the two payloads were built from '
            f'different runs and do not agree'
        )
        return

    sources_map = sources.get('sources')
    if not isinstance(sources_map, dict):
        failures.append(
            'source_coverage: sources.json "sources" field is missing or not a JSON object'
        )
        return
    if len(sources_map) != sources_source_count:
        failures.append(
            f'source_coverage: sources.json declares source_count={sources_source_count} '
            f'but its "sources" object has {len(sources_map)} entries'
        )
        return

    has_source_slugs = {n.get('slug') for n in node_list if n.get('has_source')}
    sources_slugs = set(sources_map.keys())
    if has_source_slugs != sources_slugs:
        missing = sorted(has_source_slugs - sources_slugs)[:5]
        extra = sorted(sources_slugs - has_source_slugs)[:5]
        failures.append(
            f'source_coverage: the set of node slugs with has_source:true does not match '
            f'the "sources" object\'s keys (missing from sources.json: {missing}; present '
            f'in sources.json but not marked has_source:true in nodes.json: {extra})'
        )
        return

    passes.append(
        f'source_coverage: source_count == decl_count == sources.json source_count == '
        f'len(sources.json "sources") == len(has_source:true slugs) == {decl_count} '
        f'(zero misses, cross-checked against sources.json)'
    )


def check_pin_consistency(pin: str, nodes: dict, sources: dict, failures: list[str], passes: list[str]) -> None:
    """nodes.json pin and sources.json pin must both equal the PIN this build was run
    for — not merely equal each other, which a stale-but-matching pair from a previous
    run could also satisfy."""
    nodes_pin = nodes.get('pin')
    sources_pin = sources.get('pin')
    if not nodes_pin or not sources_pin:
        failures.append(
            f'pin_consistency: missing pin field(s) — nodes.json pin={nodes_pin!r}, '
            f'sources.json pin={sources_pin!r}'
        )
        return
    if nodes_pin != pin:
        failures.append(
            f'pin_consistency: nodes.json pin ({nodes_pin}) != extracted/PIN ({pin}) — '
            f'nodes.json appears to be stale'
        )
        return
    if sources_pin != pin:
        failures.append(
            f'pin_consistency: sources.json pin ({sources_pin}) != extracted/PIN ({pin}) '
            f'— sources.json appears to be stale'
        )
        return
    passes.append(f'pin_consistency: nodes.json pin == sources.json pin == extracted/PIN ({pin})')


def load_json(path: Path, label: str, failures: list[str]) -> dict | None:
    if not path.is_file():
        failures.append(f'{label}: file not found: {path}')
        return None
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        failures.append(f'{label}: invalid JSON in {path}: {exc}')
        return None
    if not isinstance(data, dict):
        failures.append(
            f'{label}: expected a JSON object at the top level of {path}, got '
            f'{type(data).__name__}'
        )
        return None
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--lean-root', required=True,
                        help='Path to the leray-hopf checkout used for the source-enabled build')
    parser.add_argument('--pin-file', default=str(REPO_ROOT / 'extracted' / 'PIN'),
                        help='Path to extracted/PIN (default: %(default)s)')
    parser.add_argument('--nodes-json', default=str(REPO_ROOT / 'site' / 'data' / 'nodes.json'),
                        help='Path to the built nodes.json (default: %(default)s)')
    parser.add_argument('--sample', type=int, default=0,
                        help='compare only every Nth embedded snippet against the checkout '
                             '(default 0 = compare all; CI must use the default)')
    parser.add_argument('--sources-json', default=str(REPO_ROOT / 'site' / 'data' / 'sources.json'),
                        help='Path to the built sources.json (default: %(default)s)')
    args = parser.parse_args()

    lean_root = Path(args.lean_root)
    pin_file = Path(args.pin_file)
    nodes_path = Path(args.nodes_json)
    sources_path = Path(args.sources_json)

    failures: list[str] = []
    passes: list[str] = []

    pin: str | None = None
    if not pin_file.is_file():
        failures.append(f'pin_match: PIN file not found: {pin_file}')
    else:
        pin = pin_file.read_text(encoding='utf-8').strip()
        if not pin:
            failures.append(f'pin_match: PIN file is empty: {pin_file}')
            pin = None

    if not lean_root.is_dir():
        failures.append(f'pin_match: --lean-root does not exist or is not a directory: {lean_root}')
    else:
        if pin is not None:
            check_pin_match(lean_root, pin, failures, passes)
        check_clean_detached(lean_root, failures, passes)

    nodes = load_json(nodes_path, 'source_coverage/pin_consistency (nodes.json)', failures)
    sources = load_json(sources_path, 'source_coverage/pin_consistency (sources.json)', failures)

    if nodes is not None and sources is not None:
        check_source_coverage(nodes, sources, failures, passes)
        if pin is not None:
            check_pin_consistency(pin, nodes, sources, failures, passes)
        check_source_text_matches_checkout(lean_root, nodes, sources, failures, passes,
                                           sample=args.sample)

    for p in passes:
        print(f'PASS: {p}')

    if failures:
        print(f'\n{len(failures)} provenance check(s) FAILED:', file=sys.stderr)
        for f in failures:
            print(f'  FAIL: {f}', file=sys.stderr)
        return 1

    print(f'\nAll {len(passes)} provenance checks passed.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
