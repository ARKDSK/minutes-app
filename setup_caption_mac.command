#!/bin/bash
cd "$(dirname "$0")"
echo "==================================="
echo " 動画字幕自動生成アプリ セットアップ中..."
echo "==================================="
if ! command -v ffmpeg >/dev/null 2>&1; then
    echo ""
    echo "ffmpegが見つかりません。Homebrewでインストールします。"
    echo "（Homebrewが未インストールの場合は https://brew.sh を先にご確認ください）"
    brew install ffmpeg
fi
python3 -m pip install -r requirements.txt
echo ""
echo "==================================="
echo " セットアップ完了！"
echo " run_caption_mac.command をダブルクリックして起動してください"
echo "==================================="
read -p "Enterキーで閉じます..."
