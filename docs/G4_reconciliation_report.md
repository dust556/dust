# G4 仕様照合レポート（権威文書受領後の再判定）

| 項目 | 内容 |
|---|---|
| 対象コミット | `cc4a360`（G4実装、照合時点でコード無変更） |
| 照合日 | 2026-09-22 |
| 作業範囲 | **仕様照合のみ**。ロジック変更・利益改善・パラメータ変更は一切行っていない |
| source_hash | `59b5da9afa41627dbb243090a37883c064266ccd8b5f2b5f59902d48ab295c61` |

## 0. 権威文書と spec_hash 確定（CR-001 → CLOSED）

3文書を全文読み込みました。SHA-256はG3研究開始記録に印字されたハッシュ表と**一致**しています。

| 文書 | 役割 | SHA-256 | 照合 |
|---|---|---|---|
| Master Specification v0.4 | G3の唯一の正本 | `229f29920ee411cf008442f56a1061583fc564ad50c979c32bf7996ada7ff965` | 開始記録の記載値と一致 |
| G2 Re-Audit Report v0.4 | G2判定の証跡（BLOCKER 0 / HIGH 0 / MEDIUM 0 / LOW 2 / PASS） | `7d17353844c88030622638abd10c5b475c7f74eea26936b21c87e8c15d64fbeb` | 開始記録の記載値と一致 |
| G3研究開始記録 | G3統制の凍結パッケージ | `d068cdc797a6708629c21df2a085afa6a8a3d46b388f200340e856e1376ab82c` | — |

`manifests/spec_hash.txt` に記録済み。読み込み範囲: 仕様書 全17章＋付録A-D（542行・表33件）、G2報告 全3ページ、G3開始記録 全5ページ。

### 章番号の訂正

G4実装時に使用した章番号は依頼プロンプトの番号であり、正本と異なっていました。正本の番号は以下です。

| プロンプト章 | 正本 v0.4 章 |
|---|---|
| 3 環境・口座 | 2 / 15.2 |
| 4 MTF時刻同期 | 4.1（週末gapは 4.2） |
| 5 / 6 / 7 / 8 | 5 / 6 / 7 / 8（同じ） |
| 9 SL・Risk・Lot | 9.1 / 9.2 |
| 10 DD State Machine | 11.1 / 11.2 |
| 11 DailyEntryLock | 11.3 |
| 12 Portfolio・Correlation | 11.4 |
| 13 Execution・Deviation | 9.3 |
| 14 Exit Modes | 10 / 10.1 / 10.2 |
| 15 Timeout | 10.3 |
| 16 Logging | 12 |
| 17 G3 Inputs | 13.4 / 16 |
| 24 Final Holdout | 13.3 |

`docs/implementation_mapping.md` の章番号を正本準拠へ訂正済み。

---

## 1. 仕様と一致していた実装（証跡つき）

| 正本 | 仕様原文（要旨） | 実装 | 判定 |
|---|---|---|---|
| 4.1 | decision_tick、signal_close_time、H4/M15は実バー時刻列から「完全に閉じた最後のバー」、shift=1固定に依存しない | `G3ResolveClosedBarIndex()` | 一致 |
| 4.1 | signal_id原子consume → File+GV flush → 判定開始、クラッシュ時fail-closed | `G3ConsumeSignal()` | 一致 |
| 5.1 / 5.2 | Direction Gateは無得点、slope>+0.10ATR、ADX14>=20かつDI一致 | `SignalH4.mqh` | 一致 |
| 6 | 押し/戻りはshift=1,2,3、構造は EMA20[1]>EMA50[1] かつ EMA20[1]>EMA20[4] | `SetupM15.mqh` | 一致（ATRのshiftのみ相違 → DEV-001） |
| 7.1 / 7.2 | Breakoutはハードゲート、Body/Range>=0.60、上端25%、EMA9/20モメンタム、Range<=0は無効 | `TriggerM5.mqh` | 一致 |
| **8.1** | **M15 Setup は「最低点なし」** | M15に下限なし | **一致（CR-011）** |
| 8.2 | VolRatio = **M5** ATR14[1] / median(ATR14 shifts 2..101)、0.80-1.80で1点、>2.50新規禁止 | `MarketFilters.mqh` | 一致（CR-007） |
| 8.3 | SpreadRatio = (Ask-Bid) / **M5** ATR14[1]、<=0.12で1点、>0.20新規禁止 | `MarketFilters.mqh` | 一致（CR-007） |
| 8.1 / 11.1 / 付録A | `threshold = (dd_state == RESTRICTED ? 6 : 5)`、G3は4/5/6を事前登録比較 | `G3EffectiveScoreThreshold()` | 一致（CR-005）※登録値域内で等価 |
| 9.1 | Raw SL、1.0ATR拡張、2.5ATR見送り、StopLevel+1pointまで安全側、補正後2.5ATR超は発注しない | `RiskManager.mqh` | 一致 |
| 9.1 | FreezeLevelは保有後のSL変更可否に使用、変更不可なら延期、不利方向へ動かさない | `ManagePositions()` | 一致 |
| 9.2 | OrderCalcProfitをcanonical、floor丸め、VolumeMin超過は発注禁止、VolumeMaxは切下げ | `G3ComputeLot()` | 一致 |
| 9.3 | deviation式、PipSize、HardCap、cap超は送信せず`deviation_cap_hit`、送信時max(1,min(...)) | `G3BuildDeviationPlan()` | 一致（CR-012） |
| 9.3 | 同一decision_tickで最大1回、無限リトライ禁止 | `G3SendMarketOrder()` | 一致 |
| 9.3 | post-fill risk >105%は縮小、不可なら全決済、`execution_risk_violation`記録 | `EvaluateDecisionTick()` | 一致 |
| 10 | A: TP=2.0R・BE/Trail/Partial禁止 / B: +1.0R BE・+1.5R約50% partial・ATR×2.0 / C: ATR×2.5 | `ExitManager.mqh` | 一致 |
| 10.1 | floor後remaining>=VolumeMin、**40%未満/60%超はskip**、不可時はBE+Trailで全量管理、直後にexposure再計算 | `G3BuildPartialPlan()` | 一致 |
| 10.3 | Trailは不利方向へ戻さない、Timeout時MFE<0.75Rなら残存ロットのみ、優先順位 broker state → protective exit → timeout | `ManagePositions()` | 一致 |
| **11.1** | **DD = (PeakEquity - CurrentEquity) / PeakEquity**、悪化即時・改善はヒステリシス、10%はlatch | `G3DrawdownPct()` / `G3NextDDState()` | **一致（CR-007）** |
| 11.1 | 0.50 / 0.25 / 0.10 / 0%、復帰 DD<5% と DD<7%、Manual reset + DD<9% + audit log | `RiskManager.mqh` / `StateStore.mqh` | 一致 |
| 11.2 | PeakEquity, DDState, HardStopLatched, DailyStartEquity, ServerDate, last_signal_id, schema_version, checksum をFile+GVへ、不一致は保守側、両欠損はSTATE_UNCERTAIN | `StateStore.mqh` | 一致（keyのみ相違 → DEV-003） |
| 11.3 | DailyStartEquity比 -2.0%以下で当日新規のみ禁止、強制全決済しない | `G3DailyEntryLocked()` | 一致 |
| 11.4 | Max 3 / 総initial risk 1.50% / 同一currency component同方向 <=1.00% / BUY EURUSD は EUR+ USD- | `PortfolioManager.mqh` | 一致 |
| **11.4** | **「position sideを掛けた signed correlation >=0.70」** | `G3SignedLegCorrelation(..., direction_adjusted=true)` | **一致（CR-004）** |
| 11.4 | D1直近60 complete barsの**log return** Pearson、不足時CORR_WARMUP_UNKNOWN、相関0扱い禁止、未知cluster <=0.75% | `G3D1Returns()` / `G3CheckPortfolio()` | 一致（CR-007） |
| 12 | 約定だけでなく候補/見送りも記録 | `EVAL`レコード | 一致 |
| 13.3 | G3環境にHoldoutデータ・ディレクトリを置かない | 静的チェックで強制 | 一致 |
| 15.1 | モジュール構成 TimeSync / SignalH4 / SetupM15 / TriggerM5 / MarketFilters / RiskManager / PortfolioManager / OrderManager / ExitManager / StateStore / Logger | `src/` 11モジュール | 一致（gap検知のみ欠落 → DEV-002） |
| 15.2 | OnInitでRETAIL_HEDGING以外はINIT_FAILED、Netting互換コードを混在させない | `OnInit()` | 一致 |
| 15.3 | iMA/iATR/iADX標準、MedianATR100はshifts 2..101のcomplete値 | `OnInit()` / `MarketFilters` | 一致 |

---

## 2. 原本照合で新たに判明した仕様不一致（DEV-001〜017）

実装は変更していません。以下は報告のみです。

### BLOCKER

**DEV-001 — M15押し/戻りのATRがshift固定（正本 6章）**
正本: 「Low[1], Low[2], Low[3] のいずれか <= EMA20同shift + 0.20×**ATR同shift**」「各Low/Highは同じshiftのEMA20/**ATR**と比較し」。
実装: `M15Input.atr14_s1` 1個をshift1,2,3すべてに適用（`src/SetupM15.mqh:23,37`）。旧A-03の仮定は**否定**されました。
影響: M15 pullback flag → m15_score → total_score → エントリー可否。全取引に影響。

**DEV-002 — 週末・異常ギャップのクールダウンが未実装（正本 4.2 / 15.1 / 付録A）**
正本: 「上位足の連続バー間隔が通常周期の2倍を超えるgapを検知した場合、gap直後に完成した最初のH4バーでは新規シグナルを出さない」。15.1でgap検知はTimeSyncの責務、付録Aに `if post_weekend_gap_cooldown or data_invalid: skip`。
実装: `src/` 全体にgap検知なし（grep一致0件）。
影響: 仕様が禁止するシグナルを発注する。14.2の自動FAIL（仕様不一致）に該当。

**DEV-003 — StateStoreのkeyに symbol が入り、口座横断のDD状態が共有されない（正本 11.2）**
正本: 「StateStoreは **account_login + MagicNumber** をkeyとして…永続化する」。
実装: `state_<account>_<magic>_<symbol>.txt` / GV接頭辞 `G3_<magic>_<symbol>_`（`src/StateStore.mqh:240-246`）。
影響: 1銘柄1インスタンス構成では PeakEquity / DDState / DailyStartEquity が銘柄ごとに分裂し、口座単位のDD State MachineとDailyEntryLockが仕様どおり機能しない。14.2の自動FAIL（「10% DD Hard Stop、DailyEntryLock…のいずれかが機能しない」）に該当。

### HIGH

**DEV-004 — cost-adjusted BE のコスト定義が相違（正本 10.2）**
正本: BE SLは「既発生commission + swap + 推定exit commission」控除後に損益0以上となる最小価格。**Spreadは実取引価格関係に内包されるため二重加算しない**。
実装: `cost_price = (Ask - Bid) + commission`（`src/G3_ResearchEA.mq5:927`）。スプレッドを明示的に加算しており、正本の禁止事項に抵触。swapと実commission履歴も未使用。旧A-06の仮定は**否定**されました。
影響: ExitMode B のBE位置。

**DEV-005 — 16章のOAT/Safety/Execution stress パラメータがInput化されていない**
正本16章は41行のパラメータ登録表（Class C/H/S/E/D）を持ち、H classはOAT感度必須。13.4は「許可: 事前登録したScoreThreshold, ExitMode, Timeoutと、**16章のOAT sensitivity**」。
実装: Input化は3件のみ。特に **RESTRICTED ScoreThreshold（16章: baseline 6、OAT 5/6/7）** と **Deviation Hard Cap（16章・9.3: 1.0/2.0/3.0 pips execution stress）** が `#define` 固定（`MarketFilters.mqh:21`, `OrderManager.mqh:20`）。
影響: 14.1「OAT family summaryを完全提示し、未報告parameter/testがないこと。個別の良結果だけを選択提示した場合はG3 FAIL」を満たせない。
※実装方法（Input追加 vs OAT点ごとの個別ビルド）は13.4の総当たり禁止と両立させる必要があり、方式決定はG1/G2判断事項。CR-006Rとして提出。

**DEV-006 — execution stress のモデルが13.5と不一致**
正本13.5 / G3開始記録: Base / Stress-1（spread **×1.5**、entry・exit各 **0.25×observed spread** の不利slippage）/ Stress-2（×2.0、各0.50）/ Stress-3（×3.0、各1.00）。
実装: `InpStressExtraSpreadPoints`（**絶対point加算**）のみ。倍率モデルでなく、slippage stressは未実装。
影響: 14.1「Stress-1でExpectancy_R>0を維持」の評価ができない。

### MEDIUM

**DEV-007 — fakeout_3 / fakeout_6 が未投入（正本 12 / 7.2）**
正本12: 「fakeout_3 / fakeout_6 | breakout後3/6本以内**反転SL等の診断flag**」。7.2: 「entry後3/6本以内の反転SL率、MFE3/6bars、MAE3/6barsをログから集計」。
実装: `NA_SPEC_UNDEFINED` 固定。定義は存在したため、旧ISSUE-005の前提は誤りでした。
影響: 13.6・G3開始記録が要求するfakeoutサブグループ分析が不能。

**DEV-008 — Commission見積りが事前riskに未加算（正本 9.2）**
正本: 「Commission見積りを利用可能なら事前riskに加える」。実装: `RiskManager.mqh` に該当処理なし。

### LOW

| ID | 内容 | 正本 |
|---|---|---|
| DEV-009 | `state_store_status` の値が `STORE_OK/FILE_ONLY/GV_ONLY/MISMATCH_CONSERVATIVE/BOTH_LOST/FRESH` の6値。正本は `OK / RECOVERED / UNCERTAIN` の3値 | 12 |
| DEV-010 | `sl_raw_distance` / `sl_final_distance` を列として持たない（価格のみ。距離は導出可能） | 9.1 |
| DEV-011 | `SYMBOL_TRADE_TICK_VALUE_PROFIT/LOSS` を照合用に記録していない | 9.2 |
| DEV-012 | サーバ日付が逆行した場合に DailyStartEquity を再resetし得る（二重reset防止が未実装） | 15.4 |
| DEV-013 | 相関窓が61 complete D1 bars（60リターン）。正本は「直近60 complete bars」。実装の方が1本保守的 | 11.4 |
| DEV-014 | STATE_UNCERTAIN時、付録Aは`manage_open_positions`前にreturn。実装は11.2に従い建玉管理を継続し新規のみ禁止 | 11.2 / 付録A |
| DEV-015 | skip_reason の優先順位が付録Aと相違（実装はH4 score下限をbreakout gateより先に評価）。可否の結論は同一、ログ帰属のみ差異 | 付録A |
| DEV-016 | ログ列名の相違（`order_calc_profit_1lot`↔`risk_1lot_calc`、`corr_state`↔`corr_unavailable`、feature flagの`f_`接頭辞） | 12 |
| DEV-017 | STATE_UNCERTAINからの手動復旧手順が正本にも未記載（「手動復旧を要求する」のみ）。実装は自動再開しないため14.2には適合 | 11.2 / 14.2 |

---

## 3. ISSUE / CR 再判定

### CLOSED（原本照合により解決）

| 旧ID | 旧深刻度 | 再判定 | 根拠 |
|---|---|---|---|
| ISSUE-001 / CR-001 | BLOCKER | **CLOSED** | 3文書受領。spec_hash確定、開始記録のハッシュ表と一致 |
| ISSUE-002 / CR-004 | HIGH | **CLOSED** | 11.4「position sideを掛けたsigned correlation」＝方向調整。**実装は正しい** |
| ISSUE-004 / CR-005 | MEDIUM | **CLOSED** | 11.1・8.1・付録A `threshold=(RESTRICTED?6:5)`・16章の独立パラメータ。**実装は登録値域内で等価** |
| ISSUE-005 / CR-002 | MEDIUM | **CLOSED** | 12章・7.2に定義あり。未投入は DEV-007 へ移管 |
| ISSUE-006 / CR-006 | MEDIUM | **CLOSED** | 16章41行の登録表＋13.5で全リスト判明。入力面の不足は DEV-005 / DEV-006 へ移管 |
| ISSUE-007 / CR-007 | MEDIUM | **CLOSED** | ATR=M5（8.2/8.3）確定。M15は同shift（6章）＝ DEV-001 |
| ISSUE-008 / CR-007 | MEDIUM | **CLOSED** | 11.1でDD定義確定。**実装は正しい** |
| ISSUE-009 / CR-012 | LOW | **CLOSED** | 9.3の原文がプロンプトと同一。**実装の逐語解釈が正しい** |
| ISSUE-010 / CR-010 | MEDIUM | **CLOSED** | 10.2に定義あり。実装の相違は DEV-004 へ移管 |
| ISSUE-011 / CR-011 | LOW | **CLOSED** | 8.1「M15 Setup 0-2 最低点なし」。**実装は正しい** |
| ISSUE-014 / CR-007 | MEDIUM | **CLOSED** | 11.4「D1直近60 complete barsのlog return Pearson」。**実装は正しい**（窓1本差は DEV-013） |
| ISSUE-015 / CR-013 | LOW | **CLOSED** | 11.2「手動復旧を要求」＋14.2「UNCERTAINで自動再開は自動FAIL」。**実装は適合**。残件は DEV-017 |
| ISSUE-017 | LOW | **CLOSED** | 11.4「Max positions = 3」はportfolio単位。**実装の口座横断解釈が正しい** |

仮定の再判定: **A-01 / A-02 / A-04 / A-05 / A-07 / A-08 / A-09 / A-10 / A-11 / A-12 / A-13 / A-14 は正本により確認され仮定から除外**。**A-03（M15 ATR）と A-06（BE cost）は正本により否定**され、DEV-001 / DEV-004 になりました。

### OPEN 維持（指示により未解決のまま）

| ID | 深刻度 | 根拠 |
|---|---|---|
| ISSUE-016 / CR-014 | BLOCKER | MetaEditor実コンパイル・統合テスト未実施 |
| ISSUE-012 / CR-009 | BLOCKER | 13.1が要求するPrimary/第2feed、symbol specification、initial equity、account currency、コスト情報が未受領（G3開始記録も同旨） |
| ISSUE-013 / CR-008 | BLOCKER | 13.2は72ヶ月と「60ヶ月しかない場合」のみ定義。**G3開始記録が明示的に「61〜71か月…の固定分割はv0.4に明示されていない。分割を推測して研究を開始しない。G1への仕様照会又はCRの対象として保留する」と記載** |
| ISSUE-003 / CR-003 | HIGH | MT5テスターは1EAのみ実行。複数通貨ポートフォリオ検証方式が未決 |

### 新規 CR

| ID | 内容 |
|---|---|
| CR-006R | 16章H-class約30パラメータのOAT実行方式の指定（EA Input追加 / OAT点ごとの個別ビルド のいずれか）。13.4の総当たり禁止と両立する方式をG1/G2が決定すること |
| CR-015 | 13.5のexecution stress（spread倍率・slippage adverse）を、EA内モデル／テスター設定／後処理のどこで実現するかの指定 |
| CR-016 | fakeout_3 / fakeout_6 の「反転SL等」の確定定義（SL約定のみか、BE/Trail決済を含むか、起点はentryかbreakoutか） |

---

## 4. 未実施のまま維持した項目（指示どおり）

1. MetaEditorでの実コンパイル・統合テスト — **未実施**
2. Primary/Second tick feed、symbol specification、initial equity、account currency — **未受領**
3. 61〜71ヶ月データ時の扱い — **保留**（正本・開始記録とも未定義、推測禁止）
4. MT5での複数通貨ポートフォリオ検証方式（CR-003） — **未決**

## 5. 本照合で変更したもの

* `manifests/spec_hash.txt` / `build_manifest.json` — 権威文書3件のSHA-256を記録
* `tools/compute_hashes.py` — 権威文書ハッシュ表を追加
* `docs/implementation_mapping.md` — 章番号を正本準拠へ訂正
* `docs/change_requests.md` — ISSUE/CR再判定
* `docs/known_limitations.md` — 仮定A-01〜A-14の再判定
* 本ファイル

**`src/` および `config/` のコードは1行も変更していません。**
静的チェック 0 issues / 単体テスト 142 assertions 0 failures は照合後も維持。
