# G4 仕様適合パッチ報告（DEV-001 / 002 / 003 / 004 / 008 / 009-016）

| 項目 | 内容 |
|---|---|
| 基準 | `docs/G4_reconciliation_report.md`（コミット `d95a7ae`） |
| 作業範囲 | **Master Specification v0.4との明白な実装不一致の是正のみ**。仕様変更・利益改善・パラメータ調整なし |
| 変更前 source_hash | `59b5da9afa41627dbb243090a37883c064266ccd8b5f2b5f59902d48ab295c61` |
| 変更後 source_hash | `b141c0ffac55bd09a878ec1a759d505ccc56308c7cf8339588bbab0495a3e7db` |
| 変更後 release_hash | `1f0064e6668d7f965834e346e6e343e2f7f0d18a40c42eaf6142254f6ecf9e0c` |

---

## 1. 修正内容

### DEV-001 (BLOCKER) — M15 pullbackのATRを同shiftに

正本6章「各Low/Highは同じshiftのEMA20/**ATR**と比較し」。

* `M15Input.atr14_s1` を `atr14[3]` に変更（spec shift 1,2,3）
* `G3M15PullbackFlag()` は shift k の判定に `0.20 × ATR14[k]` を使用
* ATR<=0 の shift はその shift のみスキップ（従来は全体を無効化）
* EAは `CopyBufSeries(h_m15_atr, 0, m15_idx, 3, ...)` で3本取得
* 0.20 を `G3_M15_PULLBACK_ATR` として16章のbaselineと対応付け

**回帰テストが旧挙動を弁別することを別プログラムで実証済み**: R-001a は旧ルールで false / 新ルールで true、R-001b は旧ルールで true / 新ルールで false。

### DEV-002 (BLOCKER) — weekend / abnormal gap cooldown

正本4.2・15.1（gap検知はTimeSyncの責務）・付録A `post_gap_cooldown`。

* `G3IsPostGapBar()` を TimeSync に追加。連続バー間隔が **通常周期の2倍超** のとき、その新しい側のバーを「gap直後に完成した最初のバー」と判定
* `G3ResolveHtfBar()` に `post_gap_out` を追加
* EAはH4参照バーが post_gap のとき新規シグナルを出さず `POST_GAP_COOLDOWN` で記録
* 境界: ちょうど2倍は gap ではない（「2倍を**超える**」の逐語実装）。隣接バーが無い場合は flag しない
* 13.6のサブグループ分析のため `post_gap` 列をログに追加

### DEV-003 (BLOCKER) — StateStore key を account_login + MagicNumber へ

正本11.2「StateStoreは account_login + MagicNumber をkeyとして…永続化する」。

* **口座単位レコード**（`state_<account>_<magic>.txt` / GV `G3_<magic>_*`）: PeakEquity, DDState, HardStopLatched, DailyStartEquity, ServerDate, schema_version, checksum。**全銘柄インスタンスで共有**
* **銘柄単位の signal ledger**（`signal_<account>_<magic>_<symbol>.txt` / GV `G3S_<magic>_<symbol>_*`）: last_signal_id / last_signal_time。signal_id は symbol + M5 bar open time なので本質的に銘柄単位
* `RefreshAccountState()` は毎tick、**ロックを取得 → 共有レコードを再読込（保守的マージ）→ 更新 → 変更時のみ両ストアへflush → 解放** の順で read-modify-write を直列化
* schema_version を 2 へ更新（旧レコードは読み込まれず再初期化される）

### DEV-004 (HIGH) — cost-adjusted BE を10.2通りに

正本10.2「既発生commission + swap + 推定exit commission を控除後で0以上になる最小価格」「Spreadは…**二重加算しない**」。

* **スプレッド加算を削除**
* `G3BreakevenCostMoney(commission_incurred, swap_accrued, commission_exit_estimate)` を追加。純額がクレジットなら0（割引にはしない）
* EAは建玉ごとに deal history の実commission（`PositionCommissionIncurred()`）と `POSITION_SWAP` を取得。exit commission は「entry側のlot当たりcommission実績と同額」と仮定（10.2 baseline）
* 実績が無い場合のみ broker fee schedule 相当の入力から per-leg を推定
* 金額→価格距離の換算は `MoneyToPriceDistance()`（当該volume基準）

### DEV-008 (MEDIUM) — commission見積りを事前riskへ加算

正本9.2「Commission見積りを利用可能なら事前riskに加える」。

* `CommissionPerLotRoundTurn()` を追加。明示の fee schedule 入力を優先し、無ければ直近30日の当該symbol+magicのdeal historyから per-lot round turn を推定、それも無ければ0
* `risk_1lot_total = |OrderCalcProfit(entry→SL, 1lot)| + commission_per_lot` をロット計算・candidate risk・post-fill risk判定に使用
* `commission_per_lot_est` をログ化

### DEV-009〜016（仕様文言で一意に決まるもの）

| DEV | 修正 |
|---|---|
| DEV-009 | `state_store_status` を正本12の **OK / RECOVERED / UNCERTAIN** に。内部6値は `state_store_detail` 列へ退避 |
| DEV-010 | `sl_raw_distance` / `sl_final_distance` 列を追加（9.1） |
| DEV-011 | `tick_value_profit` / `tick_value_loss` 列を追加（9.2 照合用） |
| DEV-012 | 日次resetを**前進時のみ**（`today > server_date`）に変更。時計逆行・再接続で二重resetしない（15.4） |
| DEV-013 | 相関窓を 61 → **60 complete D1 bars**（59 log returns）。ちょうど60本で `CORR_WARMUP_UNKNOWN` にならない（11.4の「60本が不足する場合」の逐語解釈） |
| DEV-015 | 判定順を付録Aへ整合: direction → breakout gate → 全スコア算出 → H4>=1 / M5>=1 / TotalScore → Vol/Spread hard filter。可否の結論は不変、`skip_reason` の帰属のみ変更 |
| DEV-016 | ログ列名を正本12へ: `h4_slope, h4_adx, m15_pullback, m15_structure, breakout_gate, m5_candle, m5_momentum` / `stop_level` / `risk_1lot_calc` / `slippage` / `mfe_3bars, mae_3bars, mfe_6bars, mae_6bars` / `result_r` / `corr_unavailable` |

ログ列は 96 → **104列**。`schema/research_log_schema.md` はソースから再生成済み。

---

## 2. 仕様文言で一意に決まらないため変更しなかったもの

| DEV | 理由 |
|---|---|
| DEV-014 | 付録Aは STATE_UNCERTAIN 時に `manage_open_positions` より前に return するが、11.2は「**新規取引**を禁止」と書く。建玉を無管理にする方が危険であり、11.2に従う現行挙動（新規のみ禁止）を維持。G1判断待ち |
| DEV-017 | STATE_UNCERTAIN からの手動復旧手順は正本にも記載が無い。自動再開しない現行挙動は14.2に適合 |

## 3. 指示により今回変更しなかった設計論点（OPEN維持）

* DEV-005 / CR-006R — 16章OATの実行方式
* DEV-006 / CR-015 — execution stress（spread倍率・slippage）の実装箇所
* DEV-007 / CR-016 — fakeout_3 / fakeout_6 の厳密定義
* ISSUE-003 / CR-003 — 複数通貨ポートフォリオ検証方式
* ISSUE-013 / CR-008 — 61〜71ヶ月データ分割
* ISSUE-016 / CR-014 — MetaEditor実コンパイル・統合テスト
* ISSUE-012 / CR-009 — feed / symbol spec / initial equity / account currency

---

## 4. テスト

| 項目 | 結果 |
|---|---|
| 既存142 assertions 再実行 | **全件PASS**（構造変更に伴い state store 群を口座レコードと signal ledger に分割、M15 fixture を per-shift ATR に更新） |
| 追加した回帰 assertions | **37件**（R-001a〜d, R-002a〜f, R-003a〜g, R-004a〜f, R-005a〜b, R-006, R-007a〜k） |
| 合計 | **179 assertions / 0 failures** |
| ビルド | `g++ -std=c++17 -Wall -Wextra -Werror` — warning 0 |
| 静的チェック | 0 issues |

回帰テストは修正箇所ごとに旧挙動と新挙動を弁別する値を使っています。特にDEV-001は、旧ルールを再現した別プログラムで R-001a/R-001b が反転することを確認済みです。

## 5. ハッシュ再生成

```
source_hash  : b141c0ffac55bd09a878ec1a759d505ccc56308c7cf8339588bbab0495a3e7db
config_hash  : 37c820c795a23d9c30a11b19d8bd811f0bbd0c255819b86695a1c8dd1d2ebe5e
schema_hash  : 01c3b3ff4cab5d507cdf8791c789f3803e8ad3dfb2d599e13cf068f8cdefe5e4
release_hash : 1f0064e6668d7f965834e346e6e343e2f7f0d18a40c42eaf6142254f6ecf9e0c
spec_hash    : 229f29920ee411cf008442f56a1061583fc564ad50c979c32bf7996ada7ff965
EA_hash      : PENDING_METAEDITOR_COMPILE
```

`config/` は未変更のため `config_hash` は不変です。
