# Manus（または任意の自律エージェント環境）向け実行プロンプト

以下をそのまま貼り付けてください。**段階実行になっており、各段階で停止して
報告するよう指示してあります。** いきなり全ユニバースを回して数時間後に
失敗するのを避けるためです。

---

## プロンプト本文（ここから下をコピー）

````text
米国小型株スクリーニングエンジンの実データ検証を実行してください。
コードは完成しておりテスト済みです。あなたのタスクはデータ取得と実行です。

## リポジトリ

git clone https://github.com/dust556/dust.git
cd dust/screener
git checkout claude/us-small-cap-screening-engine-lcv4b5

Python 3.9以上。コア部分は標準ライブラリのみで動くので pip install は不要です。
まず ./run_tests.sh を実行し、256件全部が通ることを確認してください。
1件でも失敗したら、そこで停止して内容を報告してください。

## 必須の事前設定

export SEC_USER_AGENT="あなたの名前 あなたのメールアドレス"

SECは連絡先を含むUser-Agentを要求します。未設定だと全リクエストが
ブロックされます。実在するメールアドレスを使ってください。

すべてのコマンドに以下を付けてください:
  --set cache_ttl_hours=0     キャッシュを無期限にする（既定は24時間で、
                              複数日にわたる取得では期限切れ再取得が起きる）
  --cache-dir /永続パス/cache  セッションが落ちても再開できるようにする

## 段階1: パイプラインの疎通確認（所要20分以内）

100銘柄で全経路を通します。

smallcap universe --exchanges Nasdaq,NYSE --out universe_full.txt
head -100 universe_full.txt > universe_smoke.txt

smallcap backtest \
  --universe-file universe_smoke.txt \
  --start 2018-01-01 --end 2025-12-31 \
  --benchmark IWM \
  --set cache_ttl_hours=0 --cache-dir ./cache \
  --out bt_smoke/

【ここで停止して報告してください】
- 何銘柄が取得でき、何銘柄が失敗したか
- bt_smoke/backtest.md の「Read this before the numbers」節の全文
- 平均保有銘柄数（avg holdings）
- 1銘柄あたりのおおよその所要時間

平均保有銘柄数が0または1なら、そこから先に進んでも意味がありません。
報告して指示を待ってください。

## 段階2: 時点別ユニバースの構築（所要30〜60分）

サバイバーシップバイアス対策です。EDGARのfull-indexから、各時点で実際に
上場していた企業（後に倒産・上場廃止した企業を含む）を復元します。

smallcap universe-history \
  --start 2015-01-01 --end 2025-12-31 \
  --set cache_ttl_hours=0 --cache-dir ./cache \
  --out universe_by_date.json \
  --coverage-out coverage.json

【ここで停止して報告してください】
- 出力される "ticker coverage: mean X%, worst Y%" の数値
- coverage.json の periods 配列のうち最初と最後の3件

このカバレッジ率が、バックテストに残存するサバイバーシップバイアスの
推定値です。**この数字は結果の解釈に必須なので、必ず報告してください。**

## 段階3: ファクターデータの取得

Ken French Data Library から月次ファクターを取得します:
https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html
「Fama/French 3 Factors」の CSV（monthly）をダウンロードし、
factors.csv として保存してください。

ヘッダーやフッターの注記は残したままで構いません（パーサーが処理します）。
パーセント表記も自動判別されます。

確認: ファイル内に "Mkt-RF" "SMB" "HML" "RF" の列があること。

## 段階4: 本番実行（数時間〜。中断・再開可能）

これは長時間ジョブです。セッション時間に上限がある環境では、
**キャッシュディレクトリが永続化されていることを必ず先に確認してください。**
途中で落ちても、同じコマンドを再実行すればキャッシュから再開されます。

smallcap backtest \
  --universe-file universe_full.txt \
  --universe-history universe_by_date.json \
  --start 2015-01-01 --end 2025-12-31 \
  --benchmark IWM \
  --factors factors.csv \
  --ablation \
  --workers 4 \
  --set cache_ttl_hours=0 --set insider.max_filings=200 \
  --cache-dir ./cache \
  --out bt_full/

--workers を上げても取得は速くなりません。SECのレート制限（10req/秒）に対する
リミッタはプロセス全体で共有されているためです。4程度にしておくと、
通信待ちの裏でJSONのパースが進むぶんだけ僅かに得をします。
それ以上増やしても待ち時間が増えるだけです。

## 段階5: 悲観シナリオの確認（必須）

上場廃止銘柄の決済方法を変えて再実行します。データはキャッシュ済みなので
短時間で終わります。

smallcap backtest \
  --universe-file universe_full.txt \
  --universe-history universe_by_date.json \
  --start 2015-01-01 --end 2025-12-31 \
  --benchmark IWM --factors factors.csv \
  --missing-price-policy zero \
  --workers 4 \
  --set cache_ttl_hours=0 --set insider.max_filings=200 \
  --cache-dir ./cache \
  --out bt_pessimistic/

**この2つの結果の差は小さくありません。**戦略もデータも同一で、
違いは「株価が取得できなくなった銘柄をどう決済するか」だけです。
同梱フィクスチャでは +17.07% と -1.55% の差が出ます。
両方を報告してください。片方だけの報告は無意味です。

## 最終報告に必ず含めるもの

1. bt_full/backtest.md の「Read this before the numbers」節の全文
   （バイアスと警告。ここを省略した報告は受け取れません）
2. 段階2のカバレッジ率
3. drop と zero 両方のCAGR・超過リターン
4. ファクター調整後アルファとそのt値、および観測数
5. アブレーション表（5条件それぞれを外した場合）
6. 平均保有銘柄数とリバランス期間数
7. 取得に失敗した銘柄数と、主な失敗理由

## 重要な注意

- **CAGRだけを報告しないでください。** ファクター調整後アルファとバイアス欄が
  本体です。生のCAGRは小型株エクスポージャーの対価を含んでおり、
  戦略の価値を示しません。
- **数値を良く見せようとしないでください。** 条件を満たす銘柄が0件、
  アルファがマイナス、t値が有意でない——いずれも正当な結果です。
  そのまま報告してください。
- **エラーを握りつぶさないでください。** 取得失敗が多発した場合、
  その件数と理由が結果そのものより重要です。
- 株価の取得元は既定で stooq.com です。数千銘柄のバルクアクセスは
  スロットルまたはブロックされる可能性があります。**段階1で株価取得の
  失敗が目立つ場合は、段階4に進まず報告してください。**
  有料ベンダーのCSVを --prices-dir で与える必要があります。
````

---

## この指示書の設計意図

各段階で停止させているのは、**失敗を早く検知するため**です。特に:

- **段階1で止める理由**: 平均保有銘柄数が0〜1件なら、8時間かけて全ユニバースを
  回しても得られるのはノイズです。ここで閾値の再検討が必要だと分かります。
- **段階1で株価取得を確認させる理由**: Stooqのバルクアクセス制限が、
  実務上の最大の詰まりどころです。全取得を終えてから気づくのは最悪です。
- **段階5を必須にした理由**: `drop` と `zero` の差は、「市場を上回る戦略」と
  「損失を出す戦略」を分けます。片方だけ見て結論を出すのが、この種の検証で
  最も起きやすい誤りです。
- **CAGR単独報告を禁じた理由**: 小型株スクリーンは設計上サイズファクターに
  エクスポージャーを持つので、小型株が good な期間には必ずベンチマークに勝ちます。
  それは戦略の価値ではありません。

## 環境側で先に確認すべきこと

| 項目 | 理由 |
|---|---|
| 永続ストレージの有無 | 段階4は数時間。落ちた時にキャッシュが消えると最初からやり直し |
| セッション時間上限 | 上限があるなら、段階4は分割実行するかVPSに移す |
| ディスク空き容量 | 圧縮キャッシュで6〜10GB程度（銘柄数に比例） |
| `www.sec.gov` / `data.sec.gov` への到達性 | 段階1で判明する |

**エージェント型サンドボックスは通常セッション時間に上限があり、
8〜9時間の連続バルク取得とは相性が良くありません。**
永続ストレージが使えない場合は、月数ドルのVPSで `nohup` で流すほうが確実です。
