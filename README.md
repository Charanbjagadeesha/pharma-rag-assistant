\# Pharma QA \& Regulatory Compliance Assistant (Hybrid RAG + Text-to-SQL)



An enterprise AI compliance assistant built for pharmaceutical Quality Assurance (QA) and Quality Control (QC) teams. It combines \*\*Hybrid Retrieval-Augmented Generation (Vector + BM25 + Cross-Encoder Reranking)\*\*, a \*\*Read-Only Text-to-SQL Engine\*\*, and \*\*Automated Audit Report Generation\*\* behind a role-based FastAPI backend and a clean ChatGPT-style Streamlit interface.



\---



\## Problem Statement

In pharmaceutical manufacturing, QA engineers regularly cross-check Standard Operating Procedures (SOPs) against live batch testing records during batch release audits and deviation investigations. Standard LLM chatbots often hallucinate regulatory thresholds or cannot query structured batch databases. This system solves both by routing every query to the right specialized tool and enforcing strict document-page citations.



\---



\## System Architecture



```text

User (Streamlit Chat UI)

&#x20;       │  JWT Bearer Token (QA\_Admin / QC\_Analyst)

&#x20;       ▼

FastAPI Backend (/login, /ask, /upload-sop, /audit-logs)

&#x20;       │

&#x20;       ▼

Traffic Cop Intent Router (Gemini API with Timeout \& Auto-Fallback)

&#x20;  ├──► \[RAG Engine]    ChromaDB + BM25 (RRF) ──► Cross-Encoder Reranker ──► Cited SOP Answer

&#x20;  ├──► \[SQL Engine]    Natural Language ──► Read-Only SELECT Guardrail ──► SQLite (pharma.db)

&#x20;  └──► \[Report Engine] SOP Rules + Non-Released Batches ──► Structured QA Checklist + PDF Export

