import os
import re
import json
import time
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from app.retriever import HybridRetriever

# Load GEMINI_API_KEY from .env file
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Initialize official Google GenAI client with a strict 15-second timeout (15000 ms) so it never hangs
client = genai.Client(api_key=GEMINI_API_KEY, http_options={"timeout": 15000})

# Primary model + backup models in case of temporary 503 high-demand spikes
CANDIDATE_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash"
]
DB_PATH = os.path.join("data", "pharma.db")
REPORTS_DIR = os.path.join("data", "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)


def call_gemini(prompt: str) -> str:
    """Calls Gemini with a 15s timeout and automatic fallback across candidate models."""
    last_error = None
    for attempt in range(2):
        for model_name in CANDIDATE_MODELS:
            try:
                resp = client.models.generate_content(model=model_name, contents=prompt)
                return (resp.text or "").strip()
            except Exception as e:
                last_error = e
                print(f"[WARN] {model_name} failed ({type(e).__name__}), trying next...")
                time.sleep(1)
    raise RuntimeError(f"All Gemini attempts failed after retries: {last_error}")


class PharmaAgentEngine:
    """Traffic Cop Router + 3 Specialist Tools (SOP RAG, SQL Database, Report Writer)."""

    def __init__(self):
        # Load the hybrid vector + BM25 + reranker engine once
        self.retriever = HybridRetriever()

    def route_intent(self, question: str) -> str:
        """Traffic Cop: Classifies user question into RAG, SQL, or REPORT."""
        prompt = f"""
You are an enterprise pharmaceutical routing classifier.
Classify the user's question into EXACTLY ONE category:
- SQL: Questions asking for counts, lists, averages, dates, batch IDs, equipment IDs, failed/quarantined/released batches, assay/dissolution/yield numbers from batch records.
- REPORT: Requests to generate, draft, export, or create a checklist, audit summary, CAPA form, or compliance report.
- RAG: Questions about SOP rules, cleaning procedures, hold times, acceptance limits, QA sign-off rules, or deviation timelines.

Return ONLY one word: SQL, REPORT, or RAG.
User Question: {question}
"""
        decision = call_gemini(prompt).upper()
        for label in ["SQL", "REPORT", "RAG"]:
            if label in decision:
                return label
        return "RAG"

    def run_rag_tool(self, question: str) -> dict:
        """Searches SOP PDFs via Hybrid Retrieval and generates a strictly cited answer."""
        hits = self.retriever.retrieve(question, top_k=3)
        if not hits:
            return {
                "route": "RAG",
                "answer": "No matching SOP documents were found in the knowledge base.",
                "citations": [],
                "sql_used": None
            }

        # Build numbered evidence block with exact PDF source and page number
        context_blocks = []
        citations = []
        for idx, h in enumerate(hits, start=1):
            meta = h["metadata"]
            cite_tag = f"[{meta['source']} | Page {meta['page']}]"
            context_blocks.append(f"Source {idx} {cite_tag}:\n{h['text']}")
            citations.append({
                "source": meta["source"],
                "page": meta["page"],
                "score": h["rerank_score"],
                "snippet": h["text"][:220] + "..."
            })

        context_str = "\n\n".join(context_blocks)
        prompt = f"""
You are a strict Pharmaceutical Regulatory & QA Compliance Assistant.
Answer the user's question using ONLY the verified SOP excerpts below.
Rules:
1. Cite the exact source filename and page number inline (e.g., [SOP-001_Cleaning_Validation.pdf | Page 1]).
2. If the answer is not present in the excerpts, state: "Not specified in the indexed SOP documents." Do NOT guess.
3. Keep the response clear, structured, and audit-ready.

SOP Excerpts:
{context_str}

User Question: {question}
"""
        answer_text = call_gemini(prompt)
        return {
            "route": "RAG",
            "answer": answer_text,
            "citations": citations,
            "sql_used": None
        }

    def run_sql_tool(self, question: str) -> dict:
        """Converts natural language to a safe read-only SELECT query and summarizes results."""
        schema_info = """
Table: batch_records
Columns:
- batch_id (TEXT, e.g. 'B-2026-101')
- product_name (TEXT, e.g. 'Paracetamol 500mg Tablets', 'Amoxicillin 250mg Capsules')
- mfg_date (TEXT, YYYY-MM-DD)
- equipment_id (TEXT, e.g. 'TC-04', 'FBD-02')
- assay_pct (REAL, valid range 95.0 to 105.0)
- dissolution_pct (REAL, valid >= 80.0)
- yield_pct (REAL, valid range 97.0 to 101.5)
- qc_status (TEXT: 'RELEASED', 'FAILED', or 'QUARANTINE')
- deviation_id (TEXT or NULL)
- failure_reason (TEXT or NULL)
"""
        sql_prompt = f"""
Write a single valid SQLite SELECT query to answer the user's question using this schema:
{schema_info}

Rules:
1. Return ONLY the raw SQL query—no markdown fences, no explanations.
2. Only SELECT statements are allowed.

User Question: {question}
"""
        raw_sql = call_gemini(sql_prompt)
        clean_sql = re.sub(r"^```sql|^```|```$", "", raw_sql, flags=re.IGNORECASE | re.MULTILINE).strip()

        # Security guardrail: block any write/delete query
        if not clean_sql.upper().startswith("SELECT"):
            return {
                "route": "SQL",
                "answer": "Blocked unsafe query: Only read-only SELECT queries are permitted.",
                "citations": [],
                "sql_used": clean_sql
            }

        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute(clean_sql)
            cols = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            conn.close()
        except Exception as e:
            return {
                "route": "SQL",
                "answer": f"Database query error: {e}",
                "citations": [],
                "sql_used": clean_sql
            }

        # Format rows into readable records and ask Gemini to summarize clearly
        records = [dict(zip(cols, r)) for r in rows]
        summary_prompt = f"""
You are a Pharmaceutical QC Data Analyst.
Summarize these SQL query results clearly to answer the user's question. Include exact batch IDs, metrics, and failure reasons if present.

User Question: {question}
SQL Executed: {clean_sql}
Query Results: {json.dumps(records, indent=2)}
"""
        summary_text = call_gemini(summary_prompt)
        return {
            "route": "SQL",
            "answer": summary_text,
            "citations": [{"source": "pharma.db (batch_records)", "page": 1, "score": 1.0, "snippet": clean_sql}],
            "sql_used": clean_sql
        }

    def run_report_tool(self, question: str) -> dict:
        """Combines SOP rules + live DB status to draft a structured audit report & export PDF."""
        sop_hits = self.retriever.retrieve(question, top_k=3)
        sop_context = "\n".join([f"[{h['metadata']['source']} p.{h['metadata']['page']}]: {h['text']}" for h in sop_hits])

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT batch_id, product_name, qc_status, deviation_id, failure_reason FROM batch_records WHERE qc_status != 'RELEASED'")
        flagged_rows = cursor.fetchall()
        conn.close()

        prompt = f"""
You are a Pharmaceutical Quality Assurance Lead.
Generate a formal, well-structured compliance document/checklist fulfilling the user's request.
Use the verified SOP rules and flagged batch records below. Cite exact SOP numbers.

Verified SOP Context:
{sop_context}

Current Non-Released Batches in DB:
{flagged_rows}

User Request: {question}
"""
        report_text = call_gemini(prompt)

        # Save a downloadable PDF copy in data/reports/
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_filename = f"QA_Report_{timestamp}.pdf"
        pdf_path = os.path.join(REPORTS_DIR, pdf_filename)
        self._export_report_pdf(pdf_path, question, report_text)

        return {
            "route": "REPORT",
            "answer": report_text,
            "citations": [{"source": h["metadata"]["source"], "page": h["metadata"]["page"], "score": h["rerank_score"], "snippet": h["text"][:180] + "..."} for h in sop_hits],
            "sql_used": None,
            "report_file": pdf_path
        }

    def _export_report_pdf(self, filepath: str, title: str, body: str):
        """Writes the generated compliance report into a clean downloadable PDF."""
        c = canvas.Canvas(filepath, pagesize=A4)
        width, height = A4
        c.setFont("Helvetica-Bold", 12)
        c.drawString(45, height - 45, "PHARMA QA COMPLIANCE ASSISTANT - GENERATED REPORT")
        c.setFont("Helvetica", 9)
        c.drawString(45, height - 62, f"Request: {title[:90]} | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        c.line(45, height - 70, width - 45, height - 70)

        y = height - 92
        c.setFont("Helvetica", 9)
        for raw_line in body.split("\n"):
            clean_line = raw_line.replace("**", "").replace("#", "").strip()
            if not clean_line:
                y -= 8
                continue
            words = clean_line.split(" ")
            line = ""
            for w in words:
                if len(line + w) < 92:
                    line += w + " "
                else:
                    if y < 55:
                        c.showPage()
                        c.setFont("Helvetica", 9)
                        y = height - 50
                    c.drawString(45, y, line.strip())
                    y -= 13
                    line = w + " "
            if line:
                if y < 55:
                    c.showPage()
                    c.setFont("Helvetica", 9)
                    y = height - 50
                c.drawString(45, y, line.strip())
                y -= 13
        c.save()

    def ask(self, question: str) -> dict:
        """Main entry point: Routes question via Traffic Cop and returns structured response."""
        route = self.route_intent(question)
        if route == "SQL":
            return self.run_sql_tool(question)
        elif route == "REPORT":
            return self.run_report_tool(question)
        else:
            return self.run_rag_tool(question)


# Quick standalone test across all 3 Traffic Cop routes
if __name__ == "__main__":
    engine = PharmaAgentEngine()
    test_queries = [
        "What is the maximum Dirty Equipment Hold Time for TC-04?",
        "Which batches failed or are in quarantine and why?",
        "Generate a Batch Release QA Checklist based on SOP-002."
    ]
    for q in test_queries:
        print("=" * 60)
        print(f"QUESTION: {q}")
        result = engine.ask(q)
        print(f"TRAFFIC COP ROUTE: {result['route']}")
        if result.get("sql_used"):
            print(f"SQL GENERATED: {result['sql_used']}")
        print(f"ANSWER:\n{result['answer']}\n")