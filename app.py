import os
import json
import uuid
import tempfile
import importlib
from collections import Counter
from datetime import datetime

import numpy as np
import streamlit as st
from groq import Groq
from janome.tokenizer import Tokenizer
from sentence_transformers import SentenceTransformer
from supabase import create_client

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
APP_PASSWORD = st.secrets["APP_PASSWORD"]
GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
HF_TOKEN = st.secrets.get("HUGGINGFACE_TOKEN", os.getenv("HUGGINGFACE_TOKEN", ""))
WHISPER_MODEL_SIZE = st.secrets.get("WHISPER_MODEL_SIZE", os.getenv("WHISPER_MODEL_SIZE", "small"))

# パスワード認証
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    st.set_page_config(page_title="議事録検索", page_icon="📋")
    st.title("📋 議事録検索システム")
    pw = st.text_input("パスワードを入力してください", type="password")
    if st.button("ログイン"):
        if pw == APP_PASSWORD:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("パスワードが違います")
    st.stop()


@st.cache_resource
def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


@st.cache_resource
def get_model():
    return SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")


@st.cache_resource
def get_groq():
    return Groq(api_key=GROQ_API_KEY)


@st.cache_resource
def get_tokenizer():
    return Tokenizer()


@st.cache_resource
def get_whisper():
    whisper_mod = importlib.import_module("faster_whisper")
    return whisper_mod.WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")


@st.cache_resource
def get_diarizer():
    if not HF_TOKEN:
        return None
    pyannote_audio = importlib.import_module("pyannote.audio")
    return pyannote_audio.Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1", use_auth_token=HF_TOKEN
    )


def mmss(seconds):
    seconds = int(seconds or 0)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def transcribe_audio_local(file_bytes, filename):
    """ローカル実行優先: faster-whisper + (任意) pyannote で話者分離。"""
    with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as tmp:
        tmp.write(file_bytes)
        audio_path = tmp.name

    try:
        whisper = get_whisper()
        raw_segments, _info = whisper.transcribe(
            audio_path,
            language="ja",
            beam_size=5,
            vad_filter=True,
        )

        segments = []
        for seg in raw_segments:
            text = (seg.text or "").strip()
            if not text:
                continue
            segments.append({
                "start": float(seg.start),
                "end": float(seg.end),
                "text": text,
                "speaker": "話者",
            })

        try:
            diarizer = get_diarizer()
            if diarizer is not None and segments:
                diar_spans = [
                    (float(turn.start), float(turn.end), speaker)
                    for turn, _, speaker in diarizer(audio_path).itertracks(yield_label=True)
                ]
                for seg in segments:
                    seg_mid = (seg["start"] + seg["end"]) / 2
                    for start, end, speaker in diar_spans:
                        if start <= seg_mid <= end:
                            seg["speaker"] = speaker
                            break
        except Exception:
            pass
    finally:
        try:
            os.unlink(audio_path)
        except OSError:
            pass

    full_text = "\n".join(f"[{mmss(s['start'])}] {s['speaker']}: {s['text']}" for s in segments)
    return full_text, segments


def transcribe_audio_fallback_cloud(file_bytes, filename):
    transcription = get_groq().audio.transcriptions.create(
        file=(filename, file_bytes),
        model="whisper-large-v3-turbo",
        language="ja",
    )
    text = transcription.text
    return text, [{"start": 0.0, "end": 0.0, "speaker": "話者", "text": text}]


def transcribe_audio(file_bytes, filename):
    try:
        return transcribe_audio_local(file_bytes, filename)
    except Exception as e:
        st.warning(f"ローカル音声解析に失敗したためクラウドにフォールバックしました: {e}")
        return transcribe_audio_fallback_cloud(file_bytes, filename)


db = get_supabase()
model = get_model()

STOP_WORDS = frozenset({
    "こと", "もの", "ため", "これ", "それ", "あれ", "ここ", "そこ", "あそこ",
    "よう", "とき", "場合", "必要", "確認", "対応", "実施", "検討", "予定",
    "議事録", "会議", "本日", "今回", "資料", "内容", "方針", "方向", "状況",
    "以下", "以上", "関連", "今後", "共有", "報告", "説明", "依頼",
})


def extract_tags(text, top_n=5):
    nouns = []
    for token in get_tokenizer().tokenize(text):
        pos = token.part_of_speech.split(",")
        part, sub = pos[0], pos[1]
        surface = token.surface
        if part == "名詞" and sub not in ("数", "接尾", "非自立") and len(surface) >= 2:
            if surface not in STOP_WORDS:
                nouns.append(surface)
    return ", ".join(w for w, _ in Counter(nouns).most_common(top_n))


def analyze_and_summarize(text):
    """1回のLLM呼び出しで分析(決定/保留/ToDo) + 3段階要約を取得。"""
    prompt = f"""以下の議事録を分析し、JSONのみで返してください。

項目:
- decisions: 決定事項の短い箇条書き（なければ空配列）
- pending: 保留事項の短い箇条書き（なければ空配列）
- todos: ToDoの短い箇条書き（なければ空配列）
- summary_level1: 1文で超要約
- summary_level2: 3〜5項目の要点
- summary_level3: 実行アクション中心の詳細要約（決定/保留/TODOを含む）

議事録:
{text}

出力フォーマット:
{{
  "decisions": ["..."],
  "pending": ["..."],
  "todos": ["..."],
  "summary_level1": "...",
  "summary_level2": ["..."],
  "summary_level3": ["..."]
}}"""
    try:
        resp = get_groq().chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        data = json.loads(resp.choices[0].message.content)
        analysis = {
            "decisions": data.get("decisions") or [],
            "pending": data.get("pending") or [],
            "todos": data.get("todos") or [],
        }
        summary_3 = {
            "level1": data.get("summary_level1") or "",
            "level2": data.get("summary_level2") or [],
            "level3": data.get("summary_level3") or [],
        }
        return analysis, summary_3
    except Exception as e:
        return (
            {"decisions": [], "pending": [], "todos": [], "error": str(e)},
            {"level1": "", "level2": [], "level3": []},
        )


def render_analysis(analysis):
    if not analysis or not isinstance(analysis, dict):
        return
    for label, key in (("✅ 決定事項", "decisions"), ("⏸️ 保留事項", "pending"), ("📌 ToDo", "todos")):
        items = analysis.get(key) or []
        if items:
            st.markdown(f"**{label}**")
            for x in items:
                st.markdown(f"- {x}")


def render_three_level_summary(summary):
    if not summary:
        return
    st.markdown("**🧭 3段階要約**")
    if summary.get("level1"):
        st.info(summary["level1"])
    if summary.get("level2"):
        st.markdown("**要点**")
        for x in summary["level2"]:
            st.markdown(f"- {x}")
    if summary.get("level3"):
        st.markdown("**詳細要約（アクション中心）**")
        for x in summary["level3"]:
            st.markdown(f"- {x}")


def keyword_score(query_terms, row):
    if not query_terms:
        return 0
    hay = " ".join([
        row.get("title") or "",
        row.get("content") or "",
        row.get("tags") or "",
        " ".join((row.get("summary_3") or {}).get("level2", [])),
    ]).lower()
    return sum(hay.count(q) for q in query_terms)


LIGHT_COLS = "id,date_str,title,participants,tags,analysis,summary_3"
FULL_COLS = "id,date_str,title,participants,tags,content,embedding,analysis,summary_3,transcript_segments"


def _cache_key():
    return st.session_state.get("minutes_version", 0)


@st.cache_data(show_spinner=False)
def fetch_minutes_light(_version):
    return db.table("minutes").select(LIGHT_COLS).execute().data or []


@st.cache_data(show_spinner=False)
def fetch_minutes_full(_version):
    return db.table("minutes").select(FULL_COLS).execute().data or []


def invalidate_minutes_cache():
    st.session_state["minutes_version"] = st.session_state.get("minutes_version", 0) + 1


def search_minutes(query, n=5, date_from=None, date_to=None, tag_filter=None, rows=None):
    if rows is None:
        rows = fetch_minutes_full(_cache_key())

    if date_from:
        rows = [r for r in rows if r.get("date_str", "") >= str(date_from)]
    if date_to:
        rows = [r for r in rows if r.get("date_str", "") <= str(date_to)]
    if tag_filter:
        rows = [r for r in rows if tag_filter in (r.get("tags") or "")]

    if not rows:
        return []

    query_emb = np.asarray(model.encode(query), dtype=np.float32)
    query_norm = np.linalg.norm(query_emb) + 1e-9

    embeds, valid_rows = [], []
    for r in rows:
        emb = r.get("embedding")
        if not emb:
            continue
        embeds.append(emb)
        valid_rows.append(r)

    if not valid_rows:
        return []

    mat = np.asarray(embeds, dtype=np.float32)
    norms = np.linalg.norm(mat, axis=1) + 1e-9
    sems = (mat @ query_emb) / (norms * query_norm)

    query_terms = [q.strip().lower() for q in query.split() if q.strip()]
    scored = []
    for sem, row in zip(sems, valid_rows):
        sem_f = float(sem)
        key = keyword_score(query_terms, row)
        hybrid = sem_f * 0.7 + min(key / 10.0, 1.0) * 0.3
        scored.append((hybrid, row, sem_f, key))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:n]


def recommend_similar_meetings(target_row, rows, n=3):
    base = target_row.get("embedding")
    if not base:
        return []
    base_vec = np.asarray(base, dtype=np.float32)
    base_norm = np.linalg.norm(base_vec) + 1e-9

    others = [r for r in rows if r["id"] != target_row["id"] and r.get("embedding")]
    if not others:
        return []

    mat = np.asarray([r["embedding"] for r in others], dtype=np.float32)
    norms = np.linalg.norm(mat, axis=1) + 1e-9
    sims = (mat @ base_vec) / (norms * base_norm)

    pairs = sorted(zip(sims.tolist(), others), key=lambda x: x[0], reverse=True)
    return pairs[:n]


def answer_cross_minutes_chat(question, rows):
    top = search_minutes(question, n=5, rows=rows)
    context = []
    for score, row, _sem, _key in top:
        analysis = row.get("analysis") or {}
        context.append(
            f"- {row.get('date_str')} | {row.get('title')} | score={score:.3f}\n"
            f"  決定事項: {analysis.get('decisions', [])}\n"
            f"  保留事項: {analysis.get('pending', [])}\n"
            f"  ToDo: {analysis.get('todos', [])}\n"
            f"  本文抜粋: {(row.get('content') or '')[:400]}"
        )

    prompt = (
        "以下の議事録コンテキストだけを根拠に回答してください。"
        "不明な点は不明と明示してください。\n\n"
        f"質問: {question}\n\n"
        "コンテキスト:\n" + "\n\n".join(context)
    )
    resp = get_groq().chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    return resp.choices[0].message.content, top


def get_all_tags(rows):
    seen, tags = set(), []
    for r in rows:
        for t in (r.get("tags") or "").split(","):
            t = t.strip()
            if t and t not in seen:
                seen.add(t)
                tags.append(t)
    return tags


def get_all_dates(rows):
    return sorted({r["date_str"] for r in rows if r.get("date_str")})


st.set_page_config(page_title="議事録検索", page_icon="📋", layout="wide")
st.title("📋 議事録検索システム")

# ---- UI ----
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📝 議事録を追加",
    "🔍 検索",
    "📄 一覧",
    "📌 会議詳細",
    "💬 AI横断チャット",
])

# ---- 議事録追加 ----
with tab1:
    st.header("議事録を追加")
    fk = st.session_state.get("form_key", 0)

    col1, col2 = st.columns(2)
    with col1:
        date = st.date_input("日付", key=f"date_{fk}")
        title = st.text_input("タイトル（例：週次定例 4/20）", key=f"title_{fk}")
    with col2:
        participants = st.text_input("参加者（カンマ区切り）", key=f"participants_{fk}")

    audio_file = st.file_uploader(
        "🎙️ 音声ファイル（ローカル解析優先）",
        type=["mp3", "wav", "m4a", "mp4", "ogg", "webm"],
    )
    if audio_file and st.button("📝 文字起こしする"):
        with st.spinner("文字起こし・話者分離中..."):
            transcribed, segments = transcribe_audio(audio_file.read(), audio_file.name)
            st.session_state[f"transcribed_{fk}"] = transcribed
            st.session_state[f"segments_{fk}"] = segments
            st.rerun()

    if f"transcribed_{fk}" in st.session_state:
        st.session_state[f"content_{fk}"] = st.session_state.pop(f"transcribed_{fk}")

    content = st.text_area("議事録内容", height=300, key=f"content_{fk}")

    if "pending_tags" in st.session_state:
        st.session_state[f"tags_{fk}"] = st.session_state.pop("pending_tags")

    tag_col, btn_col = st.columns([4, 1])
    with tag_col:
        tags = st.text_input("タグ（カンマ区切り）", key=f"tags_{fk}")
    with btn_col:
        st.write("")
        st.write("")
        if st.button("🏷️ 自動生成"):
            if content:
                st.session_state["pending_tags"] = extract_tags(content)
                st.rerun()
            else:
                st.warning("先に議事録内容を入力してください")

    if st.button("💾 保存する", type="primary"):
        if title and content:
            with st.spinner("保存中（抽出/要約/埋め込み）..."):
                embedding = model.encode(content).tolist()
                analysis, summary_3 = analyze_and_summarize(content)
                db.table("minutes").insert({
                    "id": str(uuid.uuid4()),
                    "date_str": str(date),
                    "title": title,
                    "participants": participants,
                    "tags": tags,
                    "content": content,
                    "embedding": embedding,
                    "analysis": analysis,
                    "summary_3": summary_3,
                    "transcript_segments": st.session_state.get(f"segments_{fk}", []),
                }).execute()
            invalidate_minutes_cache()
            st.session_state["form_key"] = fk + 1
            st.success(f"✅ 「{title}」を保存しました")
            st.rerun()
        else:
            st.error("タイトルと内容は必須です")

# ---- 検索 ----
with tab2:
    st.header("検索（ハイブリッド: semantic + keyword）")
    query = st.text_input("🔍 検索ワード")

    light_rows = fetch_minutes_light(_cache_key())
    dates = get_all_dates(light_rows)
    date_min = datetime.strptime(dates[0], "%Y-%m-%d").date() if dates else None
    date_max = datetime.strptime(dates[-1], "%Y-%m-%d").date() if dates else None
    all_tags = get_all_tags(light_rows)

    col_a, col_b = st.columns(2)
    with col_a:
        date_from = st.date_input("日付（開始）", value=date_min, key="date_from")
    with col_b:
        date_to = st.date_input("日付（終了）", value=date_max, key="date_to")

    selected_tag = st.selectbox("タグ", options=[""] + all_tags)
    n_results = st.slider("表示件数", 1, 20, 5)

    if query:
        with st.spinner("検索中..."):
            results = search_minutes(
                query, n=n_results, date_from=date_from, date_to=date_to,
                tag_filter=selected_tag or None,
            )
        if not results:
            st.info("該当なし")
        for hybrid, row, sem, key in results:
            with st.expander(
                f"📅 {row['date_str']} | {row['title']} | hybrid={hybrid:.3f} (semantic={sem:.3f}, keyword={key})"
            ):
                st.write(f"**参加者**: {row.get('participants') or '-'}")
                st.write(f"**タグ**: {row.get('tags') or '-'}")
                render_analysis(row.get("analysis"))
                render_three_level_summary(row.get("summary_3"))
                st.markdown("---")
                st.write(row.get("content") or "")

# ---- 一覧 ----
with tab3:
    st.header("議事録一覧")
    rows = sorted(fetch_minutes_light(_cache_key()), key=lambda r: r.get("date_str", ""), reverse=True)
    st.write(f"登録件数: **{len(rows)}件**")
    for row in rows:
        with st.expander(f"📅 {row.get('date_str')} | {row.get('title')}"):
            st.write(f"**参加者**: {row.get('participants') or '-'}")
            st.write(f"**タグ**: {row.get('tags') or '-'}")
            render_analysis(row.get("analysis"))
            render_three_level_summary(row.get("summary_3"))

# ---- 会議詳細 ----
with tab4:
    st.header("会議詳細")
    rows = sorted(fetch_minutes_full(_cache_key()), key=lambda r: r.get("date_str", ""), reverse=True)
    if not rows:
        st.info("議事録がありません")
    else:
        id_to_row = {r["id"]: r for r in rows}
        labels = {r["id"]: f"{r['date_str']} | {r['title']}" for r in rows}
        selected_id = st.selectbox(
            "会議を選択", options=list(id_to_row.keys()),
            format_func=lambda rid: labels[rid],
        )
        current = id_to_row[selected_id]

        st.subheader(current.get("title", "無題"))
        st.caption(f"開催日: {current.get('date_str')} / 参加者: {current.get('participants') or '-'}")
        render_analysis(current.get("analysis"))
        render_three_level_summary(current.get("summary_3"))

        st.markdown("**🎙️ タイムスタンプ付き文字起こし**")
        segments = current.get("transcript_segments") or []
        if segments:
            for seg in segments:
                sec = int(seg.get("start", 0))
                st.markdown(
                    f"- [[{mmss(sec)}] {seg.get('speaker', '話者')}: {seg.get('text', '')}]"
                    f"(?meeting_id={current['id']}&t={sec})"
                )
        else:
            st.write("セグメントなし")

        st.markdown("**📚 類似会議レコメンド**")
        recs = recommend_similar_meetings(current, rows, n=3)
        if recs:
            for sim, row in recs:
                st.markdown(f"- {row.get('date_str')} | {row.get('title')} (類似度: {sim:.2f})")
        else:
            st.write("類似候補なし")

# ---- AI横断チャット ----
with tab5:
    st.header("AIチャット（全議事録横断質問）")
    q = st.text_input("質問", placeholder="例: 認証基盤の決定事項と未解決課題を横断で教えて")
    if st.button("回答を生成") and q:
        rows = fetch_minutes_full(_cache_key())
        with st.spinner("回答生成中..."):
            answer, refs = answer_cross_minutes_chat(q, rows)
        st.markdown("### 回答")
        st.write(answer)
        st.markdown("### 参照会議")
        for score, row, _sem, _key in refs:
            st.markdown(f"- {row.get('date_str')} | {row.get('title')} (score={score:.3f})")
