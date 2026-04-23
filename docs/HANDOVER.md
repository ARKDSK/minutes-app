# 議事録アプリ 引き継ぎ資料

最終更新: 2026-04-23

本書は、サイト管理者への引き継ぎを目的として、アプリの概要・構成・セット
アップ・運用・トラブルシューティング・コード構造をまとめたものです。

---

## 1. アプリ概要

会議の音声ファイルを Streamlit 上でアップロードすると、以下をワンストップで
行う Web アプリケーションです。

1. 音声の文字起こし（ローカル優先 / クラウドフォールバック）
2. 話者分離（任意）
3. 決定事項 / 保留事項 / ToDo の抽出
4. 3段階要約（超要約 / 要点 / アクション中心の詳細）
5. 全議事録を対象としたハイブリッド検索（semantic + keyword）
6. 会議詳細画面（タイムスタンプ付き発話一覧・類似会議レコメンド）
7. AI による全議事録横断チャット

## 2. 技術スタック

| 種別 | 採用技術 |
| --- | --- |
| フロントエンド / サーバ | Streamlit (Python) |
| データベース | Supabase (PostgreSQL + pgvector 相当 JSON) |
| 埋め込み | sentence-transformers (`paraphrase-multilingual-MiniLM-L12-v2`) |
| ローカル文字起こし | `faster-whisper` (CPU int8, 既定: `small`) |
| 話者分離 (任意) | `pyannote.audio` (HuggingFace トークン必須) |
| クラウドフォールバック文字起こし | Groq Whisper (`whisper-large-v3-turbo`) |
| LLM (抽出・要約・チャット) | Groq (`llama-3.1-8b-instant`) |
| 形態素解析 (タグ自動生成) | Janome |

## 3. リポジトリ構成

```
minutes-app/
├── app.py                    # 本体 (Streamlit 1 ファイル構成)
├── requirements.txt          # Python 依存関係
├── docker-compose.yml        # (任意) ローカル MySQL（将来用途）
├── README.md                 # 簡易ガイド
├── .gitignore
├── .streamlit/
│   └── secrets.toml.example  # 秘密情報テンプレート
└── docs/
    ├── HANDOVER.md           # 本書
    └── minutes-app-v-spec.md # 要件定義
```

`.streamlit/secrets.toml` は `.gitignore` で除外されます。本番環境で実ファイ
ルを配置してください。

## 4. セットアップ手順

### 4-1. Supabase 側準備

1. Supabase プロジェクトを作成。
2. `minutes` テーブルを作成（下記スキーマを参照）。
3. プロジェクトの `URL` と `anon key` を取得。

`minutes` テーブル DDL（例）:

```sql
create table minutes (
  id uuid primary key,
  date_str text,
  title text,
  participants text,
  tags text,
  content text,
  embedding jsonb,
  analysis jsonb,
  summary_3 jsonb,
  transcript_segments jsonb
);
```

> `embedding` は 384 次元の float 配列を JSON で保存しています。pgvector 拡張
> を使う運用に切り替える場合は、読み書き箇所の型を合わせてください。

### 4-2. 必要な API キー

| 用途 | 取得先 | secrets キー |
| --- | --- | --- |
| DB | Supabase プロジェクト設定 | `SUPABASE_URL`, `SUPABASE_KEY` |
| ログインPW | 任意の強力なパスワード | `APP_PASSWORD` |
| LLM / 音声クラウド | https://console.groq.com/ | `GROQ_API_KEY` |
| 話者分離 (任意) | https://huggingface.co/settings/tokens | `HUGGINGFACE_TOKEN` |

### 4-3. ローカル起動

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# secrets.toml を編集

streamlit run app.py
```

初回起動時に、`sentence-transformers` と `faster-whisper` がモデルをダウン
ロードします（合計 1〜2 GB 程度）。以降は `@st.cache_resource` による常駐で
再ダウンロードは発生しません。

### 4-4. Streamlit Cloud 等へのデプロイ

- Streamlit Community Cloud: リポジトリを接続し、`secrets.toml` の中身を
  Secrets 設定画面に貼り付けるだけで動作します。
- 自前サーバ (Linux / Docker): `streamlit run app.py --server.port 8501`
  でリッスンし、リバースプロキシ (Nginx 等) 経由で公開してください。

## 5. 画面と使い方

アクセス時にパスワード（`APP_PASSWORD`）を要求します。

| タブ | 主な操作 |
| --- | --- |
| 📝 議事録を追加 | 音声アップロード → 文字起こし → 内容編集 → 「保存する」で抽出/要約/埋め込み生成。タグは手入力か「🏷️ 自動生成」。 |
| 🔍 検索 | キーワード入力 + 期間 / タグ絞込で、semantic + keyword のハイブリッドスコアで表示。 |
| 📄 一覧 | 登録済み議事録の分析結果・3段階要約を新しい順に確認。 |
| 📌 会議詳細 | 会議を選択し、タイムスタンプ付き発話リスト・類似会議レコメンドを確認。 |
| 💬 AI横断チャット | 自然文で質問 → 上位マッチの会議を根拠に LLM が回答。参照会議も併記。 |

## 6. コード構造（app.py）

単一ファイル構成です。以下の責務ごとにブロックが分かれています。

| セクション | 行の目安 | 役割 |
| --- | --- | --- |
| 設定読み込み | 冒頭 | `st.secrets` + 環境変数から設定ロード |
| 認証 | `if not st.session_state["authenticated"]` | パスワードゲート |
| リソースキャッシュ | `@st.cache_resource` 関数群 | Supabase / 埋め込みモデル / Groq / Janome / Whisper / Diarizer を常駐化 |
| 文字起こし | `transcribe_audio_local` / `_fallback_cloud` / `transcribe_audio` | ローカル優先・失敗時クラウド |
| LLM パイプライン | `analyze_and_summarize` | 決定/保留/ToDo + 3段階要約を 1 コールで取得 |
| 検索 / 推薦 | `search_minutes` / `recommend_similar_meetings` | NumPy 行列積でベクトル化 |
| データ取得 | `fetch_minutes_light` / `fetch_minutes_full` | `@st.cache_data` で Supabase へのアクセス抑制 |
| UI | 最下部 `tab1〜tab5` | Streamlit タブ構築 |

### データモデル（Supabase `minutes` テーブル）

| カラム | 型 | 説明 |
| --- | --- | --- |
| `id` | uuid | 主キー |
| `date_str` | text | `YYYY-MM-DD` |
| `title` | text | 会議タイトル |
| `participants` | text | カンマ区切り |
| `tags` | text | カンマ区切り |
| `content` | text | 議事録本文 |
| `embedding` | jsonb | 文埋め込み 384 次元 |
| `analysis` | jsonb | `{decisions, pending, todos}` |
| `summary_3` | jsonb | `{level1, level2, level3}` |
| `transcript_segments` | jsonb | `[{start, end, speaker, text}]` |

## 7. 運用 Tips

- **軽量化の既定**: Whisper モデルは `small` int8。さらに軽くしたい場合は
  `WHISPER_MODEL_SIZE=base` か `tiny`。精度優先なら `medium` / `large-v3`。
- **キャッシュ無効化**: 保存時に `invalidate_minutes_cache()` を呼んで一覧を
  最新化しています。別プロセスから書き込んだ場合はブラウザのリロードで
  キャッシュを明示的にクリアしてください。
- **話者分離**: `HUGGINGFACE_TOKEN` 未設定、または `pyannote/speaker-
  diarization-3.1` モデルの利用規約に同意していない場合は自動スキップ。
- **LLM 品質**: `llama-3.1-8b-instant` は応答が速い代わりに、長文の議事録に
  対しては要点漏れがあり得ます。より厳密にしたい場合は `app.py` 内の
  `analyze_and_summarize` / `answer_cross_minutes_chat` のモデル名を Groq の
  上位モデル（例: `llama-3.3-70b-versatile`）に差し替えてください。

## 8. トラブルシューティング

| 症状 | 原因と対処 |
| --- | --- |
| 起動時に `KeyError: 'SUPABASE_URL'` | `secrets.toml` のキー名が違う / ファイル未配置。`.streamlit/secrets.toml.example` を参照。 |
| 文字起こしが非常に遅い | `WHISPER_MODEL_SIZE` を `base` / `tiny` に変更。もしくはクラウドフォールバックを常用。 |
| 話者分離が効かない | `HUGGINGFACE_TOKEN` の設定と HuggingFace 上でのモデル利用規約への同意を確認。 |
| 検索結果が 1 件も出ない | 対象行の `embedding` が `null` の可能性。該当レコードを一度編集保存すると再計算される。 |
| `保存エラー` が出る | Supabase テーブルのカラム名・型が本書「データモデル」節と一致しているか確認。 |
| 画面が真っ白 / ローディングが固まる | 初回ロード中はモデルダウンロードで数分かかります。ログ (`streamlit run` のコンソール) を確認。 |

## 9. バックアップ / セキュリティ

- Supabase 側でポイントインタイムリカバリ（PITR）または日次ダンプを有効化し
  てください。
- `APP_PASSWORD` は十分な長さの乱数を推奨。流出時は再発行のうえ全員に再配布。
- `GROQ_API_KEY` / `HUGGINGFACE_TOKEN` はリポジトリにコミットしないよう、
  `.streamlit/secrets.toml` もしくはデプロイ先のシークレット管理機能を使用。

## 10. 連絡 / 引き継ぎ完了時の確認項目

- [ ] Supabase プロジェクト所有権を管理者アカウントに移管済み
- [ ] Groq / HuggingFace のキーを管理者発行分へ差し替え済み
- [ ] 本書の手順でローカル起動に成功することを確認
- [ ] 本番環境で「議事録を追加 → 検索 → AI 横断チャット」まで通しで動作
- [ ] パスワード・各 API キーを安全な場所に保管
