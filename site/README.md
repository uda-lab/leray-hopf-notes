# site/

Pure-static interactive viewer. No framework, no bundler, no npm at runtime; the only
vendored dependency is KaTeX (see `vendor/VENDORED.md`).

## Structure

```
site/
  index.html            entry point
  app.js                vanilla JS SPA (hash routing, all rendering client-side)
  styles.css
  vendor/
    VENDORED.md          how KaTeX was vendored (version + re-vendor commands)
    katex/               katex.min.js + katex.min.css + auto-render.min.js + fonts/
  data/
    .gitkeep             preserves directory (generated JSON is not committed)
    nodes.json           built by scripts/build_site_data.py (decls ⋈ corpus, no source bodies)
    sources.json         built by scripts/build_site_data.py (verbatim Lean source, lazy-loaded)
    coverage.json        built by scripts/coverage.py
    
**Note:** `site/data/*.json` files are generated artifacts, not source-reviewed files.
They are produced locally via `build_site_data.py` and in CI via `.github/workflows/ci.yml`.
CI builds a source-enabled payload (leray-hopf checked out at `extracted/PIN`) on every
pull request and every push to `main`, and deploys it to GitHub Pages on `main` once the
owner has explicitly enabled the `vars.PAGES_DEPLOY_ENABLED` repository variable
(notes#32 Phase B — see "CI build workflow" below).
```

## License scope

The site viewer code is licensed as a software component under Apache-2.0. Mathematical
explanations, annotations, and prose content rendered by the viewer are licensed under
CC-BY-4.0 unless otherwise noted. Generated `site/data/*.json` files are derived artifacts,
not source-reviewed material; downstream users should observe the licenses of the Lean
source and annotation/prose inputs from which they were generated. Vendored third-party
assets under `site/vendor/` (currently KaTeX, MIT) carry their own upstream license — see
`site/vendor/VENDORED.md` and `site/vendor/katex/LICENSE` — and are not covered by the
Apache-2.0/CC-BY-4.0 split above. See the root `LICENSE.md` for the full, authoritative
per-path scope.

## Build & preview

### Local build

**Important:** After a fresh clone, `site/data/*.json` files do not exist (they are gitignored).
You must run `build_site_data.py` before serving the site.

```bash
# from repo root — build site data first
# Option 1: with verbatim Lean source (requires leray-hopf checkout at extracted/PIN)
python3 scripts/build_site_data.py --lean-root /path/to/leray-hopf
# -> site/data/nodes.json (with has_source:true) + site/data/sources.json (populated)

# Option 2: without leray-hopf checkout (source-less build)
python3 scripts/build_site_data.py
# -> site/data/nodes.json (with has_source:false) + site/data/sources.json (empty stub)

# Then serve (any static server; no build step, no server-side code)
cd site && python3 -m http.server 8000
# open http://localhost:8000/
```

### CI build workflow (Phase B: public deployment)

`.github/workflows/ci.yml` runs on every pull request and every push to `main` (the only
branch `push:` is scoped to), as four jobs (`build-artifact` is
gated on the first two passing, via `needs:`, rather than re-running their checks;
`deploy-pages` is gated on `build-artifact`):

1. `validate` — corpus/glossary/prose lint, coverage report, a structure-only
   `scripts/build_site_data.py` run, and the `scripts/verify_source_provenance.py`
   regression tests
2. `render-tests` — `npm test` (jsdom render harness)
3. `build-artifact` — reads `extracted/PIN`, checks out `uda-lab/leray-hopf` at that
   exact commit using the workflow's default `github.token` (`leray-hopf` is public, so
   this is a plain read — not an unauthenticated clone, but not a privileged one
   either; workflow `permissions:` only restricts API calls against *this* repo), builds
   site data **with** `--lean-root` (source-enabled), runs
   `scripts/verify_source_provenance.py` as a fail-closed gate (see below), generates a
   size report, and uploads the entire `site/` directory as a workflow artifact (every
   push and PR — for inspection) plus a `github-pages` deployment artifact (only on
   `main`, and only once `vars.PAGES_DEPLOY_ENABLED == 'true'` — see below)
4. `deploy-pages` — `needs: [build-artifact]`; deploys the `github-pages` artifact via
   `actions/deploy-pages`, gated identically to the artifact upload above

PRs build and validate the source-enabled payload but never deploy it — only a push
(or manual `workflow_dispatch`) on `main`, with the deploy gate variable set, reaches
`deploy-pages`.

**Explicit deploy gate: `vars.PAGES_DEPLOY_ENABLED`.**
Rather than let "Pages isn't configured in Settings yet" stand in as an implicit block
on publishing, the workflow requires an owner-controlled repository Actions variable
(`Settings → Secrets and variables → Actions → Variables → PAGES_DEPLOY_ENABLED`,
unset/false by default) to be explicitly set to `true` before the `github-pages`
artifact is even built, let alone deployed. This makes "ready to publish" an
affirmative decision the owner makes, not a side effect of enabling Pages for
unrelated reasons.

**Published provenance: `build-provenance.json` + `SHA256SUMS`.** The build-time gate
below proves the payload came from the exact `extracted/PIN` commit — and that proof
used to stop at the workflow log, leaving the deployed site carrying no evidence of it.
`scripts/emit_build_provenance.py` writes the evidence into the payload itself: the
pinned source commit and its URL, the payload counts (`decl_count` / `source_count` /
`proof_status_counts`), the CI run that produced it (or an explicit `"ci": null` for a
local build — it does not invent a run id), and the SHA-256 of every published file — the whole `site/` tree, not just the data, since that is what the artifact steps upload.
Verification needs nothing but the deployed site:

```bash
cd site && sha256sum -c data/SHA256SUMS
```

`SHA256SUMS` covers the provenance record too, so a change to the evidence itself is
detectable; the record's own file list excludes itself and `SHA256SUMS`, refuses to write at
all if either `nodes.json`'s or `sources.json`'s pin disagrees with `extracted/PIN` — a
record attesting to the wrong commit would be worse than none — and clears any previous
run's record and digests first, so stale evidence cannot survive a refusal in a reused
workspace.

**Leak scan: `scripts/scan_generated_payload.py`.** The payload embeds verbatim Lean
source and the whole corpus, so it is where a stray absolute path, credential, or agent
transcript would actually become public. That audit was performed by hand once
(notes#32, 2026-07-16); this makes it a gate on every build, covering every `*.json`
in `site/data` (so payload files added later are scanned without editing the scanner)
plus a structural check that no declaration is sourced from a `Scratch/` module.

Its patterns are calibrated against a real source-enabled build, because the corpus is
full of prose that naive rules misread: a `[A-Za-z]:\\` "Windows drive" pattern matches
`$f:\mathbb R$` and `$\int\nabla u:\nabla u$`. Equally, "agent prose" is scoped to
machine-generated session artifacts (session ids, transcript paths, agent home
directories) and *not* to human-written provenance — the corpus deliberately cites
issues, PRs and review rounds, and flagging those would fail every build on content
that is published by design. `test/issue32_payload_hardening.test.py` pins both halves:
planted leaks must be caught, and that legitimate content must not be.

**Runtime provenance: the frontend refuses a mismatched payload.** `nodes.json` and
`sources.json` are fetched separately and joined in the browser, so a stale or swapped
`sources.json` would attach the wrong Lean text to the right declaration — the one
failure the build-time gate cannot see. `loadSources()` captures the expected pin at
request time, binds the source cache to it (so a reload that swaps in a different commit
refetches instead of serving the old cached text with no comparison at all), requires
*exact* agreement including one-sided absence, and rejects a payload whose `pin` differs, and the source panel says so
explicitly rather than degrading to "source not found", which would read like a missing
file and invite a pointless retry.

**Fail-closed provenance gate (notes#32).** `scripts/verify_source_provenance.py`
independently re-derives, rather than trusts, the following before any deployment can
proceed:
- the leray-hopf checkout's `git rev-parse HEAD` equals `extracted/PIN`, verified via
  `git` plumbing against the checkout itself, not the `ref:` string used to request it
- the checkout is clean (`git status --porcelain` empty) and HEAD is detached (not
  tracking a movable branch)
- `nodes.json`'s `source_count` equals `decl_count` (every declaration got embedded
  source; zero extraction misses), cross-checked against `sources.json`'s own declared
  `source_count`, the actual size of its `sources` object (required to be present and a
  JSON object — a missing/wrong-typed field is itself a failure, not skipped), and that
  the exact set of node slugs marked `has_source: true` matches `sources.json`'s keys
- **both** `nodes.json`'s and `sources.json`'s `pin` fields equal `extracted/PIN` — not
  merely each other, which a stale-but-mutually-consistent pair from an earlier run
  could also satisfy

Any violation exits non-zero and fails the `build-artifact` job, which blocks
`deploy-pages` via `needs:`. Run it locally as
`python3 scripts/verify_source_provenance.py --lean-root <path>`; see the script's
module docstring for the full rationale and `test/verify_source_provenance.test.py`
for the regression coverage.

**GitHub Pages must also be enabled by an admin.** Repository visibility and Pages
source configuration ("Settings → Pages → Source: GitHub Actions") are a separate
owner/admin action outside this workflow's scope (notes#32 non-goals). Even after
`vars.PAGES_DEPLOY_ENABLED` is set, the `deploy-pages` job fails at the
`actions/deploy-pages` step until Pages is enabled this way; `build-artifact` and
the rest of CI are unaffected.

### Source-enabled builds

To include verbatim Lean source in the site, `build_site_data.py` requires
`--lean-root <path>` pointing to a checkout of `uda-lab/leray-hopf` at the commit
specified in `extracted/PIN`. The script extracts source text from the Lean files
and populates `sources.json` for lazy loading.

Without `--lean-root`, the site still works but shows file:line references instead
of embedded source code.

`build_site_data.py` shells out to `coverage.py` by default, so a single invocation
refreshes both data files. Flags: `--no-coverage` (skip coverage refresh),
`--out <path>` (write nodes.json elsewhere; the paired `sources.json` is written next
to it unless `--sources-out` is supplied). A source-enabled build (with `--lean-root`)
keeps source bodies out of `nodes.json` itself: they live in the separate `sources.json`,
which the site lazy-loads per declaration only when a source panel is opened.

## Data flow

```
extracted/decls.json (or names-fallback.json)  +  corpus/**/*.yaml
        → scripts/build_site_data.py → site/data/nodes.json
                                     → site/data/sources.json
        → scripts/coverage.py        → site/data/coverage.json
                                      ↓
                          site/app.js loads static JSON files
```

The site loads `nodes.json` and `coverage.json` up front. It fetches `sources.json`
only when a declaration source panel is opened. Adding annotations (S3 seed) is
purely a corpus + rebuild operation — **no site code changes required**.

## Routes (hash-based)

- `#/` — home (2 capstone cards, coverage summary, chapter list)
- `#/chapter/<id>` — chapter page (defs group / theorems group; private helpers folded per file)
- `#/decl/<slug>` — declaration node page (Lean ⇄ Japanese, uses accordion, used-by, DAG links)
- `#/dag` — declaration dependency graph (type/value-constant edges, not a proof tree),
  progressive disclosure from the 2 capstone roots
- `#/coverage` — per-chapter × per-tier coverage table
- `#/proof-status` — every declaration whose `proof_status` is not the default `verified`
  (sorry / scaffold / retired / invalid-statement), generated straight from `nodes.json`
- `#/search/<query>` — full name (substring) + short name (prefix) +
  statement_ja/proof_ja/tags/doc (substring) search, grouped by kind

`slug` is the display name when unique, else the declaration `id` (private-helper name
collisions; run `scripts/build_site_data.py` — it prints `Collision groups: N (M decls)`
and lists them in the `collisions` field of the generated `site/data/nodes.json` — for
the current collision count; corpus join for those keys off name+file, per notes#7).

### Page metadata (notes#73)

`app.js`'s `route()` calls `setPageMeta()` on every route change, which updates
`document.title`, `<meta name="description">`, `<link rel="canonical">`, and the
`og:*` meta tags to match the current route (site name / declaration name / chapter
label / etc.). `index.html` also carries static site-level `description`/`og:*` tags
for the pre-JS document paint. This improves browser tab titles, bookmarks, and
share/unfurl previews for tools that execute JS, but does **not** by itself make
per-declaration routes independently crawlable by search engines that don't execute
JS — the hash fragment is still one HTML document. See the "page metadata" comment
block in `app.js` and the remaining-work checklist on notes#73 for the prerendered
static-route follow-up that would close that gap.

## Graceful degradation

- **Empty corpus** — every node renders from extracted metadata with `未注釈` placeholders.
- **No `decls.json`** — falls back to `names-fallback.json` (skeleton: names/kinds/files,
  no signatures or dependency edges; `has_full_metadata: false`).
- **No `--lean-root`** — nodes carry `has_source: false` and `sources.json` is empty;
  the proof band shows the doc-comment + `file:startLine–endLine` reference instead
  of the Lean body.
