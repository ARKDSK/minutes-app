import streamlit as st
from supabase import create_client
from sentence_transformers import SentenceTransformer
from janome.tokenizer import Tokenizer
from collections import Counter
from datetime import datetime
import numpy as np
import uuid

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

@st.cache_resource
def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

@st.cache_resource
def get_model():
    return SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

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

def cosine_sim(a, b):
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))

def search_minutes(query, n=5, date_from=None, date_to=None, tag_filter=None):
    query_emb = model.encode(query).tolist()
    rows = db.table("minutes").select("*").execute().data
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
            with st.spinner("保存中..."):
                embedding = model.encode(content).tolist()
                db.table("minutes").insert({
                    "id": str(uuid.uuid4()),
                    "date_str": str(date),
                    "title": title,
                    "participants": participants,
                    "tags": tags,
                    "content": content,
                    "embedding": embedding
                }).execute()
            st.session_state["form_key"] = fk + 1
            st.success(f"✅ 「{title}」を保存しました！")
            st.rerun()
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
                        st.markdown("---")
                        st.write(row["content"])
            else:
                st.info("該当する議事録が見つかりませんでした")

# ---- 一覧 ----
with tab3:
    st.header("議事録一覧")
    rows = db.table("minutes").select("id,date_str,title,participants,tags,content").execute().data
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
                        with st.spinner("保存中..."):
                            embedding = model.encode(e_content).tolist()
                            db.table("minutes").update({
                                "date_str": str(e_date),
                                "title": e_title,
                                "participants": e_participants,
                                "tags": e_tags,
                                "content": e_content,
                                "embedding": embedding
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
