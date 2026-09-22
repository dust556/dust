# G4 Research EA 実装報告書

| 項目 | 内容 |
|---|---|
| 成果物 | G3 Research EA（MetaTrader 5 / MQL5） |
| 権威文書 | Master Specification v0.4 |
| 担当 | G4実装担当 / Claude Code |
| ブランチ | `claude/g3-research-ea-cp6pc7` |
| コミット | `cc4a360` |
| 目的 | G3数値研究（IS / OOS / Walk-Forward / Stress / Monte Carlo / 感度分析）用データ生成 |
| 最終ステータス | **NOT_READY_FOR_G3_DATA** |

本EAは測定器であり取引商品ではありません。収益性の判断、最適化、Final Holdoutへの
アクセスは一切行っていません。PASS/FAIL判定はManusが行います。

---

## 1. 完成ソース一覧

### `src/` — 13ファイル

| ファイル | 担当仕様章 |
|---|---|
| `G3_ResearchEA.mq5` | EA本体 / OnInit口座モード検査 / decision_tick / ポジション管理 |
| `G3Types.mqh` | 共通型・reason code・移植可能数学（median, Pearson, floor, FNV-1a） |
| `TimeSync.mqh` | 4.1 MTF同期・closed bar解決・signal_id |
| `SignalH4.mqh` | 5 H4 direction gate / quality 0-2 |
| `SetupM15.mqh` | 6 M15 setup 0-2 |
| `TriggerM5.mqh` | 7 M5 breakout hard gate / quality 0-2 |
| `MarketFilters.mqh` | 8 VolRatio / SpreadRatio / total score / effective threshold |
| `RiskManager.mqh` | 9 SL 3段階 / lot / 10 DD state machine / 11 DailyEntryLock |
| `PortfolioManager.mqh` | 12 MaxPositions / total risk / currency exposure / correlation guard |
| `OrderManager.mqh` | 13 市場再取得 / deviation / 単発OrderSend |
| `ExitManager.mqh` | 14 ExitMode A/B/C / partial / trail / 15 timeout / MFE・MAE |
| `StateStore.mqh` | 4.1 exactly-once / 10 二重ストア・checksum・audit log |
| `ResearchLogger.mqh` | 16 研究CSV（96列） |

### その他の成果物

| ディレクトリ | 内容 |
|---|---|
| `config/` | `baseline.set` / `score_4.set` / `score_5.set` / `score_6.set` |
| `schema/` | `research_log_schema.md`（96列）/ `reason_codes.md`（41コード）※ソースから自動生成 |
| `tests/` | ホスト単体テスト（実行可能）/ 統合テスト計画 / 既知シナリオ |
| `manifests/` | `build_manifest.json` / `EA_hash.txt` / `spec_hash.txt` / `config_hash.txt` |
| `docs/` | 実装対応表 / 制約 / ISSUE・CR / コンパイル報告 / Input一覧 / 本報告書 |
| `tools/` | 静的チェッカ / ハッシュ算出 / ドキュメント生成器（5スクリプト） |

---

## 2. コンパイル結果

**Compile: NOT_RUN**

本実行環境（Linuxコンテナ）にMetaEditor / MetaTrader 5 / Wineが存在せず、
第21章のコンパイルゲートは**実行不能**でした。PASSと偽って報告していません
（ISSUE-016 / CR-014）。

### 代替として実際に実行した検証

| 検証 | コマンド | 結果 |
|---|---|---|
| 静的事前チェック | `python3 tools/mql5_static_check.py` | **0 issues**（13ファイル / G3シンボル193定義・125参照） |
| ホスト単体テストのビルド | `g++ -std=c++17 -Wall -Wextra -Werror` | **warning 0 / error 0** |

### 静的チェックの検査内容

1. 括弧（`{}` `()` `[]`）の均衡 — コメント・文字列リテラル認識あり
2. `#if` / `#ifndef` / `#endif` のネスト均衡
3. include guardの存在と整合、`#include` 先の解決
4. 呼び出されている全 `G3*` シンボルが `src/` 内で定義されているか
5. **禁止構文スキャン** — Final Holdout / martingale / ナンピン / netting /
   `WebRequest`（外部リアルタイム判断）/ optimizer
6. **shift=0（形成中バー）読み取りの正当化必須化** — `CopyClose` / `CopyOpen` /
   `CopyHigh` / `CopyLow` / `CopyBuffer` / `CopyRates` が start=0 を使う場合、
   直上4行以内に `G3-CHECK: shift0-safe` の明示的根拠コメントが無ければ失敗

該当は `G3D1Returns()` の1箇所のみ。index 0 は「スキップするためにコピーするだけで
値は一切使用しない」ことをソース内に注記済みです。

---

## 3. warning / error 一覧

| 対象 | error | warning |
|---|---|---|
| MQL5（MetaEditor） | **UNKNOWN** — 実行不能 | **UNKNOWN** — 実行不能 |
| 静的チェック | 0 | 0 |
| ホストテストビルド（`-Wall -Wextra -Werror`） | 0 | 0 |

MQL5コンパイラのwarningは未確認です。第21章のゲートはISSUE-016 / CR-014として
未解決のまま残しています。**warningを勝手に無視・抑制した箇所はありません。**

---

## 4. Implementation Mapping

`docs/implementation_mapping.md` に「仕様章 → 実装ファイル → 関数 → テストケース」の
対応表を作成しました（70行超）。

例:

```
4.1 MTF sync
  → TimeSync.mqh
  → G3ResolveClosedBarIndex() / G3ResolveHtfBar()
  → T-001 test_no_forming_H4_reference

10 StateStore
  → StateStore.mqh
  → G3ReconcileStores() / G3MergeConservative()
  → T-009 test_both_stores_lost_state_uncertain

13 deviation hard cap
  → OrderManager.mqh
  → G3BuildDeviationPlan()
  → T-022 test_deviation_cap_exceeded_blocks_send
```

`T-xxx` は実行可能なホスト単体テスト、`I-xxx` はMT5端末が必要な統合テストです。

---

## 5. Unit Test結果

**PASS — 142 assertions / 0 failures**

実行: `tests/run_unit_tests.sh`（C++17コンパイラのみ、MetaTrader不要）

EAと**同一の `src/*.mqh` の純粋ロジック部**を、MQL5 shim（`tests/host/mql5_shim.h`）
経由でホストコンパイラがビルドして実行しています。ロジックを別実装したモックでは
ありません。端末依存コードは `#ifndef G3_HOST_TEST` で分離されています。

### グループ別内訳

| グループ | 仕様章 | assertion数 |
|---|---|---|
| `test_time_sync` | 4.1 MTF同期 / decision_tick / signal_id | 7 |
| `test_state_store` | 10 StateStore / 二重ストア / exactly-once | 14 |
| `test_dd_state_machine` | 10, 11 DD状態機械 / hysteresis / latch / DailyEntryLock | 15 |
| `test_risk_and_lots` | 9 SL配置 / RiskMoney / lot / post-fill risk | 17 |
| `test_deviation` | 13 PipSize / deviation / HardCap | 11 |
| `test_exits` | 14, 15 ExitMode / partial / trail / timeout / MFE・MAE | 25 |
| `test_portfolio` | 12 ポートフォリオ制限 / 通貨エクスポージャ / 相関ガード | 15 |
| `test_signal_logic` | 5, 6, 7, 8 H4 / M15 / M5 / market quality | 33 |
| `test_log_schema` | 16 研究ログスキーマ整合 | 5 |

### 第20章の要求項目カバレッジ（純粋ロジックで検証可能なもの）

| 要求項目 | テストID | 結果 |
|---|---|---|
| forming H4/M15を参照しない | T-001, T-001b, T-003 | PASS |
| DST / server timezone | T-001b（エポック秒境界演算） | PASS |
| 週末gap | T-002 | PASS |
| signal_id重複防止 | T-005, T-005b, T-005c | PASS |
| EA再起動 | T-006 | PASS |
| File破損 | T-007, T-007b, T-007c | PASS |
| GlobalVariable破損 | T-008 | PASS |
| 両方破損 → STATE_UNCERTAIN | T-009, T-009b | PASS |
| DD 6 / 8 / 10% 境界 | T-011, T-011b, T-012, T-012b, T-013 | PASS |
| DD recovery hysteresis | T-014, T-014b, T-014c, T-014d | PASS |
| 10% HardStop latch | T-013, T-015 | PASS |
| DailyEntryLock | T-017 | PASS |
| Lot floor | T-018, T-018b, T-018c | PASS |
| VolumeMin拒否 | T-019 | PASS |
| JPY / 非JPY | T-020b, T-020d | PASS |
| 3桁 / 5桁 | T-020, T-020b, T-021, T-021b | PASS |
| StopLevel | T-023, T-023b, T-026 | PASS |
| Deviation HardCap | T-021〜T-021f, T-022 | PASS |
| post-fill risk 105% | T-027, T-027b, T-027c | PASS |
| Partial不可 0.01lot | T-028 | PASS |
| Partial 40-60%境界 | T-029, T-029b, T-029c, T-029d | PASS |
| Trail逆行禁止 | T-030, T-030b | PASS |
| Timeout | T-031, T-031b, T-031c, T-031d | PASS |
| Correlation READY | T-032, T-032b, T-032c | PASS |
| CORR_WARMUP_UNKNOWN | T-033, T-033b | PASS |
| FreezeLevel | — | 統合テスト I-022 へ |
| OrderSend失敗 | — | 統合テスト I-014, I-015 へ |
| Retail Hedging guard | — | 統合テスト I-001 へ |
| Netting拒否 | — | 統合テスト I-002 へ |

---

## 6. Integration Test結果

**NOT_RUN** — MT5端末が必要なため本環境では実行不能。

`tests/integration_test_plan.md` に **29ケース（I-001〜I-029）** を、前提条件・手順・
期待結果つきで定義し、全件 `NOT_RUN` と明記しています。主なもの:

| ID | ケース |
|---|---|
| I-001 / I-002 | Retail Hedging guard / Netting口座での `INIT_FAILED` |
| I-004 | decision_tickが新M5バーの最初のtickであること |
| I-005 / I-006 | consume→flush→判定の順序 / consume直後クラッシュ時の重複防止 |
| I-010 / I-010b / I-010c | File破損 / GV破損 / 両破損 → STATE_UNCERTAIN |
| I-014 / I-015 | OrderSendが1回のみ・retryなし / 失敗時のログ |
| I-016 | post-fill risk 105%超時の縮小または全決済 |
| I-021 | 再起動時のポジション状態復元 |
| I-022 | StopLevel / FreezeLevel |
| I-023 / I-024 | DST切替 / 週末gap |
| I-029 | Final Holdout成果物が存在しないことの確認 |

---

## 7. G3用Input一覧

詳細は `docs/g3_inputs.md`。

### 登録済み研究Input（第17章）

| Input | 型 | 許容値 | 既定 | 仕様章 |
|---|---|---|---|---|
| `InpScoreThreshold` | `ENUM_G3_SCORE_THRESHOLD` | 4 / 5 / 6 のみ | 5（baseline） | 8 |
| `InpExitMode` | `ENUM_G3_EXIT_MODE` | A(0) / B(1) / C(2) | A | 14 |
| `InpTimeout` | `ENUM_G3_TIMEOUT` | OFF(0) / 6 / 12 / 18 / 24 | OFF | 15 |

enum化により、テスターで範囲外の値を選択できません。これが総当たり最適化グリッドを
作らせない設計上の担保になっています。

### Execution stress Input（既定値は無影響）

| Input | 型 | 既定 | 効果 |
|---|---|---|---|
| `InpStressExtraSpreadPoints` | `int` | 0 | SpreadRatioフィルタとdeviation計算に用いるスプレッドへ加算 |
| `InpStressCommissionPerLot` | `double` | 0.0 | 1.00ロットあたり手数料。cost-adjusted BE用に価格換算 |

スリッページのstressは未実装です。EAからMT5テスターへスリッページを注入する手段が
存在しないためで、ISSUE-006 / L-06として記録しています。

### Safety stress Input

**1つも作成していません。** 第9〜12章の安全側定数（リスク率、DD閾値、hysteresis、
MaxPositions、リスク上限、相関閾値）は仕様で固定されており、パラメータ化していません。
事前登録リストが未提供のためです（CR-006）。

### 研究基盤Input（判定に一切影響しない）

`InpMagic` / `InpRunId` / `InpManualHardStopReset`

---

## 8. CSVログ schema

`schema/research_log_schema.md`（**96列**、`G3LogHeader()` からスクリプト生成）

* 形式: CSV / カンマ区切り / ANSI / CRLF
* 出力先: `<共通フォルダ>/Files/G3RSRCH/log_<account>_<magic>_<symbol>_<run_id>.csv`
* `record_type` = `EVAL` / `ENTRY` / `PARTIAL` / `EXIT`
* **約定した取引だけでなく、候補・見送りも全decision_tickで1行出力**
* 全レコードを `signal_id` で結合可能

第16章の必須フィールドは全て実装済みです。ただし `fakeout_3` / `fakeout_6` は
仕様に定義が存在しないため、**推測実装せず `NA_SPEC_UNDEFINED` 固定**としています
（CR-002）。

スキーマとコードの乖離を防ぐため、`schema/research_log_schema.md` と
`schema/reason_codes.md` はソースから自動生成しています
（`tools/gen_log_schema.py` / `tools/gen_reason_codes.py`）。列に説明が欠けていると
生成が失敗します。

---

## 9. hash / manifest

```
source_hash  : 59b5da9afa41627dbb243090a37883c064266ccd8b5f2b5f59902d48ab295c61
config_hash  : 37c820c795a23d9c30a11b19d8bd811f0bbd0c255819b86695a1c8dd1d2ebe5e
schema_hash  : b85614847bd45afd3fb43d5592e4dd6bb3b4dccecb7f150960ff7d666489d168
release_hash : d47ec0a8955f41bcc88afaac47a6f510b38a885064d666561ff6545abe131f65
EA_hash      : PENDING_METAEDITOR_COMPILE
spec_hash    : PENDING_SPEC_DOCUMENT
```

SHA-256算出スクリプト `tools/compute_hashes.py` を同梱しています（再実行で同一値）。

**再現性ルール**: G3の結果が引用可能になるのは、`source_hash`、`config_hash`、
そして実際にコンパイルされた `EA_hash` の3つが全て記録されたときのみです。

---

## 10. Known Limitations

詳細は `docs/known_limitations.md`。

### 仕様が沈黙している箇所で置いた仮定（A-01〜A-14）

| ID | 仮定 |
|---|---|
| A-01 | DD% = (PeakEquity − Equity) ÷ PeakEquity × 100（peakはequity基準） |
| A-02 | 偶数個サンプルのmedianは中央2値の平均 |
| A-03 | M15プルバック帯の 0.20×ATR は M15 ATR14 shift 1 |
| A-04 | 第8・9・13章の `ATR14[1]` は M5 ATR14 shift 1 |
| A-05 | 相関はD1終値対数リターン。60リターンには61本の確定バーが必要 |
| A-06 | cost-adjusted BE のコスト = 現在スプレッド＋手数料Input（価格換算） |
| A-07 | StopsLevelの基準価格は BUY→Bid / SELL→Ask |
| A-08 | 「同一currency component同方向」は符号付き通貨エクスポージャ |
| A-09 | ストア不一致時の保守的マージ規則（DD severe / latch OR / peak max 等） |
| A-10 | RESTRICTED時のみ `max(6, input)`、他状態は登録Input値 |
| A-11 | DD回復は1評価あたり1段階（RESTRICTED→MODERATE→NORMAL） |
| A-12 | PeakEquityはequity基準でリセットしない |
| A-13 | DailyStartEquityはサーバ日付変更後の最初のtickで確定 |
| A-14 | signal消費は銘柄ごとに単調。過去・同一のidは拒否 |

全てログ列に出力しているため、原本との突合後に影響を再実行なしで測定できます。

### 制約（L-01〜L-11）主要項目

| ID | 制約 |
|---|---|
| L-01 | 本環境にMQL5ツールチェーンが無く、コンパイルゲートを実行できない |
| L-02 | ホストテストは純粋ロジックのみ。端末依存部は未実行 |
| L-04 | MFE/MAEはtickごとに決済側価格で更新。ティック密度に解像度が依存 |
| L-06 | スリッページstressはEAから注入不能 |
| L-08 | `fakeout_3` / `fakeout_6` は未定義のため未投入 |
| **L-09** | **MT5ストラテジーテスターは1EAしか実行しないため、1銘柄1インスタンス設計では第12章のポートフォリオ制約をバックテストで再現できない** |
| L-10 | STATE_UNCERTAINからの復帰手順が仕様に無い |

L-09は研究設計に直接影響するため、ISSUE-003 / CR-003として提出しています。

---

## 11. ISSUE一覧（全17件）

`docs/change_requests.md` に全文。

| ID | 深刻度 | 概要 |
|---|---|---|
| ISSUE-001 | **BLOCKER** | Master Specification v0.4 / G2 Re-Audit v0.4 / G3研究開始記録が環境内に存在しなかった（リポジトリは空）。実装は権威順位4位のプロンプト記述のみに依拠。`spec_hash` 算出不可 |
| ISSUE-012 | **BLOCKER** | tick feed / 第2フィード / symbol spec / initial equity / account currency / データ期間 未提供 |
| ISSUE-013 | **BLOCKER** | 61〜71ヶ月時のIS/OOS/WF分割がv0.4に未定義 |
| ISSUE-016 | **BLOCKER** | 第21章コンパイルゲートの実行環境が無い |
| ISSUE-002 | **HIGH** | 「signed correlation」が方向調整込みか生Pearson符号か不明 |
| ISSUE-003 | **HIGH** | テスター1EA制約によりポートフォリオ制約が検証不能（L-09） |
| ISSUE-004 | MEDIUM | DD表の `Score>=5` と登録Input 4 の関係が未定義 |
| ISSUE-005 | MEDIUM | `fakeout_3` / `fakeout_6` の定義が存在しない |
| ISSUE-006 | MEDIUM | OAT対象・safety stress の事前登録リスト未提供 |
| ISSUE-007 | MEDIUM | 第6・8・9・13章のATR時間軸／shiftが明示されていない |
| ISSUE-008 | MEDIUM | DDの定義（peak基準・リセット規則）が未記載 |
| ISSUE-010 | MEDIUM | cost-adjusted BE のコスト構成が未列挙 |
| ISSUE-014 | MEDIUM | 相関の入力系列（価格／単純リターン／対数リターン）が未指定 |
| ISSUE-009 | LOW | 第13章の deviation `min()` 式が到達不能（cap超は送信しないため） |
| ISSUE-011 | LOW | M15のみ最小スコアの記載が無い（記載どおり下限なしで実装） |
| ISSUE-015 | LOW | STATE_UNCERTAINからの復帰手順が未定義 |
| ISSUE-017 | LOW | MaxPositions=3 が口座単位か銘柄単位か未記載 |

### ISSUE-002の扱い（重要）

判定は方向調整版で行いつつ、**生Pearson版の値も同時にログ出力**しています
（`corr_cluster_risk` と `corr_cluster_risk_raw`）。どちらの解釈が正しくても、
再実行なしで影響を評価できます。

---

## 12. CHANGE REQUEST一覧（全14件）

| ID | 要求 | 対応ISSUE |
|---|---|---|
| CR-001 | Master Spec v0.4・G2 Re-Audit v0.4・G3開始記録の原本とSHA-256の提供 | ISSUE-001 |
| CR-002 | `fakeout_3` / `fakeout_6` の定義（基準レベル・窓・フラグか量か） | ISSUE-005 |
| CR-003 | ポートフォリオ研究データの生成方式の決定（案a/b/cを提示、実装側では選択せず） | ISSUE-003 |
| CR-004 | 「signed correlation」の定義確定 | ISSUE-002 |
| CR-005 | 登録ScoreThresholdとDD表の最小スコアの関係の定義 | ISSUE-004 |
| CR-006 | OAT対象・safety stress・execution stress の事前登録リスト公開 | ISSUE-006 |
| CR-007 | ATR時間軸／DD定義／相関入力系列の確認 | ISSUE-007, 008, 014 |
| CR-008 | 61〜71ヶ月データの分割定義、または最小データ長の明示 | ISSUE-013 |
| CR-009 | tick feed・symbol spec・initial equity・account currency・期間の提供 | ISSUE-012 |
| CR-010 | cost-adjusted BE のコスト構成の列挙 | ISSUE-010 |
| CR-011 | M15に最小スコアが無いことの確認 | ISSUE-011 |
| CR-012 | deviation `min()` 式が冗長であることの確認 | ISSUE-009 |
| CR-013 | STATE_UNCERTAIN からの復帰手順の定義 | ISSUE-015 |
| CR-014 | MetaEditor搭載機の指定とコンパイルゲート実行、`.ex5` ハッシュの記録 | ISSUE-016 |

### CR-003の提示案（決定はManus）

* **案a**: 単一インスタンス多銘柄モード。decision_tickを「各銘柄の新M5バー後に
  *観測された*最初のtick」と再定義（第4.1章からの明示的な逸脱となる）
* **案b**: 銘柄別バックテスト＋EVAL/ENTRY/EXITログを第12章の規則で再生する
  オフラインポートフォリオシミュレータ
* **案c**: ポートフォリオ根拠をforward / live運用に限定

---

## 13. 仕様一致 自己監査

### 絶対禁止項目（第2章）

| 項目 | 監査結果 |
|---|---|
| Final Holdoutへのアクセス | **なし**（未導入・未参照・未計算・未可視化。ディレクトリも作成せず） |
| Final Holdout期間のバックテスト | **なし** |
| 形成中バー shift=0 の売買判定利用 | **なし**（静的チェッカで機械的に強制） |
| look-ahead | **なし**（H4/M15は `open+period <= signal_close_time` で解決） |
| repaint依存 | **なし**（M5はshift 1以降のみ参照） |
| ナンピン | **なし** |
| マーチンゲール / 損失後の倍掛け | **なし**（ロットは常に `Equity × RiskPct ÷ 1lot損失` のみ） |
| 仕様外のフィルタ追加 | **なし** |
| 結果を見てパラメータ変更 | **なし**（バックテスト自体を実行していない） |
| GA / Bayesian / 総当たり最適化 | **なし**（enum Inputでグリッド化を阻止） |
| Netting口座への対応追加 | **なし**（`RETAIL_HEDGING` 以外は `INIT_FAILED`） |
| 外部AIによるリアルタイム売買判断 | **なし**（`WebRequest` 等を静的スキャンで禁止） |
| 仕様にないニュースフィルタ | **なし** |
| 同一signal_idの重複注文 | **構造的に不可**（consume → 二重flush → 判定の順。flush失敗時は機会損失側に倒す） |
| 仕様不明点の自己判断補完 | **なし**（全てISSUE / CRとして提出、仮定はA-xxとして文書化・ログ出力） |

### 仕様適合サマリ

* **仕様と矛盾する実装: 0件**
* 仕様が沈黙している箇所での仮定: **14件**（全て文書化・CSV出力）
* 第22章準拠: 架空のバックテスト結果は**一切作成していません**

---

## 最終結果

```
G4 RESEARCH EA IMPLEMENTATION RESULT

- Compile:            NOT_RUN  (MetaEditor unavailable in this environment;
                      static pre-compile check PASS, 0 issues;
                      host build with -Wall -Wextra -Werror: 0 warnings)
- Unit Tests:         PASS     (142 assertions, 0 failures)
- Integration Tests:  NOT_RUN  (29 cases planned, MT5 terminal required)
- Spec Deviations:    0        (plus 14 documented assumptions where the
                      specification is silent)
- Open BLOCKER:       4        (ISSUE-001, 012, 013, 016)
- Open HIGH:          2        (ISSUE-002, 003)
- Change Requests:    14

Final Status:

NOT_READY_FOR_G3_DATA
```

### NOT_READY の理由と解除条件（この3点のみ）

1. **CR-014** — MetaEditor搭載機でコンパイルし、error/warningを逐語記録、
   `.ex5` のSHA-256を `manifests/EA_hash.txt` へ記入（第21章ゲート）
2. **CR-001** — Master Specification v0.4原本の提供（全数値の突合と `spec_hash` 確定）
3. **CR-009 / CR-008** — tick feed・symbol spec・initial equity・account currency・
   データ期間の提供と、61〜71ヶ月時の分割定義

これらが揃えば、コード側は追加改修なしでG3データ生成に入れる状態です。
収益性・勝率の推定は一切行っていません。

---

## 付録: 検証の再現手順

```sh
python3 tools/mql5_static_check.py     # 構造＋禁止構文スキャン
tests/run_unit_tests.sh                # 142 assertions
python3 tools/compute_hashes.py        # manifest / ソースハッシュ
python3 tools/gen_log_schema.py        # schema/research_log_schema.md 再生成
python3 tools/gen_reason_codes.py      # schema/reason_codes.md 再生成
python3 tools/gen_unit_test_plan.py    # tests/unit_test_plan.md 再生成
```
