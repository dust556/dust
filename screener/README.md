# 米国小型株 定量スクリーニングエンジン

5つの条件で米国上場企業を機械的に選別し、**なぜその判定になったかを全て
数値付きで出力する**リサーチエンジン。データソースは SEC EDGAR (XBRL) で、
APIキーは不要。

| # | 条件 | 典拠 | 実装 |
|---|---|---|---|
| ① | 時価総額 5〜30億ドル | Fama & French (1992), *JF* | `criteria/c1_market_cap.py` |
| ② | 粗利率40%以上、かつ改善傾向 | Novy-Marx (2013), *JFE* "The Other Side of Value" | `criteria/c2_gross_margin.py` |
| ③ | ROIC > 資本コスト、かつ高再投資率 | Mauboussin (Credit Suisse 各レポート) | `criteria/c3_returns.py` |
| ④ | 有利子負債 / EBITDA 3倍以下 | — | `criteria/c4_leverage.py` |
| ⑤ | 経営陣の持株比率 10%以上 | Jensen & Meckling (1976) | `criteria/c5_insider.py` |

## クイックスタート

```sh
# 依存パッケージなしで動作確認 (同梱フィクスチャ)
./run_tests.sh
PYTHONPATH=src python3 -m smallcap screen --provider fixtures --out out/

# インストール
pip install -e .

# SEC は連絡先付きの User-Agent を要求する (未設定だとブロックされる)
export SEC_USER_AGENT="Your Name your@email.com"

# 実データで実行
smallcap screen --tickers AAPL,ADBE,MSFT --out out/

# 全上場銘柄を対象に
smallcap universe --exchanges Nasdaq,NYSE --out universe.txt
smallcap screen --universe-file universe.txt --workers 4 --out out/

# 1銘柄の全計算過程を表示
smallcap explain ACME

# バックテスト (スクリーンを過去に遡って実行し、成績を測定)
smallcap backtest --universe-file universe.txt \
  --start 2015-01-01 --end 2025-12-31 \
  --benchmark IWM --factors F-F_Research_Data_Factors.CSV \
  --ablation --out bt/
```

出力は `out/` に3種類:

| ファイル | 用途 |
|---|---|
| `results.json` | 全中間計算値 + 実行時の設定 (再現用) |
| `results.csv` | 表計算ソフト用の1行1銘柄サマリ |
| `report.md` | 判定理由を文章で記述したレポート |

## バックテスト

「この5条件は機能するのか」に数字で答えるための基盤。詳細は
[`docs/backtest.md`](docs/backtest.md)。

- 四半期リバランス（提出書類の更新頻度に合わせた既定値）
- **報告ラグ**: 期末から75日後にリバランス。12月期末の10-Kを1月1日に
  読めることにするのが、バックテストが取引不可能になる最も一般的な経路
- **ルックアヘッド遮断**: 提出書類も株価も株式数も `as_of` 時点まで巻き戻される
- **ファクター調整**: 小型株スクリーンがベンチマークを上回るのは設計上当然なので、
  Mkt-RF / SMB / HML への回帰で「そのエクスポージャーの対価を払った後に残るもの」
  を測る
- **アブレーション**: 5条件を1つずつ外して、どれが実際に効いているかを見る
- **サバイバーシップバイアス対策**: `universe-history` がEDGARのfull-indexから
  各時点の上場企業リストを復元する。CIK→ティッカーに変換できない企業
  （＝上場廃止組）の割合を**残存バイアスの推定値として数値報告する**

出力レポートは**バイアス欄を成績の前に置く**。サバイバーシップバイアス、
コスト未計上、サンプル数の警告を読む前にCAGRを見て結論を出すのが、
バックテストの最も一般的な誤用であるため。

```sh
# 各時点の上場企業リストをEDGARのfull-indexから生成する
# (後に倒産・上場廃止した企業も含まれる)
smallcap universe-history --start 2015-01-01 --end 2025-12-31 \
  --out universe_by_date.json --coverage-out coverage.json

# それを与えてバックテストする
smallcap backtest --universe-history universe_by_date.json ...

# 上場廃止銘柄を全損と仮定した悲観的な下限を確認する
smallcap backtest --missing-price-policy zero ...
```

## 主要オプション

```sh
# 過去日付でのスクリーニング (その日に公開済みの数値のみ使用)
smallcap screen --as-of 2024-06-30 --universe-file universe.txt --out out/

# 閾値の変更 (感応度分析)
smallcap screen --tickers ACME --set returns.min_roic=0.20 --set leverage.max_debt_to_ebitda=2.0

# 設定ファイル
smallcap screen --config config/example.json --universe-file universe.txt

# ネットワークを一切使わない (キャッシュのみ)
smallcap screen --offline --universe-file universe.txt

# Claude による定性レビューを追加 (判定には影響しない)
pip install -e ".[ai]"
smallcap screen --tickers ACME --ai --out out/
```

## 設計上の要点

### データが無いことと、条件を満たさないことを区別する

各条件は `PASS` / `FAIL` / `INSUFFICIENT_DATA` の3値を返す。データ欠損を
`FAIL` に丸めると、開示の薄い企業が理由不明のまま消える。スコア計算では
判定不能の条件は分母からも除外され、`data_quality` が閾値を下回る銘柄は
ランキング対象外となる。

レポートには条件別の判定不能件数を必ず出力する。**この数字が大きい場合、
それは企業についての発見ではなくデータ網羅性の問題である。**

### ポイントインタイム

XBRL の各数値は提出日を持つ。`--as-of` 指定時は、その日までに公開されて
いた数値のみを使う。修正再表示後の数値で過去をスクリーニングすると、
実際には取引できなかった結果が出る。

### 判定は機械的、AIは解釈のみ

`--ai` による Claude のレビューは判定・スコア・順位を**一切変更しない**。
その役割は、数値の好意的な解釈に対する**対立仮説を列挙させること**にある
(例: 粗利率の改善は実体か、原価の科目組み替えか)。レポート上は常に
「LLM生成・未検証」と明示される。

## 構成

```
src/smallcap/
├── config.py            全閾値 (JSON/YAML/CLI で上書き可能)
├── models.py            プロバイダ非依存のデータ構造
├── metrics.py           ROIC / WACC / EBITDA / 再投資率などの導出
├── engine.py            実行・並列化・エラー隔離
├── scoring.py           複合スコアとデータ品質
├── report.py            JSON / CSV / Markdown 出力
├── cli.py               コマンドライン
├── criteria/            5条件 (1ファイル1条件)
├── universe.py          EDGAR full-indexからの時点別ユニバース構築
├── backtest/
│   ├── calendar.py      リバランス日と報告ラグ
│   ├── portfolio.py     組入・ウェイト・欠損株価の扱い
│   ├── performance.py   CAGR/Sharpe/最大DD、多変量OLS
│   ├── factors.py       Fama-French ファクター読み込み
│   ├── runner.py        バックテストループとアブレーション
│   └── report.py        バイアスを先頭に置くレポート
├── providers/
│   ├── sec_edgar.py     XBRL companyfacts + Form 3/4/5 解析
│   ├── prices.py        株価・ベータ推定
│   └── fixtures.py      オフライン再生用
└── ai/analyst.py        Claude 定性レビュー (任意)
```

## テスト

```sh
./run_tests.sh          # 256件、外部依存・ネットワーク不要
```

フィクスチャは各条件の分岐を1つずつ検証するよう作られている
(`IDEAL` = 全通過、`FADING` = 粗利率は高いが低下傾向、`NOSKIN` = 持株比率不足、
`THINDATA` = 判定不能、など)。生成元は `tools/make_fixtures.py`。

## 制約事項

**実行前に [`docs/methodology.md`](docs/methodology.md) を読むこと。**
各条件の計算式と、それが見落とすものを記述している。特に重要な3点:

1. **条件⑤の持株比率は下限値である。** Form 3/4/5 から算出しており、真の
   内部者持株比率より低く出る。権威あるソースは DEF 14A の委任状であり、
   本エンジンは解析していない。閾値近傍の不合格は `NEAR MISS` として警告する。
2. **条件②は会計上の組み替えと実体的改善を区別できない。** 売上原価から
   販管費への科目移動だけで粗利率は上昇する。
3. **条件①はカバレッジの薄さを検証していない。** 時価総額のみを見ている。
   アナリストカバレッジ数は無料データソースに存在しない。

バックテストについては [`docs/backtest.md`](docs/backtest.md) に、除去できない
バイアス（サバイバーシップ、コスト未計上、上場廃止銘柄の決済価格、サンプルサイズ）
を記述している。**実データでの検証はまだ行われていない。** 同梱フィクスチャは
機構の動作確認用であり、5条件が超過リターンを生むという証拠ではない。

本エンジンはリサーチ用の測定器であり、投資助言ではない。5条件を満たすことは
**調査を始める理由**であって、調査の結論ではない。
