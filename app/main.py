import os
import json
import shutil
from datetime import datetime, timedelta, timezone
import jwt
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import FileResponse
from pydantic import BaseModel
from app.agent_engine import PharmaAgentEngine
from app.ingest import ingest_directory, SOPS_DIR

# Secret signing key for JWT login tokens
JWT_SECRET = "pharma_enterprise_secret_key_2026"
JWT_ALGORITHM = "HS256"
AUDIT_LOG_PATH = os.path.join("data", "audit_logs.jsonl")

# Demo enterprise user accounts with Role-Based Access Control (RBAC)
USERS_DB = {
    "qa_admin": {
        "password": "admin123",
        "role": "QA_Admin",
        "full_name": "Priya Nair (QA Manager)"
    },
    "qc_analyst": {
        "password": "analyst123",
        "role": "QC_Analyst",
        "full_name": "Rohan Verma (QC Lab Analyst)"
    }
}

app = FastAPI(
    title="Enterprise Pharma Regulatory & QA Knowledge Assistant",
    version="1.0.0"
)
security = HTTPBearer()

# Initialize the AI Agent Engine once on server startup
print("[INFO] Starting Pharma Agent Engine...")
agent_engine = PharmaAgentEngine()


class LoginRequest(BaseModel):
    username: str
    password: str


class AskRequest(BaseModel):
    question: str


def write_audit_log(username: str, role: str, action: str, detail: str):
    """Appends a timestamped compliance record to data/audit_logs.jsonl."""
    entry = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "user": username,
        "role": role,
        "action": action,
        "detail": detail
    }
    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Validates Bearer JWT token and returns the logged-in user's profile and role."""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session token expired. Please log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid authentication token.")


@app.get("/")
def health_check():
    """Simple health check endpoint."""
    return {"status": "online", "service": "Pharma Regulatory & QA Knowledge Assistant"}


@app.post("/login")
def login(req: LoginRequest):
    """Authenticates user credentials and issues a signed JWT token with role permissions."""
    user = USERS_DB.get(req.username)
    if not user or user["password"] != req.password:
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    payload = {
        "sub": req.username,
        "role": user["role"],
        "full_name": user["full_name"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=8)
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    write_audit_log(req.username, user["role"], "LOGIN", "User authenticated successfully")
    return {
        "access_token": token,
        "token_type": "bearer",
        "username": req.username,
        "role": user["role"],
        "full_name": user["full_name"]
    }


@app.post("/ask")
def ask_assistant(req: AskRequest, current_user: dict = Depends(get_current_user)):
    """Routes the user's question through Traffic Cop (RAG, SQL, or REPORT) and logs the query."""
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    result = agent_engine.ask(question)
    write_audit_log(
        current_user["sub"],
        current_user["role"],
        f"QUERY_{result['route']}",
        question
    )
    return result


@app.post("/upload-sop")
def upload_sop(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    """Admin-only endpoint: Uploads a new SOP file (.pdf, .docx, .xlsx) and re-indexes knowledge base."""
    # Enforce Role-Based Access Control (RBAC): block QC_Analyst from modifying SOPs
    if current_user["role"] != "QA_Admin":
        write_audit_log(
            current_user["sub"],
            current_user["role"],
            "UPLOAD_DENIED",
            f"Unauthorized upload attempt: {file.filename}"
        )
        raise HTTPException(
            status_code=403,
            detail="Access Denied: Only QA_Admin users can upload or modify regulatory SOP documents."
        )

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".pdf", ".docx", ".xlsx"]:
        raise HTTPException(status_code=400, detail="Unsupported file format. Upload .pdf, .docx, or .xlsx only.")

    save_path = os.path.join(SOPS_DIR, file.filename)
    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Re-index documents and refresh retriever memory so new SOP is immediately searchable
    chunk_count = ingest_directory(SOPS_DIR)
    agent_engine.__init__()

    write_audit_log(
        current_user["sub"],
        current_user["role"],
        "SOP_UPLOADED",
        f"Uploaded & indexed {file.filename} ({chunk_count} total chunks)"
    )
    return {
        "message": f"Successfully uploaded and indexed '{file.filename}'.",
        "total_indexed_chunks": chunk_count
    }


@app.get("/audit-logs")
def get_audit_logs(current_user: dict = Depends(get_current_user)):
    """Admin-only endpoint: Returns recent compliance audit trail entries."""
    if current_user["role"] != "QA_Admin":
        raise HTTPException(status_code=403, detail="Access Denied: Only QA_Admin users can view system audit logs.")

    if not os.path.exists(AUDIT_LOG_PATH):
        return {"logs": []}

    with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]
    return {"logs": list(reversed(lines[-50:]))}


@app.get("/download-report/{filename}")
def download_report(filename: str, current_user: dict = Depends(get_current_user)):
    """Allows authenticated users to download a generated PDF compliance report."""
    safe_name = os.path.basename(filename)
    file_path = os.path.join("data", "reports", safe_name)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Report file not found.")
    return FileResponse(path=file_path, filename=safe_name, media_type="application/pdf")