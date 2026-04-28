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
HUGGINGFACE_TOKEN="..." # 話者分離を有効化する場合
```

## ローカル音声解析について

- ローカル優先は `faster-whisper` を使用（CPU 実行）。
- 話者分離は `pyannote.audio` を利用し、`HUGGINGFACE_TOKEN` がある場合に有効化。
- ローカル解析に失敗した場合は Groq Whisper API に自動フォールバックします。
