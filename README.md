# 議事録アプリ（PHP 版）

素の PHP + MySQL で実装した議事録管理アプリです。Streamlit 版（Python）と同等の
機能（音声文字起こし・決定/保留/ToDo 抽出・3段階要約・ハイブリッド検索・類似会議
レコメンド・AI 横断チャット）を提供します。フレームワーク非依存、依存は PHP 標準
拡張のみ（PDO mysql, curl, mbstring, fileinfo）です。

## 構成

```
minutes-app-php/
├── public/
│   ├── index.php          # フロントコントローラ
│   └── assets/style.css
├── src/
│   ├── bootstrap.php      # 設定ロード・インスタンス生成
│   ├── Db.php             # PDO ラッパ
│   ├── Auth.php           # パスワード認証 + CSRF
│   ├── Groq.php           # Groq API (chat / whisper) クライアント
│   ├── Pipeline.php       # LLM パイプライン + bigram 類似度
│   └── View.php           # テンプレヘルパ
├── views/                 # 各画面テンプレート
├── config/
│   └── config.example.php # 設定テンプレート
├── sql/
│   └── init.sql           # DB スキーマ
├── uploads/               # 音声一時置き場（.gitkeep のみ）
└── README.md
```

## 必要環境

- PHP 8.1 以上
- MySQL 5.7 または 8.x（`ngram` パーサによる全文検索）
- PHP 拡張: `pdo_mysql`, `curl`, `mbstring`, `fileinfo`

## セットアップ

```bash
# 1. DB 作成
mysql -uroot -p < sql/init.sql

# 2. 設定ファイル作成
cp config/config.example.php config/config.php
# エディタで config/config.php を編集:
#   - app_password
#   - db.user/db.pass（init.sql で作成したユーザー）
#   - groq_api_key

# 3. 開発用に起動（PHP ビルトインサーバ）
php -S 127.0.0.1:8000 -t public
# → http://127.0.0.1:8000/ でアクセス
```

本番環境では Apache / Nginx + php-fpm 構成にし、`public/` をドキュメントルートに
設定してください。`uploads/` 直下には Web からアクセスできないように（例: Nginx
で `location /uploads/ { deny all; }`）しておくのが安全です。

## 必要な API キー

| 用途 | 取得先 | 設定キー |
| --- | --- | --- |
| LLM / 文字起こし | https://console.groq.com/ | `groq_api_key` |
| ログインパスワード | 任意の強い値 | `app_password` |

## 機能

- 📝 **議事録追加**: 音声アップロード → Groq Whisper 文字起こし → 本文/タグ編集 → 保存。
- 🏷️ **タグ自動生成**: LLM に依頼してカンマ区切りキーワードを抽出。
- 🔍 **ハイブリッド検索**: 文字 bigram 類似度（semantic 相当）+ キーワード一致スコア。
- 📄 **一覧**: 分析結果・3段階要約を折りたたみ表示。
- 📌 **会議詳細**: タイムスタンプ付き発話リスト + 類似会議レコメンド。
- 💬 **AI 横断チャット**: 質問に対し、関連議事録を根拠に LLM が回答。
- 🔒 **パスワード認証 + CSRF**: セッションベース、CSRF トークン付き。

## Python 版との差分

- **埋め込み**: Python 版は `sentence-transformers` の多言語モデル。PHP 版は外部依存を
  増やさないため、文字 bigram の頻度ベクトル cosine 類似度で代替しています。
  精度を上げたい場合は OpenAI `text-embedding-3-small` API 等を `src/Pipeline.php` に
  組み込むのが簡単です。
- **ローカル文字起こし**: Python 版は `faster-whisper` + `pyannote.audio` でローカル解析。
  PHP 版は Groq Whisper API のみ（ブラウザ + PHP 単体でオフライン解析するのは現実的
  でないため）。話者分離は非対応です。
- **タグ抽出**: Python 版は Janome 形態素解析。PHP 版は LLM 呼び出しで代替。

## 参考

- データモデル: `sql/init.sql`
- LLM プロンプトは `src/Pipeline.php` 内。モデルを変更するには `config/config.php`
  の `groq_chat_model` を `llama-3.3-70b-versatile` など上位モデルへ。
