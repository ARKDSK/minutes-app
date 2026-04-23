# Minutes App V

議事録を蓄積・検索・横断活用するアプリです。現状実装は Streamlit ベースで、会議音声の文字起こしから抽出・要約・検索・横断チャットまで一気通貫で扱えます。

## 主な機能

- 音声アップロードで文字起こし開始（**ローカル解析優先**、失敗時クラウドフォールバック）
- 話者分離（pyannote が利用可能な場合は重め設定で実行）
- 決定事項 / 保留事項 / ToDo 抽出
- 3段階要約（超要約 / 要点 / アクション中心詳細）
- 会議詳細画面で分析結果とタイムスタンプ付き発話リンクを表示
- シンプル全文検索 + 会議横断ハイブリッド検索（semantic + keyword）
- 類似会議レコメンド
- AIチャットで全議事録横断質問

## セットアップ

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## 必要な secrets（`.streamlit/secrets.toml`）

```toml
SUPABASE_URL="..."
SUPABASE_KEY="..."
APP_PASSWORD="..."
GROQ_API_KEY="..."
HUGGINGFACE_TOKEN="..."   # 話者分離を有効化する場合
WHISPER_MODEL_SIZE="small" # 任意: tiny / base / small / medium / large-v3（既定: small）
```

## ローカル音声解析について

- ローカル優先は `faster-whisper` を使用（CPU int8 実行、既定 `small` モデル）。
- より高精度にしたい場合は `WHISPER_MODEL_SIZE` を `medium` / `large-v3` に変更可能。
- 話者分離は `pyannote.audio` を利用し、`HUGGINGFACE_TOKEN` がある場合に有効化。
- ローカル解析に失敗した場合は Groq Whisper API に自動フォールバックします。

## パフォーマンス最適化

- Whisper / pyannote / Groq / SentenceTransformer / Janome は `@st.cache_resource` で常駐化。
- 議事録一覧は軽量カラムのみ取得し、詳細画面でのみフル取得。保存時にキャッシュを無効化。
- コサイン類似度はベクトル化した NumPy 行列積で一括計算。
- 分析抽出と3段階要約は 1 回の LLM 呼び出しに統合し、保存時の待ち時間を約半減。
