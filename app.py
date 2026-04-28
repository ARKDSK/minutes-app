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
import csv
from io import StringIO

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
def extract_analysis(text):
    client = Groq(api_key=GROQ_API_KEY)
    prompt = f"""以下の議事録から「決定事項」「保留事項」「ToDo」を抽出してください。
各項目は短い箇条書き（1項目20〜60文字程度）にしてください。
該当が無い場合は空配列にしてください。
JSON形式のみで返答し、説明文は一切含めないでください。

議事録:
{text}

出力フォーマット:
{{"decisions": ["..."], "pending": ["..."], "todos": ["..."]}}"""
    try:
        resp = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        data = json.loads(resp.choices[0].message.content)
        return {
            "decisions": data.get("decisions", []) or [],
            "pending": data.get("pending", []) or [],
            "todos": data.get("todos", []) or [],
        }
    except Exception as e:
        return {"decisions": [], "pending": [], "todos": [], "error": str(e)}

def render_analysis(analysis):
    if not analysis or not isinstance(analysis, dict):
        return
    decisions = analysis.get("decisions") or []
    pending = analysis.get("pending") or []
    todos = analysis.get("todos") or []
    if not (decisions or pending or todos):
        return
    if decisions:
        st.markdown("**✅ 決定事項**")
        for x in decisions:
            st.markdown(f"- {x}")
    if pending:
        st.markdown("**⏸️ 保留事項**")
        for x in pending:
            st.markdown(f"- {x}")
    if todos:
        st.markdown("**📌 ToDo**")
        for x in todos:
            st.markdown(f"- {x}")



REQUIRED_COMPANY_FIELDS = [
    "tdb_company_code",
    "corporate_number",
    "company_name",
    "company_name_kana",
    "postal_code",
    "address",
    "prefecture",
    "city",
    "phone_number",
    "website_url",
    "industry_code_main",
    "industry_name_main",
    "industry_code_sub",
    "industry_name_sub",
    "business_description",
    "founded_date",
    "established_date",
    "capital_amount",
    "employee_count",
    "last_updated_at",
]


def to_float(val):
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s:
        return None
    for token in [",", "円", "人", "百万円", "千円", "%"]:
        s = s.replace(token, "")
    try:
        return float(s)
    except Exception:
        return None


def to_int(val):
    x = to_float(val)
    return int(x) if x is not None else None


def parse_company_dataset(uploaded_file):
    if not uploaded_file:
        return []
    raw = uploaded_file.read()
    name = uploaded_file.name.lower()

    if name.endswith(".json"):
        data = json.loads(raw.decode("utf-8", errors="ignore"))
        if isinstance(data, dict):
            data = [data]
        return [dict(r) for r in data if isinstance(r, dict)]

    text = raw.decode("utf-8", errors="ignore")
    delimiter = "\t" if name.endswith(".tsv") else ","
    reader = csv.DictReader(StringIO(text), delimiter=delimiter)
    return [dict(row) for row in reader]


def estimate_succession_score(row):
    score = 0
    reasons = []

    rep_age = to_int(row.get("representative_age"))
    if rep_age is not None and rep_age >= 60:
        score += 35
        reasons.append(f"代表者年齢が高め（{rep_age}歳）")

    successor_flag = str(row.get("successor_exists", "")).strip().lower()
    if successor_flag in {"0", "false", "なし", "no"}:
        score += 35
        reasons.append("後継者不在")

    employee_count = to_int(row.get("employee_count"))
    if employee_count is not None and employee_count <= 100:
        score += 10
        reasons.append("中小規模で承継ニーズが高い可能性")

    years = to_int(row.get("business_years"))
    if years is not None and years >= 20:
        score += 20
        reasons.append("事業歴が長く承継タイミングの可能性")

    return min(score, 100), reasons


def estimate_financial_risk_score(row):
    # 0=低リスク, 100=高リスク
    risk = 30
    reasons = []

    tdb_score = to_int(row.get("tdb_score") or row.get("credit_score") or row.get("評点"))
    if tdb_score is not None:
        if tdb_score < 45:
            risk += 35
            reasons.append(f"評点が低い（{tdb_score}）")
        elif tdb_score < 55:
            risk += 15
            reasons.append(f"評点が中位（{tdb_score}）")
        else:
            risk -= 10
            reasons.append(f"評点が相対的に安定（{tdb_score}）")

    operating_profit = to_float(row.get("operating_profit"))
    if operating_profit is not None and operating_profit < 0:
        risk += 25
        reasons.append("営業赤字")

    debt = to_float(row.get("interest_bearing_debt"))
    cash = to_float(row.get("cash_and_deposits"))
    if debt is not None and cash is not None and debt > cash * 2:
        risk += 20
        reasons.append("有利子負債が現預金を大きく超過")

    return min(max(risk, 0), 100), reasons


def classify_risk(risk_score):
    if risk_score >= 70:
        return "高"
    if risk_score >= 45:
        return "中"
    return "低"


def estimate_priority_score(row, succession_score, risk_score):
    # 0-100 (高いほど優先アプローチ)
    score = 40
    reasons = []

    sales = to_float(row.get("sales") or row.get("売上高"))
    if sales is not None:
        if 300 <= sales <= 5000:
            score += 20
            reasons.append("売上規模が初期買収対象に適合")
        elif sales < 100:
            score -= 10
            reasons.append("売上規模が小さめ")

    employee_count = to_int(row.get("employee_count"))
    if employee_count is not None and 20 <= employee_count <= 300:
        score += 10
        reasons.append("PMI負荷が比較的コントロールしやすい人員規模")

    score += int(succession_score * 0.25)
    score -= int(risk_score * 0.20)

    if risk_score >= 75:
        score -= 15
        reasons.append("財務・信用リスクが高く優先度調整")

    return min(max(score, 0), 100), reasons


def propose_next_actions(priority_score, risk_level, succession_score):
    actions = []
    if priority_score >= 70:
        actions.append("1週間以内にアプローチ候補として担当者を割当")
        actions.append("NDA打診前提で初回面談仮説を作成")
    elif priority_score >= 50:
        actions.append("追加情報取得（CCR詳細、決算、銀行取引情報）")
    else:
        actions.append("四半期ウォッチリストに登録し再評価")

    if succession_score >= 60:
        actions.append("事業承継ニーズ確認のため代表者ヒアリング項目を準備")

    if risk_level == "高":
        actions.append("先行して財務DD（資金繰り・債務）論点を精査")
    elif risk_level == "中":
        actions.append("簡易財務レビューと税務論点の棚卸しを実施")
    else:
        actions.append("事業シナジー仮説とPMI初期計画を先行検討")
    return actions


def evaluate_ma_candidates(rows):
    evaluated = []
    for row in rows:
        succession_score, succession_reasons = estimate_succession_score(row)
        financial_risk, risk_reasons = estimate_financial_risk_score(row)
        priority_score, priority_reasons = estimate_priority_score(row, succession_score, financial_risk)
        risk_level = classify_risk(financial_risk)

        is_candidate = priority_score >= 50 or succession_score >= 60
        evaluated.append({
            **row,
            "company_name": row.get("company_name") or row.get("商号") or "不明",
            "succession_score": succession_score,
            "financial_risk_score": financial_risk,
            "financial_risk_level": risk_level,
            "priority_score": priority_score,
            "is_candidate": is_candidate,
            "candidate_reason": " / ".join((succession_reasons + priority_reasons)[:3]) or "情報不足",
            "risk_reason": " / ".join(risk_reasons[:3]) or "情報不足",
            "next_actions": propose_next_actions(priority_score, risk_level, succession_score),
        })

    evaluated = sorted(evaluated, key=lambda x: x["priority_score"], reverse=True)
    return evaluated


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

tab1, tab2, tab3, tab4 = st.tabs(["📝 議事録を追加", "🔍 検索", "📄 一覧", "🏢 買収分析"])

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
        if st.button("📝 文字起こしする"):
            with st.spinner("文字起こし中..."):
                transcribed = transcribe_audio(audio_file.read(), audio_file.name)
                st.session_state[f"transcribed_{fk}"] = transcribed
                st.rerun()

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


# ---- 買収分析 ----
with tab4:
    st.header("M&A候補抽出・評価（帝国データ向け）")
    st.caption("候補抽出・事業承継判定・リスク判定・優先順位算出・次アクション提示を実行します。")

    st.markdown("**保存・表示する企業基本情報（推奨カラム）**")
    st.code("\n".join(REQUIRED_COMPANY_FIELDS), language="text")

    uploaded = st.file_uploader(
        "企業一覧データをアップロード（CSV / TSV / JSON）",
        type=["csv", "tsv", "json"],
        key="ma_company_dataset"
    )

    if st.button("📊 候補抽出と評価を実行", type="primary"):
        if uploaded is None:
            st.warning("先に企業一覧ファイルをアップロードしてください。")
        else:
            try:
                rows = parse_company_dataset(uploaded)
            except Exception as e:
                st.error(f"ファイル読み込みエラー: {e}")
                rows = []

            if not rows:
                st.warning("データを読み取れませんでした。ヘッダー行やJSON構造を確認してください。")
            else:
                evaluated = evaluate_ma_candidates(rows)
                candidates = [r for r in evaluated if r["is_candidate"]]
                missings = [f for f in REQUIRED_COMPANY_FIELDS if f not in rows[0].keys()]

                c1, c2, c3 = st.columns(3)
                c1.metric("総企業数", len(evaluated))
                c2.metric("買収候補数", len(candidates))
                c3.metric("候補比率", f"{(len(candidates)/len(evaluated))*100:.1f}%")

                if missings:
                    st.warning("推奨カラム不足: " + ", ".join(missings))

                st.subheader("候補企業ランキング")
                ranking = [{
                    "company_name": r["company_name"],
                    "priority_score": r["priority_score"],
                    "succession_score": r["succession_score"],
                    "financial_risk_score": r["financial_risk_score"],
                    "financial_risk_level": r["financial_risk_level"],
                    "industry_name_main": r.get("industry_name_main", ""),
                    "prefecture": r.get("prefecture", ""),
                    "candidate_reason": r["candidate_reason"],
                } for r in evaluated[:100]]
                st.dataframe(ranking, use_container_width=True)

                st.subheader("候補企業の詳細アクション")
                for idx, r in enumerate(candidates[:20], start=1):
                    with st.expander(f"{idx}. {r['company_name']}（優先度: {r['priority_score']}）"):
                        st.write(f"**事業承継候補スコア**: {r['succession_score']}")
                        st.write(f"**財務・信用リスク**: {r['financial_risk_score']}（{r['financial_risk_level']}）")
                        st.write(f"**候補理由**: {r['candidate_reason']}")
                        st.write(f"**リスク要約**: {r['risk_reason']}")
                        st.markdown("**次アクション**")
                        for action in r["next_actions"]:
                            st.markdown(f"- {action}")

                st.download_button(
                    "評価結果JSONをダウンロード",
                    data=json.dumps(evaluated, ensure_ascii=False, indent=2),
                    file_name="ma_candidate_evaluation.json",
                    mime="application/json"
                )
