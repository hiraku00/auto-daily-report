Macの画面を定期的にキャプチャして文字認識(OCR)を行い、作業ログを記録するツールです。Googleカレンダーの予定と合わせて、Claude（Claude Code の `claude -p`）に日報を自動生成させることができます。

## 特徴
- **自動記録**: 1分ごとに画面のテキストとアクティブなアプリ名を記録。
- **プライバシー重視**: スクリーンショット画像は保存せず、テキスト情報のみをローカルに保存します。
- **Googleカレンダー連携**: 今日の予定を取得し、作業ログとの乖離を確認できます。
- **完全自動化**: 蓄積したログを30分ごとに要約してプロンプトを作り、`claude -p` で日報を作成・保存します。ブラウザ操作は不要です。

## 必要要件
- macOS (Vision Frameworkを使用するため)
- Python 3.9以上
- Google Cloud Project (Calendar API用)
- Claude Code（`claude` コマンド）をインストールし、Claude のサブスクリプション（Pro / Max）でログイン済みであること

## セットアップ手順

### 1. 必要なライブラリのインストール

ターミナルで以下のコマンドを実行し、依存ライブラリをインストールしてください。

```bash
pip install -r requirements.txt
```

### 2. GoogleカレンダーAPIの設定

Googleカレンダーの予定を取得するために、以下の設定が必要です。

1. [Google Cloud Console](https://console.cloud.google.com/) で新しいプロジェクトを作成します。
2. 「**API とサービス**」 > 「**ライブラリ**」から **Google Calendar API** を検索し、有効化します。
3. 「**API とサービス**」 > 「**認証情報**」で **OAuth クライアント ID** を作成します（アプリケーションの種類は **デスクトップ アプリ**）。
4. クライアントIDを作成したら、JSON形式の認証情報をダウンロードし、ファイル名を `credentials.json` に変更して、このプロジェクトのルートディレクトリに配置してください。

> **注意**: 初回実行時にブラウザが立ち上がり、Googleアカウントへのアクセス許可が求められます。

### 3. Macの権限設定

このツールは画面の内容を読み取るため、以下の権限が必要です。

- **画面収録 (Screen Recording)**: ターミナル（または実行するIDE）に許可を与えてください。
  - 「システム設定」 > 「プライバシーとセキュリティ」 > 「画面収録」
- **アクセシビリティ (Accessibility)**: 必要に応じて許可してください。

### 4. dashboard への送信設定（任意）

日報を dashboard（Cloudflare Workers + D1）へ送る場合は、`.env.example` を `.env` にコピーし、dashboard のURLと Cloudflare Access の service token を設定します。`.env` は `.gitignore` の対象です。

```bash
cp .env.example .env
```

## 使い方

### 記録の開始 (常駐プロセス)

朝、業務を開始する際に以下のコマンドでログ記録を開始します。終了は `Ctrl+C` です。

```bash
python main.py
```

実行中は `logs/` ディレクトリに `daily_log_YYYY-MM-DD.jsonl` が生成され、1分ごとに追記されます。

### 日報の生成 (業務終了時)

1日の終わりに以下のコマンドを実行します。

```bash
# 今日の日報を作成する場合
python daily_report.py

# 過去の日付（例: 2024年12月24日）の日報を作成する場合
python daily_report.py --date 241224
```

1. その日のログ（`logs/daily_log_YYYY-MM-DD.jsonl`）を30分ごとに要約し、カレンダー予定と合わせて `templates/report_prompt_template.md` からプロンプトを作ります。記録期間・キャプチャ回数・ログ欠落はプログラムが正確に計算します。
2. `claude -p` にプロンプトを渡し、日報の本文（`## 1.`〜`## 5.`）を書かせます（1〜2分程度）。
3. 見出しを付けて `outputs/daily_report_YYYY-MM-DD.md` に保存します。
4. 保存した日報を dashboard へ送ります（`.env` が未設定、または送信に失敗しても日報は保存されたままです。`--no-sync` で送信しません）。
5. 日曜の日報ならその週、月末の日報ならその月のサマリを作って dashboard へ送ります（下の「週・月のサマリ」）。その日の日報を作り忘れても、次に日報を作ったときに、終わった直前の週・月のサマリがまだ無ければ作ります。`--no-summary` で作りません。

* 作業ログ（jsonl）のうち日報に入れたくない行は、`daily_report.py` を実行する前に `logs/daily_log_YYYY-MM-DD.jsonl` から消してください。Claude にはログの要約を渡し、dashboard には日報とサマリの Markdown だけを送ります（jsonl は送りません）。

* `claude -p` はログイン中のサブスクリプションで動くため、API の従量課金はかかりません（サブスクリプションの使用量には数えられます）。環境変数 `ANTHROPIC_API_KEY` は渡さないようにしています。
* 同じ日付の日報が既にあるときは止まります。作り直すときは `--force` を付けます。
* `--model sonnet` のようにモデルを指定できます。`--dry-run` を付けると、送らずにプロンプトを表示します。

### dashboard への送信

`daily_report.py` を通さずに作成・編集した日報は、手で送ります。内容が変わっていない日報は dashboard 側で何も書かれないので、何度送り直しても問題ありません。送るのは日報の Markdown だけで、作業ログ（`logs/`）は送りません。

```bash
python sync_dashboard.py 261021          # 指定した日付（複数可）
python sync_dashboard.py --all           # outputs/ の全日報
python sync_dashboard.py --all --dry-run # 送る対象を表示するだけ
python sync_dashboard.py --summaries     # outputs/weekly/・outputs/monthly/ の週・月のサマリをすべて送る
python sync_dashboard.py --delete 261023 # 間違って送った日報を dashboard から消す（outputs/ のファイルは残る）
python sync_dashboard.py --reparse       # dashboard 側の解析の規則を変えた後、登録済みの日報を作り直させる
```

### 週・月のサマリ

期間内の日報を読み直して、「何をして何が進んだか」の振り返りを `claude -p` に書かせ、`outputs/weekly/`・`outputs/monthly/` に保存して dashboard へ送ります（`--no-sync` で送りません）。週末・月末は `daily_report.py` が自動で作るので、手で実行するのは作り直すときや過去の期間を作るときです。時間や回数の集計は dashboard（D1）で出せますが、文章のまとめはこちらで作ります。日数・記録時間・ログ欠落の合計はプログラムが計算してプロンプトに渡します。

```bash
python summarize.py week               # 直近の終わった週（月曜〜日曜）→ weekly_YYYY-MM-DD.md（週の初日）
python summarize.py week 261015        # 2026-10-15 を含む週
python summarize.py month              # 直近の終わった月 → monthly_YYYY-MM.md
python summarize.py month 2610         # 2026年10月
```

* 週次は各日の「メイン作業・作業詳細・知見・作業中だったファイル」を、月次はプロンプトが大きくなりすぎないよう「メイン作業・知見」だけを渡します。
* 同じ期間のサマリが既にあるときは止まります。作り直すときは `--force`。`--model`、`--dry-run` も使えます。
* 形式は `templates/summary_prompt_template.md` で決めます。

## ファイル構成

- `main.py`: ログ記録用スクリプト
- `daily_report.py`: 日報生成・自動化スクリプト
- `sync_dashboard.py`: 日報を dashboard へ送るスクリプト
- `summarize.py`: 週・月のサマリを作るスクリプト
- `src/`: 
    - `report_generator.py`: プロンプトの作成と、回答から日報への仕上げ
    - `log_digest.py`: 作業ログの要約、記録期間・ログ欠落の計算
    - `claude_runner.py`: `claude -p` の呼び出し
    - `dashboard_sync.py`: dashboard の API（`POST /api/daily-reports`、`POST /api/daily-report-summaries`）への送信
    - `summary_generator.py`: 週・月の期間、集計、サマリの作成、週末・月末に作る期間の判定
    - `ocr_utils.py`: 画面OCR処理
    - `app_utils.py`: アプリ名取得
    - `calendar_utils.py`: カレンダー連携
- `templates/report_prompt_template.md`: 日報のプロンプトのテンプレート（日報の形式はここで決める）
- `templates/summary_prompt_template.md`: 週・月のサマリのプロンプトのテンプレート
- `.env.example`: dashboard への送信設定の雛形
- `outputs/`: 生成された日報の保存先（週次サマリは `outputs/weekly/`、月次は `outputs/monthly/`）
- `logs/`: 作業ログ保存先
