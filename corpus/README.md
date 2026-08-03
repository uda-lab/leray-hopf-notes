# corpus/

Per-declaration annotation YAML files.

## Layout

```
corpus/LerayHopf/<slug>.yaml
```

The corpus is **flat**: every entry sits directly in `corpus/LerayHopf/`, and the Lean module
hierarchy is *not* mirrored as directories. For example, the declaration
`LerayHopf.rellich_seq_compact`, defined in `LerayHopf/Torus/RellichEmbedding.lean`, lives at:

```
corpus/LerayHopf/rellich_seq_compact.yaml
```

The defining module plays no part in that path — there is no `Torus/` directory, and the
`R3` / `Torus` split never becomes a directory anywhere in the corpus. Module names *do*
appear, flattened onto dots inside the filename, in the one case where they are needed to
tell two same-named declarations apart; see Naming below.

## Schema

See `docs/schemas/corpus.schema.json` for the full JSON Schema (draft-07).

Key fields:
- `name` — fully-qualified Lean declaration name
- `file` — source path from `extracted/decls.json`; optional for unique names, required when the
  same display `name` appears in more than one declaration
- `tier` — `full` (statement + proof + gap) or `gloss` (1–3 line role summary)
- `statement_ja` — Japanese translation of the mathematical statement
- `proof_ja` — Japanese proof narrative (required for `tier: full` theorems)
- `gap` — formalization gap assessment (`none | mild | large`)
- `chapter` — chapter assignment from `docs/schemas/chapters.yaml`
- `tags` — optional free-form tags

## Naming

**For a new entry**, take the fully-qualified name and strip the leading `LerayHopf.`. A
declaration that carries a namespace keeps it in the filename, dots and all — the slug is not
reduced to the last component:

```
LerayHopf.Galerkin.GlobalLerayHopfSolution
  -> corpus/LerayHopf/Galerkin.GlobalLerayHopfSolution.yaml
```

`scripts/workpacket.py` prints the correct path for each declaration it emits, so prefer that
over deriving one by hand.

**When the display `name` is ambiguous** — carried by more than one declaration, as happens
for private helpers of the same name in different modules — a flat corpus cannot give both the
same filename. Qualify the slug with the defining module path, flattened onto dots:

```
LerayHopf.measurable_natFloor_real   (two private declarations, two modules)
  -> corpus/LerayHopf/Bochner.StepFunctionCompactness.measurable_natFloor_real.yaml
  -> corpus/LerayHopf/R3.SpacetimePrecompact.measurable_natFloor_real.yaml
```

Disambiguate by **prefixing**, never by suffixing: `measurable_natFloor_real_a.yaml` would
spell a declaration that does not exist. `validate.py` enforces this form for ambiguous names,
deriving the expected prefix from the required `file` field.

**Existing files vary.** Most follow the rule above, but a few hundred predate it and drop
intermediate namespaces — `corpus/LerayHopf/GelfandTriple.yaml` annotates
`LerayHopf.Bochner.GelfandTriple`, and a handful drop only part of a namespace. These are not
being renamed: the filename is a convention, not a key, and mass-renaming would churn every
corpus path for no functional gain. Do not copy those shapes for new entries.

**The filename is a convention, not a key.** The join is on the `name` field, which must match
a declaration in `extracted/decls.json`; `file` disambiguates when a display `name` is
ambiguous (notes#7).

`validate.py` checks that the filename's **last dot-component** equals the declaration's simple
name, which catches a typo or a half-edited copy of a neighbouring entry. For unambiguous names
it cannot check more than that — the historical slug shapes above coexist, so requiring full
equality would mean renaming hundreds of files (notes#120). For **ambiguous** names it checks
the whole slug, since there a wrong module prefix does not merely look untidy: it points the
reader at the wrong declaration.

## 執筆規約（notes#12 v1.1 — 組版・レジスタ）

owner の v1 実見レビューを反映した凍結規約。`scripts/prose_lint.py --strict` が
pre-commit / CI で機械チェックする。D1・D2 の Lean 名・D5 は**ハードエラー**、長すぎる
インライン数式は警告だが、`--strict` では警告も失敗扱いになるため、いずれも通す必要が
ある（notes#124）。

### D1. 段落と物理改行

- **prose フィールド（`statement_ja` / `proof_ja` / `gap.note`）は 1 段落 = 1 物理行で書く。**
  段落内で折り返さない。空行が段落区切りになる。
- レンダラは空行で `<p>` に分割し、幅・高さ・文字数に基づく切断は**一切しない**。
  ホームカードは第 1 段落全文、ホバーカードは予算内最後の「。」までを表示する
  （どちらも文の途中では切らない）。

### D2. 数式

- 長い／重い数式（インラインで全角換算 ~20 字超、または分数・総和・複数関係子を含む）は
  **ディスプレイ数式 `$$ ... $$`** にする。
- **数式内に Lean 宣言名を書かない。** `\mathrm{divTestFunctional}` のような camelCase・
  アンダースコアを含む名前は禁止。標準の数学記法と意訳語で書く（例: 「発散記号」「粘性形式」）。

### D3. 自然言語のレジスタ（文体）

- `statement_ja` / `proof_ja` は**通常の数学論文・書籍の文体**のみ。Lean 宣言名・
  「構造体」「フィールド」「インスタンス」等の Lean 用語・tactic 名を出さない。
- Lean 固有の注意（総和規約・代表元・インスタンス解決・mathlib 補題名など）は
  `gap.note` に書く。`gap.note` 内では mathlib 補題名を `` `code` `` で表してよい。

### D4. 自己完結（宣言ページは 1 件ずつ独立に描画される）

- **`statement_ja` / `proof_ja` / `gap.note` に、隣の項目を指す相対参照を書かない。** サイトは
  宣言ごとに独立したページを描画するため、「上の補題」「上と同じ仮定」「前述の評価」には
  読者から見て参照先が無く、条件付きの主張が**無条件の主張に見える**。
- 参照したい相手が宣言なら `[[表示語|宣言名]]` で名指しする（D5）。仮定なら**書き下す**。
- **「…など」で仮定を畳まない。** 何が省略されたか読者に分からず、主張の適用範囲を判断
  できなくなる点で相対参照と同じ欠陥である。
- 同一エントリ内での「上記の四つのデータ」「同じ近似子が両方の評価を達成する」のような
  参照は問題ない。判定は「このページだけを読んで意味が確定するか」である。

機械検出はできるが、**そのまま鵜呑みにはできない** — 「$\mathbb{R}^3$ 上の作用素」「$(0,b]$
上の積分」のような後置詞用法を大量に拾う。検出したうえで目で選別すること。

```sh
python3 - "$f" <<'EOF' | grep -nE '同じ|上の|上記|前述|こちら|など|同様|同上|前掲'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1], encoding='utf-8'))
print(d.get('statement_ja') or '')
print(d.get('proof_ja') or '')
print((d.get('gap') or {}).get('note') or '')
EOF
```

検出語には **`同様` / `同上` / `前掲` を必ず含める** — 「同様である。」だけの証明文は
参照先を持たない後方参照であり、D4 違反として最も見落としやすい形（実際に 5 件が
初回の掃き取りを通過した）。

（`sed` で `statement_ja` から `gap:` までを切り出す形では **`gap.note` が読まれない** —
本規約は `gap.note` にも適用されるので、3 フィールドを明示的に取ること。）

（notes#74 の第 10・11・12 波と #146 で、この形の指摘を繰り返し受けた。書いた直後に掃くのが
最も安い。）

### D5. インライン記法

レンダラが対応するのは次のインライン記法と KaTeX 数式のみ。それ以外の markdown
（見出し・リスト・リンク・引用）は非対応で lint がブロックする。

- `` `code` `` → 等幅（gap.note で mathlib 補題名などに使う）
- `**強調**` → ボールド
- `[[表示語]]` / `[[表示語|宣言名または slug]]` → 下線付きの参照。ホバーで定義カード、
  クリックでそのノードへ遷移する。「証明を読んでいて気になったら開ける便利メモ」。
  `|` を省くと表示語を display name として解決する。**意訳語からでも対応する Lean 定義に
  届かせるための記法。** 参照先は `extracted/decls.json` に実在する宣言名にすること。

## 数式記法（KaTeX）

`statement_ja` と `proof_ja` の本文では TeX 数式を書ける。サイトはビルド時に
vendored KaTeX でレンダリングする（CDN 不使用）。

- **インライン**: `$ ... $` — 例: `発散ゼロな初期値 $u_0 \in L^2_\sigma(\mathbb{R}^3)$`
- **ディスプレイ**: `$$ ... $$` — 中央寄せの別行立て数式

規約:

- YAML はブロックスカラー（`statement_ja: |`）で書くこと。バックスラッシュがそのまま
  KaTeX に渡る（プレーンスカラーだとエスケープ解釈でずれる）。
- 各段落は 1 物理行に収める（D1）。ディスプレイ数式も 1 行で書く。
- `$` を数式以外（通貨など）で使うときはレンダリングされるので避けるか `\$` を使う。
- KaTeX 未対応のコマンドは避ける（サイトは `throwOnError:false` で失敗時は生テキスト表示）。
