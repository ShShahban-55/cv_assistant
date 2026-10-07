import hashlib
import html
import json
import re

import streamlit as st
from huggingface_hub import InferenceClient
from pypdf import PdfReader

st.set_page_config(page_title="CV Assistant", page_icon="✨", layout="centered")

MODEL_NAME = st.secrets.get("MODEL_NAME", "meta-llama/Llama-3.1-8B-Instruct")
client = InferenceClient(model=MODEL_NAME, token=st.secrets["HF_TOKEN"])

CSS = """
<style>
.stApp {background: radial-gradient(circle at 15% 10%, #1e1b4b 0%, #0f172a 45%, #020617 100%);}
header[data-testid="stHeader"] {background: transparent;}
.hero {padding: 26px 24px; border-radius: 22px; margin-bottom: 18px; color: white;
  background: linear-gradient(135deg, #6366f1, #8b5cf6 55%, #ec4899);
  box-shadow: 0 12px 40px rgba(99,102,241,.35);}
.hero h1 {margin: 0; font-size: 1.9rem; color: white; padding: 0;}
.hero p {margin: 6px 0 0; opacity: .92;}
.card {padding: 18px 20px; border-radius: 18px; margin-bottom: 16px;
  background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.12);
  backdrop-filter: blur(8px);}
.card h3 {margin: 0 0 2px; color: #fff;}
.muted {color: #a5b4fc; font-size: .9rem;}
.chip {display: inline-block; padding: 4px 12px; margin: 3px; border-radius: 999px;
  background: rgba(99,102,241,.2); border: 1px solid rgba(139,92,246,.55);
  color: #e0e7ff; font-size: .8rem;}
.item {padding: 8px 0; border-bottom: 1px dashed rgba(255,255,255,.12); color: #e2e8f0;}
.item:last-child {border-bottom: none;}
.stChatMessage {background: rgba(255,255,255,.05); border-radius: 16px;}
.stChatMessage p {unicode-bidi: plaintext;}
div.stButton > button {border-radius: 999px; border: 1px solid rgba(139,92,246,.6);
  background: rgba(99,102,241,.15); color: #e0e7ff;}
div.stButton > button:hover {background: #6366f1; color: white; border-color: #6366f1;}
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


# ---------- Hero ----------
st.markdown(
    '<div class="hero"><h1>✨ CV Assistant</h1>'
    "<p>ارفعي الـ CV واسألي أي سؤال، هيرد عليكي بالمطلوب بس.</p></div>",
    unsafe_allow_html=True,
)

# ---------- Input ----------
with st.sidebar:
    st.header("📂 الـ CV")
    uploaded = st.file_uploader("PDF أو TXT", type=["pdf", "txt"])
    pasted = st.text_area("أو الصقي النص هنا", height=160)
    if st.button("🗑️ مسح المحادثة"):
        st.session_state["history"] = []
        st.rerun()

text = ""
if uploaded is not None:
    text = read_cv(uploaded)
elif pasted.strip():
    text = pasted

if not text.strip():
    st.markdown(
        '<div class="card"><h3>ابدأي من هنا 👈</h3>'
        '<span class="muted">ارفعي ملف الـ CV من القائمة الجانبية (أو افتحيها من السهم أعلى اليسار).</span></div>',
        unsafe_allow_html=True,
    )
    st.stop()

sig = hashlib.md5(text.encode("utf-8", errors="ignore")).hexdigest()
if st.session_state.get("sig") != sig:
    st.session_state.update(sig=sig, history=[], profile=None, cv_text=text)

# ---------- Profile card (parsed once per CV) ----------
if st.session_state.get("profile") is None:
    try:
        with st.spinner("جاري قراءة الـ CV..."):
            raw = chat(
                [{"role": "user", "content": PARSE_PROMPT.format(cv_text=text[:6000])}], 900
            )
            st.session_state["profile"] = extract_json(raw)
    except Exception as e:
        st.session_state["profile"] = {}
        st.warning(f"مقدرتش أعمل ملخص للـ CV ({e})، بس تقدري تسألي عادي.")

p = st.session_state.get("profile") or {}
if p:
    skills = "".join(f'<span class="chip">{esc(s)}</span>' for s in p.get("skills", [])[:14])
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
    st.markdown(
        f'<div class="card"><h3>{esc(p.get("full_name"))}</h3>'
        f'<div class="muted">📧 {esc(p.get("email"))}</div></div>',
        unsafe_allow_html=True,
    )
    with st.expander("📋 ملخص الـ CV"):
        st.markdown(
            f'<div class="card">{skills or "—"}</div>'
            f'<div class="card">{edu or "—"}</div>'
            f'<div class="card">{exp or "—"}</div>',
            unsafe_allow_html=True,
        )

# ---------- Quick questions ----------
st.markdown('<span class="muted">أسئلة سريعة:</span>', unsafe_allow_html=True)
cols = st.columns(len(QUICK))
pending = None
for col, (label, question) in zip(cols, QUICK):
    if col.button(label, use_container_width=True):
        pending = question

# ---------- Chat ----------
for role, content in st.session_state["history"]:
    with st.chat_message(role, avatar="🙋‍♀️" if role == "user" else "🤖"):
        st.write(content)

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
