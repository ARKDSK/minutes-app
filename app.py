import streamlit as st
from supabase import create_client
from sentence_transformers import SentenceTransformer
from groq import Groq
from janome.tokenizer import Tokenizer
from collections import Counter
from datetime import datetime
import numpy as np
import uuid
import tempfile
import os
import json
import time

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
APP_PASSWORD = st.secrets["APP_PASSWORD"]
GROQ_API_KEY = st.secrets["GROQ_API_KEY"]

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

def transcribe_audio(file_bytes, filename):
    client = Groq(api_key=GROQ_API_KEY)
    transcription = client.audio.transcriptions.create(
        file=(filename, file_bytes),
        model="whisper-large-v3-turbo",
        language="ja"
    )
    return transcription.text

db = get_supabase()
model = get_model()

# タグ自動生成
_tokenizer = None
def extract_tags(text, top_n=5):
    global _tokenizer
    if _tokenizer is None:
        _tokenizer = Tokenizer()
    stop_words = {
        "こと", "もの", "ため", "これ", "それ", "あれ", "ここ", "そこ", "あそこ",
        "よう", "とき", "場合", "必要", "確認", "対応", "実施", "検討", "予定",
        "議事録", "会議", "本日", "今回", "資料", "内容", "方針", "方向", "状況",
        "以下", "以上", "関連", "今後", "共有", "報告", "説明", "依頼"
    }
    nouns = []
    for token in _tokenizer.tokenize(text):
        part = token.part_of_speech.split(",")[0]
        sub = token.part_of_speech.split(",")[1]
        surface = token.surface
        if part == "名詞" and sub not in ("数", "接尾", "非自立") and len(surface) >= 2:
            if surface not in stop_words:
                nouns.append(surface)
    counts = Counter(nouns)
    return ", ".join([w for w, _ in counts.most_common(top_n)])

# 議事録から決定事項・保留事項・ToDoを抽出
def _extract_one(text):
    client = Groq(api_key=GROQ_API_KEY)
    system_prompt = """あなたは熟練した議事録要約者です。社内共有でそのまま使える実務的な要約を作成します。

【要約ルール】
- 文字起こし特有の言いよどみ、重複、脱線、相づち、言い直しは省いて整理する
- 明らかな誤変換・誤認識は、文脈上ほぼ確実な場合のみ自然な表現に補正する
- 補正に確信が持てない固有名詞・専門用語は無理に直さず、そのまま残すか「要確認」と明記する
- 発言内容を勝手に補完・推測しない
- 「決定したこと」と「まだ議論中のこと」を必ず分ける
- 自然で実務にそのまま使える日本語でまとめる
- AIっぽい不自然な表現は避ける
- 冗長にせず、ただし情報不足にならないように整理する
- 同じ内容が繰り返し出てくる場合は一つに統合する
- 会議全体の背景や意図が分かる場合は、短く補足してよい
- 出力は必ず指定したJSONフォーマットのみ（説明文・前置き・コードブロックは一切不要）"""
    user_prompt = f"""以下は会議の文字起こしです。この内容をもとに、社内共有でそのまま使える実務的な要約を作成してください。

【出力項目】
- overview: 会議概要（この会議が何についての会議だったかを2〜4文で要約）
- key_points: 要点整理（論点ごとの箇条書き。重要な背景や方針転換があれば明記）
- decisions: 決定事項（この会議で確定した内容のみ。決まっていない内容は含めない。ない場合は空配列）
- concerns: 課題・懸念点（未整理の論点、今後詰める必要がある点、運用上の不安や説明不足など）
- todos: 今後のアクション（やるべきことの箇条書き。発言内に担当者・期限があれば反映し、不明なら「担当未定」「期限未定」と記載）
- unconfirmed: 未確定事項（方針は出ているがまだ確定していないこと）
- oneliner: 一言まとめ（会議全体を1〜2文で簡潔に）

【文字起こし】
-----
{text}
-----

【出力JSONフォーマット】
{{"overview": "...", "key_points": ["..."], "decisions": ["..."], "concerns": ["..."], "todos": ["..."], "unconfirmed": ["..."], "oneliner": "..."}}"""
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
    )
    data = json.loads(resp.choices[0].message.content)
    return {
        "overview": data.get("overview", "") or "",
        "key_points": data.get("key_points", []) or [],
        "decisions": data.get("decisions", []) or [],
        "concerns": data.get("concerns", []) or [],
        "todos": data.get("todos", []) or [],
        "unconfirmed": data.get("unconfirmed", []) or [],
        "oneliner": data.get("oneliner", "") or "",
    }

def extract_analysis(text):
    # Groq無料枠TPM 6000 を踏まえ、1チャンクあたり約2000文字（≒3000-4000トークン）まで
    MAX_CHARS = 2000
    try:
        if len(text) <= MAX_CHARS:
            return _extract_one(text)
        # 長文：分割→抽出→マージ
        chunks = [text[i:i+MAX_CHARS] for i in range(0, len(text), MAX_CHARS)]
        merged = {"overview": "", "key_points": [], "decisions": [], "concerns": [],
                  "todos": [], "unconfirmed": [], "oneliner": ""}
        overviews = []
        oneliners = []
        progress = st.progress(0.0, text=f"長文のため{len(chunks)}分割で抽出中...")
        for idx, ch in enumerate(chunks):
            if idx > 0:
                time.sleep(12)  # TPM制限対策
            part = _extract_one(ch)
            if part.get("overview"):
                overviews.append(part["overview"])
            if part.get("oneliner"):
                oneliners.append(part["oneliner"])
            merged["key_points"].extend(part.get("key_points", []))
            merged["decisions"].extend(part.get("decisions", []))
            merged["concerns"].extend(part.get("concerns", []))
            merged["todos"].extend(part.get("todos", []))
            merged["unconfirmed"].extend(part.get("unconfirmed", []))
            progress.progress((idx + 1) / len(chunks), text=f"抽出中 {idx+1}/{len(chunks)}")
        progress.empty()
        # 重複削除（順序保持）
        for k in ("key_points", "decisions", "concerns", "todos", "unconfirmed"):
            merged[k] = list(dict.fromkeys(merged[k]))
        # 最終統合パス：overview/oneliner を一本化
        try:
            time.sleep(12)
            client = Groq(api_key=GROQ_API_KEY)
            final = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "複数の部分要約を統合し、重複を排除して自然な日本語に再構成してください。原文コピーは禁止。JSONのみ返答。"},
                    {"role": "user", "content": f"""次は同じ会議を分割して要約したものです。会議概要と一言まとめを統合してください。

【会議概要群】
{chr(10).join(overviews)}

【一言まとめ群】
{chr(10).join(oneliners)}

【出力】
{{"overview": "2〜4文の会議概要", "oneliner": "1〜2文の総括"}}"""}
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            fin = json.loads(final.choices[0].message.content)
            merged["overview"] = fin.get("overview", "") or (overviews[0] if overviews else "")
            merged["oneliner"] = fin.get("oneliner", "") or (oneliners[0] if oneliners else "")
        except Exception:
            merged["overview"] = overviews[0] if overviews else ""
            merged["oneliner"] = oneliners[0] if oneliners else ""
        return merged
    except Exception as e:
        return {"overview": "", "key_points": [], "decisions": [], "concerns": [],
                "todos": [], "unconfirmed": [], "oneliner": "", "error": str(e)}

def analysis_to_text(analysis):
    """要約データをコピペしやすいプレーンテキスト形式に整形"""
    if not analysis or not isinstance(analysis, dict):
        return ""
    lines = []
    # 旧形式
    if "summary_short" in analysis or "summary_long" in analysis or "pending" in analysis:
        if analysis.get("summary_short"):
            lines.append(f"【一言要約】\n{analysis['summary_short']}\n")
        if analysis.get("summary_long"):
            lines.append(f"【詳細要約】\n{analysis['summary_long']}\n")
        if analysis.get("decisions"):
            lines.append("【決定事項】")
            lines += [f"・{x}" for x in analysis["decisions"]]
            lines.append("")
        if analysis.get("pending"):
            lines.append("【保留事項】")
            lines += [f"・{x}" for x in analysis["pending"]]
            lines.append("")
        if analysis.get("todos"):
            lines.append("【ToDo】")
            lines += [f"・{x}" for x in analysis["todos"]]
        return "\n".join(lines).strip()
    # 新形式
    if analysis.get("oneliner"):
        lines.append(f"【一言まとめ】\n{analysis['oneliner']}\n")
    if analysis.get("overview"):
        lines.append(f"【会議概要】\n{analysis['overview']}\n")
    if analysis.get("key_points"):
        lines.append("【要点整理】")
        lines += [f"・{x}" for x in analysis["key_points"]]
        lines.append("")
    lines.append("【決定事項】")
    if analysis.get("decisions"):
        lines += [f"・{x}" for x in analysis["decisions"]]
    else:
        lines.append("・今回確定した決定事項は限定的")
    lines.append("")
    if analysis.get("concerns"):
        lines.append("【課題・懸念点】")
        lines += [f"・{x}" for x in analysis["concerns"]]
        lines.append("")
    if analysis.get("todos"):
        lines.append("【今後のアクション（ToDo）】")
        lines += [f"・{x}" for x in analysis["todos"]]
        lines.append("")
    if analysis.get("unconfirmed"):
        lines.append("【未確定事項】")
        lines += [f"・{x}" for x in analysis["unconfirmed"]]
    return "\n".join(lines).strip()

def render_analysis(analysis, copy_key=None):
    if not analysis or not isinstance(analysis, dict):
        return
    # 旧形式（summary_short/summary_long/pending）の互換表示
    legacy = "summary_short" in analysis or "summary_long" in analysis or "pending" in analysis
    if legacy:
        if analysis.get("summary_short"):
            st.info(f"📝 {analysis['summary_short']}")
        if analysis.get("summary_long"):
            with st.expander("詳細要約を表示"):
                st.write(analysis["summary_long"])
        if analysis.get("decisions"):
            st.markdown("**✅ 決定事項**")
            for x in analysis["decisions"]:
                st.markdown(f"- {x}")
        if analysis.get("pending"):
            st.markdown("**⏸️ 保留事項**")
            for x in analysis["pending"]:
                st.markdown(f"- {x}")
        if analysis.get("todos"):
            st.markdown("**📌 ToDo**")
            for x in analysis["todos"]:
                st.markdown(f"- {x}")
        copy_text = analysis_to_text(analysis)
        if copy_text:
            with st.expander("📋 要約をコピー（右上のアイコンをクリック）"):
                st.code(copy_text, language=None)
        return

    overview = analysis.get("overview") or ""
    key_points = analysis.get("key_points") or []
    decisions = analysis.get("decisions") or []
    concerns = analysis.get("concerns") or []
    todos = analysis.get("todos") or []
    unconfirmed = analysis.get("unconfirmed") or []
    oneliner = analysis.get("oneliner") or ""

    if not any([overview, key_points, decisions, concerns, todos, unconfirmed, oneliner]):
        return

    if oneliner:
        st.info(f"📝 {oneliner}")
    if overview:
        st.markdown("**🗂️ 会議概要**")
        st.write(overview)
    if key_points:
        st.markdown("**📌 要点整理**")
        for x in key_points:
            st.markdown(f"- {x}")
    if decisions:
        st.markdown("**✅ 決定事項**")
        for x in decisions:
            st.markdown(f"- {x}")
    else:
        st.markdown("**✅ 決定事項**")
        st.caption("今回確定した決定事項は限定的")
    if concerns:
        st.markdown("**⚠️ 課題・懸念点**")
        for x in concerns:
            st.markdown(f"- {x}")
    if todos:
        st.markdown("**🚀 今後のアクション（ToDo）**")
        for x in todos:
            st.markdown(f"- {x}")
    if unconfirmed:
        st.markdown("**⏸️ 未確定事項**")
        for x in unconfirmed:
            st.markdown(f"- {x}")

    # コピー用テキスト（右上のアイコンでクリップボードに一発コピー可能）
    copy_text = analysis_to_text(analysis)
    if copy_text:
        with st.expander("📋 要約をコピー（右上のアイコンをクリック）"):
            st.code(copy_text, language=None)

def cosine_sim(a, b):
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))

def search_minutes(query, n=5, date_from=None, date_to=None, tag_filter=None):
    query_emb = model.encode(query).tolist()
    rows = db.table("minutes").select("id,date_str,title,participants,tags,content,embedding,analysis").execute().data
    if date_from:
        rows = [r for r in rows if r.get("date_str", "") >= str(date_from)]
    if date_to:
        rows = [r for r in rows if r.get("date_str", "") <= str(date_to)]
    if tag_filter:
        rows = [r for r in rows if tag_filter in (r.get("tags") or "")]
    scored = sorted(
        [(cosine_sim(query_emb, r["embedding"]), r) for r in rows],
        reverse=True
    )
    return scored[:n]

def get_all_tags():
    rows = db.table("minutes").select("tags").execute().data
    tags = []
    for r in rows:
        for t in (r.get("tags") or "").split(","):
            t = t.strip()
            if t and t not in tags:
                tags.append(t)
    return tags

def get_all_dates():
    rows = db.table("minutes").select("date_str").execute().data
    dates = sorted([r["date_str"] for r in rows if r.get("date_str")])
    return dates

# ---- UI ----
st.set_page_config(page_title="議事録検索", page_icon="📋", layout="wide")
st.title("📋 議事録検索システム")

tab1, tab2, tab3 = st.tabs(["📝 議事録を追加", "🔍 検索", "📄 一覧"])

# ---- 議事録を追加 ----
with tab1:
    st.header("議事録を追加")
    fk = st.session_state.get("form_key", 0)

    col1, col2 = st.columns(2)
    with col1:
        date = st.date_input("日付", key=f"date_{fk}")
        title = st.text_input("タイトル（例：週次定例 4/20）", key=f"title_{fk}")
    with col2:
        participants = st.text_input("参加者（カンマ区切り）", key=f"participants_{fk}")

    # 音声ファイルから文字起こし
    audio_file = st.file_uploader("🎙️ 音声ファイルから文字起こし（任意）",
        type=["mp3", "wav", "m4a", "mp4", "ogg", "webm"])
    if audio_file:
        size_mb = audio_file.size / (1024 * 1024)
        st.caption(f"ファイルサイズ: {size_mb:.1f} MB")
        if st.button("📝 文字起こしする"):
            try:
                with st.spinner("文字起こし中..."):
                    transcribed = transcribe_audio(audio_file.read(), audio_file.name)
                    st.session_state[f"transcribed_{fk}"] = transcribed
                    st.rerun()
            except Exception as e:
                st.error(f"文字起こしエラー: {type(e).__name__}: {e}")
                st.error(f"詳細: {getattr(e, 'message', '')} / {getattr(e, 'status_code', '')} / {getattr(e, 'body', '')}")

    # 文字起こし結果があれば content に反映
    if f"transcribed_{fk}" in st.session_state:
        st.session_state[f"content_{fk}"] = st.session_state.pop(f"transcribed_{fk}")

    content = st.text_area("議事録内容", height=300,
        placeholder="ここに議事録の内容を貼り付けてください...", key=f"content_{fk}")

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
                with st.spinner("タグを生成中..."):
                    st.session_state["pending_tags"] = extract_tags(content)
                st.rerun()
            else:
                st.warning("先に議事録内容を入力してください")

    if st.button("💾 保存する", type="primary"):
        if title and content:
            try:
                with st.spinner("保存中（要点を抽出しています）..."):
                    embedding = model.encode(content).tolist()
                    analysis = extract_analysis(content)
                    db.table("minutes").insert({
                        "id": str(uuid.uuid4()),
                        "date_str": str(date),
                        "title": title,
                        "participants": participants,
                        "tags": tags,
                        "content": content,
                        "embedding": embedding,
                        "analysis": analysis
                    }).execute()
                st.session_state["form_key"] = fk + 1
                st.success(f"✅ 「{title}」を保存しました！")
                st.rerun()
            except Exception as e:
                st.error(f"保存エラー: {type(e).__name__}: {e}")
                st.error(f"詳細: {getattr(e, 'message', '')} / {getattr(e, 'code', '')} / {getattr(e, 'details', '')}")
        else:
            st.error("タイトルと内容は必須です")

# ---- 検索 ----
with tab2:
    st.header("検索")
    query = st.text_input("🔍 検索ワードを入力",
        placeholder="例：認証の実装方法、APIのエラー対応、インフラ構成...")

    all_dates = get_all_dates()
    date_min = datetime.strptime(all_dates[0], "%Y-%m-%d").date() if all_dates else None
    date_max = datetime.strptime(all_dates[-1], "%Y-%m-%d").date() if all_dates else None
    all_tags = get_all_tags()

    col_a, col_b = st.columns(2)
    with col_a:
        date_from = st.date_input("日付（開始）", value=date_min, key="date_from")
    with col_b:
        date_to = st.date_input("日付（終了）", value=date_max, key="date_to")

    if all_tags:
        st.write("**タグで絞り込む:**")
        selected_tag = st.session_state.get("selected_tag", "")
        cols = st.columns(min(len(all_tags), 6))
        for i, tag in enumerate(all_tags):
            with cols[i % 6]:
                label = f"✅ {tag}" if tag == selected_tag else tag
                if st.button(label, key=f"tag_{tag}"):
                    st.session_state["selected_tag"] = "" if selected_tag == tag else tag
                    st.rerun()
        selected_tag = st.session_state.get("selected_tag", "")
        if selected_tag:
            st.caption(f"タグ「{selected_tag}」で絞り込み中　[同じタグをクリックで解除]")

    n_results = st.slider("表示件数", 1, 20, 5)

    if query or st.session_state.get("selected_tag"):
        effective_query = query or st.session_state.get("selected_tag", "")
        total = len(db.table("minutes").select("id").execute().data)
        if total == 0:
            st.info("まだ議事録が登録されていません")
        else:
            results = search_minutes(
                effective_query, n=n_results,
                date_from=date_from, date_to=date_to,
                tag_filter=st.session_state.get("selected_tag")
            )
            if results:
                st.write(f"**{len(results)}件** が見つかりました")
                for sim, row in results:
                    relevance = max(0, int(sim * 100))
                    with st.expander(f"📅 {row['date_str']}  |  {row['title']}  |  関連度: {relevance}%"):
                        if row.get("participants"):
                            st.write(f"**参加者**: {row['participants']}")
                        if row.get("tags"):
                            st.write(f"**タグ**: {row['tags']}")
                        render_analysis(row.get("analysis"))
                        st.markdown("---")
                        st.write(row["content"])
            else:
                st.info("該当する議事録が見つかりませんでした")

# ---- 一覧 ----
with tab3:
    st.header("議事録一覧")
    rows = db.table("minutes").select("id,date_str,title,participants,tags,content,analysis").execute().data
    rows = sorted(rows, key=lambda r: r.get("date_str", ""), reverse=True)
    st.write(f"登録件数: **{len(rows)}件**")

    for row in rows:
        doc_id = row["id"]
        with st.expander(f"📅 {row.get('date_str', '不明')}  |  {row.get('title', '無題')}"):
            editing = st.session_state.get(f"editing_{doc_id}", False)

            if editing:
                e_date = st.date_input("日付",
                    value=datetime.strptime(row["date_str"], "%Y-%m-%d").date(),
                    key=f"e_date_{doc_id}")
                e_title = st.text_input("タイトル", value=row.get("title", ""), key=f"e_title_{doc_id}")
                e_participants = st.text_input("参加者", value=row.get("participants", ""), key=f"e_part_{doc_id}")

                if f"pending_tags_{doc_id}" in st.session_state:
                    st.session_state[f"e_tags_{doc_id}"] = st.session_state.pop(f"pending_tags_{doc_id}")

                e_tag_col, e_btn_col = st.columns([4, 1])
                with e_tag_col:
                    e_tags = st.text_input("タグ", key=f"e_tags_{doc_id}")
                with e_btn_col:
                    st.write("")
                    st.write("")
                    if st.button("🏷️ 自動生成", key=f"e_autotag_{doc_id}"):
                        e_content_for_tag = st.session_state.get(f"e_content_{doc_id}", row["content"])
                        if e_content_for_tag:
                            with st.spinner("生成中..."):
                                st.session_state[f"pending_tags_{doc_id}"] = extract_tags(e_content_for_tag)
                            st.rerun()

                e_content = st.text_area("議事録内容", value=row["content"], height=300, key=f"e_content_{doc_id}")

                save_col, cancel_col = st.columns(2)
                with save_col:
                    if st.button("💾 保存", type="primary", key=f"save_{doc_id}"):
                        with st.spinner("保存中（要点を抽出しています）..."):
                            embedding = model.encode(e_content).tolist()
                            analysis = extract_analysis(e_content)
                            db.table("minutes").update({
                                "date_str": str(e_date),
                                "title": e_title,
                                "participants": e_participants,
                                "tags": e_tags,
                                "content": e_content,
                                "embedding": embedding,
                                "analysis": analysis
                            }).eq("id", doc_id).execute()
                        st.session_state[f"editing_{doc_id}"] = False
                        st.session_state.pop(f"pending_tags_{doc_id}", None)
                        st.rerun()
                with cancel_col:
                    if st.button("キャンセル", key=f"cancel_{doc_id}"):
                        st.session_state[f"editing_{doc_id}"] = False
                        st.rerun()
            else:
                if row.get("participants"):
                    st.write(f"**参加者**: {row['participants']}")
                if row.get("tags"):
                    st.write(f"**タグ**: {row['tags']}")
                render_analysis(row.get("analysis"))
                st.markdown("---")
                st.write(row["content"])

                edit_col, del_col = st.columns(2)
                with edit_col:
                    if st.button("✏️ 編集", key=f"edit_{doc_id}"):
                        st.session_state[f"editing_{doc_id}"] = True
                        st.rerun()
                with del_col:
                    if st.button("🗑️ 削除", key=f"del_{doc_id}"):
                        db.table("minutes").delete().eq("id", doc_id).execute()
                        st.rerun()
