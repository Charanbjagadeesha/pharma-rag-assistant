import time
from app.agent_engine import PharmaAgentEngine

EVAL_CASES = [
    {"question": "What is the maximum Dirty Equipment Hold Time for TC-04?", "expected_route": "RAG", "expected_keyword": "24", "must_cite": True},
    {"question": "What is the Clean Equipment Hold Time limit before re-sanitization is required?", "expected_route": "RAG", "expected_keyword": "72", "must_cite": True},
    {"question": "How many days are allowed for Root Cause Analysis and CAPA implementation?", "expected_route": "RAG", "expected_keyword": "15", "must_cite": True},
    {"question": "What is the SOP procedure for nuclear reactor coolant inspection?", "expected_route": "RAG", "expected_keyword": "not specified", "must_cite": False},
    {"question": "Which batches failed or are in quarantine and why?", "expected_route": "SQL", "expected_keyword": "B-2026-103", "must_cite": False},
    {"question": "Which batch has the lowest dissolution percentage in the database?", "expected_route": "SQL", "expected_keyword": "74", "must_cite": False},
    {"question": "Generate a Batch Release QA Checklist based on SOP-002.", "expected_route": "REPORT", "expected_keyword": "SOP-002", "must_cite": True}
]

def run_benchmark():
    print("Running PharmaAgentEngine Evaluation Benchmark...\n")
    engine = PharmaAgentEngine()
    total = len(EVAL_CASES)
    route_hits = answer_hits = citation_hits = 0
    cite_total = sum(1 for c in EVAL_CASES if c["must_cite"])
    for i, c in enumerate(EVAL_CASES, 1):
        t0 = time.time()
        res = engine.ask(c["question"])
        r_ok = res["route"] == c["expected_route"]
        a_ok = c["expected_keyword"].lower() in res["answer"].lower()
        c_ok = (".pdf" in res["answer"].lower())  if c["must_cite"] else True
        route_hits += int(r_ok)
        answer_hits += int(a_ok)
        citation_hits += int(c["must_cite"] and c_ok)
        status = "PASS" if (r_ok and a_ok and c_ok) else "CHECK"
        print(f"[{i}/{total}] {status} ({round(time.time()-t0, 2)}s) - Route: {res['route']} - Q: {c['question']}")
    print("\n" + "="*55)
    print(f"Intent Routing Accuracy : {route_hits}/{total} ({round(route_hits/total*100, 1)}%)")
    print(f"Factual & SQL Accuracy  : {answer_hits}/{total} ({round(answer_hits/total*100, 1)}%)")
    print(f"Inline Citation Rate    : {citation_hits}/{cite_total} ({round(citation_hits/cite_total*100, 1)}%)")
    print("="*55)

if __name__ == "__main__":
    run_benchmark()
