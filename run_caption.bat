@echo off
echo 動画字幕自動生成アプリを起動中...
echo ※ 事前にffmpegをインストールし、PATHに通してください（https://ffmpeg.org/download.html）
echo ブラウザが自動で開きます（少し待ってください）
streamlit run caption_app.py
pause
