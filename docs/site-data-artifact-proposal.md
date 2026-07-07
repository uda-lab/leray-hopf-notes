# Task

Investigate the committed `site/data/nodes.json` artifact and propose the lowest-risk way to preserve the static-site UX while reducing repository diff noise and agent/token cost.

# Goal

Keep the current pure-static viewer behavior intact: `site/app.js` can load `data/nodes.json` and `data/coverage.json` from any static server, declaration pages can show Japanese annotations, dependency links, and the collapsed Lean source band, and contributors can still preview the site without a Pages-specific build step.

# Scope

## In

- Repository workflow for the generated `site/data/nodes.json` artifact.
- Diff/review handling for generated site data.
- Future migration options for splitting metadata, payloads, and embedded Lean source.

## Out

- Regenerating `site/data/nodes.json`.
- Changing `scripts/build_site_data.py`, `scripts/validate.py`, `scripts/count_decls.py`, schemas, corpus YAML, or the site runtime.
- Requiring a new CI/Pages deployment path in this proposal PR.

# Current state

`site/data/nodes.json` is a committed generated artifact built by `scripts/build_site_data.py`. The static app fetches it as one JSON payload and then fetches `site/data/coverage.json`.

Targeted measurements from the current tracked artifact:

- Tracked blob: `site/data/nodes.json`, `5,780,060` bytes.
- Gzipped payload size: `939,425` bytes.
- Declaration records: `1,412`.
- Annotated records: `1,412`.
- Source-bearing records: `1,412`.
- Raw embedded `source` text: `2,109,455` bytes before JSON escaping and indentation.
- Raw `doc` text: `403,919` bytes.
- Raw `signature` text: `327,547` bytes.
- Compact serialized corpus payloads: about `1,288,858` bytes.

The site already has a graceful no-source mode: when records have `has_source: false`, declaration pages show doc-comment text and `file:startLine-endLine` instead of the verbatim Lean body.

# Options

## Keep committed with generated/diff handling

Keep `site/data/nodes.json` committed and source-embedded. Mark it as generated in `.gitattributes`, and document that reviews should inspect generator/corpus/extracted changes plus aggregate validation output rather than reading the full generated diff.

Pros:

- Lowest implementation risk.
- Preserves current static hosting and local preview behavior.
- Keeps GitHub Pages/simple static deploys independent of a Lean checkout.
- Avoids touching the generator or site runtime.
- Immediately reduces GitHub diff noise for the generated file.

Cons:

- The full artifact still exists in Git history and working tree.
- Regeneration still creates a large local diff.
- Agents can still read it if prompted too broadly.

## Generate in CI or Pages

Stop committing `site/data/nodes.json` and build it during CI or Pages deployment.

Pros:

- Removes the large generated file from normal PR diffs.
- Makes generated output reproducible if CI pins all inputs.

Cons:

- Higher operational risk: the current source-embedded artifact requires a `lean-pde` checkout at `extracted/PIN`.
- Running without `--lean-root` would preserve the site but remove the verbatim Lean source UX.
- Pages/local preview would need a documented build step and artifact handling.
- The generator currently shells out to coverage by default, so the build contract would need to cover both site data files.

## Shard metadata, payload, and source

Split the single payload into an index plus smaller JSON shards, for example:

- `site/data/index.json`: global metadata, chapters, capstones, slug/name lookup, dependency edges, and lightweight declaration metadata.
- `site/data/nodes/<slug>.json`: per-declaration corpus, doc, signature, and source state.
- Optional chapter shards for chapter pages and search.

Pros:

- Reduces initial load and localizes future diffs.
- Lets route-level UI load only what it needs.
- Can preserve static hosting because shards are still static files.

Cons:

- Requires coordinated changes to the generator, app loading model, tests, and failure states.
- Search and DAG routes need either a sufficiently rich index or additional shards.
- Many small files can increase repository churn unless the shard boundaries are chosen carefully.

## Separate embedded Lean source

Keep node metadata and annotation payloads together, but move verbatim Lean source into a source-specific file or per-node source shards loaded only when the user expands the Lean source detail.

Pros:

- Directly targets a large contributor to artifact size: about `2.1` MB of raw source text before JSON overhead.
- Matches the existing UI: source is collapsed by default and already has a no-source fallback.
- Can preserve UX by lazy-loading source on demand and falling back to file/line references if the source shard is missing.
- Smaller blast radius than a full metadata/payload sharding redesign.

Cons:

- Still requires generator and app changes.
- Needs careful validation that every `has_source` record maps to an available source payload.
- Search/highlighting code must avoid assuming `node.source` is present at initial load.

# Recommendation

Use a two-step path.

First, keep `site/data/nodes.json` committed and mark it generated with `.gitattributes`:

```gitattributes
site/data/nodes.json linguist-generated
```

This is the lowest-risk immediate mitigation because it does not change generated data, the generator, the app, local preview, or Pages behavior. It reduces default GitHub diff noise while preserving the existing static-site UX.

Second, if artifact churn remains a problem after the corpus stabilizes, migrate only embedded Lean source out of `nodes.json` before attempting full sharding. Source separation gives the best size-to-risk ratio because the source body is collapsed by default, already optional in the data model, and has an existing fallback UX.

# Migration notes

For the immediate mitigation:

- No data migration is required.
- No rebuild is required.
- Reviewers should treat `site/data/nodes.json` as generated and inspect changes through `scripts/build_site_data.py`, corpus/extracted inputs, and aggregate validation output.

For a future source-separation migration:

- Add a generated source payload such as `site/data/source/<slug>.json` or a compact source map keyed by slug.
- Keep `has_source` as the UI contract, but make source text lazy-loaded when the source detail is expanded.
- Preserve the current fallback for missing source shards: doc-comment plus `file:startLine-endLine`.
- Add a validator that checks every `has_source: true` node has a corresponding source payload.
- Keep a temporary compatibility path for older `node.source` fields until the migration PR updates the committed artifact.

# Validation notes

Minimum validation for the current proposal:

- `git diff --stat` should show only docs and `.gitattributes`.
- `python3 scripts/validate.py` should pass.
- `python3 scripts/coverage.py` should pass and rewrite only deterministic coverage output, if any.
- `npm test` should pass.

Minimum validation for a future source-separation PR:

- Build site data with and without `--lean-root`.
- Verify `decl_count`, `annotated_count`, and dependency edge counts are unchanged.
- Verify source payload count equals `source_count` for source-embedded builds.
- Run the render tests and a static preview smoke test for declaration pages with source present and absent.
