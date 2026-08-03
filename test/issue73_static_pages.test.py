#!/usr/bin/env python3
"""
issue73_static_pages.test.py — regression checks for the prerendered declaration pages.

The pages exist so a crawler that does not run script can fetch a declaration; the checks
here therefore pin the properties that make that true (a real path per declaration, a
canonical pointing at it, the prose present in the markup) and the properties that make the
output safe to publish repeatedly (determinism, stale removal, no inline script).

Slug-to-path encoding gets the most attention because it is where the silent failures live:
a slug is a Lean declaration name, not a path segment, and the universe contains non-ASCII
names, apostrophes, and pairs differing only in case.

Run: python3 test/issue73_static_pages.test.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD = REPO_ROOT / 'scripts' / 'build_static_pages.py'
SIZE_REPORT = REPO_ROOT / 'scripts' / 'site_data_size_report.py'

CHECKS: list[str] = []


def check(label: str, cond: bool, detail: str = '') -> None:
    CHECKS.append(label)
    if cond:
        print(f'  ok  {label}')
    else:
        print(f'  FAIL {label}')
        if detail:
            print(f'       {detail[:600]}')
        sys.exit(1)


def run(script: Path, *args: str) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, str(script), *args],
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def node(slug: str, *, statement: str = '主張。', name: str | None = None) -> dict:
    return {
        'slug': slug, 'name': name or slug, 'shortName': slug.split('.')[-1],
        'kind': 'theorem', 'file': 'LerayHopf/R3/Foo.lean', 'startLine': 1, 'endLine': 2,
        'has_source': False, 'corpus': {'statement_ja': statement},
    }


def make_site(root: Path, nodes: list[dict], pin: str = 'a' * 40) -> Path:
    site = root / 'site'
    (site / 'data').mkdir(parents=True, exist_ok=True)
    (site / 'data' / 'nodes.json').write_text(json.dumps({
        'pin': pin, 'built_at': '2026-08-03T00:00:00Z', 'decl_count': len(nodes),
        'annotated_count': len(nodes), 'source_count': 0, 'has_source': False,
        'nodes': nodes,
    }, ensure_ascii=False), encoding='utf-8')
    return site


def pages(site: Path) -> dict[str, str]:
    return {p.parent.name: p.read_text(encoding='utf-8')
            for p in (site / 'decl').rglob('index.html')}


# --------------------------------------------------------------------------- tests

def test_emits_one_page_per_declaration() -> None:
    with tempfile.TemporaryDirectory() as td:
        site = make_site(Path(td), [node('LerayHopf.a'), node('LerayHopf.b')])
        code, out = run(BUILD, '--site', str(site))
        check('the generator succeeds', code == 0, out)
        got = pages(site)
    check('one page per declaration', sorted(got) == ['LerayHopf.a', 'LerayHopf.b'], str(sorted(got)))
    check('the page carries the declaration name in an h1',
          '<h1><code>LerayHopf.a</code></h1>' in got['LerayHopf.a'], got['LerayHopf.a'][:400])


def test_output_is_deterministic() -> None:
    """A rebuild of an unchanged payload must be byte-identical, or every deploy churns the
    artifact and its digests for no reason."""
    with tempfile.TemporaryDirectory() as td:
        site = make_site(Path(td), [node(f'LerayHopf.d{i}') for i in range(12)])
        run(BUILD, '--site', str(site))
        first = pages(site)
        first_map = (site / 'sitemap.xml').read_text(encoding='utf-8')
        run(BUILD, '--site', str(site))
        second = pages(site)
        second_map = (site / 'sitemap.xml').read_text(encoding='utf-8')
    check('pages are byte-identical across runs', first == second)
    check('the sitemap is byte-identical across runs', first_map == second_map)


def test_sitemap_has_no_lastmod() -> None:
    """`built_at` moves on every CI run whether or not a declaration changed. A lastmod
    that claims change when there was none is the kind crawlers learn to discount."""
    with tempfile.TemporaryDirectory() as td:
        site = make_site(Path(td), [node('LerayHopf.a')])
        run(BUILD, '--site', str(site))
        xml = (site / 'sitemap.xml').read_text(encoding='utf-8')
        root = ET.fromstring(xml)
    ns = '{http://www.sitemaps.org/schemas/sitemap/0.9}'
    locs = [e.text for e in root.iter(f'{ns}loc')]
    check('the sitemap parses as XML', root.tag == f'{ns}urlset', root.tag)
    check('it lists the site root and every page', len(locs) == 2, str(locs))
    check('the declaration URL is the static path',
          any(l.endswith('/decl/LerayHopf.a/') for l in locs), str(locs))
    check('no lastmod is emitted', not list(root.iter(f'{ns}lastmod')))


def test_slug_encoding_matches_the_url() -> None:
    """Non-ASCII and apostrophes are percent-encoded so the directory name and the URL in
    the canonical are the same string — if they diverge, the canonical points at a 404."""
    slugs = ['LerayHopf.crossWithIξ', "LerayHopf.H1Sigma'", 'LerayHopf.plain']
    with tempfile.TemporaryDirectory() as td:
        site = make_site(Path(td), [node(s) for s in slugs])
        run(BUILD, '--site', str(site))
        got = pages(site)
    check('non-ASCII slug is percent-encoded',
          'LerayHopf.crossWithI%CE%BE' in got, str(sorted(got)))
    check('apostrophe slug is percent-encoded',
          'LerayHopf.H1Sigma%27' in got, str(sorted(got)))
    check('an already-safe slug is left alone', 'LerayHopf.plain' in got, str(sorted(got)))
    for segment, html_text in got.items():
        m = re.search(r'<link rel="canonical" href="([^"]+)">', html_text)
        check(f'canonical present for {segment}', m is not None, html_text[:300])
        check(f'canonical path equals the directory for {segment}',
              m.group(1).endswith(f'/decl/{segment}/'), m.group(1))


def test_case_insensitive_collisions_get_distinct_paths() -> None:
    """`LerayHopf.StageData` and `LerayHopf.stageData` differ only in case. On a
    case-insensitive filesystem one would overwrite the other, so which page survived would
    depend on the developer's machine. Both must get distinct, stable directories."""
    with tempfile.TemporaryDirectory() as td:
        site = make_site(Path(td), [node('LerayHopf.StageData'), node('LerayHopf.stageData'),
                                    node('LerayHopf.unique')])
        run(BUILD, '--site', str(site))
        got = pages(site)
    check('both colliding declarations get a page', len(got) == 3, str(sorted(got)))
    lowered = [s.lower() for s in got]
    check('no two directories collide case-insensitively',
          len(set(lowered)) == len(lowered), str(sorted(got)))
    suffixed = sorted(s for s in got if '~' in s)
    check('both members of the group are suffixed, not just one',
          len(suffixed) == 2, str(suffixed))
    check('the non-colliding slug keeps its plain directory',
          'LerayHopf.unique' in got, str(sorted(got)))

    # Order independence: the same declarations in the opposite order must give the same map.
    with tempfile.TemporaryDirectory() as td:
        site2 = make_site(Path(td), [node('LerayHopf.unique'), node('LerayHopf.stageData'),
                                     node('LerayHopf.StageData')])
        run(BUILD, '--site', str(site2))
        got2 = pages(site2)
    check('the segment map does not depend on payload order',
          sorted(got) == sorted(got2), f'{sorted(got)} vs {sorted(got2)}')


def test_stale_pages_are_removed() -> None:
    """A declaration removed upstream must not keep a live page describing something that
    no longer exists — nor a sitemap entry pointing at it."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        site = make_site(root, [node('LerayHopf.keep'), node('LerayHopf.drop')])
        run(BUILD, '--site', str(site))
        check('both pages exist initially', len(pages(site)) == 2)
        make_site(root, [node('LerayHopf.keep')])
        run(BUILD, '--site', str(site))
        got = pages(site)
        xml = (site / 'sitemap.xml').read_text(encoding='utf-8')
    check('the removed declaration loses its page', sorted(got) == ['LerayHopf.keep'], str(sorted(got)))
    check('and its sitemap entry', 'LerayHopf.drop' not in xml)


def test_prose_is_escaped_and_math_survives() -> None:
    with tempfile.TemporaryDirectory() as td:
        site = make_site(Path(td), [node(
            'LerayHopf.p',
            statement='[[球への制限|LerayHopf.restrictToBall]]は $\\lVert u\\rVert$ 以下。'
                      '<script>alert(1)</script> と **強調** と `code`。\n\n第二段落。')])
        run(BUILD, '--site', str(site))
        page = pages(site)['LerayHopf.p']
    check('raw HTML in prose is escaped', '<script>alert(1)</script>' not in page)
    check('the escaped form is present', '&lt;script&gt;' in page, page[page.find('<main'):][:400])
    check('math delimiters survive for the KaTeX pass', '$\\lVert u\\rVert$' in page)
    check('bold becomes strong', '<strong>強調</strong>' in page)
    check('backticks become code', '<code>code</code>' in page)
    check('a wikilink is reduced to its display word', '球への制限' in page)
    check('and does not become a link (full-name resolution is ambiguous, notes#139)',
          'LerayHopf.restrictToBall' not in page.split('<main')[1].split('</main>')[0])
    check('both paragraphs are emitted', '第二段落。' in page)


def test_pages_carry_no_inline_script() -> None:
    """The pages ship the site's CSP (`script-src 'self'`, no 'unsafe-inline'). An inline
    block would be silently dropped by the browser, so the KaTeX pass would never run."""
    with tempfile.TemporaryDirectory() as td:
        site = make_site(Path(td), [node('LerayHopf.a')])
        run(BUILD, '--site', str(site))
        page = pages(site)['LerayHopf.a']
    check('a CSP is present', "script-src 'self'" in page)
    check('base-uri is locked down, so no <base> may be introduced',
          "base-uri 'none'" in page and '<base ' not in page)
    for m in re.finditer(r'<script\b([^>]*)>(.*?)</script>', page, re.S):
        check('every script tag is external and has an empty body',
              'src=' in m.group(1) and not m.group(2).strip(), m.group(0)[:200])


def test_generator_refuses_a_malformed_payload() -> None:
    for label, nodes in (('an empty nodes array', []),
                         ('an entry with no slug', [{'name': 'x'}]),
                         ('a non-object entry', ['LerayHopf.a'])):
        with tempfile.TemporaryDirectory() as td:
            site = make_site(Path(td), nodes)
            code, out = run(BUILD, '--site', str(site))
        check(f'the generator refuses {label}', code != 0, out)
    with tempfile.TemporaryDirectory() as td:
        site = Path(td) / 'site'
        (site / 'data').mkdir(parents=True)
        code, out = run(BUILD, '--site', str(site))
        check('the generator refuses a missing nodes.json', code != 0, out)


def test_base_url_is_normalised() -> None:
    with tempfile.TemporaryDirectory() as td:
        site = make_site(Path(td), [node('LerayHopf.a')])
        run(BUILD, '--site', str(site), '--base-url', 'https://example.org/x')
        page = pages(site)['LerayHopf.a']
    check('a base URL without a trailing slash still yields one path separator',
          'href="https://example.org/x/decl/LerayHopf.a/"' in page, page[:600])


def test_size_report_measures_the_published_tree() -> None:
    """notes#73 widened the budget from site/data to site/**. If it had not, the report
    would say "within budget" while the pages grew the deployed artifact without limit."""
    with tempfile.TemporaryDirectory() as td:
        site = make_site(Path(td), [node(f'LerayHopf.d{i}') for i in range(30)])
        run(BUILD, '--site', str(site))
        proc = subprocess.run(
            [sys.executable, '-c',
             'import sys, runpy, pathlib;'
             f'sys.argv=["r"];'
             'import importlib.util as u;'
             f'spec=u.spec_from_file_location("r", {str(SIZE_REPORT)!r});'
             'm=u.module_from_spec(spec); spec.loader.exec_module(m);'
             f'm.SITE_DATA_DIR=pathlib.Path({str(site / "data")!r});'
             'print(m.published_tree_sizes(m.site_root()));'
             'print(m.site_root())'],
            capture_output=True, text=True)
    check('the report exposes a published-tree measurement', proc.returncode == 0, proc.stderr)
    check('the published tree is rooted at the site, not site/data',
          proc.stdout.strip().splitlines()[-1].endswith('site'), proc.stdout)
    measured = eval(proc.stdout.strip().splitlines()[0])  # noqa: S307 - our own output
    check('it counts the declaration pages, not just the payload',
          measured['files'] >= 31, str(measured))


def main() -> None:
    test_emits_one_page_per_declaration()
    test_output_is_deterministic()
    test_sitemap_has_no_lastmod()
    test_slug_encoding_matches_the_url()
    test_case_insensitive_collisions_get_distinct_paths()
    test_stale_pages_are_removed()
    test_prose_is_escaped_and_math_survives()
    test_pages_carry_no_inline_script()
    test_generator_refuses_a_malformed_payload()
    test_base_url_is_normalised()
    test_size_report_measures_the_published_tree()
    print(f'\nAll {len(CHECKS)} notes#73 static-page checks passed.')


if __name__ == '__main__':
    main()
