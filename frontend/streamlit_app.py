import os
import sys
import time
import subprocess
import requests
import streamlit as st

# Auto-generate sample data & start FastAPI backend in background for cloud deployment
if not os.path.exists("data/pharma.db"):
    subprocess.run([sys.executable, "scripts/generate_data.py"], check=False)
if not os.path.exists("data/bm25_index.pkl"):
    subprocess.run([sys.executable, "-m", "app.ingest"], check=False)

if "backend_started" not in st.session_state:
    try:
        requests.get("http://127.0.0.1:8000/docs", timeout=1)
    except Exception:
        subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"])
        time.sleep(3)
    st.session_state.backend_started = True

API_URL = "http://127.0.0.1:8000"

st.set_page_config(
    page_title="Pharma QA Assistant",
    page_icon="💊",
    layout="centered",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .block-container {
        max-width: 820px;
        padding-top: 2rem;
        padding-bottom: 5rem;
    }
    .route-pill {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 600;
        background-color: rgba(16, 163, 127, 0.15);
        color: #10a37f;
        margin-bottom: 6px;
    }
    div.stButton > button {
        border-radius: 12px;
        text-align: left;
        padding: 0.75rem 1rem;
        border: 1px solid rgba(128, 128, 128, 0.25);
        transition: all 0.15s ease;
    }
    div.stButton > button:hover {
        border-color: #10a37f;
    }
</style>
""", unsafe_allow_html=True)

if "token" not in st.session_state:
    st.session_state.token = None
if "user_info" not in st.session_state:
    st.session_state.user_info = {}
if "messages" not in st.session_state:
    st.session_state.messages = []
if "show_audit" not in st.session_state:
    st.session_state.show_audit = False


def auth_headers():
    return {"Authorization": f"Bearer {st.session_state.token}"}


# --- LOGIN SCREEN ---
if not st.session_state.token:
    st.markdown("<h1 style='text-align: center; margin-bottom: 0.2rem;'>💊 Pharma QA Assistant</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray; margin-bottom: 2rem;'>Regulatory SOPs • Batch QC Analytics • Automated Audit Reports</p>", unsafe_allow_html=True)

    with st.container(border=True):
        st.subheader("Sign in to continue")
        username = st.text_input("Username", value="qa_admin", placeholder="Enter username")
        password = st.text_input("Password", type="password", value="admin123", placeholder="Enter password")

        if st.button("Continue", use_container_width=True, type="primary"):
            try:
                res = requests.post(
                    f"{API_URL}/login",
                    json={"username": username, "password": password},
                    timeout=10
                )
                if res.status_code == 200:
                    data = res.json()
                    st.session_state.token = data["access_token"]
                    st.session_state.user_info = data
                    st.rerun()
                else:
                    st.error(res.json().get("detail", "Invalid login credentials."))
            except Exception:
                st.info("Starting AI backend engine... please wait 5 seconds and click Continue again.")

        st.caption("Demo logins: `qa_admin` / `admin123` (Full Access) • `qc_analyst` / `analyst123` (Read & Query)")
    st.stop()


# --- SIDEBAR ---
info = st.session_state.user_info
is_admin = info.get("role") == "QA_Admin"

with st.sidebar:
    st.markdown("### 💊 Pharma QA AI")

    if st.button("➕  New Chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.show_audit = False
        st.rerun()

    st.divider()

    if is_admin:
        with st.expander("📄 Upload SOP Document"):
            uploaded_file = st.file_uploader(
                "PDF, DOCX, or XLSX",
                type=["pdf", "docx", "xlsx"],
                label_visibility="collapsed"
            )
            if uploaded_file is not None and st.button("Add to Knowledge Base", use_container_width=True):
                with st.spinner("Indexing..."):
                    files = {"file": (uploaded_file.name, uploaded_file.getvalue())}
                    up_res = requests.post(
                        f"{API_URL}/upload-sop",
                        headers=auth_headers(),
                        files=files,
                        timeout=60
                    )
                    if up_res.status_code == 200:
                        st.success("Indexed!")
                    else:
                        st.error(up_res.json().get("detail", "Upload error."))

        if st.button("📜 View Audit Trail", use_container_width=True):
            st.session_state.show_audit = not st.session_state.show_audit
            st.rerun()

    st.markdown("<br>" * 6, unsafe_allow_html=True)
    st.divider()
    st.caption(f"👤 **{info.get('full_name')}**\nRole: `{info.get('role')}`")
    if st.button("Log out", use_container_width=True):
        st.session_state.token = None
        st.session_state.user_info = {}
        st.session_state.messages = []
        st.session_state.show_audit = False
        st.rerun()


# --- AUDIT TRAIL VIEW ---
if st.session_state.show_audit and is_admin:
    col_title, col_back = st.columns([4, 1])
    col_title.subheader("📜 Compliance Audit Trail")
    if col_back.button("← Back to Chat", use_container_width=True):
        st.session_state.show_audit = False
        st.rerun()

    log_res = requests.get(f"{API_URL}/audit-logs", headers=auth_headers(), timeout=10)
    if log_res.status_code == 200:
        logs = log_res.json().get("logs", [])
        if logs:
            st.dataframe(logs, use_container_width=True, hide_index=True)
        else:
            st.info("No activity recorded yet.")
    st.stop()


# --- WELCOME SCREEN ---
selected_prompt = None

if not st.session_state.messages:
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("<h2 style='text-align: center; font-weight: 600;'>How can I help with QA & Compliance today?</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray; margin-bottom: 2rem;'>Ask about SOP regulations, query live batch records, or generate audit checklists.</p>", unsafe_allow_html=True)

    row1_col1, row1_col2 = st.columns(2)
    with row1_col1:
        if st.button("📘 **Cleaning Hold Times**\n\nWhat is the max Dirty Equipment Hold Time for TC-04?", use_container_width=True):
            selected_prompt = "What is the maximum Dirty Equipment Hold Time for TC-04?"
    with row1_col2:
        if st.button("🧪 **Failed & Quarantined Batches**\n\nWhich batches failed or are in quarantine and why?", use_container_width=True):
            selected_prompt = "Which batches failed or are in quarantine and why?"

    row2_col1, row2_col2 = st.columns(2)
    with row2_col1:
        if st.button("📋 **Generate QA Checklist**\n\nCreate a Batch Release Checklist from SOP-002", use_container_width=True):
            selected_prompt = "Generate a Batch Release QA Checklist based on SOP-002."
    with row2_col2:
        if st.button("⏱️ **CAPA & Deviation Timelines**\n\nHow many days are allowed for RCA and CAPA?", use_container_width=True):
            selected_prompt = "How many days do we have to complete Root Cause Analysis (RCA) and CAPA implementation?"


# --- CHAT HISTORY & CITATIONS ---
def render_assistant_extras(data: dict, key_suffix: str):
    if data.get("report_file"):
        fname = os.path.basename(data["report_file"])
        dl_res = requests.get(
            f"{API_URL}/download-report/{fname}",
            headers=auth_headers(),
            timeout=15
        )
        if dl_res.status_code == 200:
            st.download_button(
                label=f"⬇️ Download PDF Report ({fname})",
                data=dl_res.content,
                file_name=fname,
                mime="application/pdf",
                key=f"dl_{fname}_{key_suffix}"
            )

    has_citations = bool(data.get("citations"))
    has_sql = bool(data.get("sql_used"))
    if has_citations or has_sql:
        with st.expander("Sources & Verification"):
            if has_sql:
                st.caption("Executed Database Query:")
                st.code(data["sql_used"], language="sql")
            if has_citations:
                for c in data["citations"]:
                    st.markdown(f"- **{c['source']}** (Page {c['page']}) — _{c['snippet']}_")


for idx, msg in enumerate(st.session_state.