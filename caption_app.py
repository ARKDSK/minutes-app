import streamlit as st
from groq import Groq
import pandas as pd
import platform
import subprocess
import tempfile
import os
import shutil
import uuid

GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
APP_PASSWORD = st.secrets["APP_PASSWORD"]

# フォントプリセット（表示名 → フォントファミリー名）
# 実行環境ごとに標準搭載されている（または packages.txt で導入した）フォントを使う
if platform.system() == "Darwin":
    FONT_PRESETS = {
        "ゴシック体（標準）": "Hiragino Sans",
        "明朝体": "Hiragino Mincho ProN",
        "丸ゴシック（ポップ）": "Hiragino Maru Gothic ProN",
    }
elif platform.system() == "Windows":
    FONT_PRESETS = {
        "ゴシック体（標準）": "Yu Gothic",
        "明朝体": "Yu Mincho",
        "丸ゴシック（ポップ）": "UD Digital Kyokasho N-R",
    }
else:
    FONT_PRESETS = {
        "ゴシック体（標準）": "Noto Sans CJK JP",
        "明朝体": "IPAexMincho",
        "丸ゴシック（ポップ）": "M PLUS 1",
    }

POSITION_PRESETS = {
    "下部": 2,  # ASS Alignment: 2 = 下中央
    "上部": 8,  # ASS Alignment: 8 = 上中央
}

# パスワード認証
if "caption_authenticated" not in st.session_state:
    st.session_state["caption_authenticated"] = False

if not st.session_state["caption_authenticated"]:
    st.set_page_config(page_title="動画字幕自動生成", page_icon="🎬")
    st.title("🎬 動画字幕自動生成アプリ")
    pw = st.text_input("パスワードを入力してください", type="password")
    if st.button("ログイン"):
        if pw == APP_PASSWORD:
            st.session_state["caption_authenticated"] = True
            st.rerun()
        else:
            st.error("パスワードが違います")
    st.stop()

st.set_page_config(page_title="動画字幕自動生成", page_icon="🎬", layout="wide")
st.title("🎬 動画字幕自動生成アプリ")
st.caption("FCPで書き出した動画をアップロードすると、自動で字幕を生成して焼き込みます。")


def run_cmd(cmd):
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode(errors="ignore")[-2000:])
    return result


def get_video_info(video_path):
    result = run_cmd([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-show_entries", "format=duration",
        "-of", "csv=p=0", video_path
    ])
    lines = [l for l in result.stdout.decode().strip().splitlines() if l]
    width, height = map(int, lines[0].split(","))
    duration = float(lines[1]) if len(lines) > 1 else 0.0
    return width, height, duration


def extract_audio(video_path, audio_path):
    run_cmd([
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", audio_path
    ])


def transcribe(audio_path):
    client = Groq(api_key=GROQ_API_KEY)
    with open(audio_path, "rb") as f:
        resp = client.audio.transcriptions.create(
            file=(os.path.basename(audio_path), f.read()),
            model="whisper-large-v3-turbo",
            language="ja",
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )
    segments = getattr(resp, "segments", None) or []
    rows = []
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if text:
            rows.append({"start": float(seg["start"]), "end": float(seg["end"]), "text": text})
    return rows


def sec_to_ass_time(sec):
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def hex_to_ass_color(hex_color):
    hex_color = hex_color.lstrip("#")
    r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
    return f"&H00{b}{g}{r}".upper()


def build_ass(rows, width, height, font_name, font_size, bold, text_color, outline_color, alignment):
    primary = hex_to_ass_color(text_color)
    outline = hex_to_ass_color(outline_color)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{primary},{primary},{outline},&H00000000,{1 if bold else 0},0,0,0,100,100,0,0,1,3,1,{alignment},40,40,{max(20, height // 12)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for row in rows:
        start = sec_to_ass_time(row["start"])
        end = sec_to_ass_time(row["end"])
        text = str(row["text"]).strip().replace("\n", "\\N")
        if not text:
            continue
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")
    return header + "\n".join(lines)


def ffmpeg_escape_path(path):
    p = path.replace("\\", "/").replace(":", "\\:")
    return p


def burn_captions(video_path, ass_path, output_path):
    vf = f"ass={ffmpeg_escape_path(ass_path)}"
    run_cmd([
        "ffmpeg", "-y", "-i", video_path,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        output_path
    ])


# ---- UI ----
video_file = st.file_uploader("🎞️ 動画ファイル（FCPから書き出したmp4/mov）", type=["mp4", "mov", "m4v"])

if video_file:
    if "work_dir" not in st.session_state or st.session_state.get("video_name") != video_file.name:
        old_dir = st.session_state.get("work_dir")
        if old_dir and os.path.isdir(old_dir):
            shutil.rmtree(old_dir, ignore_errors=True)
        st.session_state["work_dir"] = tempfile.mkdtemp(prefix="caption_")
        st.session_state["video_name"] = video_file.name
        st.session_state.pop("caption_rows", None)
        st.session_state.pop("output_path", None)

        video_path = os.path.join(st.session_state["work_dir"], "input" + os.path.splitext(video_file.name)[1])
        with open(video_path, "wb") as f:
            f.write(video_file.getbuffer())
        st.session_state["video_path"] = video_path

    st.video(st.session_state["video_path"])

    st.subheader("🎨 字幕スタイル")
    col1, col2, col3 = st.columns(3)
    with col1:
        font_label = st.selectbox("フォント", list(FONT_PRESETS.keys()))
        font_size = st.slider("文字サイズ", 20, 100, 48)
    with col2:
        text_color = st.color_picker("文字色", "#FFFFFF")
        outline_color = st.color_picker("縁取り色", "#000000")
    with col3:
        position_label = st.selectbox("表示位置", list(POSITION_PRESETS.keys()))
        bold = st.checkbox("太字にする", value=True)

    st.markdown("---")

    if st.button("📝 字幕を自動生成する", type="primary"):
        try:
            with st.spinner("音声を抽出して文字起こし中..."):
                audio_path = os.path.join(st.session_state["work_dir"], "audio.mp3")
                extract_audio(st.session_state["video_path"], audio_path)
                rows = transcribe(audio_path)
            if not rows:
                st.warning("音声から字幕を検出できませんでした。")
            else:
                st.session_state["caption_rows"] = rows
                st.success(f"✅ {len(rows)}件の字幕を生成しました。内容を確認・修正してください。")
        except Exception as e:
            st.error(f"字幕生成エラー: {type(e).__name__}: {e}")

    if "caption_rows" in st.session_state:
        st.subheader("✏️ 字幕の確認・編集")
        df = pd.DataFrame(st.session_state["caption_rows"])
        edited_df = st.data_editor(
            df,
            column_config={
                "start": st.column_config.NumberColumn("開始（秒）", disabled=True, format="%.2f"),
                "end": st.column_config.NumberColumn("終了（秒）", disabled=True, format="%.2f"),
                "text": st.column_config.TextColumn("字幕テキスト", width="large"),
            },
            hide_index=True,
            use_container_width=True,
            num_rows="dynamic",
            key="caption_editor",
        )

        if st.button("🔥 動画に字幕を焼き込む", type="primary"):
            try:
                with st.spinner("動画に字幕を焼き込み中...（動画の長さによって時間がかかります）"):
                    width, height, _ = get_video_info(st.session_state["video_path"])
                    rows = edited_df.to_dict("records")
                    ass_text = build_ass(
                        rows, width, height,
                        FONT_PRESETS[font_label], font_size, bold,
                        text_color, outline_color,
                        POSITION_PRESETS[position_label],
                    )
                    ass_path = os.path.join(st.session_state["work_dir"], "subs.ass")
                    with open(ass_path, "w", encoding="utf-8-sig") as f:
                        f.write(ass_text)

                    output_path = os.path.join(st.session_state["work_dir"], f"captioned_{uuid.uuid4().hex[:8]}.mp4")
                    burn_captions(st.session_state["video_path"], ass_path, output_path)
                    st.session_state["output_path"] = output_path
                st.success("✅ 字幕付き動画が完成しました！")
            except Exception as e:
                st.error(f"焼き込みエラー: {type(e).__name__}: {e}")

    if st.session_state.get("output_path") and os.path.exists(st.session_state["output_path"]):
        st.subheader("✅ 完成した動画")
        st.video(st.session_state["output_path"])
        with open(st.session_state["output_path"], "rb") as f:
            st.download_button(
                "⬇️ 動画をダウンロード", f,
                file_name=f"captioned_{st.session_state['video_name']}",
                mime="video/mp4",
            )
else:
    st.info("動画ファイルをアップロードしてください。")
    old_dir = st.session_state.get("work_dir")
    if old_dir and os.path.isdir(old_dir):
        shutil.rmtree(old_dir, ignore_errors=True)
    for key in ("work_dir", "video_name", "video_path", "caption_rows", "output_path"):
        st.session_state.pop(key, None)
