# 宣言 universe 移行記録 — repin ledger（2026-07 リファクタリング波以降、継続追記）

本書は repin のたびに追記される**生きた ledger**（`CONTRIBUTING.md` §5 手順 5）。
冒頭から「将来の変動要因」節までは初回の 2026-07 リファクタリング波（PIN
`013c4a0` → `a33de86`）を扱い、以降の repin はそれぞれ「追記 N」節として末尾に
積まれる。**現行 PIN は本書ではなく `extracted/PIN`（および同期が必須の
`CITATION.cff` の `references[0].commit`）が正典**であり、本書の各節は当時点の
スナップショットとして読むこと。追記が止まり後続 ledger に引き継がれた時点で
`docs/archive/`（規約は `docs/archive/README.md`）へ移す。

`uda-lab/lean-pde` の pre-publication リファクタリング波（issue #108/#110/#111/#112/#113/#114/#131
= PR #116–#138、2026-07-09〜07-11）に伴う corpus・宣言マッピングの追随記録。
PR ごとの宣言レベル差分の全履歴は notes#36 のコメント群に集約されている。本書はその
corpus 側への適用結果（何をどう機械的に変更したか）を記録する。

対応は新 PIN `a33de86522a13d05d7cee67fbc27b1b9106822f8` 時点の `extracted/decls.json`
（正典の名前 universe）で全行検証済み。

## 規模

| | 旧（013c4a0） | 新（a33de86） |
|---|---|---|
| 抽出宣言数 | 1,412 | 1,347 |
| corpus エントリ数 | 1,412 | 1,137（本波の機械的追随後） |
| display-name 衝突 | 7 組 14 宣言 | 2 組 4 宣言（`measurable_natFloor_real`, `continuous_restrictToBall'`） |

分類（`scripts/decl_diff.py` による）: 新設 +213（public 78 / private 135）、削除 −278
（public 13 / private 265）、ファイル移動 467（名前不変 — #116 の Torus/ 移設と #111/#113/#114
のファイル分割・抽出）、private→public 昇格 58、public→private 降格 0。

再現手順:

```bash
git show <旧コミット>:extracted/decls.json > /tmp/decls-old.json
python3 scripts/decl_diff.py /tmp/decls-old.json extracted/decls.json --markdown /tmp/diff.md
```

## 名称が変わったもの（エントリ改名、3 件 — lean-pde PR #117）

| 旧名 | 現行名 | 備考 |
|---|---|---|
| `LerayHopf.exists_lerayHopf_r3_axiomatic` | `LerayHopf.exists_lerayHopf_r3` | ℝ³ capstone。`_axiomatic` 接尾辞の retire |
| `LerayHopf.exists_lerayHopf_torus3_axiomatic` | `LerayHopf.exists_lerayHopf_torus3` | 𝕋³ capstone。同上 |
| `LerayHopf.exists_lerayHopf_torus3_statement` | `LerayHopf.Scaffold.exists_lerayHopf_torus3_statement` | scaffold placeholder の namespace 隔離 |

corpus 側: YAML の `name:`・ファイル名を改名し、`[[…\|旧名]]` ホバー参照を全 corpus で
再ターゲットした。

## 削除された public 宣言（13 件）とその後継

| 削除された宣言 | 後継 / 対応 |
|---|---|
| `exists_lerayHopf_r3_axiomatic` ほか rename 3 件 | 上表の改名（削除ではない） |
| `GalerkinCompactnessPackage`（GalerkinPackage.lean ごと削除） | `LerayHopf.Galerkin.CompactnessPackage`（PR #134） |
| `exists_lerayHopf_from_galerkin_package`（ExistenceFromPackage.lean ごと削除） | `LerayHopf.Galerkin.exists_lerayHopf_from_package`（PR #134） |
| `galerkinODE_bilinearPart` / `galerkinODE_linearPart`（両 lane、計 4 件） | 汎用層 `LerayHopf.Galerkin.bilinearPart` / `linearPart`（private、PR #132–#133） |
| `eLpNorm_three_le_interp_pub` | `LerayHopf.PlancherelKernels.eLpNorm_three_le_interp`（PR #121） |
| `memH1_weightedL2_integrable` | 孤児化した Bessel 系の削除（PR #126）。実用途は `memH1_weightedL2_integrable_R` |
| `Bochner.GelfandTriple.ιCLM` | 死んだ互換 shim の削除（PR #127）。後継なし |
| `TorusConvectionExtension.summable_coeff_sq'` | 共有化で `Torus.summable_norm_mFourierCoeff3_sq` 等へ集約（PR #124） |

## 削除された private 宣言（265 件）

#111 dedup 波（Fresh copy・CLM tower・restrictToBall 族などの逐語コピー）、#112 の lane 側
ODE body、#131 の TraceEnergy Hilbert toolkit 重複が主。個別の後継は notes#36 の各 PR
コメントに記録済み。corpus 側は対応する 265 エントリ（ほぼ全て `generated` gloss）+
display-name 衝突解消で不要になった重複エントリを retire した（計 275 YAML 削除）。

## ホバー参照の個別修正（5 件）

| 参照元 | 旧ターゲット | 新ターゲット |
|---|---|---|
| `convIntegralSchwartz_add_1` | `LerayHopf.convForm`（旧 universe でも dangling だった既存不良参照） | `LerayHopf.convIntegralSchwartz` |
| `convIntegralSchwartz_bound_energy` | `eLpNorm_three_le_interp_pub` | `PlancherelKernels.eLpNorm_three_le_interp` |
| `galerkinODE_vectorField_contDiff` | `galerkinODE_bilinearPart` / `galerkinODE_linearPart` | `Galerkin.bilinearPart` / `Galerkin.linearPart` |
| `integrable_viscous_integrand_of_memH1` | `memH1_weightedL2_integrable` | `memH1_weightedL2_integrable_R` |

## 新設宣言（+213）と注釈フォローアップ

新章 `galerkin-generic` を追加（`docs/schemas/chapters.yaml` 末尾）。未注釈の新設宣言は
本移行 PR の時点では coverage 未達として残り、後続の注釈パケット（notes#36 参照）で
埋める:

- **Galerkin 汎用層**（PR #132/#134、新章 galerkin-generic）: `Galerkin/DissipativeODE.lean`
  公開 6、`Galerkin/QuadraticField.lean` 公開 8（`FieldForms` ほか）、`Galerkin/Domain.lean`
  公開 3（`Domain`, `NSFormCore`, `Domain.evolution`）、`Galerkin/SolutionBundles.lean` 公開 4
  （`SolutionData`, `LerayHopfSolution`, `CompactnessPackage`, `exists_lerayHopf_from_package`）
- **lane witness / instance**（PR #133/#134）: `torusDomain` / `r3Domain` + 簡約補題 8、
  `Torus3NSForms.core` / `R3NSForms.core` + `core_b`、`torusFieldForms` / `r3FieldForms`、
  `galerkinODE_vectorField_eq_generic`（両 lane）
- **共有解析モジュール**（PR #120–#127）: `Analysis/TensorEdgeGluing` 公開 10、
  `Analysis/BoundedMultiplier` 公開 11、`Analysis/PlancherelKernels` 公開 8、
  `Analysis/BilinearExtension` 公開 3
- **b(u,v,v)=0 系**（PR #128）: `DissipativeEvolution.convForm_self_zero_right`,
  `Torus3NSForms.b_self_zero_right`, `R3NSForms.b_self_zero_right`
- **#114 教科書ステップ補題**（PR #129/#130）: TraceEnergy 6・WeakLeibniz 2 ほか —
  抽出上は private（新設 private 135 に含まれる）。注釈単位として設計されており、
  数学的に重いものは 2 層ポリシーの昇格条項で full 化してよい
- **private→public 昇格 58 件**（PR #121–#130）: FourierParseval 14、SpatialCompactness 13、
  RealComplexLpBridge 10、GalerkinODEExistence 7 ほか。public=full の 2 層ポリシーにより
  gloss→full 格上げ対象

## 適用しなかったもの

- `extracted/names-fallback.json` は設計通り休眠のまま非更新（`extracted/README.md` 参照）。
- `origin/corpus/annotation-upgrade` ブランチ（seed 2 エントリ）は、その内容が既に main の
  `AbstractEnergyLaw.energyInequality.yaml` / `Bochner.ContDiffBump.isTimeMollifier.yaml` に
  取り込まれていることを確認済み — 完全に superseded であり、取り込み不要（ブランチは削除可）。

## 将来の変動要因

`uda-lab/lean-pde#135`（ArzelaAscoliTime / GoodRepresentative の GalerkinDomain
インターフェースへの restate — stretch、時期未定）。実施された場合は本書と同じ手順
（`decl_diff.py` → 機械的追随 → 注釈フォローアップ）を小規模に繰り返す。

→ 実施された。次節（PIN a33de86 → 0afd65f）を参照。

## 追記: 小規模 repin（PIN a33de86 → 0afd65f、notes#60）

lean-pde PR #139/#141/#142/#143（issue #135 の restate〔縮小スコープ〕と issue #1
finding-6 の成分往復補題の共有化、docs 整理 2 件）への追随。抽出宣言数 1,347 → 1,349、corpus エントリ数 1,347 → 1,349（全宣言 coverage 維持）。

`decl_diff.py` による分類と corpus 側対応:

| 区分 | 宣言 | corpus 側対応 |
|---|---|---|
| private→public 昇格（H1Sigma.lean → Torus/DivergenceFree.lean へ移動、成分往復補題の共有化） | `re_compLpL_projComponentC`, `sum_inject_projComponent` | 2 層ポリシー（public=full）により gloss→full 格上げ。旧抽出元ファイルへの言及を更新 |
| 新設 private | `injectComponent_projComponent_ae`（Torus/DivergenceFree.lean）, `galerkin_norm_le_u0_generic`（R3/GoodRepresentative.lean） | gloss エントリ新設 |
| 署名変更（issue #135 restate: 仮定の Galerkin 解束を `GalerkinSolutionData_R3` から汎用束 `Galerkin.SolutionData (r3Domain 𝔊) F.core` へ一般化。主張の内容は不変） | `galerkin_weakLimit_R3`, `perTest_lipschitz_R3`, `perTest_hasDerivAt_R3` | full 2 件は gap.note に束の一般化を追記。gloss 1 件（`perTest_hasDerivAt_R3`）は本文影響なし |
| 削除 | なし | — |

display-name 衝突は 2 組 4 宣言（`measurable_natFloor_real`, `continuous_restrictToBall'`）のまま不変。
`extracted/names-fallback.json` は引き続き休眠・非更新。


## 追記 2: release-blocker 波 repin（PIN 0afd65f → d5f91f7、lean-pde#145 P0/P1）

lean-pde の公開前 P0/P1 波（issue #144/#146/#147/#148/#149/#150/#153/#158/#166/#168
= PR #159–#165/#167/#169、2026-07-16 夜〜07-17 未明）への追随。抽出宣言数 1,349 → 1,339、
corpus エントリ数 1,349 → 1,339（全宣言 coverage 維持）。

| 区分 | 宣言 | corpus 側対応 |
|---|---|---|
| 削除 −10（#144: 空虚な scaffold API と被参照ゼロ定義の除去） | `SpatialField`, `LerayHopfSolution`（旧 placeholder 版）, `ExistsLerayHopf`, `Scaffold.exists_lerayHopf_torus3_statement`, `LerayHopfNonunique`, `H1Torus`, `lerayProjection`, `lerayProjection_R3`, `AbstractGalerkinData`, `convFormSchwartzWitness` | エントリ retire（10 YAML 削除） |
| 移動+署名変更（#147/#158: Experimental 分離と偽一般形の修正） | `Bochner.w1pTime_continuous_in_H`（TimeSobolev.lean → TimeSobolevExperimental.lean、`1 ≤ p,q` → `p=q=2`） | エントリを issue #158 に従い検疫記述へ更新（一般形は偽・反例・制限と隔離の経緯を gap.note に記録） |

注: root import は #147 で sorry-free 化され、sorry 入り Bochner 4 モジュールは
`LerayHopf.Experimental` 経由でのみ到達可能となった。notes の抽出 universe は
owner 裁定（2026-07-17）により root + Experimental の両方をカバーする
（lean-pde#166 で extractor を拡張、本 repin から適用）。

## 追記 3: release candidate freeze repin（PIN d5f91f7 → 7c15710a、leray-hopf-notes#32 Phase B）

owner 裁定（issue #32、2026-07-19T15:49:25Z）による source release candidate 凍結
（`uda-lab/leray-hopf@7c15710a7b9068a2aa105fc7c11b432e7685b7b5`）への追随。leray-hopf
#151/#152/#154/#155/#156/#157/#158/#173/#177/#178/#180（PR #170–#183 の範囲、docstring/private
境界の triage・maxHeartbeats 注釈・Temam/Sobolev 記法修正・rename sync・release-cone guard 強化）
を含む 23 commits。

`lake exe extract_notes` 再実行（PIN 更新後の warm cache 上の増分 build、実際にコンパイル
されたのは 9 モジュールのみ・残り 3187 ジョブはキャッシュ再利用）: 抽出宣言数 1,339 → 1,339（増減なし）。
`decl_diff.py` による分類:

| 区分 | 件数 | 内容 | corpus 側対応 |
|---|---|---|---|
| 追加/削除/移動 | 0 | — | — |
| public→private 可視性変更（issue #155 の docstring/private 境界 triage） | 24 | すべて `LerayHopf/Torus/ConvectionExtension.lean` 内（`convBLTw` 系・`l2coeff` 系など） | 本 repin では機械的差分のみ反映（PIN/CITATION.cff 更新）。2 層ポリシー（public=full）に従うと該当 24 件は tier: full → gloss への格下げ対象だが、gloss 文面の手書き作業は本 PR のスコープ外 — 別 issue でフォローアップ |
| signature text 変更（同上 triage の副作用、doc-only） | 13 | 上記 24 件のサブセット | 同上（tier 格下げと合わせてフォローアップ） |

display-name 衝突は 2 組 4 宣言のまま不変。`validate.py` / `coverage.py` はともに green
（1339/1339 coverage、tier 不整合は非致命 — `validate.py` は `tier ∈ {full, gloss}` のみ検査
し public/private との整合は検査対象外）。`extracted/names-fallback.json` は引き続き休眠・
非更新。

## 追記 4: 時間大域キャンペーン repin（PIN 7c15710a → 4d65c05、notes#116）

`uda-lab/leray-hopf` の時間大域（global-in-time）キャンペーン 2 レーン — 𝕋³ 側 issue #195
（PR #205–#211、sub-issue #200–#204）と ℝ³ 側 issue #212（PR #218–#222、sub-issue #213–#217）
— および先行する保守 2 件（#196 pre-push env 衛生 = PR #197、#184 linter 警告一掃 = PR #198）
を含む 14 commits への追随。pin 先は `dev/v0.2.0` tip
`4d65c0570dc82495bddca873ea1344b5817a2b3c`。`main` からは fast-forward 可能（+14 −0）で
コミットハッシュは merge 後も保存されるため、main マージを待たずに pin できる。

このキャンペーンで両レーンに時間大域 capstone `exists_global_lerayHopf_torus3` /
`exists_global_lerayHopf_r3` が入った。いずれも `∃ u, ∀ T > 0, IsLerayHopfOn … T u₀ u` の形、
すなわち**ただ一本の曲線**が任意の有限区間 $[0,T]$ 上で Leray–Hopf 契約を満たす主張であり、
`∀ T, ∃ u_T` の詰め替えではない（`globalLerayHopfSolution_nonempty_iff` が literal 同値を
機械検査する）。訳語は `docs/GLOSSARY.md` の `time-global` 行で「時間大域」に固定した。

`lake exe extract_notes` 再実行（donor `.lake` を `cp -al` 共有した 4d65c05 の worktree 上、
リビルドなし）: 抽出宣言数 1,339 → 1,420。`decl_diff.py` による分類:

| 区分 | 件数 | 内容 | corpus 側対応 |
|---|---|---|---|
| 新設 | +81 | 下表の新規 8 モジュール + 既存 3 モジュールへの追加 | 全件に対訳を執筆（後続 PR、100% coverage 回復） |
| 削除 | 0 | — | — |
| ファイル移動・改名 | 0 | — | — |
| 可視性変更 | 0 | — | — |
| signature text 変更 | 38 | κ 再添字族の配線 35 件（下記）＋ `[FiniteDimensional ℝ V]` 仮定の削除 3 件 | 後続 PR で該当エントリの記述を点検 |

新設 81 件のモジュール別内訳:

| モジュール | 件数 | 役割 |
|---|---|---|
| `LerayHopf/Galerkin/GlobalContract.lean` | 21 | 領域非依存の `IsLerayHopfOn` 契約層・`GlobalLerayHopfSolution`・区間制限と曲線合同の転送補題 |
| `LerayHopf/Bochner/DiagonalExtraction.lean` | 12 | 段階部分列の入れ子合成と対角抽出 |
| `LerayHopf/R3/DiagonalGalerkin.lean` | 11 | ℝ³ 段階再帰と対角弱極限 |
| `LerayHopf/Torus/DiagonalGalerkin.lean` | 8 | 𝕋³ 同上 |
| `LerayHopf/R3/GlobalCapstone.lean` | 6 | ℝ³ 時間大域 capstone と凍結ターゲット |
| `LerayHopf/Torus/GlobalCapstone.lean` | 6 | 𝕋³ 同上 |
| `LerayHopf/R3/KappaChainExit.lean` | 4 | ℝ³ κ 鎖の型付き exit gate |
| `LerayHopf/Torus/KappaChainExit.lean` | 4 | 𝕋³ 同上 |
| `LerayHopf/R3/SpatialCompactness.lean` | 5 | 球分類の private 補助（既存モジュールへの追加） |
| `LerayHopf/R3/LimitPassage.lean` | 2 | pin 連言・強化結論の `def`（既存モジュールへの追加） |
| `LerayHopf/R3/SolutionInterfaces.lean` | 2 | κ 有効添字の単調性・発散（既存モジュールへの追加） |

signature 変更 38 件の内訳: 35 件は両レーンの Aubin–Lions 連鎖に再添字族 `κ : ℕ → ℕ`（と
`StrictMono κ`）を通した配線（`AubinLionsPackage` / `AubinLionsPackage_R3` の型引数追加を
含む）。時間大域 capstone は per-horizon の exit witness を対角部分列 `δ` に固定して走らせる
必要があり、そのために既存の有限区間連鎖を κ で一般化したもの。残り 3 件は
`LerayHopf/Galerkin/DissipativeODE.lean` の `energy_hasDerivAt_of_solution` /
`norm_le_of_forwardSolution_of_dissipative` / `solve_exists_on_step` から
`[FiniteDimensional ℝ V]` 仮定が外れたもの（仮定の削除であり主張は強化）。

### `LerayHopf/Scratch/**` の扱い

本波で Lean 側に scratch モジュールが 8 件（`GateFixture`, `KappaReindex`, `KappaShapeGate`,
`P2ExitContract`, `R3KappaSeed`, `R3ProductionCoupling`, `R3ShapeGate`, `R3StageCoherence`）
追加されたが、**抽出 universe には 1 件も入らない**。`ExtractNotes` は root の `LerayHopf` と
`LerayHopf.Experimental` の 2 モジュールのみを import して環境を反射するところ、
`LerayHopf.Scratch.*` はどちらの import 錐にも属さないためである（実際 `decls.json` の
新旧いずれにも `LerayHopf/Scratch/` 由来のレコードは 0 件）。したがって corpus 側の対応は
不要で、既存 repin と同じ扱いが自動的に維持される。抽出除外は release cone membership の
帰結であり、notes 側の設定項目ではない。

display-name 衝突は 2 組 4 宣言のまま不変。`extracted/names-fallback.json` は引き続き休眠・
非更新。

## 追記 5: 追い repin（PIN 4d65c05 → 6cd0a4b、notes#125）

`uda-lab/leray-hopf` の `dev/v0.2.0` が 3 commit 進んだことへの追随。内訳は
PR #224（#223、README のみ — Lean 宣言に影響なし）、PR #226（#154 Wave 2）、
PR #227（#225 docstring 統一）。後者 2 つが notes 側に効くが、tip `6cd0a4b` が
両方を含むため repin は 1 回で足りた。

`lake exe extract_notes` 再実行（`6cd0a4b` の worktree 上。`.lake/packages` は
hardlink 共有、`.lake/build` は donor から実コピーして seed し、#225 の docstring
変更による下流 cone のみ replay）: 抽出宣言数 1,420 → 1,425。`decl_diff.py` による分類:

| 区分 | 件数 | 内容 | corpus 側対応 |
|---|---|---|---|
| 新設 | +5 | `LerayHopf/R3/FrechetKolmogorov.lean` の private 補題（#154 Wave 2 の textbook-step 切り出し） | gloss エントリを 5 件追加（既存 private 慣行どおり） |
| 削除 | 0 | — | — |
| ファイル移動・改名 | 0 | — | — |
| 可視性変更 | 0 | — | — |
| signature text 変更 | 0 | — | — |

新設 5 件（すべて private、`chapter: compactness`、`tier: gloss`）:

| 宣言 | 内容 |
|---|---|
| `mem_closedBall_add_supportRadius_of_kernel_ne_zero` | 核の到達範囲。球 $B_R$ 上の軟化が見るのは $B_{R+r}$ 上の値だけ |
| `coeFn_translate_kernelL2R_sub` | 平行移動した核の差の点ごと表示 |
| `norm_toLp_kernel_slice_sub_eq_translate_modulus` | 核の切片の差のノルム＝核自身の平行移動モジュラス |
| `mul_div_two_mul_add_one_lt` | 上限評価から $L^2$ 評価へ渡すときの許容量 $\varepsilon/(2(V+1))$ |
| `norm_sub_lt_of_center_net` | 網の中心を経由した評価（一般のノルム空間の補題） |

`norm_sub_lt_of_center_net` は Fréchet–Kolmogorov 固有の内容を含まず、任意の
ノルム空間で成り立つ Arzelà–Ascoli の網構成の分類ステップなので、一般解析の
補題として記述した。他の 4 件は原文の `**Textbook step (...)**` doc comment に
整合させてある。

### leray-hopf#225（docstring 統一）の反映

PR #227 が Lean docstring の「有効モード写像」系表現を添字写像の語彙へ置換した分が、
本 repin で `decls.json` の `doc` に反映された。反映後の確認:

- 旧表現（`effective mode map` / `Effective absolute mode map`）を含む宣言: **0 件**
- 新表現（`outer index map` / `composed index map`）を含む宣言: **5 件**
  （`P2ExitWitness`, `R3KappaChainExitWitness`, `exists_weakLimitCurve_R3_kappa`,
  `AubinLionsPackage_R3.effective_{strictMono,tendsto_atTop}`）

これで notes site の宣言ページ（`node.doc`）から旧表現が消え、notes#122 で直した
日本語対訳と用語が揃った。日本語側の添字写像体系との齟齬は見つからなかった。

display-name 衝突は 2 組 4 宣言のまま不変。`extracted/names-fallback.json` は
引き続き休眠・非更新。

## 追記 6: v0.2.0 リリース repin（PIN 6cd0a4b → 2a06790、notes#130）

`uda-lab/leray-hopf` の v0.2.0 リリースへの追随。`dev/v0.2.0` が **true merge commit**
PR #228 で `main` へ昇格し、その SHA `2a06790` にタグ `v0.2.0`（および `v0.2.0-rc1`）が
付いた。本 repin で初めて PIN がリリースタグ上の commit を指す。

現行 PIN からの upstream 差分は 3 commit（`82627cb` = #230/#231、`7b9aae4` = #232、
マージコミット `2a06790`）だが、Lean ソースの差分は 1 ファイル・docstring のみ:

```
$ git diff --name-only 6cd0a4b 2a06790 -- '*.lean'
LerayHopf/R3/FrechetKolmogorov.lean
```

`lake exe extract_notes` 再実行（`2a06790` の worktree 上。`.lake/packages` は hardlink
共有、`.lake/build` は donor `82627cb` から実コピーして seed。`82627cb..2a06790` は
`.lean` / `lakefile.toml` / `lean-toolchain` を一切触らないため olean は完全一致で、
リビルドは発生しなかった）: 抽出宣言数 1,425 → 1,425。`decl_diff.py` による分類:

| 区分 | 件数 | 内容 | corpus 側対応 |
|---|---|---|---|
| 新設 | 0 | — | — |
| 削除 | 0 | — | — |
| ファイル移動・改名 | 0 | — | — |
| 可視性変更 | 0 | — | — |
| signature text 変更 | 0 | — | — |

`decls.json` の実差分は次の 2 種類だけである。

- `mul_div_two_mul_add_one_lt` の `doc`（leray-hopf#229 → PR #231 の修正）
- 同一ファイル内で docstring が 12 行伸びたことによる `startLine` / `endLine` のずれ
  （6 宣言: `totallyBounded_image_of_equicont_bdd`, `mollified_family_totallyBounded_L2`,
  `convolution_l2_tendsto_uniform`, `frechetKolmogorov_holds`, および同ファイルの
  private 補題 2 件）

### leray-hopf#229（doc comment の二段階修正）と gloss の整合

この docstring 変更は字句の統一ではなく、**二段階の overclaim 修正**だった。

1. 一次の誤り —「分母の `+1` が評価を `V` について一様にし、球の質量を知る前に同じ
   許容量 `ε'` が使える」。`ε' = ε/(2(V+1))` は `V` に依存するので誤り。本 repo の
   PR #126 に対する codex レビューが発見し、leray-hopf#229 として起票された。
2. **二次の誤り** — 一次修正が持ち込んだ置き換え記述「`+1` は `V/(V+1) < 1` を与え、
   証明はそれを使ってより強い `< ε/2` を導く」。マージ前の adversarial review が検出。
   実際の `calc` は等号を許す `V ≤ V+1` を使って `≤ ε/2` に至り、そこから `< ε` を
   閉じており、狭義の `< ε/2` は証明していない。

最終版の doc comment は証明が実際に踏む等号を許すステップを記述し、狭義の `< ε/2` は
「数学的には真だが statement の主張でも証明の結論でもない」と明記している。

`corpus/LerayHopf/mul_div_two_mul_add_one_lt.yaml` は PR #126 時点で**二次の誤りと
同型の記述**（`+1` の役割として $V/(V+1)<1$ を挙げ、$\varepsilon/2$ 未満を「主張より
強い」と述べる）を持っていたため、本 repin で最終 doc comment に整合させた。書かれて
いた等式・不等式自体は真だが、補題の内容として狭義の評価を前面に置く点が statement とも
証明とも一致していなかった。

なお leray-hopf#229 のクローズコメントは「notes#126 は既に正しい日本語 prose を持つため
修正目的の追い repin は不要」と記録しているが、これは一次の誤りのみを見た評価である。
二次の overclaim は notes 側にも存在していた。本節をその記録の訂正とする。

### CITATION.cff

`references[0].commit` を `2a06790` に更新したほか、PIN がリリースタグ上に乗ったため
`version: "0.2.0"` と `date-released: "2026-08-02"` を追加した。この 2 フィールドは
**PIN がリリースタグの commit と一致している間だけ**有効である。タグの付いていない
commit へ repin する際は削除すること（`commit` が抽出元の正であり続ける）。

display-name 衝突は 2 組 4 宣言のまま不変。`extracted/names-fallback.json` は
引き続き休眠・非更新。

## 追記 7: v0.2.1 リリース repin（PIN 2a06790 → e704400、leray-hopf#239）

`uda-lab/leray-hopf` の v0.2.1 リリースへの追随。`dev/v0.2.1` が **true merge commit**
PR #240 で `main` へ昇格し（親は `2a06790` = v0.2.0 リリースコミットと `61755f6` =
ブランチ tip）、その SHA `e704400` にタグ `v0.2.1` が付いた。追記 6 に続き、
本 repin でも PIN はリリースタグ上の commit を指す。

upstream 差分は 5 commit（#154 Wave 3–6 = `3bb3568` / `c6bc21c` / `6d63d04` /
`4c65483`、docs = `61755f6`）とマージコミット。Lean ソースの差分は 4 ファイル:

```
$ git diff --name-only 2a06790 e704400 -- '*.lean'
LerayHopf/R3/AubinLionsLimitPassage.lean
LerayHopf/R3/ConvectionForm.lean
LerayHopf/R3/SobolevEmbedding.lean
LerayHopf/Torus/TraceEnergy.lean
```

`lake exe extract_notes` 再実行（`61755f6` の worktree 上。`.lake/packages` は hardlink
共有、`.lake/build` は donor `8b3160c` から実コピーして seed。donor の tree は
`4c65483` と byte-identical で、`4c65483..61755f6` は `docs/build-and-checks.md` しか
触らないため olean は完全一致で、リビルドは発生しなかった。マージコミットの tree も
`61755f6` と一致するため、抽出結果はマージコミットに対するものとして正である）:
抽出宣言数 1,425 → 1,434。`decl_diff.py` による分類:

| 区分 | 件数 | 内容 | corpus 側対応 |
|---|---|---|---|
| 新設 | 9 | Wave 3–6 が切り出した private textbook-step 補題 | gloss エントリ 9 件を新設 |
| 削除 | 0 | — | — |
| ファイル移動・改名 | 0 | — | — |
| 可視性変更 | 0 | — | — |
| signature text 変更 | 0 | — | — |

**public 宣言は 837 → 837 で不変**であり、`signature_changed` も 0 である。すなわち
リリースが主張する「公開宣言リストは v0.2.0 と byte-identical」は、notes 側の独立な
抽出でも裏が取れている。universe が 9 増えるのは、抽出器が private 宣言も含めて
すべての LerayHopf モジュール宣言を出力し、可視性を `private` フィールドで表すため
である（`extracted/README.md`）。「private 補題の抽出だけなので universe 不変」は
成り立たない。

### 新設 9 件（すべて private・すべて gloss tier）

| 宣言 | 抽出元ファイル | Wave / PR | chapter |
|---|---|---|---|
| `isCoboundedUnder_ge_atTop_of_le` | `Torus/TraceEnergy.lean` | Wave 3 / #234 | energy |
| `liminf_nonneg_atTop_of_nonneg_of_le` | `Torus/TraceEnergy.lean` | Wave 3 / #234 | energy |
| `mul_div_four_mul_add_one_le` | `Torus/TraceEnergy.lean` | Wave 3 / #234 | energy |
| `exists_schwartz_seq_toLp_tendsto` | `R3/SobolevEmbedding.lean` | Wave 4 / #235 | compactness |
| `lineDeriv_toTemperedDistribution_eq_of_tendsto` | `R3/SobolevEmbedding.lean` | Wave 4 / #235 | compactness |
| `tendsto_of_norm_sub_le_of_tendsto` | `R3/SobolevEmbedding.lean` | Wave 4 / #235 | compactness |
| `abs_le_mul_of_tendsto` | `R3/ConvectionForm.lean` | Wave 5 / #236 | limit-passage |
| `sq_mul_euclidean_proj_le` | `R3/ConvectionForm.lean` | Wave 5 / #236 | limit-passage |
| `integral_add₃` | `R3/AubinLionsLimitPassage.lean` | Wave 6 / #237 | limit-passage |

chapter と tags は各抽出元ファイルの既存 private helper の慣行に合わせた。
9 件を追加したことで注釈カバレッジは 1,434/1,434 = 100% に戻る。追加しなければ
`validate.py` は通る（corpus ⊆ universe は保たれる）が、カバレッジが 1,425/1,434 =
99.4% に落ちる。

### `mul_div_four_mul_add_one_le` と追記 6 の overclaim 履歴

本補題は追記 6 で扱った `mul_div_two_mul_add_one_lt`（`R3/FrechetKolmogorov.lean`）の
$\varepsilon/4$ 版の姉妹である。追記 6 に記録したとおり、姉妹補題の doc comment は
leray-hopf#229 で二段階に修正されており、二次の誤りは「証明が $c/(c+1)<1$ を用いて
狭義の評価を示す」と述べた点にあった。本補題の主張は等号を許す $\le\varepsilon/4$ で
あり、証明が経由する段も等号を許す $c\le c+1$ である。gloss は同型の overclaim を
持ち込まないようその形で述べてある。

### CITATION.cff

`references[0].commit` を `e704400` に更新し、PIN が引き続きリリースタグ上に乗るため
`version` を `"0.2.1"`、`date-released` を `2026-08-08` に更新した。この 2 フィールドが
**PIN がリリースタグの commit と一致している間だけ**有効であるという追記 6 の但し書きは
そのまま有効である。

display-name 衝突は 2 組 4 宣言のまま不変。`extracted/names-fallback.json` は
引き続き休眠・非更新。
