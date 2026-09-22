# G4 Patch-2 実装報告（Master Specification v0.4.1a Addendum）

| 項目 | 内容 |
|---|---|
| 基準 | G4 Patch-1 Frozen Candidate（`f40086c` / source_hash `50e42c6a…62cb1`） |
| 権威 | ① Master Spec v0.4 ② v0.4.1a Addendum ③ G2 Delta Re-Audit v0.4.1a ④ Patch-1 repo |
| G2判定 | **BLOCKER 0 / HIGH 0 / MEDIUM 1 (N-3) / LOW 1 (LOW-4) / PASS**、HIGH-1・HIGH-2ともCLOSED |
| 作業範囲 | Addendum A〜G の7項目のみ。alpha条件・ScoreThreshold既定値・DD band・RiskPct・Universe・Exit A/B/C既定ロジック・Final Holdout規則・G2承認済み数値ゲートは**一切変更なし** |

入力3点のSHA-256を検証しました。アップロードされたPatch-1 ZIPは
`ed31290cc3dba6372f56c0eff9eafe6fd46134b738b3e33770ba0f7562cf927d` で、
私が凍結時に作成したZIPと**完全一致**しています。

---

## 1. 実装内容

### Addendum A / DEV-014 — STATE_UNCERTAIN時の既存建玉管理（EA）

処理順を正本付録Aの読み替えどおりに変更しました。

```
OnTick:
  RefreshAccountState()          // 信頼できる範囲でのみpeak/DDを更新
  ManagePositions()              // protective management は常に実行
  UpdateFakeoutWatches()         // 診断のみ
  if STATE_UNCERTAIN -> return   // 新規signal処理へ進まない
  decision_tick -> EvaluateDecisionTick()
```

* `src/G3_ResearchEA.mq5` の `OnTick()` に STATE_UNCERTAIN の return を新設。**Patch-1では `G3ConsumeSignal()` の後で判定していた**ため、状態ストア障害中にsignal ledgerへ書き込みが走っていました。今回は新規signal処理に入る前に返します。
* `ManagePositions()` に `protective_only` を導入。新規注文・増し玉は元から存在せず、SLは `G3MonotonicStop()` により不利方向へ動きません。**STATE_UNCERTAINを理由とした強制全決済は実装していません**（LOW-1）。
* サーバー側SL/TP・volume・ticketを毎tick再取得。protective_only かつ サーバー側保護注文が無く再構成もできない建玉は、ブローカーが保持するまま**触らない**（「状態依存の処理で再構成不能なものは実行しない」）。
* `RefreshAccountState()` は STATE_UNCERTAIN 下で peak/DailyStartEquity を更新せず、ストアへも書きません（信頼できないpeakの固着を防ぐ）。

### Addendum B / DEV-017 — 手動復旧（EA）

* 自動復旧は存在しません。`InpManualRecovery`（NONE / RECONCILE / NEW_EPOCH）、`InpOperatorId`、`InpG1ReviewRecord` をoperator用入力として追加。
* `G3RecoveryPrecheck()` が前提条件を判定し、**拒否理由も含めて全てaudit log**へ記録:
  STATE_UNCERTAINでない / operator未指定 / G1 review record未指定 / 建玉が残っている。
* `RECONCILE` は File・GV・deal history・open positions を照合して証跡を残すだけで、**stateを一切変更しません**。
* `NEW_EPOCH` は「全建玉flat」かつ「G1 review record」かつ「人間operator明示」の3条件が揃ったときのみ。`epoch_id` をインクリメントし PeakEquity / DailyStartEquity を現equityで再初期化、audit logに epoch_id / operator / timestamp / reason / prior_state_hash / current_equity を記録します。
* **HardStop不明時は解除しません** — `G3NewEpochHardStop(known=false, …)` は常に true を返し、新epochは `HARD_STOP` で開始します（G1/G2 review対象）。
* epoch作成後は `g_epoch_restart_required` により当セッションでは新規取引せず、次回OnInitで両ストア一致を確認してから再開します。
* StateStore schema_version を 2 → **3**（`epoch` フィールド追加）。旧レコードは読み込まれず再初期化されます。

### Addendum E / DEV-007 — fakeout_3 / fakeout_6（EA）

* 基準は **initial entry price と initial SL price** に固定。BUYはBid側、SELLはAsk側で initial SL へ到達したら true。
* entryを含むM5バーを **bar 1** として数え、ExitMode・BE・partial・trail・timeoutで建玉が先に終了しても観測窓は走り続けます（counterfactual判定）。
* 値は **TRUE / FALSE / NA の三値**。窓を完全に観測できなかった場合は NA であり、**falseに落としません**。再起動で復元した観測窓は `observation_gap` が立ち、未確定のものは NA で確定します。
* 6本窓の完了時に `FAKEOUT` レコードを出力（`signal_id` で結合）。EXITレコードにもその時点の判定を載せます。
* 観測窓は `fakeout_<account>_<magic>_<symbol>.csv` に永続化。

### Addendum F / ISSUE-003 — offline chronological portfolio replay（研究器具）

EA側: portfolio guard 適用**前**の strategy-eligible candidate を `SHADOW` レコードとして出力します。

オフライン側 `tools/g3research/portfolio_replay.py`:

* 同一decision timestampの処理順は固定 **AUDUSD, EURUSD, GBPUSD, NZDUSD, USDCAD, USDCHF, USDJPY**、Stage-2はASCII昇順。
* 共有Equity / PeakEquity / DD state（バンド・ヒステリシス・latch）/ DailyEntryLock / MaxPositions / total initial risk / currency exposure / Correlation Guard を**単一state machine**で逐次適用。
* DD stateに応じて risk_pct と ScoreThreshold をその時点の共有stateで再判定します。
* **銘柄別成績の単純合算を行うAPIは存在しません。**
* cross-check期間は D1 ATR14/Close の日次中央値をproxyに、非重複3ヶ月ブロックの最高/最低を機械選択（同値は最古ブロック固定）。**成績は引数にすら現れません。**
* cross-check gate は 98.0% / 0.10R / 90.0% / 1.0pp の4条件AND。
* **N-3対応**: `simultaneous_candidate_counts()` / `order_conflict_rejections()` / `representativeness_note()` を実装。同時candidate件数を報告し、5件未満なら「代表性が限定的」注記をmetadataへ出します。**新しいPASS閾値は追加していません**（開示要件のみ）。

### Addendum D / DEV-006 — deterministic execution stress replay（研究器具）

`tools/g3research/stress_replay.py`:

* シナリオは Base / Stress-1 / Stress-2 / Stress-3 の**閉じた表**のみ。v0.4 §13.5の値（×1.5+0.25 / ×2.0+0.50 / ×3.0+1.00）以外は `StressScenarioError` で拒否します。
* entry/exit双方へ不利方向に適用。stressed spread が Spread Hard Max を超えた candidate は stress run で entry reject。
* **単なるP/L控除にしていません**: stressed entry から r_distance・TP(2.0R)・BE(1.0R)・partial(1.5R)・trail ATR距離・timeout MFE基準を再計算します。
* Base parity gate は4条件AND: 99.0% / 98.0% / 0.05R / 2.0%。Net R差分率の分母は `max(|MT5 Net R|, 1.0R)`。1条件でも未達なら `stress_results_usable_as_g3_pass_evidence = False`。

### Addendum C / DEV-005 — OAT → freeze → WF → Static OOS（研究器具）

`tools/g3research/oat_pipeline.py`:

* OATは **Research IS のみ**。Development / Static OOS を渡すと `PipelineOrderError`、Final Holdout は `HoldoutAccessError`。
* pair-local family は単体pair Research IS、portfolio共有state依存 family は Research IS 上の offline portfolio replay（N-2）。
* family-level報告が不完全なら `report_oat_families()` が拒否（§14.1の「選択提示はG3 FAIL」を構造で防止）。
* freeze後にWF、WFは診断専用。`adopt_walk_forward_parameter()` は**常に例外を投げる**API として存在します。
* `wf_iteration_manifest`: 同一 (spec_hash, config_hash, data_hash) のconfirmatory WFは1回のみ。TECHNICAL_RERUNは理由・証跡が必須で、canonical windowを変更すると拒否。**LOW-4対応**として `review_required=True` を立て `technical_rerun_review_queue()` で後日レビュー可能にしています。
* Static OOSはWF後かつ仕様変更なしのときのみ one-shot。2回目は拒否。OOS閲覧後の entry/exit/score/threshold/risk_policy 変更は `oos_contaminated` を立てます。

### Addendum G / ISSUE-013 — 61〜71ヶ月データ（研究器具）

`tools/g3research/data_intake.py`:

| 保有月数 | canonical window | Holdout | Development | IS | Static OOS | 除外 |
|---|---|---|---|---|---|---|
| < 60 | — | — | — | — | — | G3 numerical gate 開始不可 |
| 60〜71 | 最新60m | 12m | 48m | 29m | 19m | 最古 0〜11m |
| >= 72 | 最新72m | 12m | 60m | 36m | 24m | 最古の余剰 |

* 余剰月は Gate performance 集計に使わず、WF foldの追加にも使いません（60m/71m で fold数は同一の4）。
* `data_intake_manifest` に canonical window と excluded period、`final_holdout_access: "NONE"` を記録。
* 71→72ヶ月境界の不連続は `boundary_note` として全manifestに載ります。

---

## 2. 変更していないもの

alpha条件、ScoreThreshold既定値（5）、DD band（6/8/10%、復帰5/7%）、RiskPct（0.50/0.25/0.10%）、Universe、Exit A/B/C の既定ロジック、Final Holdout規則、G2承認済み数値ゲート。

`config/` は未変更です（`config_hash` 不変）。研究器具の定数は `tools/g3research/spec_constants.py` がEAの `#define` と突き合わせ、**drift時は例外**にします（テストP-000）。

## 3. テスト

| 種別 | 件数 | 結果 |
|---|---|---|
| Patch-1から維持した host assertions | 179 | 全件PASS |
| Patch-2で追加した host assertions（Addendum A/B/E） | 28 | PASS |
| **host合計** | **207** | **0 failures** |
| 研究器具の回帰テスト（Addendum C/D/F/G、Python） | 59 | **0 failures** |

ご指定の最低カバレッジ項目の対応:

| 要求項目 | テストID |
|---|---|
| STATE_UNCERTAIN中もprotective management継続 | Q-005〜Q-007（観測継続）＋ OnTick順序（統合テスト I-030） |
| STATE_UNCERTAINで新規注文停止 | I-030 / Q-009b（precheck） |
| manual recovery自動実行禁止 | Q-009a〜Q-009g |
| WF iteration manifest | P-400群（5件） |
| technical rerun変更禁止 | P-400群（理由・証跡・window不変） |
| Base replay parity 4条件 | P-500群（parity gate 5件＋分母floor） |
| Stress replay | P-500群（closed table・両脚・hard max・geometry再計算） |
| fakeout_3/6 counterfactual | Q-001〜Q-008 |
| simultaneous candidate tie-break | P-600群（6件） |
| shared DD state | P-700群 |
| currency exposure | P-700群 |
| correlation guard | P-800群 |
| MaxPositions | P-700群 |
| 61/65/71/72ヶ月境界 | P-100群 |
| Final Holdout未アクセス | P-200群 + 静的チェッカの禁止構文スキャン |

## 4. ゲート

| gate | 結果 |
|---|---|
| 静的チェック | **0 issues** |
| host build（`-Wall -Wextra -Wpedantic -Werror`） | **warning 0 / error 0** |
| MetaEditor compile | **NOT_RUN** — 本環境にMQL5ツールチェーンなし。PASSとは報告しません |
| MT5統合テスト | **NOT_RUN** |
| Final Holdout | 未導入・未参照・未計算・未可視化 |

## 5. ハッシュ再生成

```
Patch-1 baseline source_hash : 50e42c6af071ea65b407680aad45acf86a682784684325ed9a6ddfa2c3462cb1
Patch-2 source_hash          : 6faa0ea1cffceb67ded95736de2315401aacf3d7ec6158ed7fc151e7028d6ee6
config_hash                  : 37c820c795a23d9c30a11b19d8bd811f0bbd0c255819b86695a1c8dd1d2ebe5e
schema_hash                  : ea3f1e17364f26c73d5e1686db76d0eaec61bdfedf7f3151aa26bac3ac20a332
release_hash                 : 61ddcf9eede0e7b0a4403e57bc347544ada7a798c953916eefa6ceea28f33eb0
spec_hash (v0.4)             : 229f29920ee411cf008442f56a1061583fc564ad50c979c32bf7996ada7ff965
addendum_hash (v0.4.1a)      : fa107ac25d161253511a69b620ef70dd66677406abb539ad8031de2b680aa40c
g2_delta_re_audit_v0.4.1a    : 5567a3297a79430d40d5b8d9009044b8b32c059e78bff48c5b2ef74c5e7f7f85
EA_hash                      : PENDING_METAEDITOR_COMPILE
```

`config/` は未変更のため `config_hash` は Patch-1 と同一です。Patch-2では
ハッシュ対象に `tests/**/*.py`・`*.sh` と `tools/**/*.sh` を追加し、テスト
スイート自体も再現性の対象に含めました。

## 6. 残る未解決項目

| id | 種別 | 内容 |
|---|---|---|
| ISSUE-016 / CR-014 | BLOCKER | MetaEditor実コンパイル・統合テスト（環境外） |
| ISSUE-012 / CR-009 | BLOCKER | Primary/第2feed、symbol spec、initial equity、account currency、コスト情報 |
| N-3 | MEDIUM（非ブロッキング） | 実装済み（開示要件）。G3実施要領への反映はManus側 |
| LOW-4 | LOW（非ブロッキング） | 実装済み（review queue）。サンプル確認手続きはG2 v0.5系 |

G2 Delta Re-Audit の申し送りどおり、N-3・LOW-4 はPatch-2の実装内容を変えるものではなく、開示・手続き面として実装に織り込みました。
