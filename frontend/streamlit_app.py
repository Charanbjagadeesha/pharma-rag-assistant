import subprocess, sys, time

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