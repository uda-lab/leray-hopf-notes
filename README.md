# lean-pde-notes — 証明掘り下げインタラクティブノート

[uda-lab/lean-pde](https://github.com/uda-lab/lean-pde)（Leray–Hopf 弱解存在の Lean 4 + mathlib
形式化、kernel-only 達成済み）の**全宣言対訳解説サイト**の作業リポジトリ。

Lean コードと「自然な日本語の数学証明として読める文章」を並置し、ホバー定義カード・
1 段アコーディオン展開・リンクナビゲーションで証明ツリーを capstone から末端まで
辿れる純静的 UI を構築する。設計・キャンペーン計画は issue #1 を参照。

## 構成（予定）

```
corpus/          宣言ごとの注釈 YAML（statement_ja / proof_ja / gap note / chapter）
extracted/       lean-pde の lake exe extract_notes が生成する機械抽出 JSON（pin コミット付き）
site/            純静的ビューア（vanilla JS SPA + ビルド済み JSON）
scripts/         コーパス⇄抽出 JSON のドリフト検査・カバレッジ集計（grep 級、ビルド不要）
```

## 参照元

- 形式化本体: `uda-lab/lean-pde`（PRIVATE）— 抽出 JSON は同 repo の warm ビルドから生成し、
  対象コミット SHA を `extracted/PIN` に記録する
- 対訳プロトタイプ: lean-pde の `docs/formalization-review-ja.md`（§4 形式化ギャップ Note の原型）
