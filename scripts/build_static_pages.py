#!/usr/bin/env python3
"""
build_static_pages.py — prerendered per-declaration pages and a sitemap (notes#73).

The viewer is a hash-routing SPA: `#/decl/<slug>` is a fragment, and fragments are never
sent to a server, so all 1425 declarations are served as one HTML document. A crawler that
does not execute script sees a single generic title and description no matter which
declaration was linked. `app.js` rewrites the title/description/canonical on every route
change, but that only helps clients that run JS — which is why notes#73's acceptance
criterion ("declaration-level metadata retrievable by major search engines") was still
unmet after that work.

This script emits, for every declaration, a real path that a crawler can fetch:

    site/decl/<segment>/index.html   self-contained page with the declaration's prose
    site/sitemap.xml                 every emitted page, for robots.txt to point at

Design notes
------------

* **Additive, not a migration** (owner decision, 2026-08-03). The existing `#/decl/<slug>`
  URLs are untouched and keep working; these pages are new addresses, not replacements.
  Nothing here edits `app.js` or the SPA's routing. Every page links into the interactive
  view, and `rel="canonical"` points at the static path (orchestrator decision) so search
  engines index the address that can actually be served to them.
* **No inline script and no `<base>`.** `site/index.html` ships a strict CSP with
  `script-src 'self'` and `base-uri 'none'`; these pages reuse it verbatim, so relative
  asset references are written out as `../../` rather than rebased, and the KaTeX pass
  lives in a separate `decl-page.js` file rather than an inline block.
* **Deterministic.** Declarations are emitted in sorted slug order, nothing reads the
  clock (the sitemap carries no `lastmod`; see `render_sitemap`), and stale output is
  removed before writing, so a rebuild of an unchanged payload produces byte-identical
  output and a rebuild of a changed one produces a reviewable diff.

Path segments
-------------

A slug is a Lean declaration name; it is *not* automatically a safe path segment. Three
hazards are handled explicitly rather than hoped away:

* **Non-ASCII.** Nine slugs carry `ℝ`, `ξ` or `ₗ`. They are percent-encoded (UTF-8, upper
  hex) so the directory name and the URL are the same string.
* **Apostrophes.** Fifteen slugs end in `'` (`H1Sigma'`). Also percent-encoded — legal in
  a path, but not worth the quoting hazard in shell and HTML.
* **Case-insensitive collisions.** `LerayHopf.StageData` and `LerayHopf.stageData` differ
  only in case, as do the `_R3` pair. On a case-insensitive filesystem (macOS, Windows)
  one would silently overwrite the other, so *which* page survived would depend on the
  developer's machine — the exact nondeterminism this script is supposed to avoid. Every
  member of a colliding group therefore gets a short digest suffix. Members are suffixed
  as a group so the result does not depend on iteration order.

Usage:
    python3 scripts/build_static_pages.py
    python3 scripts/build_static_pages.py --site site --base-url https://example.org/x/
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SITE = REPO_ROOT / 'site'
DEFAULT_BASE_URL = 'https://uda-lab.github.io/leray-hopf-notes/'

# Characters kept verbatim in a path segment. Everything else is percent-encoded.
SAFE_SEGMENT_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.-_'

# How much of the first prose paragraph goes into <meta name="description">.
DESCRIPTION_LIMIT = 200


def encode_segment(slug: str) -> str:
    """Percent-encode a slug into a path segment, keeping the URL and the directory equal."""
    return quote(slug, safe=SAFE_SEGMENT_CHARS)


def segment_map(slugs: list[str]) -> dict[str, str]:
    """slug -> path segment, with case-insensitive collisions disambiguated.

    The suffix is applied to every member of a colliding group, never to "the second one
    seen": a rule that depends on iteration order would make the output depend on the order
    of `nodes.json`, and the point of this map is that it does not.
    """
    encoded = {slug: encode_segment(slug) for slug in slugs}
    folded: dict[str, list[str]] = {}
    for slug, seg in encoded.items():
        folded.setdefault(seg.lower(), []).append(slug)
    out: dict[str, str] = {}
    for group in folded.values():
        if len(group) == 1:
            slug = group[0]
            out[slug] = encoded[slug]
            continue
        for slug in group:
            digest = hashlib.sha256(slug.encode('utf-8')).hexdigest()[:8]
            out[slug] = f'{encoded[slug]}~{digest}'
    return out


# --------------------------------------------------------------------------- prose

WIKILINK = re.compile(r'\[\[([^\]|]*)(?:\|([^\]]*))?\]\]')
BOLD = re.compile(r'\*\*(.+?)\*\*')
CODE = re.compile(r'`([^`]+)`')
MATH_SPAN = re.compile(r'\$\$.+?\$\$|\$[^$\n]+\$', re.S)


def _inline_html(text: str) -> str:
    """Escape a prose fragment and apply the inline markup the corpus actually uses.

    Math spans are masked out first so that `**` or a backtick *inside* a formula is left
    alone for KaTeX; the same reason `app.js` masks them before tokenizing. Wikilinks are
    reduced to their display word: resolving one needs the SPA's slug index, and a link
    that silently pointed at the wrong declaration would be worse than plain text — the
    more so because full-name resolution is ambiguous for colliding names (notes#139).
    """
    maths: list[str] = []

    def mask(m: re.Match[str]) -> str:
        maths.append(m.group(0))
        return f'\x00{len(maths) - 1}\x00'

    masked = MATH_SPAN.sub(mask, text)
    masked = WIKILINK.sub(lambda m: (m.group(1) or ''), masked)
    escaped = html.escape(masked, quote=False)
    escaped = BOLD.sub(lambda m: f'<strong>{m.group(1)}</strong>', escaped)
    escaped = CODE.sub(lambda m: f'<code>{m.group(1)}</code>', escaped)
    return re.sub(r'\x00(\d+)\x00', lambda m: html.escape(maths[int(m.group(1))], quote=False),
                  escaped)


def prose_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in (text or '').split('\n\n') if p.strip()]


def plain_text(text: str) -> str:
    """Prose with markup and math delimiters removed, for <meta> attributes."""
    stripped = WIKILINK.sub(lambda m: (m.group(1) or ''), text or '')
    stripped = BOLD.sub(lambda m: m.group(1), stripped)
    stripped = CODE.sub(lambda m: m.group(1), stripped)
    stripped = stripped.replace('$$', ' ').replace('$', '')
    return re.sub(r'\s+', ' ', stripped).strip()


def truncate(text: str, limit: int = DESCRIPTION_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + '…'


# --------------------------------------------------------------------------- page

def render_page(node: dict, segment: str, base_url: str, pin: str) -> str:
    name = node.get('name') or node.get('slug') or ''
    short = node.get('shortName') or name
    corpus = node.get('corpus') or {}
    statement = corpus.get('statement_ja') or ''
    paragraphs = prose_paragraphs(statement)
    summary = truncate(plain_text(paragraphs[0])) if paragraphs else (
        truncate(plain_text(node.get('doc') or '')) or f'{name} の宣言ページ。')
    canonical = f'{base_url}decl/{segment}/'
    title = f'{short} — leray-hopf-notes'
    esc = lambda s: html.escape(s, quote=True)  # noqa: E731

    body = []
    for p in paragraphs:
        body.append(f'    <p>{_inline_html(p)}</p>')
    if not body:
        body.append('    <p>この宣言には日本語の解説がまだありません。</p>')

    where = ''
    if node.get('file'):
        loc = esc(str(node['file']))
        if node.get('startLine'):
            loc += f':{int(node["startLine"])}'
        where = f'    <p class="decl-origin">定義位置: <code>{loc}</code></p>\n'

    kind = esc(str(node.get('kind') or ''))
    hash_href = '../../#/decl/' + quote(str(node.get('slug') or ''), safe='')

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)}</title>
  <meta name="description" content="{esc(summary)}">
  <link rel="canonical" href="{esc(canonical)}">
  <meta property="og:type" content="article">
  <meta property="og:site_name" content="leray-hopf-notes">
  <meta property="og:title" content="{esc(title)}">
  <meta property="og:description" content="{esc(summary)}">
  <meta property="og:url" content="{esc(canonical)}">
  <meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'">
  <link rel="stylesheet" href="../../vendor/katex/katex.min.css">
  <link rel="stylesheet" href="../../styles.css">
  <script defer src="../../vendor/katex/katex.min.js"></script>
  <script defer src="../../vendor/katex/auto-render.min.js"></script>
  <script defer src="../../decl-page.js"></script>
</head>
<body>
  <header>
    <a href="../../">leray-hopf-notes</a>
  </header>
  <main id="app">
    <h1><code>{esc(name)}</code></h1>
    <p class="decl-kind">{kind}</p>
{where}{chr(10).join(body)}
    <p><a href="{esc(hash_href)}">インタラクティブ表示で開く（依存グラフ・Lean ソース・参照の展開）</a></p>
  </main>
  <footer>
    <p>uda-lab/leray-hopf @ <code>{esc(pin)}</code></p>
  </footer>
</body>
</html>
"""


def render_sitemap(entries: list[tuple[str, str]], base_url: str) -> str:
    """Every emitted page, plus the site root.

    No `<lastmod>`. The only date available is the payload's `built_at`, which moves on
    every CI run whether or not a declaration changed — a lastmod that claims change when
    there was none is the kind search engines learn to discount, and it would churn the
    file on unrelated rebuilds. Omitting it is allowed by the sitemap schema and is honest.
    """
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    lines.append('  <url>')
    lines.append(f'    <loc>{html.escape(base_url, quote=False)}</loc>')
    lines.append('  </url>')
    for _slug, segment in entries:
        lines.append('  <url>')
        lines.append(f'    <loc>{html.escape(base_url, quote=False)}decl/{segment}/</loc>')
        lines.append('  </url>')
    lines.append('</urlset>')
    return '\n'.join(lines) + '\n'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--site', default=str(DEFAULT_SITE),
                        help='published tree (default: site/)')
    parser.add_argument('--base-url', default=DEFAULT_BASE_URL,
                        help='canonical base URL, with trailing slash')
    args = parser.parse_args()

    site = Path(args.site).resolve()
    base_url = args.base_url if args.base_url.endswith('/') else args.base_url + '/'
    nodes_path = site / 'data' / 'nodes.json'
    if not nodes_path.is_file():
        print(f'ERROR: {nodes_path} not found — run build_site_data.py first', file=sys.stderr)
        return 1
    try:
        payload = json.loads(nodes_path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        print(f'ERROR: nodes.json is not valid JSON: {exc}', file=sys.stderr)
        return 1

    nodes = payload.get('nodes')
    if not isinstance(nodes, list) or not nodes:
        print('ERROR: nodes.json has no "nodes" array to render', file=sys.stderr)
        return 1
    for node in nodes:
        if not isinstance(node, dict) or not node.get('slug'):
            print('ERROR: nodes.json contains an entry with no slug', file=sys.stderr)
            return 1

    # Stale output goes before anything is written: a declaration removed upstream must not
    # keep a live page (and a live sitemap entry) describing something that no longer exists.
    decl_root = site / 'decl'
    if decl_root.exists():
        shutil.rmtree(decl_root)
    sitemap_path = site / 'sitemap.xml'
    if sitemap_path.exists():
        sitemap_path.unlink()

    pin = str(payload.get('pin') or '')
    ordered = sorted(nodes, key=lambda n: str(n['slug']))
    segments = segment_map([str(n['slug']) for n in ordered])

    entries: list[tuple[str, str]] = []
    for node in ordered:
        slug = str(node['slug'])
        segment = segments[slug]
        page_dir = decl_root / segment
        page_dir.mkdir(parents=True, exist_ok=False)
        (page_dir / 'index.html').write_text(
            render_page(node, segment, base_url, pin), encoding='utf-8')
        entries.append((slug, segment))

    sitemap_path.write_text(render_sitemap(entries, base_url), encoding='utf-8')

    total = sum((decl_root / seg / 'index.html').stat().st_size for _s, seg in entries)
    suffixed = sum(1 for _s, seg in entries if '~' in seg)
    print(f'Wrote {len(entries)} declaration pages under {decl_root} '
          f'({total / 1048576:.1f} MiB) and {sitemap_path.name}')
    if suffixed:
        print(f'  {suffixed} page(s) carry a digest suffix (case-insensitive slug collision)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
