#!/bin/bash
cd "$(dirname "$0")"
echo "動画字幕自動生成アプリを起動中..."
python3 desktop_launcher.py
read -p "Enterキーで閉じます..."
