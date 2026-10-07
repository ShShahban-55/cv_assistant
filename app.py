import hashlib
import html
import json
import re

import streamlit as st
from huggingface_hub import InferenceClient
from pypdf import PdfReader

st.set_page_config(page_title="CV Assistant", page_icon="✨", layout="centered",
                   initial_sidebar_state="collapsed")

MODEL_NAME = st.secrets.get("MODEL_NAME", "meta-llama/Llama-3.1-8B-Instruct")
client = InferenceClient(model=MODEL_NAME, token=st.secrets["HF_TOKEN"])

CSS = """
<style>
[data-testid="stSidebar"], [data-testid="collapsedControl"], [data-testid="stSidebarCollapsedControl"] {display: none;}
#MainMenu, footer {visibility: hidden;}
header[data-testid="stHeader"] {background: transparent;}
.stApp {background: radial-gradient(circle at 20% 5%, #312e81 0%, #0f172a 42%, #020617 100%);}
.block-container {padding-top: 1.5rem; max-width: 760px;}

@keyframes flow {0%{background-position:0% 50%} 50%{background-position:100% 50%} 100%{background-position:0% 50%}}
@keyframes float {0%,100%{transform:translateY(0)} 50%{transform:translateY(-6px)}}

.hero {text-align: center; padding: 34px 20px 26px; border-radius: 26px; margin-bottom: 20px; color: white;
  background: linear-gradient(120deg, #6366f1, #8b5cf6, #ec4899, #f59e0b, #6366f1);
  background-size: 300% 300%; animation: flow 10s ease infinite;
  box-shadow: 0 14px 50px rgba(139,92,246,.4);}
.hero .logo {font-size: 2.6rem; display: inline-block; animation: float 3s ease-in-out infinite;}
.hero h1 {margin: 4px 0 0; font-size: 2.1rem; color: white; padding: 0; letter-spacing: .5px;}
.hero p {margin: 8px 0 0; opacity: .95; font-size: 1rem;}

.steps {display: flex; justify-content: center; gap: 10px; margin-bottom: 14px; flex-wrap: wrap;}
.step {padding: 6px 14px; border-radius: 999px; font-size: .82rem; color: #c7d2fe;
  background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.12);}
.step.on {background: linear-gradient(90deg,#6366f1,#ec4899); color: white; border-color: transparent;}

[data-testid="stFileUploaderDropzone"] {border: 2px dashed #8b5cf6; border-radius: 22px; padding: 34px 20px;
  background: linear-gradient(145deg, rgba(99,102,241,.16), rgba(236,72,153,.10));
  transition: all .25s;}
[data-testid="stFileUploaderDropzone"]:hover {border-color: #ec4899; transform: translateY(-2px);
  box-shadow: 0 10px 34px rgba(139,92,246,.35);}
[data-testid="stFileUploaderDropzone"] button {border-radius: 999px; background: linear-gradient(90deg,#6366f1,#ec4899);
  color: white; border: none; padding: 8px 22px;}

.profile {display: flex; align-items: center; gap: 16px; padding: 18px 20px; border-radius: 20px; margin: 14px 0;
  background: rgba(255,255,255,.07); border: 1px solid rgba(255,255,255,.14); backdrop-filter: blur(10px);}
.avatar {width: 62px; height: 62px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
  font-size: 1.5rem; font-weight: 700; color: white; flex-shrink: 0;
  background: linear-gradient(135deg,#6366f1,#ec4899); box-shadow: 0 6px 20px rgba(236,72,153,.4);}
.profile h3 {margin: 0; color: white; font-size: 1.25rem;}
.muted {color: #a5b4fc; font-size: .88rem;}
.card {padding: 14px 18px; border-radius: 16px; margin-bottom: 10px;
  background: rgba(255,255,255,.05); border: 1px solid rgba(255,255,255,.1);}
.card h4 {margin: 0 0 8px; color: #fff; font-size: 1rem;}
.chip {display: inline-block; padding: 4px 12px; margin: 3px; border-radius: 999px;
  background: rgba(99,102,241,.2); border: 1px solid rgba(139,92,246,.55); color: #e0e7ff; font-size: .8rem;}
.item {padding: 7px 0; border-bottom: 1px dashed rgba(255,255,255,.12); color: #e2e8f0; font-size: .92rem;}
.item:last-child {border-bottom: none;}

.stChatMessage {background: rgba(255,255,255,.06); border-radius: 18px; border: 1px solid rgba(255,255,255,.08);}
.stChatMessage p {unicode-bidi: plaintext;}
div.stButton > button {border-radius: 999px; border: 1px solid rgba(139,92,246,.6);
  background: rgba(99,102,241,.15); color: #e0e7ff; transition: all .2s;}
div.stButton > button:hover {background: linear-gradient(90deg,#6366f1,#ec4899); color: white; border-color: transparent;
  transform: translateY(-2px);}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

PARSE_PROMPT = """You are a smart HR assistant that parses a CV into structured data.
Use only information found in the text. Do not invent anything.
If a field is missing, use an empty string or an empty list.

Respond ONLY with JSON in this shape:
{{
  "full_name": "string",
  "email": "string",
  "education": [{{"degree": "string", "institution": "string", "year": "string"}}],
  "skills": ["string"],
  "experience": [{{"role": "string", "company": "string", "years": "string"}}]
}}

CV:
{cv_text}
"""

QA_PROMPT = """You are an assistant that answers questions about ONE candidate using ONLY the CV below.

Rules:
- Answer ONLY what the user asked. Do not add any extra information.
- Keep it very short: one sentence, or a short bullet list when several items are asked.
- If the answer is not in the CV, say it is not mentioned in the CV.
- Reply in the same language as the question.

CV:
{cv_text}
"""

QUICK = [
    ("👤 الاسم", "What is the candidate's name?"),
    ("📧 الإيميل", "What is the candidate's email?"),
    ("🛠️ المهارات", "List the candidate's skills."),
    ("🎓 التعليم", "What is the candidate's education?"),
    ("💼 الخبرة", "What is the candidate's work experience?"),
]


def chat(messages, max_tokens=700):
    res = client.chat_completion(messages=messages, max_tokens=max_tokens, temperature=0.1)
    return res.choices[0].message.content


def extract_json(text):
    m = re.findall(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if m:
        return json.loads(m[-1])
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1:
        raise ValueError("no JSON found in model output")
    return json.loads(text[s : e + 1])


def read_cv(uploaded):
    if uploaded.name.lower().endswith(".pdf"):
        return "\n".join(p.extract_text() or "" for p in PdfReader(uploaded).pages)
    return uploaded.read().decode("utf-8", errors="ignore")


def esc(x):
    return html.escape(str(x or ""))


def initials(name):
    parts = [w for w in str(name or "").split() if w]
    return "".join(w[0].upper() for w in parts[:2]) or "CV"


# ---------- Hero ----------
st.markdown(
    '<div class="hero"><div class="logo">✨</div><h1>CV Assistant</h1>'
    "<p>ارفعي الـ CV واسألي أي سؤال، هيرد عليكي بالمطلوب بس.</p></div>",
    unsafe_allow_html=True,
)

has_cv = bool(st.session_state.get("cv_text"))
st.markdown(
    f'<div class="steps"><span class="step {"" if has_cv else "on"}">1️⃣ ارفعي الـ CV</span>'
    f'<span class="step {"on" if has_cv else ""}">2️⃣ اسألي</span></div>',
    unsafe_allow_html=True,
)

# ---------- Upload ----------
uploaded = st.file_uploader(
    "ارفعي الـ CV", type=["pdf", "txt"], label_visibility="collapsed",
    help="PDF أو TXT",
)

if uploaded is None:
    for k in ("sig", "cv_text", "profile", "history"):
        st.session_state.pop(k, None)
    st.markdown(
        '<div class="muted" style="text-align:center">📄 اسحبي الملف هنا أو اضغطي Browse files</div>',
        unsafe_allow_html=True,
    )
    st.stop()

text = read_cv(uploaded)
if not text.strip():
    st.error("مقدرتش أقرأ نص من الملف. لو الـ PDF صورة (scan) جربي ملف تاني.")
    st.stop()

sig = hashlib.md5(text.encode("utf-8", errors="ignore")).hexdigest()
if st.session_state.get("sig") != sig:
    st.session_state.update(sig=sig, history=[], profile=None, cv_text=text)
    st.rerun()

# ---------- Profile (parsed once per CV) ----------
if st.session_state.get("profile") is None:
    try:
        with st.spinner("جاري قراءة الـ CV..."):
            raw = chat([{"role": "user", "content": PARSE_PROMPT.format(cv_text=text[:6000])}], 900)
            st.session_state["profile"] = extract_json(raw)
    except Exception as e:
        st.session_state["profile"] = {}
        st.warning(f"مقدرتش أعمل ملخص للـ CV ({e})، بس تقدري تسألي عادي.")

p = st.session_state.get("profile") or {}
if p:
    st.markdown(
        f'<div class="profile"><div class="avatar">{esc(initials(p.get("full_name")))}</div>'
        f'<div><h3>{esc(p.get("full_name")) or "Candidate"}</h3>'
        f'<div class="muted">📧 {esc(p.get("email"))}</div></div></div>',
        unsafe_allow_html=True,
    )
    skills = "".join(f'<span class="chip">{esc(s)}</span>' for s in p.get("skills", [])[:16])
    edu = "".join(
        f'<div class="item">🎓 {esc(e.get("degree"))} — {esc(e.get("institution"))} '
        f'<span class="muted">{esc(e.get("year"))}</span></div>'
        for e in p.get("education", [])
    )
    exp = "".join(
        f'<div class="item">💼 {esc(x.get("role"))} @ {esc(x.get("company"))} '
        f'<span class="muted">{esc(x.get("years"))}</span></div>'
        for x in p.get("experience", [])
    )
    with st.expander("📋 ملخص الـ CV"):
        if skills:
            st.markdown(f'<div class="card"><h4>🛠️ Skills</h4>{skills}</div>', unsafe_allow_html=True)
        if edu:
            st.markdown(f'<div class="card"><h4>🎓 Education</h4>{edu}</div>', unsafe_allow_html=True)
        if exp:
            st.markdown(f'<div class="card"><h4>💼 Experience</h4>{exp}</div>', unsafe_allow_html=True)

# ---------- Quick questions ----------
cols = st.columns(len(QUICK))
pending = None
for col, (label, question) in zip(cols, QUICK):
    if col.button(label, use_container_width=True):
        pending = question

# ---------- Chat ----------
for role, content in st.session_state["history"]:
    with st.chat_message(role, avatar="🙋‍♀️" if role == "user" else "🤖"):
        st.write(content)

if st.session_state["history"]:
    if st.button("🗑️ مسح المحادثة"):
        st.session_state["history"] = []
        st.rerun()

q = st.chat_input("اسألي عن الـ CV... مثلا: اسمه إيه؟") or pending
if q:
    st.session_state["history"].append(("user", q))
    with st.chat_message("user", avatar="🙋‍♀️"):
        st.write(q)
    msgs = [{"role": "system", "content": QA_PROMPT.format(cv_text=st.session_state["cv_text"][:8000])}]
    msgs += [{"role": r, "content": c} for r, c in st.session_state["history"][-6:]]
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("بفكر..."):
            try:
                ans = chat(msgs, 400)
            except Exception as e:
                ans = f"حصل خطأ: {e}"
        st.write(ans)
    st.session_state["history"].append(("assistant", ans))
