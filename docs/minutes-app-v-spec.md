# Minutes App V 要件定義（更新版）

## 1. 目的

会議音声から議事録作成を自動化し、要点抽出・要約・横断検索・横断質問までを一つの画面群で完結させる。

## 2. 対応機能

1. 録音音声アップロードで自動文字起こし
2. 話者分離（重め設定）
3. 決定事項抽出
4. 保留事項抽出
5. ToDo抽出
6. 3段階要約
7. 会議詳細画面への表示
8. タイムスタンプ付きリンク表示
9. シンプル全文検索
10. 会議横断検索の高機能化（ハイブリッドランキング）
11. 類似会議レコメンド
12. AIチャットによる全議事録横断質問
13. 音声解析のローカル実行優先

## 3. データ構造（minutes テーブル）

- id (uuid)
- date_str (YYYY-MM-DD)
- title (string)
- participants (string)
- tags (string)
- content (text)
- embedding (vector / json array)
- analysis (json: decisions / pending / todos)
- summary_3 (json: level1 / level2 / level3)
- transcript_segments (json array: start / end / speaker / text)

## 4. 検索仕様

- シンプル全文検索: title/content/tags/要約内のキーワード一致
- ハイブリッド検索: semantic 類似度 + keyword スコア
- フィルタ: 期間・タグ・表示件数

## 5. 画面仕様

- 議事録追加タブ: 音声アップロード、文字起こし、抽出・要約を保存
- 検索タブ: ハイブリッドスコア表示
- 一覧タブ: 各会議の抽出結果と要約を確認
- 会議詳細タブ: タイムスタンプ付き発話行 + 類似会議
- AI横断チャットタブ: 全議事録を根拠に回答生成

## 6. 非機能

- ローカル解析失敗時はクラウド API へフォールバック
- ローカル解析に必要な依存は optional 扱い（環境に応じて有効化）
