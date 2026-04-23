# 議事録アプリ（PHP 版）引き継ぎ資料

最終更新: 2026-04-23

本書は、素の PHP + MySQL で実装された議事録アプリをサイト管理者に引き継ぐ
ための運用ドキュメントです。

---

## 1. アプリ概要

Streamlit（Python）で実装されていた議事録アプリを、素の PHP + MySQL に
移植したバージョンです。フレームワークは使わず、PDO（mysql）と curl、
Groq の REST API を組み合わせています。

### 主な機能

1. 音声アップロード → Groq Whisper API で文字起こし
2. LLM（Groq `llama-3.1-8b-instant`）による分析（決定/保留/ToDo）
3. 同一 LLM コールで 3 段階要約（超要約 / 要点 / 詳細）
4. タグ自動生成（LLM 依頼ベース）
5. ハイブリッド検索（文字 bigram 類似度 + キーワードスコア）
6. 会議詳細画面（タイムスタンプ付き発話 + 類似会議レコメンド）
7. AI 横断チャット（全議事録を根拠に質問応答）
8. パスワード認証 + CSRF トークン

## 2. 技術スタック

| 種別 | 採用技術 |
| --- | --- |
| 言語 / ランタイム | PHP 8.1 以上 |
| DB | MySQL 5.7 / 8.x（`ngram` パーサで全文検索） |
| LLM / 文字起こし | Groq REST API（`chat/completions`, `audio/transcriptions`） |
| フロント | プレーン HTML + 軽量 CSS、JavaScript ほぼ不使用 |
| 依存拡張 | `pdo_mysql`, `curl`, `mbstring`, `fileinfo` |
| 外部ライブラリ | なし（Composer 不要） |

## 3. ディレクトリ構成

```
minutes-app-php/
├── public/
│   ├── index.php             # フロントコントローラ & ルータ
│   └── assets/style.css
├── src/
│   ├── bootstrap.php         # 設定ロード・DI
│   ├── Db.php                # PDO ラッパ（fetchMinutes など）
│   ├── Auth.php              # パスワード認証 + CSRF
│   ├── Groq.php              # Groq HTTP クライアント
│   ├── Pipeline.php          # LLM パイプライン + bigram 類似度
│   └── View.php              # テンプレヘルパ（XSSエスケープ等）
├── views/
│   ├── _layout_header.php    # 共通ヘッダ + タブ
│   ├── _layout_footer.php
│   ├── _analysis.php         # 決定/保留/ToDo 表示パーツ
│   ├── _summary.php          # 3段階要約表示パーツ
│   ├── login.php / add.php / search.php / list.php
│   ├── detail.php / chat.php
├── config/config.example.php # 設定テンプレ
├── sql/init.sql              # DB スキーマ
├── uploads/                  # 音声一時置き場（空）
├── docs/HANDOVER.md          # 本書
├── README.md
└── .gitignore
```

## 4. セットアップ手順

### 4-1. 必要なものを揃える

- PHP 8.1 以上（拡張: `pdo_mysql`, `curl`, `mbstring`, `fileinfo`）
- MySQL 5.7 以上
- Groq API キー（https://console.groq.com/ から取得）

### 4-2. DB 初期化

```bash
mysql -uroot -p < sql/init.sql
```

ユーザーを別途作りたい場合は:

```sql
CREATE USER 'minutes_user'@'%' IDENTIFIED BY 'minutes_pass';
GRANT ALL ON minutes_app.* TO 'minutes_user'@'%';
FLUSH PRIVILEGES;
```

### 4-3. 設定ファイル

```bash
cp config/config.example.php config/config.php
```

`config/config.php` を編集（Git 対象外）:

```php
return [
    'app_password' => '強いパスワード',
    'db' => [
        'host' => '127.0.0.1', 'port' => 3306,
        'name' => 'minutes_app',
        'user' => 'minutes_user', 'pass' => 'minutes_pass',
    ],
    'groq_api_key' => 'gsk_...',
    'groq_chat_model'    => 'llama-3.1-8b-instant',
    'groq_whisper_model' => 'whisper-large-v3-turbo',
    'upload_tmp_dir' => __DIR__ . '/../uploads',
    'max_upload_mb'  => 50,
];
```

### 4-4. 起動

**開発用（PHP ビルトインサーバ）**

```bash
php -S 127.0.0.1:8000 -t public
```

**本番（Nginx + php-fpm の例）**

```nginx
server {
    listen 80;
    server_name minutes.example.com;
    root /var/www/minutes-app-php/public;
    index index.php;

    client_max_body_size 60M;  # max_upload_mb + α

    location / {
        try_files $uri $uri/ /index.php?$query_string;
    }
    location ~ \.php$ {
        include fastcgi_params;
        fastcgi_pass unix:/run/php/php8.1-fpm.sock;
        fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
    }
    # 音声アップロード置き場は直接アクセス禁止
    location ^~ /uploads/ { deny all; }
}
```

`php.ini` で `upload_max_filesize` / `post_max_size` を音声ファイルサイズに合わせて
調整してください（例: 60M）。

## 5. 画面と使い方

| タブ | URL | 操作 |
| --- | --- | --- |
| ログイン | `index.php?page=login` | パスワード入力 |
| 📝 議事録を追加 | `?page=add` | 音声アップロード → 文字起こし → 本文編集 → 「保存する」で LLM 分析・要約付きで DB に登録 |
| 🔍 検索 | `?page=search` | キーワード + 期間/タグ絞込、ハイブリッドスコア順に表示 |
| 📄 一覧 | `?page=list` | 登録済みを新しい順。削除ボタンあり |
| 📌 会議詳細 | `?page=detail&id=…` | 分析・要約・タイムスタンプ付き発話・類似会議 |
| 💬 AI横断チャット | `?page=chat` | 自然文質問、LLM が上位マッチ会議を根拠に回答 |
| ログアウト | `?page=logout` | セッション破棄 |

## 6. データモデル（`minutes` テーブル）

| カラム | 型 | 説明 |
| --- | --- | --- |
| `id` | CHAR(36) | UUID 風（ランダム） |
| `date_str` | DATE | 開催日 |
| `title` | VARCHAR(255) | 会議タイトル |
| `participants` | VARCHAR(500) | カンマ区切り |
| `tags` | VARCHAR(500) | カンマ区切り |
| `content` | MEDIUMTEXT | 本文（文字起こし結果含む） |
| `analysis` | JSON | `{decisions, pending, todos}` |
| `summary_3` | JSON | `{level1, level2, level3}` |
| `transcript_segments` | JSON | `[{start, end, speaker, text}]` |
| `bigrams` | JSON | 文字 bigram 頻度マップ（検索用） |
| `created_at` / `updated_at` | TIMESTAMP | 自動設定 |

インデックス:
- `idx_date`（`date_str`）
- `ft_content`（`title, content, tags` を `ngram` パーサで全文検索）

## 7. コード読み解きガイド

| 場所 | 役割 |
| --- | --- |
| `public/index.php` | ルータ。`?page=…` と POST `action` を分岐。コントローラの役割も兼ねる |
| `src/Pipeline.php` | LLM プロンプト、bigram 類似度、ハイブリッド検索、横断チャット |
| `src/Groq.php` | REST API 呼び出し（curl）。chat / chatJson / transcribe の 3 メソッド |
| `src/Db.php` | JSON カラムの自動デコード、`fetchMinutes(light|full)` |
| `src/Auth.php` | セッション + CSRF |
| `views/` | PHP テンプレ。`View::e()` で必ずエスケープ |

## 8. 運用 Tips

- **LLM モデル差し替え**: `config/config.php` の `groq_chat_model` を変更するだけ。
  精度重視なら `llama-3.3-70b-versatile` など。
- **検索精度向上**: 現在は文字 bigram cosine + キーワード。もしよりセマンティックに
  したい場合は `src/Pipeline.php` に OpenAI `text-embedding-3-small` 等の呼び出しを
  追加し、`bigrams` カラムに並べて `embedding` カラムを保存する形に拡張できます。
- **一括再計算**: スキーマ変更後に既存行の `bigrams` / `analysis` を再生成したい場合、
  管理者スクリプトを別途書くか、一覧から削除 → 再登録で対処可能。
- **バックアップ**: `mysqldump minutes_app > backup.sql` を定期実行してください。

## 9. トラブルシューティング

| 症状 | 原因と対処 |
| --- | --- |
| `config/config.php が見つかりません` | `config/config.example.php` をコピーして作成してください |
| ログインできない | `app_password` が空または一致していない。`config.php` を確認 |
| 文字起こしで HTTP 401/403 | `groq_api_key` が無効。Groq コンソールで再発行 |
| 保存時に SQL エラー | `sql/init.sql` を流していない、または MySQL バージョンが 5.7 未満 |
| 日本語検索がヒットしない | `ngram` パーサは `ft_min_word_len=2` が必要。MySQL の `my.cnf` に `[mysqld] ngram_token_size=2` を追加し再起動 |
| 音声アップロードが 413 になる | Web サーバの `client_max_body_size` と PHP の `upload_max_filesize`/`post_max_size` を確認 |

## 10. セキュリティ・運用チェックリスト

- [ ] `config/config.php` はリポジトリに含めない（`.gitignore` 済）
- [ ] `app_password` を十分な長さのランダムに変更
- [ ] `GROQ_API_KEY` を管理者発行のキーへ差し替え
- [ ] MySQL の `minutes_user` に必要最小限の権限のみ
- [ ] `uploads/` ディレクトリを Web から直接参照できない設定
- [ ] HTTPS（TLS）でのみ公開
- [ ] DB の日次バックアップ設定
- [ ] PHP `display_errors=Off`（本番）

## 11. 連絡事項

- LLM の応答品質・応答時間は Groq 側の混雑に依存します。長時間応答がない場合は
  リトライまたはモデル変更を検討してください。
- 文字起こしは現時点で Groq Whisper API のみ対応。ローカル whisper を使いたい
  場合は Python 版との併用を推奨します。
